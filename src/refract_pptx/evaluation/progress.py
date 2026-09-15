from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from refract_pptx.presentation import DeckSnapshot, ObjectSnapshot, object_inventory
from refract_pptx.presentation.chart_style import CHART_STYLE_OPERATIONS, chart_style_similarity
from refract_pptx.presentation.typography import TEXT_OPERATIONS, typography_similarity
from refract_pptx.presentation.visual import visual_similarity


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normal_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _object_from_dict(value: dict[str, Any]) -> ObjectSnapshot:
    box = value.get("bbox_points")
    return ObjectSnapshot(
        slide=int(value["slide"]),
        slide_part=str(value.get("slide_part", "")),
        shape_id=int(value["shape_id"]),
        name=str(value.get("name", "")),
        kind=str(value.get("kind", "shape")),
        text=str(value.get("text", "")),
        bbox_points=tuple(float(item) for item in box) if box is not None else None,
        z_order=int(value.get("z_order", 0)),
        fill_color=str(value.get("fill_color", "")),
        media_sha256=str(value.get("media_sha256", "")),
        media_part=str(value.get("media_part", "")),
        media_signature=tuple(int(item) for item in value.get("media_signature", [])),
        chart=dict(value.get("chart", {})),
        table=dict(value.get("table", {})),
        connector=dict(value.get("connector", {})),
        visual=dict(value.get("visual", {})),
        typography=dict(value.get("typography", {})),
    )


def _box_similarity(
    observed: tuple[float, float, float, float] | None,
    expected: tuple[float, float, float, float] | None,
    width: float,
    height: float,
) -> float:
    if observed is None or expected is None:
        return float(observed is None and expected is None)
    observed_center = (observed[0] + observed[2] / 2, observed[1] + observed[3] / 2)
    expected_center = (expected[0] + expected[2] / 2, expected[1] + expected[3] / 2)
    diagonal = max(1.0, math.hypot(width, height))
    position_error = math.dist(observed_center, expected_center) / diagonal
    if position_error <= 0.005:
        position = 1.0
    else:
        position = _clamp((0.04 - position_error) / (0.04 - 0.005))
    size_error = max(
        abs(observed[2] - expected[2]) / max(1.0, expected[2]),
        abs(observed[3] - expected[3]) / max(1.0, expected[3]),
    )
    if size_error <= 0.025:
        size = 1.0
    else:
        size = _clamp((0.15 - size_error) / (0.15 - 0.025))
    return position * size


def _text_similarity(observed: str, expected: str) -> float:
    first = _normal_text(observed)
    second = _normal_text(expected)
    if first == second:
        return 1.0
    if not first or not second:
        return 0.0
    numeric = r"[+-]?\d+(?:[.,]\d+)*(?:%|‰)?"
    if re.findall(numeric, first) != re.findall(numeric, second):
        return 0.0
    return SequenceMatcher(None, first, second).ratio()


def _rgb(value: str) -> tuple[int, int, int] | None:
    if not value.startswith("srgbClr:"):
        return None
    token = value.split(":", 1)[1]
    if len(token) != 6:
        return None
    try:
        return tuple(int(token[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None


def _color_similarity(observed: str, expected: str) -> float:
    if observed == expected:
        return 1.0
    first = _rgb(observed)
    second = _rgb(expected)
    if first is None or second is None:
        return 0.0
    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second, strict=True)))
    if distance <= 3:
        return 1.0
    return _clamp((60 - distance) / 57)


def _media_similarity(observed: ObjectSnapshot, expected: ObjectSnapshot) -> float:
    if expected.media_sha256 and observed.media_sha256 == expected.media_sha256:
        return 1.0
    first = observed.media_signature
    second = expected.media_signature
    if not first or len(first) != len(second):
        return 0.0
    visual = 1.0 - sum(abs(a - b) for a, b in zip(first, second, strict=True)) / (255 * len(first))
    if visual >= 0.985:
        return 1.0
    return _clamp((visual - 0.80) / (0.985 - 0.80))


