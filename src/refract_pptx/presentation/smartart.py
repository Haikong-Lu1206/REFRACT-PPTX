"""Bounded native SmartArt contracts: ordered trees with a readable drawing cache.

IDs locate nodes during mutation only. Evaluation uses ordered tree paths and
normalized drawing geometry. Unsupported models are reported, not guessed.
"""

from __future__ import annotations

import math
import re
from xml.etree import ElementTree as ET

from refract_pptx.presentation.visual import falloff

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
D = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
OPERATIONS = frozenset({"set_smartart_text", "swap_smartart_text", "set_smartart_fill"})


def local(tag):
    return tag.rsplit("}", 1)[-1]


def child(node, name):
    return next((x for x in node if local(x.tag) == name), None)


def text(node):
    # Joining runs inserts no artificial spaces; paragraph boundaries do.
    return " ".join(
        "\n".join(
            "".join(x.text or "" for x in p.iter(f"{{{A}}}t")) for p in node.iter(f"{{{A}}}p")
        ).split()
    )


def _box(node):
    props = child(node, "spPr")
    transform = props.find(f"{{{A}}}xfrm") if props is not None else None
    if transform is None:
        raise ValueError("drawing node lacks an explicit transform")
    off, ext = transform.find(f"{{{A}}}off"), transform.find(f"{{{A}}}ext")
    if off is None or ext is None:
        raise ValueError("drawing node lacks bounds")
    result = [float(off.get("x")), float(off.get("y")), float(ext.get("cx")), float(ext.get("cy"))]
    if not all(math.isfinite(x) for x in result) or min(result[2:]) <= 0:
        raise ValueError("drawing node has invalid bounds")
    return result


def _fill(node):
    props = child(node, "spPr")
    color = props.find(f"{{{A}}}solidFill/{{{A}}}srgbClr") if props is not None else None
    if color is None or not re.fullmatch(r"[0-9A-Fa-f]{6}", color.get("val", "")):
        return ""
    return color.get("val").upper()


