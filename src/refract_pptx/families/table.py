from __future__ import annotations

from refract_pptx.models import TaskFamily

from .base import CapabilityCandidate, FamilyPlugin


class NativeTableRepair(FamilyPlugin):
    family = TaskFamily.NATIVE_TABLE_REPAIR
    supported_capabilities = frozenset(
        {
            "table_content_repair",
            "table_style_repair",
            "table_proportion_repair",
        }
    )

    def analyze(self, inventory: object) -> CapabilityCandidate:
        slides = tuple(getattr(inventory, "slides", ()))
        tables = sum(int(getattr(slide, "tables", 0)) for slide in slides)
        table_slides = sum(int(getattr(slide, "tables", 0)) > 0 for slide in slides)
        eligible = tables > 0
        score = min(1.0, 0.45 + tables / 12 + table_slides / 20) if eligible else 0.0
        return CapabilityCandidate(
            family=self.family,
            eligible=eligible,
            score=round(score, 6),
            evidence=(f"{tables} native tables", f"tables on {table_slides} slides"),
            suggested_capabilities=(
                "table_content_repair",
                "table_style_repair",
                "table_proportion_repair",
            ),
        )


__all__ = ["NativeTableRepair"]
