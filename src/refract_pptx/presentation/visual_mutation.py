"""Bounded visual edit contract shared by compilation and mutation."""

from __future__ import annotations

import math
import re
from typing import Any
from xml.etree import ElementTree as ET

from refract_pptx.presentation.visual import A

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
VISUAL_OPERATIONS = {
    "set_rotation": "rotation",
    "set_flip": "flip",
    "set_picture_crop": "picture_crop",
    "set_shape_preset": "shape_preset",
    "set_line_style": "line_style",
}
PRESETS = {
    "rect",
    "roundRect",
    "ellipse",
    "triangle",
    "rtTriangle",
    "diamond",
    "parallelogram",
    "trapezoid",
    "hexagon",
    "chevron",
    "rightArrow",
    "leftArrow",
}
DASHES = {
    "solid",
    "dot",
    "dash",
    "lgDash",
    "dashDot",
    "lgDashDot",
    "lgDashDotDot",
    "sysDash",
    "sysDot",
    "sysDashDot",
    "sysDashDotDot",
}


def number(value: Any, low: float, high: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{name} must be finite and within [{low}, {high}]")
    return result


def validate_visual(operation: dict, kind: str, visual: dict) -> None:
    name = operation["type"]
    if kind not in {"shape", "picture", "connector"} or not visual:
        raise ValueError("Visual mutation needs a top-level shape, picture or connector transform")
    if name == "set_rotation":
        number(operation.get("degrees"), -360, 360, "degrees")
    elif name == "set_flip":
        if not any(k in operation for k in ("horizontal", "vertical")):
            raise ValueError("set_flip requires horizontal or vertical")
        if any(
            type(operation[k]) is not bool for k in ("horizontal", "vertical") if k in operation
        ):
            raise ValueError("Flip values must be booleans")
    elif name == "set_picture_crop":
        if kind != "picture":
            raise ValueError("Crop requires a picture")
        values = [
            number(operation.get(k, 0), 0, 0.95, k) for k in ("left", "top", "right", "bottom")
        ]
        if values[0] + values[2] >= 0.98 or values[1] + values[3] >= 0.98:
            raise ValueError("Crop must leave visible image content")
    elif name == "set_shape_preset":
        if kind != "shape" or operation.get("preset") not in PRESETS:
            raise ValueError("Unsupported preset or non-shape target")
        if visual.get("preset") == "custom":
            raise ValueError("Custom geometry requires a separate contract")
    elif name == "set_line_style":
        if "width_points" in operation:
            number(operation["width_points"], 0, 30, "width_points")
        if "rgb" in operation and not re.fullmatch(r"[0-9A-Fa-f]{6}", str(operation["rgb"])):
            raise ValueError("Line rgb must be six hexadecimal digits")
        if "dash" in operation and operation["dash"] not in DASHES:
            raise ValueError("Unsupported line dash")
        if not {"width_points", "rgb", "dash"} & operation.keys():
            raise ValueError("Line style requires width_points, rgb or dash")
        if not visual.get("line") or not visual["line"].get("color"):
            raise ValueError("Line mutation currently requires an explicit RGB source line")


def apply_visual(shape: ET.Element, operation: dict) -> None:
    properties = shape.find(f"{{{P}}}spPr")
    if properties is None:
        raise ValueError("Missing shape properties")
    name = operation["type"]
    if name in {"set_rotation", "set_flip"}:
        transform = properties.find(f"{{{A}}}xfrm")
        if transform is None:
            raise ValueError("Missing transform")
        if name == "set_rotation":
            transform.set("rot", str(round(float(operation["degrees"]) * 60000)))
        else:
            for key, attr in (("horizontal", "flipH"), ("vertical", "flipV")):
                if key in operation:
                    transform.set(attr, "1" if operation[key] else "0")
    elif name == "set_picture_crop":
        fill = shape.find(f"{{{P}}}blipFill")
        if fill is None:
            raise ValueError("Missing picture fill")
        crop = fill.find(f"{{{A}}}srcRect")
        if crop is None:
            crop = ET.Element(f"{{{A}}}srcRect")
            fill.insert(1, crop)
        for key, attr in zip(("left", "top", "right", "bottom"), ("l", "t", "r", "b"), strict=True):
            crop.set(attr, str(round(float(operation.get(key, 0)) * 100000)))
    elif name == "set_shape_preset":
        preset = properties.find(f"{{{A}}}prstGeom")
        if preset is None:
            raise ValueError("Missing preset geometry")
        preset.clear()
        preset.set("prst", operation["preset"])
        ET.SubElement(preset, f"{{{A}}}avLst")
    elif name == "set_line_style":
        line = properties.find(f"{{{A}}}ln")
        if line is None:
            raise ValueError("Missing line properties")
        if "width_points" in operation:
            line.set("w", str(round(float(operation["width_points"]) * 12700)))
        if "rgb" in operation:
            color = line.find(f"{{{A}}}solidFill/{{{A}}}srgbClr")
            if color is None:
                raise ValueError("Missing explicit line color")
            color.set("val", operation["rgb"].upper())
        if "dash" in operation:
            dash = line.find(f"{{{A}}}prstDash")
            if dash is None:
                dash = ET.Element(f"{{{A}}}prstDash")
                # Dash follows fill and precedes join/arrow properties.
                index = next(
                    (
                        i
                        for i, child in enumerate(line)
                        if child.tag.rsplit("}", 1)[-1]
                        in {"round", "bevel", "miter", "headEnd", "tailEnd", "extLst"}
                    ),
                    len(line),
                )
                line.insert(index, dash)
            dash.set("val", operation["dash"])