def model(data, drawing, frame_size):
    if len(frame_size) != 2 or not all(math.isfinite(v) and v > 0 for v in frame_size):
        raise ValueError("invalid SmartArt frame size")
    points = list(data.findall(f"{{{D}}}ptLst/{{{D}}}pt"))
    ids = [p.get("modelId") for p in points]
    if not ids or None in ids or len(set(ids)) != len(ids) or len(points) > 2000:
        raise ValueError("invalid or oversized SmartArt node inventory")
    semantic = {p.get("modelId"): p for p in points if p.get("type", "node") in {"node", "doc"}}
    roots = [key for key, p in semantic.items() if p.get("type") == "doc"]
    if len(roots) != 1 or not 2 <= len(semantic) <= 200:
        raise ValueError("SmartArt requires one document root and 1..199 content nodes")
    root = roots[0]
    children = {key: [] for key in semantic}
    parents = {}
    for edge in data.findall(f"{{{D}}}cxnLst/{{{D}}}cxn"):
        if edge.get("type", "parOf") != "parOf":
            continue
        source, dest = edge.get("srcId"), edge.get("destId")
        if source not in semantic or dest not in semantic or dest in parents or dest == root:
            raise ValueError("SmartArt must be a connected, single-parent semantic tree")
        parents[dest] = source
        children[source].append((int(edge.get("srcOrd", "0")), dest))
    paths = {}

    def visit(key, path):
        if key in paths:
            raise ValueError("cyclic SmartArt")
        paths[key] = path
        ordered = sorted(children[key])
        if len({order for order, _ in ordered}) != len(ordered):
            raise ValueError("ambiguous SmartArt sibling order")
        for index, (_, dest) in enumerate(ordered):
            visit(dest, path + [index])

    visit(root, [])
    if set(paths) != set(semantic):
        raise ValueError("disconnected SmartArt")
    associations = {key: key for key in semantic}
    for point in points:
        props = point.find(f"{{{D}}}prSet")
        if props is not None and props.get("presAssocID") in semantic:
            associations[point.get("modelId")] = props.get("presAssocID")
    for edge in data.findall(f"{{{D}}}cxnLst/{{{D}}}cxn"):
        if edge.get("type") == "presOf" and edge.get("srcId") in semantic:
            key, value = edge.get("destId"), edge.get("srcId")
            if key in associations and associations[key] != value:
                raise ValueError("conflicting SmartArt presentation association")
            associations[key] = value
    tree = next((n for n in drawing.iter() if local(n.tag) == "spTree"), None)
    if tree is None or any(local(n.tag) == "grpSp" for n in tree):
        raise ValueError("missing or nested SmartArt drawing cache")
    mapped = {key: [] for key in semantic}
    for shape in tree:
        if local(shape.tag) != "sp":
            continue
        key = associations.get(shape.get("modelId"))
        if key:
            mapped[key].append(shape)
        else:
            raise ValueError("unmapped shape in SmartArt drawing cache")
    if any(local(n.tag) in {"pic", "graphicFrame", "cxnSp"} for n in tree):
        raise ValueError("unsupported additional objects in SmartArt cache")
    for n in tree.iter():
        if (
            (local(n.tag) in {"scene3d", "sp3d", "effectLst", "effectDag"} and len(n))
            or (local(n.tag) == "alpha" and n.get("val") != "100000")
            or (local(n.tag) == "cNvPr" and n.get("hidden") in {"1", "true"})
        ):
            raise ValueError("SmartArt cache uses unsupported visibility effects")
    if any(len(mapped[key]) != 1 for key in semantic if key != root):
        raise ValueError("each semantic node must map to one cached drawing shape")
    if len(mapped[root]) > 1:
        raise ValueError("ambiguous SmartArt root drawing")
    if mapped[root] and any(
        list(tree).index(mapped[root][0]) > list(tree).index(mapped[key][0])
        for key in semantic
        if key != root
    ):
        raise ValueError("SmartArt root background obscures content nodes")
    group = child(tree, "grpSpPr")
    xf = group.find(f"{{{A}}}xfrm") if group is not None else None
    if xf is not None:
        if any(xf.get(k, "0") not in {"0", "false"} for k in ("rot", "flipH", "flipV")):
            raise ValueError("rotated SmartArt cache coordinate systems are not supported")
        off, ext = xf.find(f"{{{A}}}chOff"), xf.find(f"{{{A}}}chExt")
        if off is None or ext is None:
            raise ValueError("incomplete SmartArt cache coordinate system")
        canvas = [
            float(off.get("x")),
            float(off.get("y")),
            float(ext.get("cx")),
            float(ext.get("cy")),
        ]
        parent_off, parent_ext = xf.find(f"{{{A}}}off"), xf.find(f"{{{A}}}ext")
        if parent_off is None or parent_ext is None:
            raise ValueError("incomplete SmartArt cache parent transform")
        parent_box = [
            float(parent_off.get("x")),
            float(parent_off.get("y")),
            float(parent_ext.get("cx")),
            float(parent_ext.get("cy")),
        ]
    else:
        # Without a group transform, cached shape coordinates are frame-local EMUs.
        canvas = [0.0, 0.0, *frame_size]
        parent_box = canvas
    if (
        not all(math.isfinite(x) for x in canvas + parent_box)
        or min(canvas[2:] + parent_box[2:]) <= 0
    ):
        raise ValueError("invalid SmartArt cache canvas")
    nodes = []
    for key in sorted((k for k in semantic if k != root), key=lambda k: paths[k]):
        shape = mapped[key][0]
        bounds = _box(shape)
        props = child(shape, "spPr")
        preset = props.find(f"{{{A}}}prstGeom")
        if preset is None:
            raise ValueError("SmartArt custom or inherited geometry requires a separate contract")
        transform = props.find(f"{{{A}}}xfrm")
        nodes.append(
            {
                "id": key,
                "path": paths[key],
                "text": text(semantic[key]),
                "display_text": text(shape),
                "box": [
                    (parent_box[0] + (bounds[0] - canvas[0]) * parent_box[2] / canvas[2])
                    / frame_size[0],
                    (parent_box[1] + (bounds[1] - canvas[1]) * parent_box[3] / canvas[3])
                    / frame_size[1],
                    bounds[2] * parent_box[2] / canvas[2] / frame_size[0],
                    bounds[3] * parent_box[3] / canvas[3] / frame_size[1],
                ],
                "fill": _fill(shape),
                "data_fill": _fill(semantic[key]),
                "preset": preset.get("prst") if preset is not None else "custom",
                "rotation": float(transform.get("rot", 0)) / 60000 % 360,
                "flip": [transform.get(k, "0") in {"1", "true"} for k in ("flipH", "flipV")],
            }
        )
    return nodes, semantic, mapped


