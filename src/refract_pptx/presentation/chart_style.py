"""Native chart display semantics, without touching data/workbook caches."""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART_STYLE_OPERATIONS = {
    "set_chart_direction": "chart_direction",
    "set_chart_grouping": "chart_grouping",
    "set_chart_legend_position": "chart_legend_position",
    "set_chart_marker": "chart_markers",
}


def chart_style_snapshot(root: ET.Element) -> dict:
    plots = root.findall(f".//{{{C}}}plotArea")
    groups = [node for area in plots for node in area if node.tag.endswith("Chart")]
    legend = root.find(f".//{{{C}}}legend")
    position = legend.find(f"{{{C}}}legendPos") if legend is not None else None
    return {
        "groups": [
            {
                "type": node.tag.rsplit("}", 1)[-1],
                "direction": _value(node, "barDir", "col"),
                "grouping": _value(
                    node, "grouping", "clustered" if node.tag == f"{{{C}}}barChart" else "standard"
                ),
                "markers": [
                    _value(series, "marker/symbol", "none")
                    for series in node.findall(f"{{{C}}}ser")
                ],
            }
            for node in groups
        ],
        "legend_position": position.get("val", "r")
        if position is not None
        else ("r" if legend is not None else "absent"),
    }


def _value(node: ET.Element, path: str, default: str) -> str:
    child = node.find("/".join(f"{{{C}}}{part}" for part in path.split("/")))
    return child.get("val", default) if child is not None else default


def validate_chart_style(operation: dict, chart: dict) -> None:
    groups = chart.get("display", {}).get("groups", [])
    if len(groups) != 1:
        raise ValueError("Display mutation currently requires one native plot group")
    kind = groups[0]["type"]
    name, value = operation["type"], operation.get("value")
    if name == "set_chart_direction":
        if kind != "barChart" or value not in {"bar", "col"}:
            raise ValueError("Direction requires a 2D bar chart and bar/col value")
    elif name == "set_chart_grouping":
        allowed = (
            {"clustered", "stacked", "percentStacked"}
            if kind == "barChart"
            else {"standard", "stacked", "percentStacked"}
        )
        if kind not in {"barChart", "lineChart", "areaChart"} or value not in allowed:
            raise ValueError("Unsupported chart grouping")
    elif name == "set_chart_legend_position":
        if not chart.get("legend") or value not in {"l", "r", "t", "b", "tr"}:
            raise ValueError("Legend position requires an existing legend and valid position")
    elif name == "set_chart_marker":
        if kind not in {"lineChart", "scatterChart"}:
            raise ValueError("Marker mutation requires line/scatter chart")
        index = operation.get("series_index")
        if type(index) is not int or not 0 <= index < len(chart.get("series", [])):
            raise ValueError("Invalid series_index")
        if (
            value
            not in {
                "circle",
                "dash",
                "diamond",
                "dot",
                "none",
                "picture",
                "plus",
                "square",
                "star",
                "triangle",
                "x",
            }
            or value == "picture"
        ):
            raise ValueError("Unsupported marker symbol")


def apply_chart_style(root: ET.Element, operation: dict) -> None:
    group = next(
        node
        for area in root.findall(f".//{{{C}}}plotArea")
        for node in area
        if node.tag.endswith("Chart")
    )
    name = operation["type"]
    if name in {"set_chart_direction", "set_chart_grouping"}:
        tag = "barDir" if name == "set_chart_direction" else "grouping"
        child = group.find(f"{{{C}}}{tag}")
        if child is None:
            child = ET.Element(f"{{{C}}}{tag}")
            group.insert(
                1 if tag == "grouping" and group.find(f"{{{C}}}barDir") is not None else 0, child
            )
    elif name == "set_chart_legend_position":
        legend = root.find(f".//{{{C}}}legend")
        if legend is None:
            raise ValueError("Missing legend")
        child = legend.find(f"{{{C}}}legendPos")
        if child is None:
            child = ET.Element(f"{{{C}}}legendPos")
            legend.insert(0, child)
    else:
        series = group.findall(f"{{{C}}}ser")[operation["series_index"]]
        marker = series.find(f"{{{C}}}marker")
        if marker is None:
            marker = ET.Element(f"{{{C}}}marker")
            index = next(
                (
                    i
                    for i, node in enumerate(series)
                    if re.sub(r"^.*}", "", node.tag)
                    in {
                        "dPt",
                        "dLbls",
                        "trendline",
                        "errBars",
                        "cat",
                        "val",
                        "xVal",
                        "yVal",
                        "smooth",
                        "extLst",
                    }
                ),
                len(series),
            )
            series.insert(index, marker)
        child = marker.find(f"{{{C}}}symbol")
        if child is None:
            child = ET.Element(f"{{{C}}}symbol")
            marker.insert(0, child)
    child.set("val", operation["value"])


def chart_style_similarity(component: str, observed: dict, expected: dict) -> float:
    first, second = observed.get("display", {}), expected.get("display", {})
    if not first or not second:
        return 0.0
    groups_a, groups_b = first["groups"], second["groups"]
    if len(groups_a) != len(groups_b) or not groups_b:
        return 0.0
    if component == "chart_legend_position":
        return float(first["legend_position"] == second["legend_position"])
    field = {
        "chart_direction": "direction",
        "chart_grouping": "grouping",
        "chart_markers": "markers",
    }[component]
    return sum(
        a["type"] == b["type"] and a[field] == b[field]
        for a, b in zip(groups_a, groups_b, strict=True)
    ) / len(groups_b)
