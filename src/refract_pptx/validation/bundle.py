from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from refract_pptx.models import ContractError, load_task_spec
from refract_pptx.presentation import inspect_pptx


@dataclass(frozen=True)
class BundleValidation:
    path: str
    valid: bool
    issues: tuple[str, ...]
    checks: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_inside(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def validate_bundle(path: str | Path) -> BundleValidation:
    root = Path(path).resolve()
    issues: list[str] = []
    checks: dict[str, Any] = {}
    if not root.is_dir():
        return BundleValidation(str(root), False, ("bundle path is not a directory",), checks)

    required_files = ("instruction.md", "task_spec.json", "provenance.json")
    for name in required_files:
        if not (root / name).is_file():
            issues.append(f"missing required file: {name}")

    spec = None
    if (root / "task_spec.json").is_file():
        try:
            spec = load_task_spec(root / "task_spec.json")
            spec_issues = spec.validate()
            issues.extend(spec_issues)
            checks["task_spec"] = "valid" if not spec_issues else "invalid"
        except ContractError as exc:
            issues.append(str(exc))
            checks["task_spec"] = "invalid"

    if (root / "provenance.json").is_file():
        try:
            provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
            if not isinstance(provenance, dict):
                raise ValueError("root must be an object")
            checks["provenance"] = "readable"
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            issues.append(f"invalid provenance.json: {exc}")

    if spec is not None:
        for role, relative in spec.assets.items():
            resolved = _resolve_inside(root, relative)
            if resolved is None:
                issues.append(f"asset escapes bundle root: {role}={relative}")
                continue
            if role == "materials_directory":
                if not resolved.is_dir():
                    issues.append(f"missing materials directory: {relative}")
            elif not resolved.is_file():
                issues.append(f"missing asset: {role}={relative}")
        initial = spec.assets.get("initial_presentation")
        if initial:
            initial_path = _resolve_inside(root, initial)
            if initial_path is not None and initial_path.is_file():
                try:
                    checks["initial_inventory"] = inspect_pptx(initial_path).to_dict()
                except ValueError as exc:
                    issues.append(f"initial presentation is invalid: {exc}")

    instruction_path = root / "instruction.md"
    if instruction_path.is_file():
        instruction = instruction_path.read_text(encoding="utf-8").strip()
        if len(instruction) < 40:
            issues.append("instruction.md is too short to state a reconstruction objective")
        if spec is not None and instruction != spec.instruction:
            issues.append("instruction.md differs from task_spec instruction")

    return BundleValidation(
        path=str(root),
        valid=not issues,
        issues=tuple(issues),
        checks=checks,
    )
