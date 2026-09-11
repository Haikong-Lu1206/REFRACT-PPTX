"""Portable authoring workspaces with an explicit agent-design handoff."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from refract_pptx.adapters import RunnerProfile
from refract_pptx.design import compile_proposal, load_proposal, proposal_prompt
from refract_pptx.office import render_pdf
from refract_pptx.pipeline import BatchItem, BatchRunner
from refract_pptx.presentation import object_inventory
from refract_pptx.validation import ProductionPolicy


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def init_workspace(path: str | Path) -> Path:
    root = Path(path).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for name in ("designs", "runs", "configs"):
        (root / name).mkdir()
    _json(root / "refract.json", {"workspace_version": "1.0"})
    _json(root / "configs" / "production-policy.json", asdict(ProductionPolicy()))
    _json(root / "configs" / "runner.json", RunnerProfile().to_dict())
    (root / ".gitignore").write_text("designs/\nruns/\n*.local.json\n", encoding="utf-8")
    (root / "START-HERE.md").write_text(
        "# Your REFRACT workspace\n\n"
        "Prepare a design with `refract prepare-task source.pptx --reference reference.pdf "
        "--output designs/my-deck --source-uri SOURCE --license LICENSE`.\n\n"
        "Give your design agent the files in that design's HANDOFF.md. Save its JSON response "
        "as proposal.json there. REFRACT does not select a model or call an API for you.\n\n"
        "Run `refract workspace-status .` for actionable checks, then "
        "`refract build-workspace . --workers 4`. Review bundles under runs/batch/bundles.\n\n"
        "Configure configs/runner.json before deployment. Run real target-editor and blind "
        "reviews before release-desktop. A successful build is not production approval.\n",
        encoding="utf-8",
    )
    return root


def prepare_task(
    source: str | Path,
    output: str | Path,
    *,
    reference: str | Path | None,
    source_uri: str,
    license_name: str,
    materials: str | Path | None = None,
    office_executable: str | None = None,
) -> Path:
    source, target = Path(source).resolve(), Path(output).resolve()
    if target.exists():
        raise ValueError(f"design already exists; choose a new output directory: {target}")
    if not source_uri.strip() or not license_name.strip():
        raise ValueError("source URI and license are required")
    inventory = object_inventory(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".prepare-{uuid4().hex}"
    staging.mkdir()
    try:
        shutil.copy2(source, staging / "source.pptx")
        if reference is None:
            render_pdf(source, staging / "reference.pdf", executable=office_executable)
        else:
            shutil.copy2(reference, staging / "reference.pdf")
        try:
            pdf = PdfReader(staging / "reference.pdf")
            if pdf.is_encrypted or len(pdf.pages) != inventory.slide_count:
                raise ValueError("reference must be unencrypted with one page per slide")
        except PdfReadError as exc:
            raise ValueError(f"reference PDF is unreadable: {exc}") from exc
        if materials:
            material_root = Path(materials).resolve()
            if not material_root.is_dir():
                raise ValueError("materials must be a directory")
            if any(path.is_symlink() for path in material_root.rglob("*")):
                raise ValueError("materials must not contain symbolic links")
            if staging.is_relative_to(material_root):
                raise ValueError("output staging must not be inside the materials directory")
            shutil.copytree(material_root, staging / "materials")
        else:
            (staging / "materials").mkdir()
        _json(staging / "objects.json", inventory.to_dict())
        prompt = proposal_prompt(inventory, ("Inspect reference.pdf page by page and materials/.",))
        (staging / "design-prompt.txt").write_text(prompt, encoding="utf-8")
        _json(
            staging / "task.json",
            {
                "key": target.name,
                "presentation": "source.pptx",
                "reference": "reference.pdf",
                "proposal": "proposal.json",
                "materials": "materials",
                "source_uri": source_uri,
                "license": license_name,
            },
        )
        (staging / "HANDOFF.md").write_text(
            "# Design this task\n\nRead design-prompt.txt and objects.json. Inspect source.pptx, "
            "reference.pdf and materials/. "
            "Paths in a prompt do not attach images automatically.\n\n"
            "Write proposal.json using the prompt's schema. Choose visible, meaningful changes "
            "specific to this presentation. Do not fabricate unsupported capabilities or score "
            "hidden properties. The output must remain editable.\n\n"
            "Do not modify source.pptx, reference.pdf or materials while designing. "
            "No placeholder proposal is supplied: task design needs your judgment.\n",
            encoding="utf-8",
        )
        staging.rename(target)
        return target
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _root(path: str | Path) -> Path:
    root = Path(path).resolve()
    config = json.loads((root / "refract.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("workspace_version") != "1.0":
        raise ValueError("unsupported workspace version")
    return root


def _design_item(record: Path) -> BatchItem:
    value = json.loads(record.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("task.json must contain an object")
    return BatchItem.from_dict(value, base=record.parent)


def workspace_status(path: str | Path) -> dict:
    root = _root(path)
    designs = []
    for directory in sorted((root / "designs").iterdir()):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        status, detail = "ready", "Ready to build; production review is still required."
        try:
            if not (directory / "task.json").is_file():
                raise ValueError("missing task.json; create this design with prepare-task")
            item = _design_item(directory / "task.json")
            compile_proposal(load_proposal(item.proposal), object_inventory(item.presentation))
        except (OSError, ValueError, TypeError) as exc:
            status, detail = "needs_attention", str(exc)
        designs.append({"design": directory.name, "status": status, "detail": detail})
    return {
        "workspace": str(root),
        "ready": sum(d["status"] == "ready" for d in designs),
        "total": len(designs),
        "designs": designs,
    }


def build_workspace(path: str | Path, *, workers: int = 4) -> dict:
    root = _root(path)
    status = workspace_status(root)
    if not status["total"] or status["ready"] != status["total"]:
        raise ValueError("workspace has missing or invalid designs; run workspace-status first")
    items = tuple(
        _design_item(record)
        for record in sorted((root / "designs").glob("*/task.json"))
        if not record.parent.name.startswith(".")
    )
    if len({item.key for item in items}) != len(items):
        raise ValueError("duplicate design keys in workspace")
    output = root / "runs" / "batch"
    result = BatchRunner(
        output,
        state_path=output / "run-state.sqlite",
        registry_path=output / "task-registry.sqlite",
        workers=workers,
    ).run(items)
    payload = result.to_dict()
    receipt = output / f"result-{uuid4().hex}.json"
    _json(receipt, payload)
    return {**payload, "result_file": str(receipt)}
