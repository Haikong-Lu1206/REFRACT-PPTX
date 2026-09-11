from __future__ import annotations

from .base import CapabilityCandidate, FamilyPlugin
from .chart import NativeChartRepair
from .mixed import MixedPresentationRepair
from .reconstruction import ReferenceReconstruction
from .spatial import SpatialStructureRepair
from .table import NativeTableRepair

_PLUGINS: tuple[FamilyPlugin, ...] = (
    ReferenceReconstruction(),
    SpatialStructureRepair(),
    NativeChartRepair(),
    NativeTableRepair(),
    MixedPresentationRepair(),
)


def registered_families() -> tuple[FamilyPlugin, ...]:
    return _PLUGINS


def family_candidates(inventory: object) -> tuple[CapabilityCandidate, ...]:
    candidates = [plugin.analyze(inventory) for plugin in _PLUGINS]
    eligible = (item for item in candidates if item.eligible)
    return tuple(sorted(eligible, key=lambda item: -item.score))


__all__ = [
    "CapabilityCandidate",
    "FamilyPlugin",
    "MixedPresentationRepair",
    "NativeTableRepair",
    "family_candidates",
    "registered_families",
]
