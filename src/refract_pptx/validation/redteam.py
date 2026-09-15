from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from refract_pptx.evaluation import evaluate_candidate
from refract_pptx.mutation import MutationError, apply_mutations
from refract_pptx.mutation.ooxml import PackageEditor
from refract_pptx.presentation import object_inventory
from refract_pptx.presentation.objects import P_NS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _plan_sha256(plan: dict[str, Any]) -> str:
    payload = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _key(value: dict[str, Any]) -> tuple[int, int]:
    return int(value["slide"]), int(value["shape_id"])


def coverage_invariant(source: str | Path, plan: dict[str, Any]) -> dict[str, Any]:
    inventory = object_inventory(source)
    source_keys = {(item.slide, item.shape_id) for item in inventory.objects}
    target_keys: list[tuple[int, int]] = []
    for mutation in plan.get("mutations", []):
        target_keys.append(_key(mutation["oracle_target"]))
        other = mutation.get("operation", {}).get("other_oracle_target")
        if isinstance(other, dict):
            target_keys.append(_key(other))
    protected_keys = [_key(item) for item in plan.get("protected_objects", [])]
    declared = target_keys + protected_keys
    duplicate_count = len(declared) - len(set(declared))
    missing = sorted(source_keys - set(declared))
    unexpected = sorted(set(declared) - source_keys)
    return {
        "valid": not duplicate_count and not missing and not unexpected,
        "source_objects": len(source_keys),
        "target_objects": len(target_keys),
        "protected_objects": len(protected_keys),
        "duplicates": duplicate_count,
        "missing": [list(item) for item in missing],
        "unexpected": [list(item) for item in unexpected],
    }


def _reordered_candidate(source: Path, output: Path) -> Path | None:
    editor = PackageEditor(source)
    root = editor.xml("ppt/presentation.xml")
    slide_list = root.find(f".//{{{P_NS}}}sldIdLst")
    if slide_list is None or len(slide_list) < 2:
        return None
    children = list(slide_list)
    slide_list.remove(children[0])
    slide_list.append(children[0])
    return editor.write(output)


def _protected_damage(source: Path, plan: dict[str, Any], output: Path) -> Path | None:
    for target in plan.get("protected_objects", []):
        if target.get("bbox_points") is None:
            continue
        attack = {
            "slide_parts": list(plan["slide_parts"]),
            "mutations": [
                {
                    "slide": int(target["slide"]),
                    "target_shape_id": int(target["shape_id"]),
                    "operation": {"type": "move_shape", "dx_points": 72, "dy_points": 48},
                }
            ],
        }
        try:
            return apply_mutations(source, attack, output)
        except MutationError:
            continue
    return None


def run_redteam(
    source: str | Path,
    initial: str | Path,
    plan: dict[str, Any],
    *,
    work_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Run deterministic good-agent and bad-agent boundary checks."""
    source_path = Path(source).resolve()
    initial_path = Path(initial).resolve()
    issues: list[str] = []
    coverage = coverage_invariant(source_path, plan)
    if not coverage["valid"]:
        issues.append("source object coverage invariant failed")
    single_repairs: list[dict[str, Any]] = []
    smartart_variants: list[dict[str, Any]] = []
    temp_root = Path(work_directory).resolve() if work_directory else initial_path.parent
    temp_root.mkdir(parents=True, exist_ok=True)
    temp = temp_root / f".refract-redteam-{uuid4().hex}"
    temp.mkdir()
    try:
        mutations = list(plan.get("mutations", []))
        for index, mutation in enumerate(mutations):
            partial_plan = copy.deepcopy(plan)
            partial_plan["mutations"] = [
                item for item_index, item in enumerate(mutations) if item_index != index
            ]
            candidate = apply_mutations(
                source_path,
                partial_plan,
                temp / f"single-repair-{index}.pptx",
            )
            result = evaluate_candidate(candidate, initial_path, plan)
            entry = {
                "mutation_id": mutation["mutation_id"],
                "score": result.score,
                "hard_gates": result.hard_gates,
            }
            single_repairs.append(entry)
            if result.score <= 0:
                issues.append(f"single repair has no positive reward: {mutation['mutation_id']}")
            if not all(result.hard_gates.values()):
                issues.append(
                    f"single repair triggers a catastrophic gate: {mutation['mutation_id']}"
                )

        reorder_path = _reordered_candidate(source_path, temp / "reordered.pptx")
        from refract_pptx.validation.smartart import variants

        for mutation in mutations:
            if not mutation.get("oracle_target", {}).get("smartart", {}).get("supported"):
                continue
            for name, path, equivalent in variants(source_path, mutation, temp):
                result = evaluate_candidate(path, initial_path, plan)
                valid = result.score >= 0.999999 if equivalent else result.score < 0.999999
                smartart_variants.append(
                    {
                        "mutation_id": mutation["mutation_id"],
                        "variant": name,
                        "score": result.score,
                        "valid": valid,
                    }
                )
                if not valid:
                    issues.append(f"SmartArt red-team failed: {mutation['mutation_id']}/{name}")
        reorder: dict[str, Any] = {"applicable": reorder_path is not None}
        if reorder_path is not None:
            result = evaluate_candidate(reorder_path, initial_path, plan)
            reorder.update({"score": result.score, "hard_gates": result.hard_gates})
            if result.score != 0 or result.hard_gates.get("slide_order", True):
                issues.append("slide reorder did not trigger the expected hard gate")

        protected_path = _protected_damage(source_path, plan, temp / "protected-damage.pptx")
        protected: dict[str, Any] = {"applicable": protected_path is not None}
        if protected_path is not None:
            result = evaluate_candidate(protected_path, initial_path, plan)
            protected.update(
                {
                    "score": result.score,
                    "preservation_multiplier": result.preservation_multiplier,
                }
            )
            if result.score >= 0.999999:
                issues.append("visible protected-object damage did not reduce the score")
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    return {
        "receipt_version": "1.0",
        "source_sha256": _sha256(source_path),
        "initial_sha256": _sha256(initial_path),
        "plan_sha256": _plan_sha256(plan),
        "valid": not issues,
        "issues": issues,
        "coverage": coverage,
        "single_repairs": single_repairs,
        "smartart_variants": smartart_variants,
        "slide_reorder": reorder,
        "protected_damage": protected,
    }


__all__ = ["coverage_invariant", "run_redteam"]
