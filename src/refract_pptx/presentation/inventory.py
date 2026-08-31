from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


class PresentationInspectionError(ValueError):
    """Raised when a presentation package cannot be inspected safely."""


_SLIDE_PART = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(frozen=True)
class SlideInventory:
    number: int
    shapes: int
    text_characters: int
    pictures: int
    groups: int
    connectors: int
    tables: int
    charts: int
    diagrams: int
    has_timing: bool
    has_transition: bool


@dataclass(frozen=True)
class PresentationInventory:
    path: str
    sha256: str
    package_bytes: int
    package_parts: int
    slide_width: int | None
    slide_height: int | None
    slides: tuple[SlideInventory, ...]
    media_files: int
    notes_slides: int
    masters: int
    layouts: int

    @property
    def slide_count(self) -> int:
        return len(self.slides)

    @property
    def total_shapes(self) -> int:
        return sum(slide.shapes for slide in self.slides)

    @property
    def native_object_types(self) -> tuple[str, ...]:
        totals = {
            "picture": sum(slide.pictures for slide in self.slides),
            "group": sum(slide.groups for slide in self.slides),
            "connector": sum(slide.connectors for slide in self.slides),
            "table": sum(slide.tables for slide in self.slides),
            "chart": sum(slide.charts for slide in self.slides),
            "diagram": sum(slide.diagrams for slide in self.slides),
            "timing": sum(slide.has_timing for slide in self.slides),
            "transition": sum(slide.has_transition for slide in self.slides),
        }
        return tuple(name for name, count in totals.items() if count)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["slide_count"] = self.slide_count
        value["total_shapes"] = self.total_shapes
        value["native_object_types"] = list(self.native_object_types)
        return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_xml(package: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        data = package.read(name)
        if len(data) > 32 * 1024 * 1024:
            raise PresentationInspectionError(f"XML part is unexpectedly large: {name}")
        return ET.fromstring(data)
    except (KeyError, ET.ParseError) as exc:
        raise PresentationInspectionError(f"cannot parse {name}: {exc}") from exc


def _relationship_targets(package: zipfile.ZipFile, slide_part: str) -> list[tuple[str, str]]:
    path = Path(slide_part)
    relationship_part = str(path.parent / "_rels" / f"{path.name}.rels").replace("\\", "/")
    if relationship_part not in package.namelist():
        return []
    root = _parse_xml(package, relationship_part)
    return [
        (node.attrib.get("Type", ""), node.attrib.get("Target", ""))
        for node in root.findall(f"{{{_R_NS}}}Relationship")
    ]


def _slide_inventory(
    package: zipfile.ZipFile, slide_part: str, slide_number: int
) -> SlideInventory:
    root = _parse_xml(package, slide_part)
    shape_tree = root.find(f".//{{{_P_NS}}}spTree")
    direct_children = list(shape_tree) if shape_tree is not None else []
    shape_tags = {"sp", "pic", "graphicFrame", "grpSp", "cxnSp", "contentPart"}
    shapes = sum(child.tag.rsplit("}", 1)[-1] in shape_tags for child in direct_children)
    pictures = len(root.findall(f".//{{{_P_NS}}}pic"))
    groups = len(root.findall(f".//{{{_P_NS}}}grpSp"))
    connectors = len(root.findall(f".//{{{_P_NS}}}cxnSp"))
    tables = len(root.findall(f".//{{{_A_NS}}}tbl"))
    text_characters = sum(len(node.text or "") for node in root.findall(f".//{{{_A_NS}}}t"))
    relationships = _relationship_targets(package, slide_part)
    charts = sum("/chart" in rel_type.lower() for rel_type, _ in relationships)
    diagrams = sum("/diagram" in rel_type.lower() for rel_type, _ in relationships)
    return SlideInventory(
        number=slide_number,
        shapes=shapes,
        text_characters=text_characters,
        pictures=pictures,
        groups=groups,
        connectors=connectors,
        tables=tables,
        charts=charts,
        diagrams=diagrams,
        has_timing=root.find(f".//{{{_P_NS}}}timing") is not None,
        has_transition=root.find(f".//{{{_P_NS}}}transition") is not None,
    )


def inspect_pptx(path: str | Path) -> PresentationInventory:
    source = Path(path).resolve()
    if not source.is_file():
        raise PresentationInspectionError(f"file does not exist: {source}")
    if source.stat().st_size > 2 * 1024 * 1024 * 1024:
        raise PresentationInspectionError("presentation exceeds the 2 GiB inspection limit")
    try:
        with zipfile.ZipFile(source) as package:
            bad_part = package.testzip()
            if bad_part:
                raise PresentationInspectionError(f"package CRC failed for {bad_part}")
            names = package.namelist()
            if "ppt/presentation.xml" not in names:
                raise PresentationInspectionError("package does not contain ppt/presentation.xml")
            slide_parts = sorted(
                (
                    (int(match.group(1)), name)
                    for name in names
                    if (match := _SLIDE_PART.match(name))
                ),
                key=lambda item: item[0],
            )
            if not slide_parts:
                raise PresentationInspectionError("package contains no slides")
            presentation = _parse_xml(package, "ppt/presentation.xml")
            slide_size = presentation.find(f".//{{{_P_NS}}}sldSz")
            width = int(slide_size.attrib["cx"]) if slide_size is not None else None
            height = int(slide_size.attrib["cy"]) if slide_size is not None else None
            slides = tuple(
                _slide_inventory(package, name, number) for number, name in slide_parts
            )
            media_files = sum(
                name.startswith("ppt/media/") and not name.endswith("/") for name in names
            )
            notes_slides = sum(
                bool(re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", name))
                for name in names
            )
            masters = sum(
                bool(re.match(r"ppt/slideMasters/slideMaster\d+\.xml$", name))
                for name in names
            )
            layouts = sum(
                bool(re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", name))
                for name in names
            )
            return PresentationInventory(
                path=str(source),
                sha256=_sha256(source),
                package_bytes=source.stat().st_size,
                package_parts=len(names),
                slide_width=width,
                slide_height=height,
                slides=slides,
                media_files=media_files,
                notes_slides=notes_slides,
                masters=masters,
                layouts=layouts,
            )
    except zipfile.BadZipFile as exc:
        raise PresentationInspectionError(f"not a valid PPTX package: {source}") from exc