def _chart_data_similarity(observed: dict[str, Any], expected: dict[str, Any]) -> float:
    observed_series = list(observed.get("series", []))
    expected_series = list(expected.get("series", []))
    if not expected_series:
        return float(not observed_series)
    scores: list[float] = []
    used: set[int] = set()
    for target in expected_series:
        best_index = -1
        best_score = 0.0
        for index, candidate in enumerate(observed_series):
            if index in used:
                continue
            name = _text_similarity(str(candidate.get("name", "")), str(target.get("name", "")))
            expected_values = [str(item) for item in target.get("values", [])]
            observed_values = [str(item) for item in candidate.get("values", [])]
            count = max(len(expected_values), len(observed_values), 1)
            values = (
                sum(
                    first == second
                    for first, second in zip(observed_values, expected_values, strict=False)
                )
                / count
            )
            expected_categories = target.get("categories", [])
            observed_categories = candidate.get("categories", [])
            if expected_categories:
                categories = sum(
                    _normal_text(str(a)) == _normal_text(str(b))
                    for a, b in zip(observed_categories, expected_categories, strict=False)
                ) / max(len(expected_categories), len(observed_categories), 1)
                score = 0.1 * name + 0.2 * categories + 0.7 * values
            else:
                score = 0.25 * name + 0.75 * values
            if score > best_score:
                best_index, best_score = index, score
        if best_index >= 0:
            used.add(best_index)
        scores.append(best_score)
    cardinality = min(len(observed_series), len(expected_series)) / max(
        len(observed_series), len(expected_series), 1
    )
    return cardinality * sum(scores) / len(scores)


def _chart_elements_similarity(observed: dict[str, Any], expected: dict[str, Any]) -> float:
    title = _text_similarity(str(observed.get("title", "")), str(expected.get("title", "")))
    legend = float(bool(observed.get("legend")) == bool(expected.get("legend")))
    return 0.6 * title + 0.4 * legend


def _series_style_similarity(observed: dict[str, Any], expected: dict[str, Any]) -> float:
    observed_series = list(observed.get("series", []))
    expected_series = list(expected.get("series", []))
    if not expected_series:
        return float(not observed_series)
    scores = []
    for index, target in enumerate(expected_series):
        if index >= len(observed_series):
            scores.append(0.0)
            continue
        scores.append(
            _color_similarity(
                str(observed_series[index].get("color", "")),
                str(target.get("color", "")),
            )
        )
    cardinality = min(len(observed_series), len(expected_series)) / max(
        len(observed_series), len(expected_series), 1
    )
    return cardinality * sum(scores) / len(scores)


def _table_cells(table: dict[str, Any]) -> list[dict[str, Any]]:
    return [cell for row in table.get("rows", []) for cell in row.get("cells", [])]


def _table_structure_similarity(observed: dict[str, Any], expected: dict[str, Any]) -> float:
    if not expected:
        return float(not observed)
    dimensions = 0.5 * float(observed.get("row_count") == expected.get("row_count")) + 0.5 * float(
        observed.get("column_count") == expected.get("column_count")
    )
    first = _table_cells(observed)
    second = _table_cells(expected)
    count = max(len(first), len(second), 1)
    merges = (
        sum(
            (
                candidate.get("grid_span", 1),
                candidate.get("row_span", 1),
                candidate.get("horizontal_merge", False),
                candidate.get("vertical_merge", False),
            )
            == (
                target.get("grid_span", 1),
                target.get("row_span", 1),
                target.get("horizontal_merge", False),
                target.get("vertical_merge", False),
            )
            for candidate, target in zip(first, second, strict=False)
        )
        / count
    )
    return 0.6 * dimensions + 0.4 * merges


