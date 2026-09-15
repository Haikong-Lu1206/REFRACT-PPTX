"""Explicit, visible text formatting without run-boundary or font-family contracts."""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from refract_pptx.presentation.visual import A, falloff
from refract_pptx.presentation.visual_mutation import number

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
TEXT_OPERATIONS = {
    "set_font_size": "font_size",
    "set_text_color": "text_color",
    "set_text_emphasis": "text_emphasis",
}
PARAGRAPH_OPERATIONS = {
    "set_paragraph_alignment": "paragraph_alignment",
    "set_paragraph_bullet": "paragraph_bullet",
    "set_paragraph_indent": "paragraph_indent",
}
TEXT_OPERATIONS.update(PARAGRAPH_OPERATIONS)


def text_snapshot(shape: ET.Element) -> dict:
    body = shape.find(f"{{{P}}}txBody")
    if body is None:
        return {}
    spans = []
    paragraphs = []
    for paragraph in body.findall(f"{{{A}}}p"):
        props = paragraph.find(f"{{{A}}}pPr")
        attributes = props.attrib if props is not None else {}
        bullet = None
        if props is not None:
            for child in props:
                tag = child.tag.rsplit("}", 1)[-1]
                if tag in {"buNone", "buChar", "buAutoNum"}:
                    bullet = {
                        "kind": tag,
                        "char": child.get("char"),
                        "type": child.get("type"),
                        "start": child.get("startAt", "1"),
                    }
        paragraphs.append(
            {
                "alignment": attributes.get("algn"),
                "bullet": bullet,
                "margin": float(attributes["marL"]) / 12700 if "marL" in attributes else None,
                "indent": float(attributes["indent"]) / 12700 if "indent" in attributes else None,
            }
        )
        defaults = paragraph.find(f"{{{A}}}pPr/{{{A}}}defRPr")
        for run in paragraph:
            text = run.find(f"{{{A}}}t")
            if text is None or not text.text:
                continue
            properties = run.find(f"{{{A}}}rPr")
            attrs = dict(defaults.attrib) if defaults is not None else {}
            if properties is not None:
                attrs.update(properties.attrib)
            color = None
            for source in (defaults, properties):
                if source is not None:
                    fill = source.find(f"{{{A}}}solidFill")
                    if fill is not None:
                        rgb = fill.find(f"{{{A}}}srgbClr")
                        color = rgb.get("val").upper() if rgb is not None else None
            spans.append(
                {
                    "text": text.text,
                    "size": float(attrs["sz"]) / 100 if "sz" in attrs else None,
                    "color": color,
                    "bold": attrs["b"] in {"1", "true"} if "b" in attrs else None,
                    "italic": attrs["i"] in {"1", "true"} if "i" in attrs else None,
                    "underline": attrs.get("u"),
                }
            )
        spans.append({"text": "\n"})
    return {"spans": spans, "paragraphs": paragraphs}


def validate_text(operation: dict, typography: dict) -> None:
    name = operation["type"]
    if name in PARAGRAPH_OPERATIONS:
        index = operation.get("paragraph_index")
        paragraphs = typography.get("paragraphs", [])
        if type(index) is not int or not 0 <= index < len(paragraphs):
            raise ValueError("Invalid paragraph_index")
        target = paragraphs[index]
        if name == "set_paragraph_alignment":
            if target["alignment"] is None or operation.get("alignment") not in {
                "l",
                "ctr",
                "r",
                "just",
            }:
                raise ValueError("Alignment requires explicit source alignment and l/ctr/r/just")
        elif name == "set_paragraph_bullet":
            if target["bullet"] is None or operation.get("mode") not in {"none", "character"}:
                raise ValueError(
                    "Bullet mutation requires explicit source bullet and none/character mode"
                )
            if operation["mode"] == "character" and (
                not isinstance(operation.get("character"), str) or len(operation["character"]) != 1
            ):
                raise ValueError("Bullet character must be a single Unicode character")
        else:
            if target["margin"] is None or target["indent"] is None:
                raise ValueError("Indent mutation requires explicit source margin and indentation")
            number(operation.get("margin_points"), 0, 200, "margin_points")
            number(operation.get("indent_points"), -200, 200, "indent_points")
        return
    field = {"set_font_size": "size", "set_text_color": "color"}.get(
        name, operation.get("attribute")
    )
    if name == "set_font_size":
        number(operation.get("points"), 4, 200, "points")
    elif name == "set_text_color":
        if not re.fullmatch(r"[0-9a-fA-F]{6}", str(operation.get("rgb", ""))):
            raise ValueError("Text color requires six hexadecimal digits")
    else:
        if field not in {"bold", "italic", "underline"}:
            raise ValueError("Emphasis attribute must be bold, italic or underline")
        if field == "underline":
            if operation.get("value") not in {"none", "sng", "dbl"}:
                raise ValueError("Underline must be none, sng or dbl")
        elif type(operation.get("value")) is not bool:
            raise ValueError("Bold/italic value must be boolean")
    spans = [s for s in typography.get("spans", []) if s["text"] != "\n"]
    if not spans or any(s.get(field) is None for s in spans):
        raise ValueError(
            f"Text {field} requires explicit run or paragraph-default evidence; "
            "inherited style is unsupported"
        )


