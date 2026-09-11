from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from refract_pptx.evaluation import evaluate_candidate
from refract_pptx.families import registered_families
from refract_pptx.models import TaskFamily, load_task_spec

from .bundle import validate_bundle


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _json_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def bundle_identity(bundle: str | Path) -> str:
    root = Path(bundle).resolve()
    digest = hashlib.sha256()
    relatives = [
        "init.pptx",
        "reference.pdf",
        "instruction.md",
        "task_spec.json",
        "provenance.json",
        "evaluator/plan.json",
    ]
    relatives.extend(
        sorted(
            path.relative_to(root).as_posix()
            for path in (root / "materials").rglob("*")
            if path.is_file()
        )
    )
    for relative in relatives:
        path = root / relative
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


@dataclass(frozen=True)
class ProductionPolicy:
    policy_version: str = "1.0"
    require_redteam: bool = True
    require_blind_review: bool = True
    require_office_roundtrip: bool = True
    require_known_license: bool = True
    minimum_oracle_score: float = 0.999999
    maximum_initial_score: float = 0.000001
    maximum_roundtrip_score_loss: float = 0.02

    @classmethod
    def load(cls, path: str | Path | None = None) -> ProductionPolicy:
        if path is None:
            return cls()
        value = _read_json(Path(path))
        unknown = sorted(set(value) - {item.name for item in fields(cls)})
        if unknown:
            raise ValueError("unknown production policy fields: " + ", ".join(unknown))
        return cls(**value).require_valid()

    def require_valid(self) -> ProductionPolicy:
        if self.policy_version != "1.0":
            raise ValueError("policy_version must be 1.0")
        for name in (
            "require_redteam",
            "require_blind_review",
            "require_office_roundtrip",
            "require_known_license",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        for name in (
            "maximum_initial_score",
            "minimum_oracle_score",
            "maximum_roundtrip_score_loss",
        ):
            _score(getattr(self, name), name)
        if not 0 <= self.maximum_initial_score <= self.minimum_oracle_score <= 1:
            raise ValueError("production score bounds are invalid")
        if not 0 <= self.maximum_roundtrip_score_loss <= 1:
            raise ValueError("maximum_roundtrip_score_loss must be between 0 and 1")
        return self


@dataclass(frozen=True)
class ProductionValidation:
    path: str
    valid: bool
    issues: tuple[str, ...]
    checks: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _score(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return float(value)


def record_blind_review(
    bundle: str | Path,
    *,
    reviewer: str,
    decision: str,
    notes: str = "",
) -> Path:
    root = Path(bundle).resolve()
    if decision not in {"pass", "fail"}:
        raise ValueError("blind review decision must be pass or fail")
    if not reviewer.strip():
        raise ValueError("blind review reviewer is required")
    receipt = {
        "receipt_version": "1.0",
        "bundle_identity": bundle_identity(root),
        "reviewer": reviewer.strip(),
        "decision": decision,
        "reviewed_at": datetime.now(tz=UTC).isoformat(),
        "evidence_scope": ["instruction", "init", "reference", "materials"],
        "oracle_hidden": True,
        "notes": notes.strip(),
    }
    target = root / "validation" / "blind-review.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def record_office_roundtrip(
    bundle: str | Path,
    baseline: str | Path,
    roundtripped: str | Path,
    *,
    office_suite: str,
    notes: str = "",
) -> Path:
    root = Path(bundle).resolve()
    if not office_suite.strip():
        raise ValueError("office_suite is required")
    plan = _read_json(root / "evaluator" / "plan.json")
    initial = root / "init.pptx"
    baseline_path = Path(baseline).resolve()
    roundtrip_path = Path(roundtripped).resolve()
    before = evaluate_candidate(baseline_path, initial, plan)
    after = evaluate_candidate(roundtrip_path, initial, plan)
    receipt = {
        "receipt_version": "1.0",
        "bundle_identity": bundle_identity(root),
        "office_suite": office_suite.strip(),
        "recorded_at": datetime.now(tz=UTC).isoformat(),
        "baseline_sha256": _sha256(baseline_path),
        "roundtripped_sha256": _sha256(roundtrip_path),
        "baseline_score": before.score,
        "roundtrip_score": after.score,
        "score_loss": round(max(0.0, before.score - after.score), 6),
        "hard_gates": after.hard_gates,
        "notes": notes.strip(),
    }
    target = root / "validation" / "office-roundtrip.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _validate_production(
    bundle: str | Path,
    policy: ProductionPolicy | None = None,
) -> ProductionValidation:
    root = Path(bundle).resolve()
    policy = (policy or ProductionPolicy()).require_valid()
    issues: list[str] = []
    checks: dict[str, Any] = {}
    bundle_result = validate_bundle(root)
    checks["bundle"] = bundle_result.to_dict()
    issues.extend(bundle_result.issues)
    if not bundle_result.valid:
        return ProductionValidation(str(root), False, tuple(issues), checks)
    for relative in ("evaluator/plan.json", "validation/build.json"):
        if not (root / relative).is_file():
            issues.append(f"missing production artifact: {relative}")
    if issues:
        return ProductionValidation(str(root), False, tuple(issues), checks)
    identity = bundle_identity(root)
    checks["bundle_identity"] = identity
    spec = load_task_spec(root / "task_spec.json")
    try:
        reference = PdfReader(root / "reference.pdf")
    except PdfReadError as exc:
        issues.append(f"invalid reference PDF: {exc}")
        return ProductionValidation(str(root), False, tuple(issues), checks)
    plan = _read_json(root / "evaluator" / "plan.json")
    if reference.is_encrypted or len(reference.pages) != plan["slide_count"]:
        issues.append("reference must be unencrypted and have exactly one page per slide")
    if policy.require_known_license and spec.source.license.casefold() in {
        "",
        "unknown",
        "unspecified",
    }:
        issues.append("source license is not production-eligible")
    build = _read_json(root / "validation" / "build.json")
    checks["build"] = build
    initial_score = _score(build["initial"]["score"], "initial score")
    oracle_score = _score(build["oracle"]["score"], "oracle score")
    if build.get("initial_sha256") != _sha256(root / "init.pptx"):
        issues.append("build receipt belongs to a different initial deck")
    if build.get("source_sha256") != spec.source.sha256:
        issues.append("build receipt source differs from provenance")
    if initial_score > policy.maximum_initial_score:
        issues.append(f"initial score exceeds policy: {initial_score}")
    if oracle_score < policy.minimum_oracle_score:
        issues.append(f"oracle score is below policy: {oracle_score}")

    if policy.require_redteam:
        path = root / "validation" / "redteam.json"
        if not path.is_file():
            issues.append("missing red-team receipt")
        else:
            receipt = _read_json(path)
            checks["redteam"] = receipt
            if receipt.get("valid") is not True:
                issues.append("red-team receipt did not pass")
            plan = _read_json(root / "evaluator" / "plan.json")
            if receipt.get("plan_sha256") != _json_sha256(plan):
                issues.append("red-team receipt belongs to a different evaluator plan")
            if receipt.get("initial_sha256") != _sha256(root / "init.pptx"):
                issues.append("red-team receipt belongs to a different initial deck")
            if receipt.get("source_sha256") != spec.source.sha256:
                issues.append("red-team receipt source differs from provenance")

    for name, required in (
        ("blind-review", policy.require_blind_review),
        ("office-roundtrip", policy.require_office_roundtrip),
    ):
        if not required:
            continue
        path = root / "validation" / f"{name}.json"
        if not path.is_file():
            issues.append(f"missing {name} receipt")
            continue
        receipt = _read_json(path)
        checks[name] = receipt
        if receipt.get("bundle_identity") != identity:
            issues.append(f"{name} receipt belongs to a different bundle revision")
        if name == "blind-review" and receipt.get("decision") != "pass":
            issues.append("blind review did not pass")
        if name == "office-roundtrip":
            before = _score(receipt["baseline_score"], "baseline score")
            after = _score(receipt["roundtrip_score"], "roundtrip score")
            loss = _score(receipt["score_loss"], "roundtrip score loss")
            if abs(loss - max(0.0, before - after)) > 1e-6:
                issues.append("office roundtrip score loss is inconsistent")
            if before < policy.minimum_oracle_score:
                issues.append("office roundtrip baseline is not an oracle-quality deck")
            if max(0.0, before - after) > policy.maximum_roundtrip_score_loss:
                issues.append("office roundtrip score loss exceeds policy")
            gates = receipt.get("hard_gates", {})
            required_gates = {
                "slide_count",
                "slide_order",
                "slide_size",
                "unauthorized_full_page_picture",
            }
            if (
                not isinstance(gates, dict)
                or not required_gates.issubset(gates)
                or any(gates[key] is not True for key in required_gates)
            ):
                issues.append("office roundtrip failed a catastrophic gate")

    plugins = {plugin.family: plugin for plugin in registered_families()}
    for episode in spec.episodes:
        plugin = plugins.get(episode.family)
        if plugin is None or episode.family == TaskFamily.MIXED_PRESENTATION_REPAIR:
            issues.append(f"episode {episode.episode_id} uses an unimplemented family")
            continue
        issues.extend(
            f"episode {episode.episode_id}: {issue}" for issue in plugin.validate_episode(episode)
        )
    return ProductionValidation(str(root), not issues, tuple(issues), checks)


def validate_production(
    bundle: str | Path, policy: ProductionPolicy | None = None
) -> ProductionValidation:
    """Reject malformed or incomplete evidence with an actionable diagnostic."""
    policy = (policy or ProductionPolicy()).require_valid()
    try:
        return _validate_production(bundle, policy)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, PdfReadError) as exc:
        return ProductionValidation(
            str(Path(bundle).resolve()),
            False,
            (f"invalid production evidence: {type(exc).__name__}: {exc}",),
            {},
        )


__all__ = [
    "ProductionPolicy",
    "ProductionValidation",
    "bundle_identity",
    "record_blind_review",
    "record_office_roundtrip",
    "validate_production",
]