def _table_content_similarity(observed: dict[str, Any], expected: dict[str, Any]) -> float:
    first = {
        (r, c): cell
        for r, row in enumerate(observed.get("rows", []))
        for c, cell in enumerate(row.get("cells", []))
    }
    second = {
        (r, c): cell
        for r, row in enumerate(expected.get("rows", []))
        for c, cell in enumerate(row.get("cells", []))
    }
    if not second:
        return float(not first)
    count = len(first.keys() | second.keys()) or 1
    return (
        sum(
            _text_similarity(str(first[key].get("text", "")), str(target.get("text", "")))
            for key, target in second.items()
            if key in first
        )
        / count
    )


def _table_style_similarity(observed: dict[str, Any], expected: dict[str, Any]) -> float:
    first = _table_cells(observed)
    second = _table_cells(expected)
    if not second:
        return float(not first)
    count = max(len(first), len(second), 1)
    score = 0.0
    for candidate, target in zip(first, second, strict=False):
        fill = _color_similarity(str(candidate.get("fill", "")), str(target.get("fill", "")))
        borders = float(candidate.get("borders", []) == target.get("borders", []))
        score += 0.6 * fill + 0.4 * borders
    return score / count


def _proportion_similarity(observed: list[Any], expected: list[Any]) -> float:
    if not expected:
        return float(not observed)
    if len(observed) != len(expected):
        return 0.0
    first = [max(0.0, float(item)) for item in observed]
    second = [max(0.0, float(item)) for item in expected]
    first_total = sum(first)
    second_total = sum(second)
    if first_total <= 0 or second_total <= 0:
        return float(first == second)
    error = (
        sum(abs(a / first_total - b / second_total) for a, b in zip(first, second, strict=True)) / 2
    )
    return _clamp(1.0 - error / 0.20)


def _table_proportion_similarity(observed: dict[str, Any], expected: dict[str, Any]) -> float:
    columns = _proportion_similarity(
        list(observed.get("column_widths", [])), list(expected.get("column_widths", []))
    )
    rows = _proportion_similarity(
        [row.get("height", 0) for row in observed.get("rows", [])],
        [row.get("height", 0) for row in expected.get("rows", [])],
    )
    return 0.6 * columns + 0.4 * rows


def _connector_targets_similarity(observed: dict[str, Any], expected: dict[str, Any]) -> float:
    start = float(
        observed.get("start_semantic_key", "") == expected.get("start_semantic_key", "")
        and observed.get("start", {}).get("site") == expected.get("start", {}).get("site")
    )
    end = float(
        observed.get("end_semantic_key", "") == expected.get("end_semantic_key", "")
        and observed.get("end", {}).get("site") == expected.get("end", {}).get("site")
    )
    return 0.5 * start + 0.5 * end


def _connector_style_similarity(observed: dict[str, Any], expected: dict[str, Any]) -> float:
    return (
        0.30 * float(observed.get("head") == expected.get("head"))
        + 0.30 * float(observed.get("tail") == expected.get("tail"))
        + 0.15 * float(observed.get("preset") == expected.get("preset"))
        + 0.10 * float(observed.get("line_width") == expected.get("line_width"))
        + 0.15
        * _color_similarity(
            str(observed.get("line_color", "")), str(expected.get("line_color", ""))
        )
    )


