from __future__ import annotations

from refract_pptx.models import TaskFamily

from .base import CapabilityCandidate, FamilyPlugin


class SpatialStructureRepair(FamilyPlugin):
    family = TaskFamily.SPATIAL_STRUCTURE_REPAIR
    supported_capabilities = frozenset(
        {
            "object_alignment",
            "z_order_restoration",
            "overlap_repair",
            "connector_alignment",
            "cross_slide_consistency",
            "visible_shape_style_repair",
        }
    )

    def analyze(self, inventory: object) -> CapabilityCandidate:
        slides = tuple(getattr(inventory, "slides", ()))
        shapes = int(getattr(inventory, "total_shapes", 0))
        connectors = sum(int(getattr(slide, "connectors", 0)) for slide in slides)
        groups = sum(int(getattr(slide, "groups", 0)) for slide in slides)
        pictures = sum(int(getattr(slide, "pictures", 0)) for slide in slides)
        eligible = len(slides) >= 3 and shapes >= 12
        score = min(1.0, 0.25 + shapes / 160 + connectors / 12 + groups / 20) if eligible else 0.0
        capabilities = ["object_alignment", "overlap_repair", "cross_slide_consistency"]
        if connectors:
            capabilities.append("connector_alignment")
        if groups or pictures:
            capabilities.append("z_order_restoration")
        return CapabilityCandidate(
            family=self.family,
            eligible=eligible,
            score=round(score, 6),
            evidence=(
                f"{shapes} top-level shapes",
                f"{connectors} connectors",
                f"{groups} groups",
            ),
            suggested_capabilities=tuple(capabilities),
        )
