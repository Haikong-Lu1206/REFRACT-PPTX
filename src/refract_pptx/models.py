from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    """Raised when a declarative task contract is invalid."""


class TaskFamily(StrEnum):
    REFERENCE_RECONSTRUCTION = "reference_reconstruction"
    SPATIAL_STRUCTURE_REPAIR = "spatial_structure_repair"
    NATIVE_CHART_REPAIR = "native_chart_repair"


class EvidenceTier(StrEnum):
    REFERENCE_VISIBLE = "reference_visible"
    INITIAL_STATE = "initial_state"
    MATERIAL_GROUNDED = "material_grounded"
    EDITOR_OBSERVABLE = "editor_observable"


@dataclass(frozen=True)
class SourceRecord:
    uri: str
    sha256: str
    license: str
    title: str = ""
    crawl_batch: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SourceRecord:
        return cls(
            uri=str(value.get("uri", "")).strip(),
            sha256=str(value.get("sha256", "")).lower().strip(),
            license=str(value.get("license", "")).strip(),
            title=str(value.get("title", "")).strip(),
            crawl_batch=str(value.get("crawl_batch", "")).strip(),
            metadata=dict(value.get("metadata", {})),
        )

    def validate(self) -> list[str]:
        issues: list[str] = []
        if not self.uri:
            issues.append("source.uri is required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            issues.append("source.sha256 must contain 64 lowercase hexadecimal characters")
        if not self.license:
            issues.append("source.license is required")
        return issues


@dataclass(frozen=True)
class EpisodeSpec:
    episode_id: str
    family: TaskFamily
    capability: str
    slides: tuple[int, ...]
    mutation: str
    evidence_tier: EvidenceTier
    observable_evidence: tuple[str, ...]
    weight: float
    evaluator: dict[str, float]
    acceptance: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EpisodeSpec:
        return cls(
            episode_id=str(value.get("episode_id", "")).strip(),
            family=TaskFamily(value.get("family")),
            capability=str(value.get("capability", "")).strip(),
            slides=tuple(int(item) for item in value.get("slides", [])),
            mutation=str(value.get("mutation", "")).strip(),
            evidence_tier=EvidenceTier(value.get("evidence_tier")),
            observable_evidence=tuple(
                str(item).strip() for item in value.get("observable_evidence", [])
            ),
            weight=float(value.get("weight", 0.0)),
            evaluator={str(key): float(score) for key, score in value.get("evaluator", {}).items()},
            acceptance=tuple(str(item).strip() for item in value.get("acceptance", [])),
        )

    def validate(self) -> list[str]:
        prefix = f"episode {self.episode_id or '<missing>'}"
        issues: list[str] = []
        if not self.episode_id:
            issues.append("episode_id is required")
        if not self.capability:
            issues.append(f"{prefix}: capability is required")
        if not self.slides or any(slide < 1 for slide in self.slides):
            issues.append(f"{prefix}: slides must contain positive one-based indices")
        if len(set(self.slides)) != len(self.slides):
            issues.append(f"{prefix}: slides contains duplicate indices")
        if not self.mutation:
            issues.append(f"{prefix}: mutation is required")
        if not self.observable_evidence or any(not item for item in self.observable_evidence):
            issues.append(f"{prefix}: observable_evidence must be explicit")
        if not math.isfinite(self.weight) or self.weight <= 0:
            issues.append(f"{prefix}: weight must be finite and positive")
        if not self.evaluator:
            issues.append(f"{prefix}: evaluator components are required")
        elif any(not math.isfinite(value) or value <= 0 for value in self.evaluator.values()):
            issues.append(f"{prefix}: evaluator weights must be finite and positive")
        elif not math.isclose(sum(self.evaluator.values()), 1.0, abs_tol=1e-6):
            issues.append(f"{prefix}: evaluator weights must sum to 1.0")
        if not self.acceptance or any(not item for item in self.acceptance):
            issues.append(f"{prefix}: acceptance criteria are required")
        return issues


@dataclass(frozen=True)
class TaskSpec:
    spec_version: str
    task_id: str
    title: str
    instruction: str
    family: TaskFamily
    source: SourceRecord
    episodes: tuple[EpisodeSpec, ...]
    preservation_contracts: tuple[str, ...]
    assets: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TaskSpec:
        try:
            family = TaskFamily(value.get("family"))
            episodes = tuple(EpisodeSpec.from_dict(item) for item in value.get("episodes", []))
            return cls(
                spec_version=str(value.get("spec_version", "")).strip(),
                task_id=str(value.get("task_id", "")).strip(),
                title=str(value.get("title", "")).strip(),
                instruction=str(value.get("instruction", "")).strip(),
                family=family,
                source=SourceRecord.from_dict(dict(value.get("source", {}))),
                episodes=episodes,
                preservation_contracts=tuple(
                    str(item).strip() for item in value.get("preservation_contracts", [])
                ),
                assets={str(key): str(path) for key, path in value.get("assets", {}).items()},
                metadata=dict(value.get("metadata", {})),
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ContractError(f"task specification cannot be decoded: {exc}") from exc

    def validate(self) -> list[str]:
        issues = self.source.validate()
        if self.spec_version != "1.0":
            issues.append("spec_version must be 1.0")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", self.task_id):
            issues.append("task_id must be a 3-80 character lowercase slug")
        if not self.title:
            issues.append("title is required")
        if len(self.instruction) < 40:
            issues.append("instruction must state the reconstruction objective")
        if not self.episodes:
            issues.append("at least one episode is required")
        episode_ids: set[str] = set()
        for episode in self.episodes:
            issues.extend(episode.validate())
            if episode.family != self.family:
                issues.append(f"episode {episode.episode_id}: family differs from task family")
            if episode.episode_id in episode_ids:
                issues.append(f"duplicate episode_id: {episode.episode_id}")
            episode_ids.add(episode.episode_id)
        if self.episodes and not math.isclose(
            sum(episode.weight for episode in self.episodes), 1.0, abs_tol=1e-6
        ):
            issues.append("episode weights must sum to 1.0")
        if not self.preservation_contracts or any(
            not item for item in self.preservation_contracts
        ):
            issues.append("at least one preservation contract is required")
        required_assets = {"initial_presentation", "reference_render"}
        missing_assets = sorted(required_assets - self.assets.keys())
        if missing_assets:
            issues.append(f"missing asset declarations: {', '.join(missing_assets)}")
        return issues

    def require_valid(self) -> TaskSpec:
        issues = self.validate()
        if issues:
            raise ContractError("invalid task specification:\n- " + "\n- ".join(issues))
        return self


def load_task_spec(path: str | Path) -> TaskSpec:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError("task specification root must be an object")
    return TaskSpec.from_dict(payload)

