from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from refract_pptx.families import registered_families
from refract_pptx.presentation import DeckSnapshot, ObjectSnapshot

from .proposal import AgentProposal, MutationProposal, ProposalError


@dataclass(frozen=True)
class CompiledMutation:
    mutation_id: str
    family: str
    capability: str
    slide: int
    target_shape_id: int
    target_semantic_key: str
    operation: dict[str, Any]
    evidence_tier: str
    evidence: tuple[dict[str, str], ...]
    rationale: str
    accepted_solutions: tuple[str, ...]
    scoring: dict[str, float]
    weight: float
    oracle_target: dict[str, Any]
    initial_target: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompiledPlan:
    plan_version: str
    title: str
    instruction: str
    deck_summary: str
    slide_count: int
    slide_width_points: float
    slide_height_points: float
    slide_parts: tuple[str, ...]
    mutations: tuple[CompiledMutation, ...]
    protected_objects: tuple[dict[str, Any], ...]
    preservation_contracts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_version": self.plan_version,
            "title": self.title,
            "instruction": self.instruction,
            "deck_summary": self.deck_summary,
            "slide_count": self.slide_count,
            "slide_width_points": self.slide_width_points,
            "slide_height_points": self.slide_height_points,
            "slide_parts": list(self.slide_parts),
            "mutations": [item.to_dict() for item in self.mutations],
            "protected_objects": list(self.protected_objects),
            "preservation_contracts": list(self.preservation_contracts),
        }


def _selector_matches(item: ObjectSnapshot, slide: int, selector: dict[str, Any]) -> bool:
    if item.slide != slide:
        return False
    if "shape_id" in selector and item.shape_id != int(selector["shape_id"]):
        return False
    if "kind" in selector and item.kind != str(selector["kind"]):
        return False
    if "name" in selector and item.name != str(selector["name"]):
        return False
    if "semantic_key" in selector and item.semantic_key != str(selector["semantic_key"]):
        return False
    if "media_sha256" in selector and item.media_sha256 != str(selector["media_sha256"]):
        return False
    if "text_contains" in selector:
        expected = " ".join(str(selector["text_contains"]).split()).casefold()
        observed = " ".join(item.text.split()).casefold()
        if expected not in observed:
            return False
    return True


def _resolve_target(
    inventory: DeckSnapshot, mutation: MutationProposal, selector: dict[str, Any] | None = None
) -> ObjectSnapshot:
    selector = selector or mutation.target
    matches = [
        item for item in inventory.objects if _selector_matches(item, mutation.slide, selector)
    ]
    if len(matches) != 1:
        raise ProposalError(
            f"mutation {mutation.mutation_id}: selector must resolve to exactly one object; "
            f"found {len(matches)}"
        )
    return matches[0]


def compile_proposal(proposal: AgentProposal, inventory: DeckSnapshot) -> CompiledPlan:
    proposal.require_valid()
    plugins = {plugin.family: plugin for plugin in registered_families()}
    compiled: list[CompiledMutation] = []
    targeted: set[tuple[int, int]] = set()
    for mutation in proposal.mutations:
        plugin = plugins.get(mutation.family)
        if plugin is None:
            raise ProposalError(f"mutation {mutation.mutation_id}: family is not registered")
        if mutation.capability not in plugin.supported_capabilities:
            raise ProposalError(
                f"mutation {mutation.mutation_id}: capability {mutation.capability!r} "
                f"is not supported by {mutation.family.value}"
            )
        target = _resolve_target(inventory, mutation)
        target_key = (target.slide, target.shape_id)
        if target_key in targeted:
            raise ProposalError(
                f"mutation {mutation.mutation_id}: target is already used by another mutation"
            )
        operation = dict(mutation.operation)
        operation_type = operation.get("type")
        if operation_type == "remove_shape" and target.kind not in {"shape", "picture"}:
            raise ProposalError(
                f"mutation {mutation.mutation_id}: removing native {target.kind} objects is not "
                "registered because dependent package parts require a family-specific mutator"
            )
        if operation_type == "set_text" and not target.text:
            raise ProposalError(
                f"mutation {mutation.mutation_id}: set_text requires a target with visible text"
            )
        if str(operation_type).startswith(("set_chart", "remove_chart")) and target.kind != "chart":
            raise ProposalError(
                f"mutation {mutation.mutation_id}: chart operations require a native chart"
            )
        if operation_type == "swap_geometry":
            other_selector = operation.get("other_target")
            if not isinstance(other_selector, dict):
                raise ProposalError(
                    f"mutation {mutation.mutation_id}: swap_geometry requires other_target"
                )
            other = _resolve_target(inventory, mutation, other_selector)
            other_key = (other.slide, other.shape_id)
            if other_key == target_key:
                raise ProposalError(
                    f"mutation {mutation.mutation_id}: swap targets must be different objects"
                )
            if other_key in targeted:
                raise ProposalError(
                    f"mutation {mutation.mutation_id}: secondary target is already in use"
                )
            operation["other_shape_id"] = other.shape_id
            operation["other_oracle_target"] = other.to_dict()
            targeted.add(other_key)
        targeted.add(target_key)
        compiled.append(
            CompiledMutation(
                mutation_id=mutation.mutation_id,
                family=mutation.family.value,
                capability=mutation.capability,
                slide=mutation.slide,
                target_shape_id=target.shape_id,
                target_semantic_key=target.semantic_key,
                operation=operation,
                evidence_tier=mutation.evidence_tier.value,
                evidence=tuple(asdict(item) for item in mutation.evidence),
                rationale=mutation.rationale,
                accepted_solutions=mutation.accepted_solutions,
                scoring=dict(mutation.scoring),
                weight=mutation.weight,
                oracle_target=target.to_dict(),
            )
        )
    protected = tuple(
        item.to_dict()
        for item in inventory.objects
        if (item.slide, item.shape_id) not in targeted
    )
    return CompiledPlan(
        plan_version="1.0",
        title=proposal.title,
        instruction=proposal.instruction,
        deck_summary=proposal.deck_summary,
        slide_count=inventory.slide_count,
        slide_width_points=inventory.slide_width_points,
        slide_height_points=inventory.slide_height_points,
        slide_parts=inventory.slide_parts,
        mutations=tuple(compiled),
        protected_objects=protected,
        preservation_contracts=proposal.preservation_contracts,
    )
