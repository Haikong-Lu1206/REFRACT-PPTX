from __future__ import annotations

from refract_pptx.models import TaskFamily

from .base import CapabilityCandidate, FamilyPlugin


class NativeChartRepair(FamilyPlugin):
    family = TaskFamily.NATIVE_CHART_REPAIR
    supported_capabilities = frozenset(
        {
            "chart_data_repair",
            "chart_type_repair",
            "series_semantics",
            "chart_layout_repair",
            "chart_style_repair",
        }
    )

    def analyze(self, inventory: object) -> CapabilityCandidate:
        slides = tuple(getattr(inventory, "slides", ()))
        charts = sum(int(getattr(slide, "charts", 0)) for slide in slides)
        chart_slides = sum(int(getattr(slide, "charts", 0)) > 0 for slide in slides)
        eligible = charts > 0
        score = min(1.0, 0.45 + charts / 12 + chart_slides / 20) if eligible else 0.0
        capabilities = (
            "chart_data_repair",
            "chart_type_repair",
            "series_semantics",
            "chart_layout_repair",
            "chart_style_repair",
        )
        return CapabilityCandidate(
            family=self.family,
            eligible=eligible,
            score=round(score, 6),
            evidence=(f"{charts} native charts", f"charts on {chart_slides} slides"),
            suggested_capabilities=capabilities,
        )