def snapshot(package, slide_part, shape):
    from refract_pptx.presentation.objects import _parse, _relationships, _shape_box

    try:
        relids = next((n for n in shape.iter() if local(n.tag) == "relIds"), None)
        if relids is None:
            raise ValueError("missing SmartArt relationship IDs")
        rel = _relationships(package, slide_part).get(relids.get(f"{{{R}}}dm"), {})
        if rel.get("target_mode") == "External" or not rel.get("target"):
            raise ValueError("missing internal SmartArt data")
        data_part = rel["target"]
        links = [
            r["target"]
            for r in _relationships(package, data_part).values()
            if r["type"].endswith("/diagramDrawing") and r.get("target_mode") != "External"
        ]
        if len(links) != 1:
            raise ValueError("SmartArt requires one internal drawing cache")
        box = _shape_box(shape)
        if box is None:
            raise ValueError("SmartArt frame has no bounds")
        frame_size = [value * 12700 for value in box[2:]]
        nodes, _, _ = model(_parse(package, data_part), _parse(package, links[0]), frame_size)
        return {
            "supported": True,
            "data_part": data_part,
            "drawing_part": links[0],
            "frame_size": frame_size,
            "nodes": nodes,
        }
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        return {"supported": False, "reason": str(exc)}


def validate(operation, diagram):
    if not diagram.get("supported"):
        raise ValueError("unsupported SmartArt: " + diagram.get("reason", "no native diagram"))
    nodes = diagram["nodes"]
    if any(n["text"] != n["display_text"] or not n["text"] for n in nodes):
        raise ValueError("source SmartArt needs nonempty, consistent semantic and displayed text")
    if any(n["data_fill"] and n["data_fill"] != n["fill"] for n in nodes):
        raise ValueError("source SmartArt fill overrides disagree with the drawing cache")
    index = operation.get("node_index")
    if type(index) is not int or not 0 <= index < len(nodes):
        raise ValueError("SmartArt node_index is out of range")
    if operation["type"] == "swap_smartart_text":
        other = operation.get("other_node_index")
        if type(other) is not int or not 0 <= other < len(nodes) or other == index:
            raise ValueError("SmartArt swap requires a distinct valid node")
        if nodes[index]["text"] == nodes[other]["text"]:
            raise ValueError("SmartArt swap would not change content")
    elif operation["type"] == "set_smartart_text":
        if not isinstance(operation.get("text"), str) or len(operation["text"]) > 4000:
            raise ValueError(
                "SmartArt replacement text must be a string of at most 4000 characters"
            )
        if " ".join(operation["text"].split()) == nodes[index]["text"]:
            raise ValueError("SmartArt replacement would not change content")
        probe = ET.Element("text")
        probe.text = operation["text"]
        try:
            ET.fromstring(ET.tostring(probe))
        except ET.ParseError as exc:
            raise ValueError("SmartArt replacement contains invalid XML characters") from exc
    else:
        if not nodes[index]["fill"] or not re.fullmatch(
            r"[0-9A-Fa-f]{6}", str(operation.get("rgb", ""))
        ):
            raise ValueError("SmartArt fill needs an explicit source RGB and replacement RGB")
        if nodes[index]["fill"] == operation["rgb"].upper():
            raise ValueError("SmartArt fill would not change appearance")


