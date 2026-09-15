"""Visible object properties, independent of IDs and XML namespace prefixes."""

from __future__ import annotations

import math
from typing import Any
from xml.etree import ElementTree as ET

A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def visual_snapshot(shape: ET.Element) -> dict[str, Any]:
    properties = shape.find("{http://schemas.openxmlformats.org/presentationml/2006/main}spPr")
    if properties is None:
        return {}
    transform = properties.find(f"{{{A}}}xfrm")
    attrs = transform.attrib if transform is not None else {}
    result: dict[str, Any] = {
        "rotation": (float(attrs.get("rot", 0)) / 60000) % 360,
        "flip_h": attrs.get("flipH", "0") in {"1", "true"},
        "flip_v": attrs.get("flipV", "0") in {"1", "true"},
    }
    preset = properties.find(f"{{{A}}}prstGeom")
    result["preset"] = preset.get("prst", "") if preset is not None else "custom"
    crop = shape.find(f".//{{{A}}}srcRect")
    result["crop"] = [
        float(crop.get(k, 0)) / 100000 if crop is not None else 0.0 for k in ("l", "t", "r", "b")
    ]
    line = properties.find(f"{{{A}}}ln")
    if line is not None:
        color = line.find(f"{{{A}}}solidFill/{{{A}}}srgbClr")
        dash = line.find(f"{{{A}}}prstDash")
        result["line"] = {
            "width": float(line.get("w", 0)) / 12700,
            "color": color.get("val", "").upper() if color is not None else "",
            "dash": dash.get("val", "solid") if dash is not None else "solid",
            "visible": line.find(f"{{{A}}}noFill") is None,
        }
    return result


def falloff(error: float, full: float, zero: float) -> float:
    if not math.isfinite(error):
        return 0.0
    return max(0.0, min(1.0, (zero - abs(error)) / (zero - full)))


def visual_similarity(component: str, observed: dict, expected: dict) -> float:
    if not observed or not expected:
        return float(observed == expected)
    if component == "rotation":
        error = abs(observed.get("rotation", 0) - expected.get("rotation", 0)) % 360
        return falloff(min(error, 360 - error), 1.0, 20.0)
    if component == "flip":
        return float(all(observed.get(k) == expected.get(k) for k in ("flip_h", "flip_v")))
    if component == "picture_crop":
        # Max side error: three correct sides cannot hide one severely cropped edge.
        return falloff(
            max(abs(a - b) for a, b in zip(observed["crop"], expected["crop"], strict=True)),
            0.005,
            0.15,
        )
    if component == "shape_preset":
        return float(observed.get("preset") == expected.get("preset"))
    if component == "line_style":
        first, second = observed.get("line", {}), expected.get("line", {})
        if not first or not second:
            return float(first == second)
        color = float(first["color"] == second["color"])
        if first["color"] and second["color"]:
            delta = max(
                abs(int(first["color"][i : i + 2], 16) - int(second["color"][i : i + 2], 16))
                for i in (0, 2, 4)
            )
            color = falloff(delta, 8, 64)
        return (
            color
            + falloff(first["width"] - second["width"], 0.25, 3)
            + float(first["dash"] == second["dash"])
            + float(first["visible"] == second["visible"])
        ) / 4
    raise ValueError(f"Unknown visual component: {component}")
