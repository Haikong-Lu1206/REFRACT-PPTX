from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from refract_pptx.design import AgentProposal, compile_proposal
from refract_pptx.evaluation import evaluate_candidate
from refract_pptx.models import EpisodeSpec, EvidenceTier, SourceRecord, TaskFamily, TaskSpec
from refract_pptx.mutation import apply_mutations
from refract_pptx.presentation import object_inventory
from refract_pptx.validation import validate_bundle


class BuildError(ValueError):
    """Raised when a task cannot pass deterministic build gates."""


@dataclass(frozen=True)
class BuildResult:
    path: str
    task_id: str
    initial_score: float
    oracle_score: float
    mutation_count: int
    valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _task_family(plan: dict[str, Any]) -> TaskFamily:
    families = {TaskFamily(item["family"]) for item in plan["mutations"]}
    if len(families) == 1:
        return next(iter(families))
    return TaskFamily.MIXED_PRESENTATION_REPAIR


def _task_spec(
    task_id: str,
    proposal: AgentProposal,
    plan: dict[str, Any],
    source: SourceRecord,
) -> TaskSpec:
    episodes = []
    for item in plan["mutations"]:
        evidence = tuple(
            f"{claim['source']}:{claim['locator']} - {claim['supports']}"
            for claim in item["evidence"]
        )
        episodes.append(
            EpisodeSpec(
                episode_id=item["mutation_id"],
                family=TaskFamily(item["family"]),
                capability=item["capability"],
                slides=(int(item["slide"]),),
                mutation=str(item["rationale"]),
                evidence_tier=EvidenceTier(item["evidence_tier"]),
                observable_evidence=evidence,
                weight=float(item["weight"]),
                evaluator={key: float(value) for key, value in item["scoring"].items()},
                acceptance=tuple(item["accepted_solutions"]),
            )
        )
    return TaskSpec(
        spec_version="1.0",
        task_id=task_id,
        title=proposal.title,
        instruction=proposal.instruction,
        family=_task_family(plan),
        source=source,
        episodes=tuple(episodes),
        preservation_contracts=proposal.preservation_contracts,
        assets={
            "initial_presentation": "init.pptx",
            "reference_render": "reference.pdf",
            "materials_directory": "materials",
        },
        metadata={
            "compiled_plan": "evaluator/plan.json",
            "validation_receipt": "validation/build.json",
        },
    ).require_valid()


def _extract_picture_materials(
    source: Path, plan: dict[str, Any], materials: Path
) -> list[str]:
    extracted: list[str] = []
    with zipfile.ZipFile(source) as package:
        names = set(package.namelist())
        for mutation in plan["mutations"]:
            target = mutation["oracle_target"]
            if (
                mutation["operation"].get("type") != "remove_shape"
                or target.get("kind") != "picture"
            ):
                continue
            media_part = str(target.get("media_part", ""))
            if media_part not in names:
                raise BuildError(
                    f"picture material is missing for mutation {mutation['mutation_id']}"
                )
            payload = package.read(media_part)
            digest = hashlib.sha256(payload).hexdigest()
            suffix = Path(media_part).suffix.lower() or ".bin"
            filename = f"asset-{digest[:12]}{suffix}"
            destination = materials / filename
            if destination.exists() and destination.read_bytes() != payload:
                raise BuildError(f"material hash-name collision: {filename}")
            destination.write_bytes(payload)
            extracted.append(filename)
    return sorted(set(extracted))


def build_task(
    source_pptx: str | Path,
    reference_pdf: str | Path,
    proposal: AgentProposal,
    output: str | Path,
    *,
    task_id: str,
    source_uri: str,
    license_name: str,
    materials: str | Path | None = None,
) -> BuildResult:
    """Build into a staging directory and publish only after all deterministic gates pass."""
    source_path = Path(source_pptx).resolve()
    reference_path = Path(reference_pdf).resolve()
    target = Path(output).resolve()
    if not source_path.is_file():
        raise BuildError(f"source presentation does not exist: {source_path}")
    if not reference_path.is_file():
        raise BuildError(f"reference render does not exist: {reference_path}")
    if not source_uri or not license_name:
        raise BuildError("source URI and license are required")
    if target.exists():
        raise BuildError(f"output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}-{uuid4().hex}"
    staging.mkdir()
    try:
        inventory = object_inventory(source_path)
        compiled = compile_proposal(proposal, inventory)
        plan = compiled.to_dict()
        _write_json(staging / "evaluator" / "plan.json", plan)
        initial_path = apply_mutations(source_path, compiled, staging / "init.pptx")
        shutil.copy2(reference_path, staging / "reference.pdf")
        materials_path = staging / "materials"
        if materials is None:
            materials_path.mkdir()
        else:
            supplied = Path(materials).resolve()
            if not supplied.is_dir():
                raise BuildError(f"materials directory does not exist: {supplied}")
            shutil.copytree(supplied, materials_path)
        extracted_materials = _extract_picture_materials(source_path, plan, materials_path)

        initial_result = evaluate_candidate(initial_path, initial_path, compiled)
        oracle_result = evaluate_candidate(source_path, initial_path, compiled)
        if initial_result.score > 1e-6:
            raise BuildError(
                f"mutation does not produce a zero-score initial state: {initial_result.score}"
            )
        if oracle_result.score < 0.999999:
            raise BuildError(
                f"source oracle does not recover full credit: {oracle_result.score}"
            )

        source_record = SourceRecord(
            uri=source_uri,
            sha256=_sha256(source_path),
            license=license_name,
            title=source_path.stem,
        )
        spec = _task_spec(task_id, proposal, plan, source_record)
        _write_json(staging / "task_spec.json", asdict(spec))
        _write_json(staging / "provenance.json", asdict(source_record))
        (staging / "instruction.md").write_text(
            proposal.instruction.strip() + "\n", encoding="utf-8"
        )
        receipt = {
            "initial": initial_result.to_dict(),
            "oracle": oracle_result.to_dict(),
            "source_sha256": source_record.sha256,
            "initial_sha256": _sha256(initial_path),
            "extracted_materials": extracted_materials,
        }
        _write_json(staging / "validation" / "build.json", receipt)
        validation = validate_bundle(staging)
        if not validation.valid:
            raise BuildError("bundle validation failed: " + "; ".join(validation.issues))
        staging.replace(target)
        return BuildResult(
            path=str(target),
            task_id=task_id,
            initial_score=initial_result.score,
            oracle_score=oracle_result.score,
            mutation_count=len(compiled.mutations),
            valid=True,
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["BuildError", "BuildResult", "build_task"]
