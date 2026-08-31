from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from refract_pptx.models import EvidenceTier, TaskFamily


class ProposalError(ValueError):
    """Raised when an agent proposal is not safe to compile."""


ALLOWED_EVIDENCE_SOURCES = frozenset(
    {"reference", "initial", "materials", "instruction", "repeated_pattern"}
)
ALLOWED_SCORE_COMPONENTS = frozenset(
    {
        "existence",
        "geometry",
        "text",
        "fill",
        "media_identity",
        "z_order",
        "chart_type",
        "chart_data",
        "chart_elements",
        "series_style",
    }
)
ALLOWED_OPERATIONS: dict[TaskFamily, frozenset[str]] = {
    TaskFamily.REFERENCE_RECONSTRUCTION: frozenset(
        {"remove_shape", "move_shape", "resize_shape", "set_text", "set_fill"}
    ),
    TaskFamily.SPATIAL_STRUCTURE_REPAIR: frozenset(
        {"move_shape", "resize_shape", "swap_geometry", "change_z_order"}
    ),
    TaskFamily.NATIVE_CHART_REPAIR: frozenset(
        {
            "remove_chart_legend",
            "remove_chart_title",
            "set_series_color",
            "set_chart_value",
        }
    ),
}


@dataclass(frozen=True)
class EvidenceClaim:
    source: str
    locator: str
    supports: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EvidenceClaim:
        return cls(
            source=str(value.get("source", "")).strip(),
            locator=str(value.get("locator", "")).strip(),
            supports=str(value.get("supports", "")).strip(),
        )

    def validate(self, prefix: str) -> list[str]:
        issues: list[str] = []
        if self.source not in ALLOWED_EVIDENCE_SOURCES:
            issues.append(f"{prefix}: unsupported evidence source: {self.source}")
        if not self.locator:
            issues.append(f"{prefix}: evidence locator is required")
        if not self.supports:
            issues.append(f"{prefix}: evidence must state what it supports")
        return issues


@dataclass(frozen=True)
class MutationProposal:
    mutation_id: str
    family: TaskFamily
    capability: str
    slide: int
    target: dict[str, Any]
    operation: dict[str, Any]
    evidence_tier: EvidenceTier
    evidence: tuple[EvidenceClaim, ...]
    rationale: str
    accepted_solutions: tuple[str, ...]
    scoring: dict[str, float]
    weight: float

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> MutationProposal:
        return cls(
            mutation_id=str(value.get("mutation_id", "")).strip(),
            family=TaskFamily(value.get("family")),
            capability=str(value.get("capability", "")).strip(),
            slide=int(value.get("slide", 0)),
            target=dict(value.get("target", {})),
            operation=dict(value.get("operation", {})),
            evidence_tier=EvidenceTier(value.get("evidence_tier")),
            evidence=tuple(EvidenceClaim.from_dict(item) for item in value.get("evidence", [])),
            rationale=str(value.get("rationale", "")).strip(),
            accepted_solutions=tuple(
                str(item).strip() for item in value.get("accepted_solutions", [])
            ),
            scoring={str(key): float(score) for key, score in value.get("scoring", {}).items()},
            weight=float(value.get("weight", 0.0)),
        )

    def validate(self) -> list[str]:
        prefix = f"mutation {self.mutation_id or '<missing>'}"
        issues: list[str] = []
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", self.mutation_id):
            issues.append(f"{prefix}: mutation_id must be a lowercase slug")
        if not self.capability:
            issues.append(f"{prefix}: capability is required")
        if self.slide < 1:
            issues.append(f"{prefix}: slide must be a positive one-based index")
        if not self.target:
            issues.append(f"{prefix}: target selector is required")
        operation_type = str(self.operation.get("type", ""))
        if operation_type not in ALLOWED_OPERATIONS[self.family]:
            issues.append(
                f"{prefix}: operation {operation_type!r} is not allowed for {self.family}"
            )
        if not self.evidence:
            issues.append(f"{prefix}: observable evidence is required")
        for claim in self.evidence:
            issues.extend(claim.validate(prefix))
        if len(self.rationale) < 20:
            issues.append(f"{prefix}: rationale must explain why the mutation is meaningful")
        if not self.accepted_solutions or any(not item for item in self.accepted_solutions):
            issues.append(f"{prefix}: accepted_solutions are required")
        if not self.scoring:
            issues.append(f"{prefix}: scoring components are required")
        else:
            unsupported = sorted(set(self.scoring) - ALLOWED_SCORE_COMPONENTS)
            if unsupported:
                issues.append(f"{prefix}: unsupported scoring components: {', '.join(unsupported)}")
            if any(not math.isfinite(value) or value <= 0 for value in self.scoring.values()):
                issues.append(f"{prefix}: scoring weights must be finite and positive")
            elif not math.isclose(sum(self.scoring.values()), 1.0, abs_tol=1e-6):
                issues.append(f"{prefix}: scoring weights must sum to 1.0")
        if not math.isfinite(self.weight) or self.weight <= 0:
            issues.append(f"{prefix}: task weight must be finite and positive")
        return issues


@dataclass(frozen=True)
class AgentProposal:
    proposal_version: str
    title: str
    instruction: str
    deck_summary: str
    mutations: tuple[MutationProposal, ...]
    preservation_contracts: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AgentProposal:
        try:
            return cls(
                proposal_version=str(value.get("proposal_version", "")).strip(),
                title=str(value.get("title", "")).strip(),
                instruction=str(value.get("instruction", "")).strip(),
                deck_summary=str(value.get("deck_summary", "")).strip(),
                mutations=tuple(
                    MutationProposal.from_dict(item) for item in value.get("mutations", [])
                ),
                preservation_contracts=tuple(
                    str(item).strip() for item in value.get("preservation_contracts", [])
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ProposalError(f"proposal cannot be decoded: {exc}") from exc

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.proposal_version != "1.0":
            issues.append("proposal_version must be 1.0")
        if not self.title or len(self.instruction) < 40 or len(self.deck_summary) < 20:
            issues.append("title, macro instruction, and deck_summary are required")
        if not self.mutations:
            issues.append("at least one mutation is required")
        mutation_ids: set[str] = set()
        for mutation in self.mutations:
            issues.extend(mutation.validate())
            if mutation.mutation_id in mutation_ids:
                issues.append(f"duplicate mutation_id: {mutation.mutation_id}")
            mutation_ids.add(mutation.mutation_id)
        if self.mutations and not math.isclose(
            sum(mutation.weight for mutation in self.mutations), 1.0, abs_tol=1e-6
        ):
            issues.append("mutation task weights must sum to 1.0")
        if not self.preservation_contracts:
            issues.append("preservation_contracts are required")
        return issues

    def require_valid(self) -> AgentProposal:
        issues = self.validate()
        if issues:
            raise ProposalError("invalid agent proposal:\n- " + "\n- ".join(issues))
        return self


def load_proposal(path: str | Path) -> AgentProposal:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProposalError(f"cannot read proposal {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProposalError("proposal root must be an object")
    return AgentProposal.from_dict(payload)