def _component_similarity(
    component: str,
    observed: ObjectSnapshot | None,
    expected: ObjectSnapshot,
    width: float,
    height: float,
) -> float:
    if component == "existence":
        return float(observed is not None)
    if observed is None:
        return 0.0
    if component in {"rotation", "flip", "picture_crop", "shape_preset", "line_style"}:
        identity = _media_similarity(observed, expected) if expected.kind == "picture" else 1.0
        if expected.text:
            identity *= _text_similarity(observed.text, expected.text)
        return identity * visual_similarity(component, observed.visual, expected.visual)
    if component == "geometry":
        return _box_similarity(observed.bbox_points, expected.bbox_points, width, height)
    if component == "text":
        return _text_similarity(observed.text, expected.text)
    if component == "fill":
        return _color_similarity(observed.fill_color, expected.fill_color)
    if component == "media_identity":
        return _media_similarity(observed, expected)
    if component == "z_order":
        return _clamp(1.0 - abs(observed.z_order - expected.z_order) / 5)
    if component == "chart_type":
        return float(observed.chart.get("plot") == expected.chart.get("plot"))
    if component in CHART_STYLE_OPERATIONS.values():
        return chart_style_similarity(
            component, observed.chart, expected.chart
        ) * _chart_data_similarity(observed.chart, expected.chart)
    if component in TEXT_OPERATIONS.values():
        return typography_similarity(component, observed.typography, expected.typography)
    if component == "chart_data":
        return _chart_data_similarity(observed.chart, expected.chart)
    if component == "chart_elements":
        return _chart_elements_similarity(observed.chart, expected.chart)
    if component == "series_style":
        return _series_style_similarity(observed.chart, expected.chart)
    if component == "table_structure":
        return _table_structure_similarity(observed.table, expected.table)
    if component == "table_content":
        return _table_content_similarity(observed.table, expected.table)
    if component == "table_style":
        return _table_style_similarity(observed.table, expected.table)
    if component == "table_proportions":
        return _table_proportion_similarity(observed.table, expected.table)
    if component == "connector_targets":
        return _connector_targets_similarity(observed.connector, expected.connector)
    if component == "connector_style":
        return _connector_style_similarity(observed.connector, expected.connector)
    raise ValueError(f"unsupported evaluator component: {component}")


def _identity_weight(expected: ObjectSnapshot, candidate: ObjectSnapshot) -> float:
    if expected.slide != candidate.slide or expected.kind != candidate.kind:
        return 0.0
    scores = [0.0]
    if expected.shape_id == candidate.shape_id:
        scores.append(0.92)
    if expected.semantic_key == candidate.semantic_key:
        scores.append(1.0)
    if expected.media_sha256 and expected.media_sha256 == candidate.media_sha256:
        scores.append(1.0)
    elif expected.media_signature and candidate.media_signature:
        scores.append(0.95 * _media_similarity(candidate, expected))
    if expected.text and candidate.text:
        scores.append(0.9 * _text_similarity(candidate.text, expected.text))
    if expected.name and expected.name == candidate.name:
        scores.append(0.78)
    if expected.chart and candidate.chart:
        scores.append(0.9 * _chart_data_similarity(candidate.chart, expected.chart))
    if expected.table and candidate.table:
        scores.append(0.9 * _table_content_similarity(candidate.table, expected.table))
    if expected.connector and candidate.connector and expected.name == candidate.name:
        scores.append(0.88)
    return max(scores)


def _hungarian_max(weights: list[list[float]]) -> list[int | None]:
    """Maximum-weight one-to-one assignment with one dummy column per row."""
    if not weights:
        return []
    row_count = len(weights)
    real_columns = max((len(row) for row in weights), default=0)
    column_count = max(row_count, real_columns + row_count)
    padded = [row + [0.0] * (column_count - len(row)) for row in weights]
    maximum = max((value for row in padded for value in row), default=0.0)
    costs = [[maximum - value for value in row] for row in padded]
    u = [0.0] * (row_count + 1)
    v = [0.0] * (column_count + 1)
    p = [0] * (column_count + 1)
    way = [0] * (column_count + 1)
    for row_index in range(1, row_count + 1):
        p[0] = row_index
        minimum = [math.inf] * (column_count + 1)
        used = [False] * (column_count + 1)
        column = 0
        while True:
            used[column] = True
            current_row = p[column]
            delta = math.inf
            next_column = 0
            for candidate_column in range(1, column_count + 1):
                if used[candidate_column]:
                    continue
                current = (
                    costs[current_row - 1][candidate_column - 1]
                    - u[current_row]
                    - v[candidate_column]
                )
                if current < minimum[candidate_column]:
                    minimum[candidate_column] = current
                    way[candidate_column] = column
                if minimum[candidate_column] < delta:
                    delta = minimum[candidate_column]
                    next_column = candidate_column
            for candidate_column in range(column_count + 1):
                if used[candidate_column]:
                    u[p[candidate_column]] += delta
                    v[candidate_column] -= delta
                else:
                    minimum[candidate_column] -= delta
            column = next_column
            if p[column] == 0:
                break
        while True:
            previous = way[column]
            p[column] = p[previous]
            column = previous
            if column == 0:
                break
    assignment: list[int | None] = [None] * row_count
    for column in range(1, column_count + 1):
        if p[column] and column - 1 < real_columns:
            assignment[p[column] - 1] = column - 1
    return assignment


