from __future__ import annotations

import copy
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from refract_pptx.design.compiler import CompiledPlan
from refract_pptx.presentation.chart_style import CHART_STYLE_OPERATIONS, apply_chart_style
from refract_pptx.presentation.chart_workbook import update_workbook_value
from refract_pptx.presentation.objects import (
    A_NS,
    C_NS,
    EMU_PER_POINT,
    P_NS,
    PKG_REL_NS,
    R_NS,
)
from refract_pptx.presentation.typography import TEXT_OPERATIONS, apply_text
from refract_pptx.presentation.visual import visual_snapshot
from refract_pptx.presentation.visual_mutation import (
    VISUAL_OPERATIONS,
    apply_visual,
    number,
    validate_visual,
)


class MutationError(ValueError):
    """Raised when a compiled mutation cannot be applied deterministically."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class PackageEditor:
    def __init__(self, path: str | Path):
        source = Path(path)
        try:
            with zipfile.ZipFile(source) as package:
                self.infos = {item.filename: copy.copy(item) for item in package.infolist()}
                self.parts = {
                    item.filename: package.read(item.filename) for item in package.infolist()
                }
        except zipfile.BadZipFile as exc:
            raise MutationError(f"invalid PPTX package: {source}") from exc
        self.xml_roots: dict[str, ET.Element] = {}

    def xml(self, part: str) -> ET.Element:
        if part not in self.parts:
            raise MutationError(f"missing package part: {part}")
        if part not in self.xml_roots:
            try:
                self.xml_roots[part] = ET.fromstring(self.parts[part])
            except ET.ParseError as exc:
                raise MutationError(f"invalid XML part {part}: {exc}") from exc
        return self.xml_roots[part]

    def relationships(self, source_part: str) -> dict[str, str]:
        directory, filename = posixpath.split(source_part)
        rels_part = posixpath.join(directory, "_rels", f"{filename}.rels")
        if rels_part not in self.parts:
            return {}
        root = self.xml(rels_part)
        result: dict[str, str] = {}
        for node in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
            relationship_id = node.attrib.get("Id", "")
            target = node.attrib.get("Target", "")
            if relationship_id and target and node.attrib.get("TargetMode") != "External":
                result[relationship_id] = posixpath.normpath(
                    posixpath.join(posixpath.dirname(source_part), target)
                )
        return result

    def remove_relationship(self, source_part: str, relationship_id: str) -> str:
        directory, filename = posixpath.split(source_part)
        rels_part = posixpath.join(directory, "_rels", f"{filename}.rels")
        if rels_part not in self.parts:
            return ""
        root = self.xml(rels_part)
        for node in list(root):
            if node.attrib.get("Id") != relationship_id:
                continue
            target = node.attrib.get("Target", "")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))
            root.remove(node)
            return resolved
        return ""

    def remove_part_if_unreferenced(self, target_part: str) -> bool:
        for rels_part in tuple(self.parts):
            if not rels_part.endswith(".rels") or "/_rels/" not in rels_part:
                continue
            directory, filename = posixpath.split(rels_part)
            source_directory = posixpath.dirname(directory)
            source_part = posixpath.join(source_directory, filename[: -len(".rels")])
            root = self.xml(rels_part)
            for node in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
                if node.attrib.get("TargetMode") == "External":
                    continue
                resolved = posixpath.normpath(
                    posixpath.join(
                        posixpath.dirname(source_part),
                        node.attrib.get("Target", ""),
                    )
                )
                if resolved == target_part:
                    return False
        self.parts.pop(target_part, None)
        self.infos.pop(target_part, None)
        self.xml_roots.pop(target_part, None)
        return True

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w") as package:
            for name, info in self.infos.items():
                payload = self.parts[name]
                if name in self.xml_roots:
                    payload = ET.tostring(
                        self.xml_roots[name], encoding="utf-8", xml_declaration=True
                    )
                package.writestr(info, payload)
        return target


def _metadata_id(shape: ET.Element) -> int | None:
    metadata = next((node for node in shape.iter() if _local(node.tag) == "cNvPr"), None)
    if metadata is None:
        return None
    try:
        return int(metadata.attrib.get("id", ""))
    except ValueError:
        return None


def _find_shape(root: ET.Element, shape_id: int) -> tuple[ET.Element, ET.Element]:
    shape_tree = root.find(f".//{{{P_NS}}}spTree")
    if shape_tree is None:
        raise MutationError("slide has no shape tree")

    def visit(parent: ET.Element) -> tuple[ET.Element, ET.Element] | None:
        for child in parent:
            if _metadata_id(child) == shape_id:
                return child, parent
            result = visit(child)
            if result is not None:
                return result
        return None

    result = visit(shape_tree)
    if result is None:
        raise MutationError(f"shape id {shape_id} was not found")
    return result


def _transform(shape: ET.Element) -> tuple[ET.Element, ET.Element, ET.Element]:
    transform = next((node for node in shape.iter() if _local(node.tag) == "xfrm"), None)
    if transform is None:
        raise MutationError("target shape has no editable transform")
    offset = next((node for node in transform if _local(node.tag) == "off"), None)
    extent = next((node for node in transform if _local(node.tag) == "ext"), None)
    if offset is None or extent is None:
        raise MutationError("target transform has no offset or extent")
    return transform, offset, extent


def _number(args: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(args.get(key, default))
    except (TypeError, ValueError) as exc:
        raise MutationError(f"operation argument {key} must be numeric") from exc
    if not (-1e9 < value < 1e9):
        raise MutationError(f"operation argument {key} is outside the safe range")
    return value


def _move(shape: ET.Element, operation: dict[str, Any]) -> None:
    _, offset, _ = _transform(shape)
    dx = _number(operation, "dx_points", 0.0) * EMU_PER_POINT
    dy = _number(operation, "dy_points", 0.0) * EMU_PER_POINT
    offset.attrib["x"] = str(round(int(offset.attrib["x"]) + dx))
    offset.attrib["y"] = str(round(int(offset.attrib["y"]) + dy))


def _resize(shape: ET.Element, operation: dict[str, Any]) -> None:
    _, _, extent = _transform(shape)
    scale_x = _number(operation, "scale_x", 1.0)
    scale_y = _number(operation, "scale_y", 1.0)
    if not (0.05 <= scale_x <= 20 and 0.05 <= scale_y <= 20):
        raise MutationError("resize scale must be between 0.05 and 20")
    extent.attrib["cx"] = str(round(int(extent.attrib["cx"]) * scale_x))
    extent.attrib["cy"] = str(round(int(extent.attrib["cy"]) * scale_y))


def _swap_geometry(first: ET.Element, second: ET.Element) -> None:
    first_transform, first_offset, first_extent = _transform(first)
    second_transform, second_offset, second_extent = _transform(second)
    first_values = (
        dict(first_offset.attrib),
        dict(first_extent.attrib),
        dict(first_transform.attrib),
    )
    second_values = (
        dict(second_offset.attrib),
        dict(second_extent.attrib),
        dict(second_transform.attrib),
    )
    first_offset.attrib.clear()
    first_offset.attrib.update(second_values[0])
    first_extent.attrib.clear()
    first_extent.attrib.update(second_values[1])
    second_offset.attrib.clear()
    second_offset.attrib.update(first_values[0])
    second_extent.attrib.clear()
    second_extent.attrib.update(first_values[1])
    for key in {"rot", "flipH", "flipV"}:
        if key in second_values[2]:
            first_transform.attrib[key] = second_values[2][key]
        else:
            first_transform.attrib.pop(key, None)
        if key in first_values[2]:
            second_transform.attrib[key] = first_values[2][key]
        else:
            second_transform.attrib.pop(key, None)


def _change_z_order(shape: ET.Element, parent: ET.Element, operation: dict[str, Any]) -> None:
    children = list(parent)
    current = children.index(shape)
    if "index" in operation:
        target = int(operation["index"])
    else:
        target = current + int(operation.get("delta", 0))
    target = max(0, min(len(children) - 1, target))
    parent.remove(shape)
    parent.insert(target, shape)


def _set_text(shape: ET.Element, operation: dict[str, Any]) -> None:
    nodes = [node for node in shape.iter() if _local(node.tag) == "t"]
    if not nodes:
        raise MutationError("target shape has no text runs")
    nodes[0].text = str(operation.get("text", ""))
    for node in nodes[1:]:
        node.text = ""


def _shape_properties(shape: ET.Element) -> ET.Element:
    properties = next((node for node in shape if _local(node.tag) in {"spPr", "grpSpPr"}), None)
    if properties is None:
        properties = ET.SubElement(shape, f"{{{P_NS}}}spPr")
    return properties


def _set_fill(shape: ET.Element, operation: dict[str, Any]) -> None:
    rgb = str(operation.get("rgb", "")).upper()
    if not re.fullmatch(r"[0-9A-F]{6}", rgb):
        raise MutationError("set_fill requires a six-digit RGB value")
    properties = _shape_properties(shape)
    fill_kinds = {"noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"}
    for child in list(properties):
        if _local(child.tag) in fill_kinds:
            properties.remove(child)
    solid = ET.Element(f"{{{A_NS}}}solidFill")
    ET.SubElement(solid, f"{{{A_NS}}}srgbClr", {"val": rgb})
    properties.insert(0, solid)


def _table(shape: ET.Element) -> ET.Element:
    table = next((node for node in shape.iter() if _local(node.tag) == "tbl"), None)
    if table is None:
        raise MutationError("target is not a native table")
    return table


def _table_cell(shape: ET.Element, operation: dict[str, Any]) -> ET.Element:
    rows = [node for node in _table(shape) if _local(node.tag) == "tr"]
    row_index = int(operation.get("row", -1))
    column_index = int(operation.get("column", -1))
    if row_index < 0 or row_index >= len(rows):
        raise MutationError(f"table row is out of range: {row_index}")
    cells = [node for node in rows[row_index] if _local(node.tag) == "tc"]
    if column_index < 0 or column_index >= len(cells):
        raise MutationError(f"table column is out of range: {column_index}")
    return cells[column_index]


def _set_table_cell_fill(shape: ET.Element, operation: dict[str, Any]) -> None:
    cell = _table_cell(shape, operation)
    properties = next((node for node in cell if _local(node.tag) == "tcPr"), None)
    if properties is None:
        properties = ET.SubElement(cell, f"{{{A_NS}}}tcPr")
    rgb = str(operation.get("rgb", "")).upper()
    if not re.fullmatch(r"[0-9A-F]{6}", rgb):
        raise MutationError("set_table_cell_fill requires a six-digit RGB value")
    for child in list(properties):
        if _local(child.tag) in {"noFill", "solidFill", "gradFill", "blipFill", "pattFill"}:
            properties.remove(child)
    solid = ET.Element(f"{{{A_NS}}}solidFill")
    ET.SubElement(solid, f"{{{A_NS}}}srgbClr", {"val": rgb})
    properties.insert(0, solid)


def _set_table_column_width(shape: ET.Element, operation: dict[str, Any]) -> None:
    grid = next((node for node in _table(shape) if _local(node.tag) == "tblGrid"), None)
    if grid is None:
        raise MutationError("native table has no column grid")
    columns = [node for node in grid if _local(node.tag) == "gridCol"]
    index = int(operation.get("column", -1))
    if index < 0 or index >= len(columns):
        raise MutationError(f"table column is out of range: {index}")
    width = _number(operation, "width_points", -1)
    if width <= 1:
        raise MutationError("table column width must be greater than one point")
    columns[index].attrib["w"] = str(round(width * EMU_PER_POINT))


def _set_table_row_height(shape: ET.Element, operation: dict[str, Any]) -> None:
    rows = [node for node in _table(shape) if _local(node.tag) == "tr"]
    index = int(operation.get("row", -1))
    if index < 0 or index >= len(rows):
        raise MutationError(f"table row is out of range: {index}")
    height = _number(operation, "height_points", -1)
    if height <= 1:
        raise MutationError("table row height must be greater than one point")
    rows[index].attrib["h"] = str(round(height * EMU_PER_POINT))


def _connector_non_visual(shape: ET.Element) -> ET.Element:
    node = next((item for item in shape.iter() if _local(item.tag) == "cNvCxnSpPr"), None)
    if node is None:
        raise MutationError("target is not a native connector")
    return node


def _reverse_connector(shape: ET.Element) -> None:
    non_visual = _connector_non_visual(shape)
    start = next((node for node in non_visual if _local(node.tag) == "stCxn"), None)
    end = next((node for node in non_visual if _local(node.tag) == "endCxn"), None)
    if start is None or end is None:
        raise MutationError("connector must have both attached endpoints to reverse")
    start_values, end_values = dict(start.attrib), dict(end.attrib)
    start.attrib.clear()
    start.attrib.update(end_values)
    end.attrib.clear()
    end.attrib.update(start_values)
    properties = next((node for node in shape if _local(node.tag) == "spPr"), None)
    property_children = properties if properties is not None else ()
    line = next((node for node in property_children if _local(node.tag) == "ln"), None)
    if line is not None:
        head = next((node for node in line if _local(node.tag) == "headEnd"), None)
        tail = next((node for node in line if _local(node.tag) == "tailEnd"), None)
        head_type = head.attrib.get("type", "none") if head is not None else "none"
        tail_type = tail.attrib.get("type", "none") if tail is not None else "none"
        if head is None:
            head = ET.SubElement(line, f"{{{A_NS}}}headEnd")
        if tail is None:
            tail = ET.SubElement(line, f"{{{A_NS}}}tailEnd")
        head.attrib["type"] = tail_type
        tail.attrib["type"] = head_type


def _detach_connector(shape: ET.Element, operation: dict[str, Any]) -> None:
    endpoint = str(operation.get("endpoint", ""))
    local_name = {"start": "stCxn", "end": "endCxn"}.get(endpoint)
    if local_name is None:
        raise MutationError("connector endpoint must be start or end")
    non_visual = _connector_non_visual(shape)
    node = next((item for item in non_visual if _local(item.tag) == local_name), None)
    if node is None:
        raise MutationError(f"connector {endpoint} endpoint is already detached")
    non_visual.remove(node)


def _set_connector_arrowhead(shape: ET.Element, operation: dict[str, Any]) -> None:
    endpoint = str(operation.get("endpoint", ""))
    local_name = {"start": "headEnd", "end": "tailEnd"}.get(endpoint)
    if local_name is None:
        raise MutationError("connector arrow endpoint must be start or end")
    arrow_type = str(operation.get("arrow_type", ""))
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*|none", arrow_type):
        raise MutationError("connector arrow_type is invalid")
    properties = next((node for node in shape if _local(node.tag) == "spPr"), None)
    if properties is None:
        raise MutationError("connector has no shape properties")
    line = next((node for node in properties if _local(node.tag) == "ln"), None)
    if line is None:
        line = ET.SubElement(properties, f"{{{A_NS}}}ln")
    arrow = next((node for node in line if _local(node.tag) == local_name), None)
    if arrow is None:
        arrow = ET.SubElement(line, f"{{{A_NS}}}{local_name}")
    arrow.attrib["type"] = arrow_type


def _chart_root(
    editor: PackageEditor, slide_part: str, shape: ET.Element
) -> tuple[str, ET.Element]:
    reference = next((node for node in shape.iter() if _local(node.tag) == "chart"), None)
    if reference is None:
        raise MutationError("target is not a native chart")
    relationship_id = reference.attrib.get(f"{{{R_NS}}}id", "")
    chart_part = editor.relationships(slide_part).get(relationship_id, "")
    if not chart_part:
        raise MutationError("chart relationship cannot be resolved")
    return chart_part, editor.xml(chart_part)


def _remove_chart_element(chart_root: ET.Element, local_name: str) -> None:
    for parent in chart_root.iter():
        for child in list(parent):
            if _local(child.tag) == local_name:
                parent.remove(child)
                return
    raise MutationError(f"chart element is already absent: {local_name}")


def _chart_series(chart_root: ET.Element, index: int) -> ET.Element:
    series = [node for node in chart_root.iter() if _local(node.tag) == "ser"]
    if index < 0 or index >= len(series):
        raise MutationError(f"chart series index is out of range: {index}")
    return series[index]


def _set_series_color(chart_root: ET.Element, operation: dict[str, Any]) -> None:
    series = _chart_series(chart_root, int(operation.get("series_index", -1)))
    rgb = str(operation.get("rgb", "")).upper()
    if not re.fullmatch(r"[0-9A-F]{6}", rgb):
        raise MutationError("set_series_color requires a six-digit RGB value")
    properties = next((node for node in series if _local(node.tag) == "spPr"), None)
    if properties is None:
        properties = ET.SubElement(series, f"{{{C_NS}}}spPr")
    solid = next((node for node in properties if _local(node.tag) == "solidFill"), None)
    if solid is None:
        solid = ET.SubElement(properties, f"{{{A_NS}}}solidFill")
    solid.clear()
    ET.SubElement(solid, f"{{{A_NS}}}srgbClr", {"val": rgb})


def _set_chart_value(
    chart_root: ET.Element, operation: dict[str, Any], editor: PackageEditor, chart_part: str
) -> None:
    series = _chart_series(chart_root, int(operation.get("series_index", -1)))
    point_index = int(operation.get("point_index", -1))
    parent = series.find(f"{{{C_NS}}}val")
    if parent is None:
        parent = series.find(f"{{{C_NS}}}yVal")
    if parent is None:
        raise MutationError("Chart series has no supported value axis")
    caches = [node for node in parent.iter() if _local(node.tag) in {"numCache", "numLit"}]
    if not caches:
        raise MutationError("chart series has no numeric cache")
    point = next(
        (
            node
            for node in caches[-1]
            if _local(node.tag) == "pt" and int(node.attrib.get("idx", -1)) == point_index
        ),
        None,
    )
    if point is None:
        raise MutationError(f"chart point index is out of range: {point_index}")
    value = next((node for node in point if _local(node.tag) == "v"), None)
    if value is None:
        raise MutationError("chart point has no value node")
    number(operation.get("value"), -1e100, 1e100, "chart value")
    new_value = str(operation["value"])
    formula = parent.findtext(f".//{{{C_NS}}}f", "")
    if formula:
        external = chart_root.find(f"{{{C_NS}}}externalData")
        if external is None:
            raise MutationError("Formula-backed chart requires an embedded workbook")
        part = editor.relationships(chart_part).get(external.get(f"{{{R_NS}}}id", ""), "")
        if not part:
            raise MutationError("Missing embedded chart workbook")
        try:
            editor.parts[part] = update_workbook_value(
                editor.parts[part], formula, point_index, new_value
            )
        except ValueError as exc:
            raise MutationError(str(exc)) from exc
    value.text = new_value


def _plan_dict(plan: CompiledPlan | dict[str, Any]) -> dict[str, Any]:
    return plan.to_dict() if isinstance(plan, CompiledPlan) else plan


def apply_mutations(
    source: str | Path,
    plan: CompiledPlan | dict[str, Any],
    output: str | Path,
) -> Path:
    payload = _plan_dict(plan)
    editor = PackageEditor(source)
    slide_parts = list(payload.get("slide_parts", []))
    for mutation in payload.get("mutations", []):
        slide = int(mutation["slide"])
        if slide < 1 or slide > len(slide_parts):
            raise MutationError(f"mutation slide is out of range: {slide}")
        slide_part = slide_parts[slide - 1]
        slide_root = editor.xml(slide_part)
        target, parent = _find_shape(slide_root, int(mutation["target_shape_id"]))
        operation = dict(mutation["operation"])
        operation_type = str(operation.get("type", ""))
        if operation_type in TEXT_OPERATIONS:
            apply_text(target, operation)
        elif operation_type in CHART_STYLE_OPERATIONS:
            chart_part, chart_root = _chart_root(editor, slide_part, target)
            apply_chart_style(chart_root, operation)
        elif operation_type in VISUAL_OPERATIONS:
            try:
                from refract_pptx.presentation.objects import _shape_kind

                validate_visual(operation, _shape_kind(target), visual_snapshot(target))
                apply_visual(target, operation)
            except ValueError as exc:
                raise MutationError(str(exc)) from exc
        elif operation_type == "move_shape":
            _move(target, operation)
        elif operation_type == "resize_shape":
            _resize(target, operation)
        elif operation_type == "swap_geometry":
            other, _ = _find_shape(slide_root, int(operation["other_shape_id"]))
            _swap_geometry(target, other)
        elif operation_type == "change_z_order":
            _change_z_order(target, parent, operation)
        elif operation_type == "remove_shape":
            media_relationship = ""
            if _local(target.tag) == "pic":
                blip = next((node for node in target.iter() if _local(node.tag) == "blip"), None)
                if blip is not None:
                    media_relationship = blip.attrib.get(f"{{{R_NS}}}embed", "")
            parent.remove(target)
            if media_relationship:
                media_part = editor.remove_relationship(slide_part, media_relationship)
                if media_part:
                    editor.remove_part_if_unreferenced(media_part)
        elif operation_type == "set_text":
            _set_text(target, operation)
        elif operation_type == "set_fill":
            _set_fill(target, operation)
        elif operation_type == "set_table_cell_text":
            _set_text(_table_cell(target, operation), operation)
        elif operation_type == "set_table_cell_fill":
            _set_table_cell_fill(target, operation)
        elif operation_type == "set_table_column_width":
            _set_table_column_width(target, operation)
        elif operation_type == "set_table_row_height":
            _set_table_row_height(target, operation)
        elif operation_type == "reverse_connector":
            _reverse_connector(target)
        elif operation_type == "detach_connector_endpoint":
            _detach_connector(target, operation)
        elif operation_type == "set_connector_arrowhead":
            _set_connector_arrowhead(target, operation)
        elif operation_type in {
            "remove_chart_legend",
            "remove_chart_title",
            "set_series_color",
            "set_chart_value",
        }:
            chart_part, chart_root = _chart_root(editor, slide_part, target)
            if operation_type == "remove_chart_legend":
                _remove_chart_element(chart_root, "legend")
            elif operation_type == "remove_chart_title":
                _remove_chart_element(chart_root, "title")
            elif operation_type == "set_series_color":
                _set_series_color(chart_root, operation)
            else:
                _set_chart_value(chart_root, operation, editor, chart_part)
        else:
            raise MutationError(f"unsupported compiled operation: {operation_type}")
    return editor.write(output)
