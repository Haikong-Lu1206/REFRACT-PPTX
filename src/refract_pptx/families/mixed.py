from __future__ import annotations

from refract_pptx.models import TaskFamily

from .base import CapabilityCandidate, FamilyPlugin
from .chart import NativeChartRepair
from .reconstruction import ReferenceReconstruction
from .spatial import SpatialStructureRepair
from .table import NativeTableRepair


class MixedPresentationRepair(FamilyPlugin):
    family = TaskFamily.MIXED_PRESENTATION_REPAIR
    supported_capabilities = frozenset().union(
        ReferenceReconstruction.supported_capabilities,
        SpatialStructureRepair.supported_capabilities,
        NativeChartRepair.supported_capabilities,
        NativeTableRepair.supported_capabilities,
    )

    def analyze(self, inventory: object) -> CapabilityCandidate:
        candidates = (
            ReferenceReconstruction().analyze(inventory),
            SpatialStructureRepair().analyze(inventory),
            NativeChartRepair().analyze(inventory),
            NativeTableRepair().analyze(inventory),
        )
        eligible = [item for item in candidates if item.eligible]
        capabilities = tuple(
            dict.fromkeys(
                capability
                for item in eligible
                for capability in item.suggested_capabilities
            )
        )
        score = sum(item.score for item in eligible) / max(len(eligible), 1)
        return CapabilityCandidate(
            family=self.family,
            eligible=len(eligible) >= 2,
            score=round(score, 6) if len(eligible) >= 2 else 0.0,
            evidence=tuple(
                f"{item.family.value}: {', '.join(item.evidence)}" for item in eligible
            ),
            suggested_capabilities=capabilities,
        )
