from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from refract_pptx.models import EpisodeSpec, TaskFamily


@dataclass(frozen=True)
class CapabilityCandidate:
    family: TaskFamily
    eligible: bool
    score: float
    evidence: tuple[str, ...]
    suggested_capabilities: tuple[str, ...]


class FamilyPlugin(ABC):
    family: TaskFamily
    supported_capabilities: frozenset[str]

    @abstractmethod
    def analyze(self, inventory: object) -> CapabilityCandidate:
        raise NotImplementedError

    def validate_episode(self, episode: EpisodeSpec) -> list[str]:
        issues: list[str] = []
        if episode.family != self.family:
            issues.append("episode belongs to a different family")
        if episode.capability not in self.supported_capabilities:
            issues.append(f"unsupported capability: {episode.capability}")
        return issues