def _set_text(node, value):
    runs = list(node.iter(f"{{{A}}}t"))
    if not runs:
        raise ValueError("SmartArt node has no text runs")
    runs[0].text = value
    for run in runs[1:]:
        run.text = ""


def apply(editor, target, operation, contract):
    data, drawing = editor.xml(contract["data_part"]), editor.xml(contract["drawing_part"])
    nodes, semantic, mapped = model(data, drawing, contract["frame_size"])
    validate(operation, {"supported": True, "nodes": nodes})
    index = operation["node_index"]
    node = nodes[index]
    if operation["type"] == "set_smartart_fill":
        for element in [semantic[node["id"]], mapped[node["id"]][0]]:
            props = child(element, "spPr")
            if props is None:
                props = ET.Element(f"{{{D}}}spPr")
                position = next(
                    (i for i, n in enumerate(element) if local(n.tag) == "t"), len(element)
                )
                element.insert(position, props)
            for fill in list(props):
                if local(fill.tag) in {
                    "solidFill",
                    "noFill",
                    "gradFill",
                    "blipFill",
                    "pattFill",
                    "grpFill",
                }:
                    props.remove(fill)
            fill = ET.Element(f"{{{A}}}solidFill")
            ET.SubElement(fill, f"{{{A}}}srgbClr", {"val": operation["rgb"].upper()})
            insert_at = next(
                (
                    i
                    for i, n in enumerate(props)
                    if local(n.tag) in {"ln", "effectLst", "effectDag", "scene3d", "sp3d", "extLst"}
                ),
                len(props),
            )
            props.insert(insert_at, fill)
        return
    replacements = [(node, operation.get("text", ""))]
    if operation["type"] == "swap_smartart_text":
        other = nodes[operation["other_node_index"]]
        replacements = [(node, other["text"]), (other, node["text"])]
    for node, value in replacements:
        _set_text(semantic[node["id"]], value)
        _set_text(mapped[node["id"]][0], value)
        for point in data.findall(f"{{{D}}}ptLst/{{{D}}}pt"):
            props = point.find(f"{{{D}}}prSet")
            if (
                props is not None
                and props.get("presAssocID") == node["id"]
                and list(point.iter(f"{{{A}}}t"))
            ):
                _set_text(point, value)


def similarity(observed, expected):
    if not observed.get("supported") or not expected.get("supported"):
        return 0.0
    current = {tuple(n["path"]): n for n in observed["nodes"]}
    target = {tuple(n["path"]): n for n in expected["nodes"]}
    if not target:
        return 0.0
    scores = []
    for path, wanted in target.items():
        actual = current.get(path)
        if actual is None:
            scores.append(0.0)
            continue
        # A correct hidden data model cannot stand in for the visible answer.
        content = float(actual["text"] == wanted["text"] == actual["display_text"])
        x, y, w, h = actual["box"]
        a, b, c, d = wanted["box"]
        geometry = falloff(math.hypot(x + w / 2 - a - c / 2, y + h / 2 - b - d / 2), 0.005, 0.04)
        geometry *= falloff(max(abs(w - c) / max(c, 1e-9), abs(h - d) / max(d, 1e-9)), 0.025, 0.15)
        rotation = abs(actual["rotation"] - wanted["rotation"]) % 360
        geometry *= falloff(min(rotation, 360 - rotation), 1, 20)
        geometry *= float(actual["flip"] == wanted["flip"])
        style = float(actual["preset"] == wanted["preset"])
        if actual["data_fill"] and actual["data_fill"] != actual["fill"]:
            style = 0.0
        if wanted["fill"]:
            rgb = actual["fill"]
            color = (
                0.0
                if not rgb
                else falloff(
                    max(
                        abs(int(rgb[i : i + 2], 16) - int(wanted["fill"][i : i + 2], 16))
                        for i in (0, 2, 4)
                    ),
                    8,
                    64,
                )
            )
            style *= color
        # Wrong labels cannot earn geometry/style credit for an empty shell.
        scores.append(content * geometry * style)
    cardinality = min(len(current), len(target)) / max(len(current), len(target), 1)
    return sum(scores) / len(target) * cardinality
