from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from refract_pptx.families import family_candidates
from refract_pptx.presentation import PresentationInventory, inspect_pptx


@dataclass(frozen=True)
class ScreeningDecision:
    path: str
    accepted: bool
    quality_score: float
    reasons: tuple[str, ...]
    recommended_families: tuple[str, ...]
    inventory: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def mechanical_quality(inventory: PresentationInventory) -> float:
    slide_score = _clamp(1.0 - abs(inventory.slide_count - 16) / 20)
    shape_density = inventory.total_shapes / max(1, inventory.slide_count)
    density_score = _clamp(shape_density / 12)
    diversity_score = _clamp(len(inventory.native_object_types) / 6)
    text_slides = sum(slide.text_characters >= 40 for slide in inventory.slides)
    content_score = _clamp(text_slides / max(1, inventory.slide_count * 0.7))
    media_score = _clamp(inventory.media_files / max(1, inventory.slide_count * 0.5))
    score = (
        0.20 * slide_score
        + 0.25 * density_score
        + 0.25 * diversity_score
        + 0.20 * content_score
        + 0.10 * media_score
    )
    return round(score, 6)


def screen_inventory(
    inventory: PresentationInventory,
    *,
    minimum_slides: int = 3,
    maximum_slides: int = 100,
    minimum_shapes: int = 8,
    minimum_quality_score: float = 0.35,
) -> ScreeningDecision:
    reasons: list[str] = []
    if inventory.slide_count < minimum_slides:
        reasons.append(f"too few slides ({inventory.slide_count} < {minimum_slides})")
    if inventory.slide_count > maximum_slides:
        reasons.append(f"too many slides ({inventory.slide_count} > {maximum_slides})")
    if inventory.total_shapes < minimum_shapes:
        reasons.append(f"too few editable shapes ({inventory.total_shapes} < {minimum_shapes})")
    if inventory.slide_width is None or inventory.slide_height is None:
        reasons.append("slide size is unavailable")
    score = mechanical_quality(inventory)
    if not math.isfinite(score) or score < minimum_quality_score:
        reasons.append(f"mechanical quality below threshold ({score:.3f})")
    recommendations = tuple(candidate.family.value for candidate in family_candidates(inventory))
    if not recommendations:
        reasons.append("no registered family has enough structural evidence")
    return ScreeningDecision(
        path=inventory.path,
        accepted=not reasons,
        quality_score=score,
        reasons=tuple(reasons),
        recommended_families=recommendations,
        inventory=inventory.to_dict(),
    )


def screen_presentation(path: str | Path, **kwargs: Any) -> ScreeningDecision:
    return screen_inventory(inspect_pptx(path), **kwargs)