def _assign(
    expected: list[ObjectSnapshot], candidates: tuple[ObjectSnapshot, ...]
) -> tuple[list[ObjectSnapshot | None], list[float]]:
    weights = [[_identity_weight(target, item) for item in candidates] for target in expected]
    assignments = _hungarian_max(weights)
    matched: list[ObjectSnapshot | None] = []
    matched_weights: list[float] = []
    for row, column in enumerate(assignments):
        weight = weights[row][column] if column is not None else 0.0
        if column is None or weight < 0.45:
            matched.append(None)
            matched_weights.append(0.0)
        else:
            matched.append(candidates[column])
            matched_weights.append(weight)
    return matched, matched_weights


@dataclass(frozen=True)
class EvaluationResult:
    score: float
    raw_progress: float
    preservation_multiplier: float
    coverage_multiplier: float
    hard_gates: dict[str, bool]
    components: tuple[dict[str, Any], ...]
    violations: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _plan_dict(plan: Any) -> dict[str, Any]:
    if isinstance(plan, dict):
        return plan
    converter = getattr(plan, "to_dict", None)
    if callable(converter):
        return converter()
    raise TypeError("plan must be a mapping or expose to_dict()")


def _coverage_check(
    candidate: DeckSnapshot,
    expected: list[ObjectSnapshot],
    expected_matches: list[ObjectSnapshot | None],
    expected_weights: list[float],
) -> tuple[float, bool, list[dict[str, Any]]]:
    authorized_ids = {
        (item.slide, item.shape_id)
        for target, item, weight in zip(expected, expected_matches, expected_weights, strict=True)
        if item is not None
        and item.kind == "picture"
        and weight >= 0.90
        and _box_similarity(
            item.bbox_points,
            target.bbox_points,
            candidate.slide_width_points,
            candidate.slide_height_points,
        )
        >= 0.95
    }
    violations: list[dict[str, Any]] = []
    multiplier = 1.0
    hard_pass = True
    slide_area = max(1.0, candidate.slide_width_points * candidate.slide_height_points)
    for item in candidate.objects:
        if item.kind != "picture" or (item.slide, item.shape_id) in authorized_ids:
            continue
        if item.bbox_points is None:
            continue
        area = max(0.0, item.bbox_points[2]) * max(0.0, item.bbox_points[3])
        coverage = area / slide_area
        if coverage > 0.40:
            local_multiplier = _clamp(1.0 - (coverage - 0.40) / 0.40)
            multiplier = min(multiplier, local_multiplier)
            violations.append(
                {
                    "slide": item.slide,
                    "shape_id": item.shape_id,
                    "coverage": round(coverage, 6),
                }
            )
        if coverage >= 0.80:
            hard_pass = False
    return multiplier, hard_pass, violations


