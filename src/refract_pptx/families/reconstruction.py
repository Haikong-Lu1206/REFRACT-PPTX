from __future__ import annotations

from refract_pptx.models import TaskFamily

from .base import CapabilityCandidate, FamilyPlugin


class ReferenceReconstruction(FamilyPlugin):
    family = TaskFamily.REFERENCE_RECONSTRUCTION
    supported_capabilities = frozenset(
        {
            "picture_restoration",
            "text_reconstruction",
            "table_reconstruction",
            "mixed_slide_reconstruction",
        }
    )

    def analyze(self, inventory: object) -> CapabilityCandidate:
        slides = int(getattr(inventory, "slide_count", 0))
        object_types = tuple(getattr(inventory, "native_object_types", ()))
        diversity = len(object_types)
        eligible = slides >= 5 and diversity >= 2
        score = min(1.0, 0.35 + slides / 50 + diversity / 10) if eligible else 0.0
        capabilities = ["text_reconstruction"]
        if "picture" in object_types:
            capabilities.append("picture_restoration")
        if "table" in object_types:
            capabilities.append("table_reconstruction")
        if len(capabilities) >= 2:
            capabilities.append("mixed_slide_reconstruction")
        return CapabilityCandidate(
            family=self.family,
            eligible=eligible,
            score=round(score, 6),
            evidence=(f"{slides} slides", f"native types: {', '.join(object_types) or 'none'}"),
            suggested_capabilities=tuple(capabilities),
        )
