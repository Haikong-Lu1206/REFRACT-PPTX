from __future__ import annotations

import json
from typing import Any, Protocol

from refract_pptx.presentation import DeckSnapshot

from .proposal import ALLOWED_OPERATIONS, AgentProposal, ProposalError


class ProposalProvider(Protocol):
    def propose(self, system: str, user: str) -> dict[str, Any]: ...


SYSTEM_PROMPT = """You design difficult but solvable editable-presentation repair tasks.
Use only evidence visible in the initial deck, rendered reference, supplied materials,
instruction, or intact repeated patterns. Propose presentation-specific mutations rather than
randomly selecting a fixed family. Return declarative JSON only. Never emit executable code,
XPath, package paths, hidden ground-truth properties, or platform-specific instructions.
Every mutation must state accepted equivalent solutions and weighted evaluator components."""


def proposal_prompt(
    inventory: DeckSnapshot, evidence_context: tuple[str, ...] = ()
) -> str:
    compact_objects = [
        {
            "slide": item.slide,
            "shape_id": item.shape_id,
            "name": item.name,
            "kind": item.kind,
            "text": item.text[:240],
            "bbox_points": item.bbox_points,
            "z_order": item.z_order,
            "has_chart": bool(item.chart),
            "has_media": bool(item.media_sha256),
        }
        for item in inventory.objects
    ]
    evidence = {
        "slide_count": inventory.slide_count,
        "slide_size_points": [
            inventory.slide_width_points,
            inventory.slide_height_points,
        ],
        "objects": compact_objects,
        "attached_evidence": list(evidence_context),
    }
    operation_catalog = {
        family.value: sorted(operations) for family, operations in ALLOWED_OPERATIONS.items()
    }
    schema = {
        "proposal_version": "1.0",
        "title": "string",
        "instruction": "macro repair objective; details remain in visible evidence",
        "deck_summary": "string",
        "mutations": [
            {
                "mutation_id": "lowercase-slug",
                "family": "registered family",
                "capability": "registered family capability",
                "slide": 1,
                "target": {"shape_id": 2, "kind": "shape"},
                "operation": {"type": "registered deterministic operation"},
                "evidence_tier": "reference_visible",
                "evidence": [
                    {
                        "source": "reference",
                        "locator": "visible locator",
                        "supports": "observable fact",
                    }
                ],
                "rationale": "why this is meaningful and recoverable",
                "accepted_solutions": ["equivalent editable solution"],
                "scoring": {"geometry": 1.0},
                "weight": 1.0,
            }
        ],
        "preservation_contracts": ["visible content that must remain unchanged"],
    }
    return (
        "Analyze this presentation inventory and propose a diverse repair task. The final "
        "instruction should describe the macro reconstruction objective and rely on the visible "
        "reference for detail. Use proposal_version 1.0. A proposal may combine families. "
        "Use only selectors from the inventory and only facts supported by attached evidence. "
        "Mutation weights and each scoring map must sum to 1.0.\n\n"
        "OUTPUT SCHEMA\n"
        + json.dumps(schema, indent=2, ensure_ascii=False)
        + "\n\nOPERATION CATALOG\n"
        + json.dumps(operation_catalog, indent=2, ensure_ascii=False)
        + "\n\nPRESENTATION EVIDENCE\n"
        + json.dumps(evidence, indent=2, ensure_ascii=False)
    )


def design_proposal(
    provider: ProposalProvider,
    inventory: DeckSnapshot,
    evidence_context: tuple[str, ...] = (),
) -> AgentProposal:
    payload = provider.propose(
        SYSTEM_PROMPT,
        proposal_prompt(inventory, evidence_context),
    )
    if not isinstance(payload, dict):
        raise ProposalError("proposal provider returned a non-object payload")
    return AgentProposal.from_dict(payload).require_valid()