def _protected_similarity_base(
    observed: ObjectSnapshot | None,
    expected: ObjectSnapshot,
    width: float,
    height: float,
) -> float:
    """Compare visible semantics without treating a stable shape ID as correctness."""
    if observed is None or observed.kind != expected.kind:
        return 0.0
    geometry = _box_similarity(observed.bbox_points, expected.bbox_points, width, height)
    if expected.kind == "picture":
        content = _media_similarity(observed, expected)
        return 0.70 * content + 0.30 * geometry
    if expected.kind == "chart":
        data = _chart_data_similarity(observed.chart, expected.chart)
        chart_type = float(observed.chart.get("plot") == expected.chart.get("plot"))
        elements = _chart_elements_similarity(observed.chart, expected.chart)
        return 0.45 * data + 0.15 * chart_type + 0.15 * elements + 0.25 * geometry
    if expected.kind == "table":
        content = _table_content_similarity(observed.table, expected.table)
        structure = _table_structure_similarity(observed.table, expected.table)
        style = _table_style_similarity(observed.table, expected.table)
        return 0.40 * content + 0.25 * structure + 0.10 * style + 0.25 * geometry
    if expected.kind == "connector":
        targets = _connector_targets_similarity(observed.connector, expected.connector)
        style = _connector_style_similarity(observed.connector, expected.connector)
        return 0.40 * targets + 0.20 * style + 0.40 * geometry
    visible_components: list[float] = []
    if expected.text:
        visible_components.append(_text_similarity(observed.text, expected.text))
    if expected.fill_color:
        visible_components.append(_color_similarity(observed.fill_color, expected.fill_color))
    semantics = sum(visible_components) / len(visible_components) if visible_components else 1.0
    return 0.65 * semantics + 0.35 * geometry


def _protected_similarity(
    observed: ObjectSnapshot | None,
    expected: ObjectSnapshot,
    width: float,
    height: float,
) -> float:
    score = _protected_similarity_base(observed, expected, width, height)
    if observed is None:
        return score
    if expected.visual:
        for component in ("rotation", "flip", "shape_preset", "line_style"):
            score = min(score, visual_similarity(component, observed.visual, expected.visual))
        if expected.kind == "picture":
            score = min(score, visual_similarity("picture_crop", observed.visual, expected.visual))
    if expected.typography:
        fields = {
            "font_size": ("size",),
            "text_color": ("color",),
            "text_emphasis": ("bold", "italic", "underline"),
        }
        for component, keys in fields.items():
            if any(
                span.get(key) is not None
                for span in expected.typography.get("spans", [])
                for key in keys
            ):
                score = min(
                    score,
                    typography_similarity(component, observed.typography, expected.typography),
                )
    return score


