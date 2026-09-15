from __future__ import annotations

import hashlib
import io
import posixpath
import re
import zipfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from PIL import Image, UnidentifiedImageError

from refract_pptx.presentation.chart_style import chart_style_snapshot
from refract_pptx.presentation.chart_workbook import workbook_consistency
from refract_pptx.presentation.typography import text_snapshot
from refract_pptx.presentation.visual import visual_snapshot

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
EMU_PER_POINT = 12700.0


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normal_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _image_signature(value: bytes) -> tuple[int, ...]:
    try:
        with Image.open(io.BytesIO(value)) as image:
            pixels = image.convert("RGB").resize((12, 12), Image.Resampling.LANCZOS)
            return tuple(pixels.tobytes())
    except (OSError, UnidentifiedImageError):
        return ()


def _parse(package: zipfile.ZipFile, part: str) -> ET.Element:
    try:
        payload = package.read(part)
    except KeyError as exc:
        raise ValueError(f"missing package part: {part}") from exc
    if len(payload) > 32 * 1024 * 1024:
        raise ValueError(f"XML part exceeds inspection limit: {part}")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError(f"invalid XML part {part}: {exc}") from exc


def _rels_part(part: str) -> str:
    directory, filename = posixpath.split(part)
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def _resolve_part(source_part: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def _relationships(package: zipfile.ZipFile, part: str) -> dict[str, dict[str, str]]:
    rels_part = _rels_part(part)
    if rels_part not in package.namelist():
        return {}
    root = _parse(package, rels_part)
    result: dict[str, dict[str, str]] = {}
    for node in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        relationship_id = node.attrib.get("Id", "")
        if not relationship_id:
            continue
        target = node.attrib.get("Target", "")
        result[relationship_id] = {
            "type": node.attrib.get("Type", ""),
            "target": _resolve_part(part, target),
            "target_mode": node.attrib.get("TargetMode", ""),
        }
    return result


def slide_parts_in_order(package: zipfile.ZipFile) -> tuple[str, ...]:
    presentation_part = "ppt/presentation.xml"
    root = _parse(package, presentation_part)
    relationships = _relationships(package, presentation_part)
    result: list[str] = []
    for node in root.findall(f".//{{{P_NS}}}sldId"):
        relationship_id = node.attrib.get(f"{{{R_NS}}}id", "")
        relationship = relationships.get(relationship_id)
        if relationship and relationship["target"] in package.namelist():
            result.append(relationship["target"])
    if result:
        return tuple(result)
    slide_pattern = re.compile(r"ppt/slides/slide(\d+)\.xml$")
    fallback = []
    for name in package.namelist():
        if match := slide_pattern.fullmatch(name):
            fallback.append((int(match.group(1)), name))
    return tuple(name for _, name in sorted(fallback))


def _shape_metadata(shape: ET.Element) -> tuple[int | None, str]:
    metadata = next((node for node in shape.iter() if _local(node.tag) == "cNvPr"), None)
    if metadata is None:
        return None, ""
    try:
        shape_id = int(metadata.attrib.get("id", ""))
    except ValueError:
        shape_id = None
    return shape_id, metadata.attrib.get("name", "")


def _shape_box(shape: ET.Element) -> tuple[float, float, float, float] | None:
    transform = next((node for node in shape.iter() if _local(node.tag) == "xfrm"), None)
    if transform is None:
        return None
    offset = next((node for node in transform if _local(node.tag) == "off"), None)
    extent = next((node for node in transform if _local(node.tag) == "ext"), None)
    if offset is None or extent is None:
        return None
    try:
        return tuple(
            round(float(value) / EMU_PER_POINT, 6)
            for value in (
                offset.attrib["x"],
                offset.attrib["y"],
                extent.attrib["cx"],
                extent.attrib["cy"],
            )
        )
    except (KeyError, ValueError):
        return None


def _shape_kind(shape: ET.Element) -> str:
    local = _local(shape.tag)
    if local == "pic":
        return "picture"
    if local == "cxnSp":
        return "connector"
    if local == "grpSp":
        return "group"
    if local == "graphicFrame":
        graphic_data = next(
            (node for node in shape.iter() if _local(node.tag) == "graphicData"), None
        )
        uri = graphic_data.attrib.get("uri", "").casefold() if graphic_data is not None else ""
        if uri.endswith("/table"):
            return "table"
        if uri.endswith("/chart"):
            return "chart"
        if "diagram" in uri:
            return "diagram"
        return "graphic_frame"
    return "shape"


def _shape_text(shape: ET.Element) -> str:
    return " ".join(node.text or "" for node in shape.iter() if _local(node.tag) == "t").strip()


def _fill_color(shape: ET.Element) -> str:
    shape_properties = next(
        (node for node in shape if _local(node.tag) in {"spPr", "grpSpPr"}), None
    )
    if shape_properties is None:
        return ""
    solid = next((node for node in shape_properties if _local(node.tag) == "solidFill"), None)
    if solid is None:
        return ""
    color = next(iter(solid), None)
    if color is None:
        return ""
    token = color.attrib.get("val", "")
    return f"{_local(color.tag)}:{token}" if token else ""


def _solid_fill_color(container: ET.Element | None) -> str:
    if container is None:
        return ""
    solid = next((node for node in container if _local(node.tag) == "solidFill"), None)
    if solid is None:
        return ""
    color = next(iter(solid), None)
    if color is None:
        return ""
    token = color.attrib.get("val", "")
    return f"{_local(color.tag)}:{token}" if token else ""


def _table_snapshot(shape: ET.Element) -> dict[str, Any]:
    table = next((node for node in shape.iter() if _local(node.tag) == "tbl"), None)
    if table is None:
        return {}
    grid = next((node for node in table if _local(node.tag) == "tblGrid"), None)
    column_widths = []
    if grid is not None:
        for column in grid:
            if _local(column.tag) != "gridCol":
                continue
            try:
                column_widths.append(round(float(column.attrib.get("w", 0)) / EMU_PER_POINT, 6))
            except ValueError:
                column_widths.append(0.0)
    rows: list[dict[str, Any]] = []
    for row in (node for node in table if _local(node.tag) == "tr"):
        try:
            height = round(float(row.attrib.get("h", 0)) / EMU_PER_POINT, 6)
        except ValueError:
            height = 0.0
        cells = []
        for cell in (node for node in row if _local(node.tag) == "tc"):
            properties = next((node for node in cell if _local(node.tag) == "tcPr"), None)
            borders = []
            if properties is not None:
                for border in properties:
                    side = _local(border.tag)
                    if side not in {"lnL", "lnR", "lnT", "lnB", "lnTlToBr", "lnBlToTr"}:
                        continue
                    color = next(
                        (
                            node
                            for node in border.iter()
                            if _local(node.tag) in {"srgbClr", "schemeClr"}
                        ),
                        None,
                    )
                    borders.append(
                        {
                            "side": side,
                            "width": border.attrib.get("w", ""),
                            "color": (
                                f"{_local(color.tag)}:{color.attrib.get('val', '')}"
                                if color is not None
                                else ""
                            ),
                        }
                    )
            cells.append(
                {
                    "text": _shape_text(cell),
                    "fill": _solid_fill_color(properties),
                    "grid_span": int(cell.attrib.get("gridSpan", "1") or 1),
                    "row_span": int(cell.attrib.get("rowSpan", "1") or 1),
                    "horizontal_merge": cell.attrib.get("hMerge", "0") in {"1", "true"},
                    "vertical_merge": cell.attrib.get("vMerge", "0") in {"1", "true"},
                    "borders": borders,
                }
            )
        rows.append({"height": height, "cells": cells})
    return {
        "rows": rows,
        "row_count": len(rows),
        "column_count": max((len(row["cells"]) for row in rows), default=len(column_widths)),
        "column_widths": column_widths,
    }


def _connector_snapshot(shape: ET.Element) -> dict[str, Any]:
    non_visual = next((node for node in shape.iter() if _local(node.tag) == "cNvCxnSpPr"), None)
    non_visual_children = non_visual if non_visual is not None else ()
    start = next((node for node in non_visual_children if _local(node.tag) == "stCxn"), None)
    end = next((node for node in non_visual_children if _local(node.tag) == "endCxn"), None)
    properties = next((node for node in shape if _local(node.tag) == "spPr"), None)
    property_children = properties if properties is not None else ()
    line = next((node for node in property_children if _local(node.tag) == "ln"), None)

    def connection(node: ET.Element | None) -> dict[str, Any]:
        if node is None:
            return {"shape_id": None, "site": None}
        try:
            shape_id = int(node.attrib.get("id", ""))
        except ValueError:
            shape_id = None
        try:
            site = int(node.attrib.get("idx", ""))
        except ValueError:
            site = None
        return {"shape_id": shape_id, "site": site}

    def arrow(local_name: str) -> str:
        line_children = line if line is not None else ()
        node = next((item for item in line_children if _local(item.tag) == local_name), None)
        return node.attrib.get("type", "none") if node is not None else "none"

    preset = next((node for node in shape.iter() if _local(node.tag) == "prstGeom"), None)
    return {
        "start": connection(start),
        "end": connection(end),
        "head": arrow("headEnd"),
        "tail": arrow("tailEnd"),
        "line_width": line.attrib.get("w", "") if line is not None else "",
        "line_color": _solid_fill_color(line),
        "preset": preset.attrib.get("prst", "") if preset is not None else "",
    }


def _picture_media(
    package: zipfile.ZipFile,
    slide_part: str,
    shape: ET.Element,
    relationships: dict[str, dict[str, str]],
) -> tuple[str, str, tuple[int, ...]]:
    blip = next((node for node in shape.iter() if _local(node.tag) == "blip"), None)
    if blip is None:
        return "", "", ()
    relationship_id = blip.attrib.get(f"{{{R_NS}}}embed", "")
    relationship = relationships.get(relationship_id)
    if not relationship or relationship.get("target_mode") == "External":
        return "", "", ()
    media_part = relationship["target"]
    if media_part not in package.namelist():
        return "", media_part, ()
    payload = package.read(media_part)
    return _sha256_bytes(payload), media_part, _image_signature(payload)


def _chart_part(shape: ET.Element, relationships: dict[str, dict[str, str]]) -> str:
    reference = next((node for node in shape.iter() if _local(node.tag) == "chart"), None)
    if reference is None:
        return ""
    relationship_id = reference.attrib.get(f"{{{R_NS}}}id", "")
    relationship = relationships.get(relationship_id)
    return relationship["target"] if relationship else ""


def _series_name(series: ET.Element) -> str:
    text = next(
        (
            node.text or ""
            for node in series.iter()
            if _local(node.tag) in {"v", "t"} and (node.text or "").strip()
        ),
        "",
    )
    return text.strip()


def _series_values(series: ET.Element) -> list[str]:
    caches = [
        node
        for node in series.iter()
        if _local(node.tag) in {"numCache", "strCache", "numLit", "strLit"}
    ]
    if not caches:
        return []
    points: list[tuple[int, str]] = []
    for point in caches[-1]:
        if _local(point.tag) != "pt":
            continue
        try:
            index = int(point.attrib.get("idx", len(points)))
        except ValueError:
            index = len(points)
        value = next((node.text or "" for node in point if _local(node.tag) == "v"), "")
        points.append((index, value))
    return [value for _, value in sorted(points)]


def _series_color(series: ET.Element) -> str:
    properties = next((node for node in series if _local(node.tag) == "spPr"), None)
    if properties is None:
        return ""
    color = next(
        (node for node in properties.iter() if _local(node.tag) in {"srgbClr", "schemeClr"}),
        None,
    )
    if color is None:
        return ""
    return f"{_local(color.tag)}:{color.attrib.get('val', '')}"


def _chart_snapshot(package: zipfile.ZipFile, chart_part: str) -> dict[str, Any]:
    if not chart_part or chart_part not in package.namelist():
        return {}
    root = _parse(package, chart_part)
    external = root.find(f"{{{C_NS}}}externalData")
    workbook_state = "absent"
    if external is not None:
        reference = _relationships(package, chart_part).get(external.get(f"{{{R_NS}}}id", ""), {})
        workbook_part = reference.get("target", "")
        try:
            workbook_state = (
                "consistent"
                if workbook_consistency(package.read(workbook_part), root)
                else "inconsistent"
            )
        except (ValueError, KeyError, IndexError, ET.ParseError, zipfile.BadZipFile):
            workbook_state = "unsupported"
    plot_area = next((node for node in root.iter() if _local(node.tag) == "plotArea"), None)
    plot = ""
    if plot_area is not None:
        plot = next(
            (_local(node.tag) for node in plot_area if _local(node.tag).endswith("Chart")),
            "",
        )
    title = next((node for node in root.iter() if _local(node.tag) == "title"), None)
    title_text = _shape_text(title) if title is not None else ""
    series = []
    for node in root.iter():
        if _local(node.tag) != "ser":
            continue
        series.append(
            {
                "name": _series_name(node),
                "values": _series_values(node),
                "categories": next(
                    (_series_values(child) for child in node if _local(child.tag) == "cat"), []
                ),
                "color": _series_color(node),
            }
        )
    return {
        "part": chart_part,
        "display": chart_style_snapshot(root),
        "workbook_state": workbook_state,
        "plot": plot,
        "title": title_text,
        "legend": any(_local(node.tag) == "legend" for node in root.iter()),
        "series": series,
    }


@dataclass(frozen=True)
class ObjectSnapshot:
    slide: int
    slide_part: str
    shape_id: int
    name: str
    kind: str
    text: str
    bbox_points: tuple[float, float, float, float] | None
    z_order: int
    fill_color: str = ""
    media_sha256: str = ""
    media_part: str = ""
    media_signature: tuple[int, ...] = ()
    chart: dict[str, Any] = field(default_factory=dict)
    table: dict[str, Any] = field(default_factory=dict)
    connector: dict[str, Any] = field(default_factory=dict)
    visual: dict[str, Any] = field(default_factory=dict)
    typography: dict[str, Any] = field(default_factory=dict)

    @property
    def semantic_key(self) -> str:
        if self.media_sha256:
            return f"{self.kind}:media:{self.media_sha256}"
        if self.text:
            digest = hashlib.sha256(_normal_text(self.text).encode()).hexdigest()
            return f"{self.kind}:text:{digest}"
        if self.chart:
            payload = repr(
                (
                    self.chart.get("plot"),
                    self.chart.get("title"),
                    [
                        (item.get("name"), item.get("values"))
                        for item in self.chart.get("series", [])
                    ],
                )
            ).encode()
            return f"chart:{hashlib.sha256(payload).hexdigest()}"
        if self.table:
            payload = repr(
                [
                    [cell.get("text") for cell in row.get("cells", [])]
                    for row in self.table.get("rows", [])
                ]
            ).encode()
            return f"table:{hashlib.sha256(payload).hexdigest()}"
        return f"{self.kind}:name:{_normal_text(self.name)}"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["semantic_key"] = self.semantic_key
        return value


@dataclass(frozen=True)
class DeckSnapshot:
    path: str
    slide_width_points: float
    slide_height_points: float
    slide_parts: tuple[str, ...]
    objects: tuple[ObjectSnapshot, ...]

    @property
    def slide_count(self) -> int:
        return len(self.slide_parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "slide_width_points": self.slide_width_points,
            "slide_height_points": self.slide_height_points,
            "slide_parts": list(self.slide_parts),
            "slide_count": self.slide_count,
            "objects": [item.to_dict() for item in self.objects],
        }


def object_snapshot_from_dict(value: dict[str, Any]) -> ObjectSnapshot:
    """Rehydrate a frozen object inventory without reading the source deck."""
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


def deck_snapshot_from_dict(value: dict[str, Any]) -> DeckSnapshot:
    """Rehydrate a deck snapshot stored in an evaluator-only asset."""
    slide_parts = tuple(str(item) for item in value.get("slide_parts", []))
    objects = tuple(object_snapshot_from_dict(item) for item in value.get("objects", []))
    snapshot = DeckSnapshot(
        path=str(value.get("path", "<frozen-inventory>")),
        slide_width_points=float(value["slide_width_points"]),
        slide_height_points=float(value["slide_height_points"]),
        slide_parts=slide_parts,
        objects=objects,
    )
    declared_count = value.get("slide_count")
    if declared_count is not None and int(declared_count) != snapshot.slide_count:
        raise ValueError("frozen inventory slide_count differs from slide_parts")
    return snapshot


def object_inventory(path: str | Path) -> DeckSnapshot:
    source = Path(path).resolve()
    try:
        with zipfile.ZipFile(source) as package:
            presentation = _parse(package, "ppt/presentation.xml")
            size = presentation.find(f".//{{{P_NS}}}sldSz")
            if size is None:
                raise ValueError("presentation has no slide size")
            width = float(size.attrib["cx"]) / EMU_PER_POINT
            height = float(size.attrib["cy"]) / EMU_PER_POINT
            slide_parts = slide_parts_in_order(package)
            objects: list[ObjectSnapshot] = []
            for slide_number, slide_part in enumerate(slide_parts, start=1):
                root = _parse(package, slide_part)
                shape_tree = root.find(f".//{{{P_NS}}}spTree")
                relationships = _relationships(package, slide_part)
                if shape_tree is None:
                    continue
                z_order = 0
                for shape in shape_tree:
                    if _local(shape.tag) not in {
                        "sp",
                        "pic",
                        "graphicFrame",
                        "grpSp",
                        "cxnSp",
                        "contentPart",
                    }:
                        continue
                    shape_id, name = _shape_metadata(shape)
                    if shape_id is None:
                        continue
                    z_order += 1
                    kind = _shape_kind(shape)
                    media_sha256 = media_part = ""
                    media_signature: tuple[int, ...] = ()
                    chart: dict[str, Any] = {}
                    table: dict[str, Any] = {}
                    connector: dict[str, Any] = {}
                    if kind == "picture":
                        media_sha256, media_part, media_signature = _picture_media(
                            package, slide_part, shape, relationships
                        )
                    elif kind == "chart":
                        chart = _chart_snapshot(package, _chart_part(shape, relationships))
                    elif kind == "table":
                        table = _table_snapshot(shape)
                    elif kind == "connector":
                        connector = _connector_snapshot(shape)
                    objects.append(
                        ObjectSnapshot(
                            slide=slide_number,
                            slide_part=slide_part,
                            shape_id=shape_id,
                            name=name,
                            kind=kind,
                            text=_shape_text(shape),
                            bbox_points=_shape_box(shape),
                            z_order=z_order,
                            fill_color=_fill_color(shape),
                            media_sha256=media_sha256,
                            media_part=media_part,
                            media_signature=media_signature,
                            chart=chart,
                            table=table,
                            connector=connector,
                            visual=visual_snapshot(shape),
                            typography=text_snapshot(shape),
                        )
                    )
            semantic_keys = {(item.slide, item.shape_id): item.semantic_key for item in objects}
            objects = [
                replace(
                    item,
                    connector={
                        **item.connector,
                        "start_semantic_key": semantic_keys.get(
                            (item.slide, item.connector.get("start", {}).get("shape_id")), ""
                        ),
                        "end_semantic_key": semantic_keys.get(
                            (item.slide, item.connector.get("end", {}).get("shape_id")), ""
                        ),
                    },
                )
                if item.connector
                else item
                for item in objects
            ]
            return DeckSnapshot(
                path=str(source),
                slide_width_points=width,
                slide_height_points=height,
                slide_parts=slide_parts,
                objects=tuple(objects),
            )
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(f"cannot inventory presentation objects: {source}") from exc
