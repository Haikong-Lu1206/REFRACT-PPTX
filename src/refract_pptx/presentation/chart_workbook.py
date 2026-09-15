"""Read/write simple embedded chart ranges without depending on workbook serialization."""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"


def range_cells(formula: str) -> tuple[str, list[str]]:
    match = re.fullmatch(
        r"('(?:[^']|'')+'|[^!\[\]]+)!\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?", formula
    )
    if not match:
        raise ValueError("Unsupported chart workbook formula")
    sheet, col, row, last_col, last_row = match.groups()
    sheet = sheet[1:-1].replace("''", "'") if sheet.startswith("'") else sheet
    start, end = int(row), int(last_row or row)
    if (last_col or col) != col or start < 1 or end < start or end - start > 100000:
        raise ValueError("Only bounded single-column chart ranges are supported")
    return sheet, [f"{col}{i}" for i in range(start, end + 1)]


def worksheet(archive: zipfile.ZipFile, name: str) -> str:
    book = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    sheet = next(
        (node for node in book.findall(f".//{{{S}}}sheet") if node.get("name") == name), None
    )
    if sheet is None:
        raise ValueError("Missing chart worksheet")
    rid = sheet.get(f"{{{R}}}id")
    rel = next(
        (node for node in rels if node.get("Id") == rid and node.get("TargetMode") != "External"),
        None,
    )
    if rel is None:
        raise ValueError("Missing internal worksheet relationship")
    target = rel.get("Target", "")
    path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
    if not path.startswith("xl/worksheets/"):
        raise ValueError("Worksheet relationship outside workbook")
    return path


def cell_value(cell: ET.Element, strings: list[str]) -> str:
    if cell.find(f"{{{S}}}f") is not None:
        raise ValueError("Formula-backed chart cells require a calculation engine")
    kind = cell.get("t", "n")
    value = cell.findtext(f"{{{S}}}v", "")
    if kind == "s":
        return strings[int(value)]
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{{{S}}}t"))
    return value


def equal_value(first: str, second: str, numeric: bool) -> bool:
    if not numeric:
        return first == second
    try:
        a, b = Decimal(first), Decimal(second)
        return a.is_finite() and b.is_finite() and a == b
    except InvalidOperation:
        return False


def workbook_consistency(data: bytes, chart: ET.Element) -> bool:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(n.text or "" for n in item.findall(f".//{{{S}}}t")) for item in root]
        for ref in chart.iter():
            if ref.tag not in {f"{{{C}}}numRef", f"{{{C}}}strRef"}:
                continue
            formula = ref.findtext(f"{{{C}}}f", "")
            name, cells = range_cells(formula)
            sheet = ET.fromstring(archive.read(worksheet(archive, name)))
            values = {
                node.get("r"): cell_value(node, strings) for node in sheet.findall(f".//{{{S}}}c")
            }
            cache = (
                ref.find(f"{{{C}}}numCache")
                if ref.tag.endswith("numRef")
                else ref.find(f"{{{C}}}strCache")
            )
            if cache is None:
                return False
            points = cache.findall(f"{{{C}}}pt")
            if len(points) != len(cells):
                return False
            indices = [int(point.get("idx", "-1")) for point in points]
            if sorted(indices) != list(range(len(cells))):
                return False
            for point, index in zip(points, indices, strict=True):
                if not equal_value(
                    values.get(cells[index], ""),
                    point.findtext(f"{{{C}}}v", ""),
                    ref.tag.endswith("numRef"),
                ):
                    return False
    return True


def update_workbook_value(data: bytes, formula: str, index: int, value: str) -> bytes:
    name, cells = range_cells(formula)
    if not 0 <= index < len(cells):
        raise ValueError("Workbook point index out of range")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        part = worksheet(archive, name)
        root = ET.fromstring(archive.read(part))
        cell = next((n for n in root.findall(f".//{{{S}}}c") if n.get("r") == cells[index]), None)
        if cell is None or cell.find(f"{{{S}}}f") is not None:
            raise ValueError("Chart value requires an existing non-formula workbook cell")
        cell.set("t", "n")
        for node in list(cell):
            cell.remove(node)
        ET.SubElement(cell, f"{{{S}}}v").text = value
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as destination:
            for info in archive.infolist():
                destination.writestr(
                    info,
                    ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    if info.filename == part
                    else archive.read(info.filename),
                )
        return output.getvalue()