def evaluate_snapshots(
    candidate: DeckSnapshot,
    initial: DeckSnapshot,
    plan: Any,
) -> EvaluationResult:
    payload = _plan_dict(plan)
    expected_targets: list[ObjectSnapshot] = []
    target_groups: list[list[int]] = []
    for mutation in payload["mutations"]:
        group = [len(expected_targets)]
        expected_targets.append(_object_from_dict(mutation["oracle_target"]))
        other = mutation.get("operation", {}).get("other_oracle_target")
        if isinstance(other, dict):
            group.append(len(expected_targets))
            expected_targets.append(_object_from_dict(other))
        target_groups.append(group)
    protected = [_object_from_dict(item) for item in payload.get("protected_objects", [])]
    all_expected = expected_targets + protected
    all_matches, all_weights = _assign(all_expected, candidate.objects)
    candidate_matches = all_matches[: len(expected_targets)]
    candidate_identity = all_weights[: len(expected_targets)]
    initial_matches, _ = _assign(expected_targets, initial.objects)
    component_results: list[dict[str, Any]] = []
    total_weight = 0.0
    weighted_progress = 0.0
    for index, mutation in enumerate(payload["mutations"]):
        group = target_groups[index]
        expected_group = [expected_targets[item] for item in group]
        candidate_group = [candidate_matches[item] for item in group]
        initial_group = [initial_matches[item] for item in group]
        component_scores: dict[str, float] = {}
        for name in mutation["scoring"]:
            score_group = range(len(group)) if name in {"geometry", "z_order"} else range(1)
            initial_similarity = sum(
                _component_similarity(
                    name,
                    initial_group[item],
                    expected_group[item],
                    candidate.slide_width_points,
                    candidate.slide_height_points,
                )
                for item in score_group
            ) / len(group if name in {"geometry", "z_order"} else [0])
            candidate_similarity = sum(
                _component_similarity(
                    name,
                    candidate_group[item],
                    expected_group[item],
                    candidate.slide_width_points,
                    candidate.slide_height_points,
                )
                for item in score_group
            ) / len(group if name in {"geometry", "z_order"} else [0])
            denominator = 1.0 - initial_similarity
            if denominator <= 1e-9:
                progress = float(candidate_similarity >= 1.0 - 1e-9)
            else:
                progress = _clamp((candidate_similarity - initial_similarity) / denominator)
            component_scores[name] = round(progress, 6)
        mutation_progress = sum(
            component_scores[name] * float(weight) for name, weight in mutation["scoring"].items()
        )
        # Native chart caches and the editable workbook must agree. This is an
        # episode-local constraint, activated only by a verified source contract.
        if expected_group[0].chart.get("workbook_state") == "consistent":
            candidate_chart = candidate_group[0].chart if candidate_group[0] else {}
            if candidate_chart.get("workbook_state") != "consistent":
                mutation_progress = 0.0
        mutation_weight = float(mutation["weight"])
        weighted_progress += mutation_progress * mutation_weight
        total_weight += mutation_weight
        component_results.append(
            {
                "mutation_id": mutation["mutation_id"],
                "progress": round(mutation_progress, 6),
                "identity_confidence": round(
                    sum(candidate_identity[item] for item in group) / len(group), 6
                ),
                "matched_shape_id": (candidate_group[0].shape_id if candidate_group[0] else None),
                "matched_shape_ids": [
                    item.shape_id if item is not None else None for item in candidate_group
                ],
                "scores": component_scores,
            }
        )
    raw_progress = weighted_progress / max(total_weight, 1e-9)

    protected_matches = all_matches[len(expected_targets) :]
    protected_loss = 0.0
    protected_details = []
    for expected, observed in zip(protected, protected_matches, strict=True):
        visible = _protected_similarity(
            observed,
            expected,
            candidate.slide_width_points,
            candidate.slide_height_points,
        )
        loss = max(0.0, 0.90 - visible) / 0.90
        protected_loss += 0.10 * loss
        if loss > 0:
            protected_details.append(
                {
                    "slide": expected.slide,
                    "shape_id": expected.shape_id,
                    "loss": round(loss, 6),
                }
            )
    expected_total = len(expected_targets) + len(protected)
    excess = max(0, len(candidate.objects) - expected_total)
    preservation_multiplier = _clamp(1.0 - min(0.7, protected_loss) - min(0.3, 0.04 * excess))

    coverage_multiplier, coverage_hard_pass, coverage_violations = _coverage_check(
        candidate, all_expected, all_matches, all_weights
    )
    size_width_error = abs(candidate.slide_width_points - float(payload["slide_width_points"]))
    size_height_error = abs(candidate.slide_height_points - float(payload["slide_height_points"]))
    hard_gates = {
        "slide_count": candidate.slide_count == int(payload["slide_count"]),
        "slide_order": tuple(candidate.slide_parts) == tuple(payload["slide_parts"]),
        "slide_size": size_width_error <= 0.1 and size_height_error <= 0.1,
        "unauthorized_full_page_picture": coverage_hard_pass,
    }
    score = raw_progress * preservation_multiplier * coverage_multiplier
    if not all(hard_gates.values()):
        score = 0.0
    return EvaluationResult(
        score=round(_clamp(score), 6),
        raw_progress=round(_clamp(raw_progress), 6),
        preservation_multiplier=round(preservation_multiplier, 6),
        coverage_multiplier=round(coverage_multiplier, 6),
        hard_gates=hard_gates,
        components=tuple(component_results),
        violations={
            "protected": protected_details[:20],
            "extra_objects": excess,
            "unauthorized_picture_coverage": coverage_violations,
        },
    )


def evaluate_candidate(
    candidate: str | Path,
    initial: str | Path,
    plan: Any,
) -> EvaluationResult:
    return evaluate_snapshots(object_inventory(candidate), object_inventory(initial), plan)