def apply_text(shape: ET.Element, operation: dict) -> None:
    body = shape.find(f"{{{P}}}txBody")
    if body is None:
        raise ValueError("Text mutation needs a text box")
    if operation["type"] in PARAGRAPH_OPERATIONS:
        paragraph = body.findall(f"{{{A}}}p")[operation["paragraph_index"]]
        props = paragraph.find(f"{{{A}}}pPr")
        if props is None:
            raise ValueError("Missing paragraph properties")
        if operation["type"] == "set_paragraph_alignment":
            props.set("algn", operation["alignment"])
        elif operation["type"] == "set_paragraph_indent":
            props.set("marL", str(round(float(operation["margin_points"]) * 12700)))
            props.set("indent", str(round(float(operation["indent_points"]) * 12700)))
        else:
            for child in list(props):
                if child.tag.rsplit("}", 1)[-1] in {"buChar", "buAutoNum", "buNone", "buBlip"}:
                    props.remove(child)
            bullet = ET.Element(
                f"{{{A}}}buNone" if operation["mode"] == "none" else f"{{{A}}}buChar"
            )
            if operation["mode"] == "character":
                bullet.set("char", operation["character"])
            index = next(
                (
                    i
                    for i, node in enumerate(props)
                    if node.tag.rsplit("}", 1)[-1] in {"tabLst", "defRPr", "extLst"}
                ),
                len(props),
            )
            props.insert(index, bullet)
        return
    for run in body.iter():
        if run.tag not in {f"{{{A}}}r", f"{{{A}}}fld"}:
            continue
        properties = run.find(f"{{{A}}}rPr")
        if properties is None:
            properties = ET.Element(f"{{{A}}}rPr")
            run.insert(0, properties)
        name = operation["type"]
        if name == "set_font_size":
            properties.set("sz", str(round(float(operation["points"]) * 100)))
        elif name == "set_text_emphasis":
            attr = {"bold": "b", "italic": "i", "underline": "u"}[operation["attribute"]]
            value = operation["value"]
            properties.set(attr, str(value) if attr == "u" else ("1" if value else "0"))
        else:
            for child in list(properties):
                if child.tag.rsplit("}", 1)[-1] in {
                    "solidFill",
                    "noFill",
                    "gradFill",
                    "blipFill",
                    "pattFill",
                    "grpFill",
                }:
                    properties.remove(child)
            fill = ET.Element(f"{{{A}}}solidFill")
            properties.insert(1 if properties.find(f"{{{A}}}ln") is not None else 0, fill)
            ET.SubElement(fill, f"{{{A}}}srgbClr", {"val": operation["rgb"].upper()})


def typography_similarity(component: str, observed: dict, expected: dict) -> float:
    def characters(value: dict) -> list[tuple[str, dict]]:
        return [(char, span) for span in value.get("spans", []) for char in span["text"]]

    first, second = characters(observed), characters(expected)
    if not second or "".join(c for c, _ in first) != "".join(c for c, _ in second):
        return 0.0
    if component in PARAGRAPH_OPERATIONS.values():
        a_paras, b_paras = observed.get("paragraphs", []), expected.get("paragraphs", [])
        if len(a_paras) != len(b_paras):
            return 0.0
        scores = []
        for a, b in zip(a_paras, b_paras, strict=True):
            if component == "paragraph_indent":
                for key in ("margin", "indent"):
                    if b.get(key) is not None:
                        scores.append(
                            falloff(a[key] - b[key], 1.5, 18) if a.get(key) is not None else 0
                        )
            else:
                field = "bullet" if component == "paragraph_bullet" else "alignment"
                if b.get(field) is not None:
                    scores.append(float(a.get(field) == b[field]))
        return sum(scores) / len(scores) if scores else 0.0
    scores = []
    fields = {
        "font_size": ["size"],
        "text_color": ["color"],
        "text_emphasis": ["bold", "italic", "underline"],
    }[component]
    for (_, a), (_, b) in zip(first, second, strict=True):
        for field in fields:
            if b.get(field) is None:
                continue
            if a.get(field) is None:
                scores.append(0.0)
            elif field == "size":
                scores.append(
                    falloff(
                        a[field] - b[field], max(0.75, b[field] * 0.03), max(4, b[field] * 0.30)
                    )
                )
            elif field == "color":
                error = max(
                    abs(int(a[field][i : i + 2], 16) - int(b[field][i : i + 2], 16))
                    for i in (0, 2, 4)
                )
                scores.append(falloff(error, 8, 64))
            else:
                scores.append(float(a[field] == b[field]))
    return sum(scores) / len(scores) if scores else 0.0
