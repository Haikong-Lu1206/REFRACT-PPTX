"""Extract unmodified documentation panels from a maintainer-supplied demonstration.

The source presentation and task files are deliberately not distributed.
Run from the repository root: python scripts/extract_evidence.py /path/to/demo.pptx
"""

import argparse
import hashlib
import json
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
SELECTION = {
    3: ("picture-geometry", ["0.000", "0.046", "0.475", "1.000"]),
    4: ("picture-transform", ["0.000", "0.049", "0.604", "1.000"]),
    15: ("cross-slide-state", ["0.000", "0.338", "0.662", "1.000"]),
    6: ("table-calibration", ["0.728", "0.928", "0.952", "1.000"]),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    output = Path("docs/images/evidence")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_title": "REFRACT Evaluator Demonstration",
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "evidence_kind": "historical demonstration, not a current evaluator rerun",
        "runtime_revision": "not recorded in the supplied presentation",
        "method": "Extract embedded image bytes and displayed scores; no pixel edits. "
        "Slide chrome and task identifiers are not reproduced.",
        "pages": [],
    }
    with zipfile.ZipFile(args.source) as archive:
        for page, (slug, scores) in SELECTION.items():
            slide = ET.fromstring(archive.read(f"ppt/slides/slide{page}.xml"))
            texts = [node.text or "" for node in slide.findall(".//a:t", NS)]
            actual_scores = [s for s in texts if re.fullmatch(r"[01]\.\d{3}", s)]
            if actual_scores != scores:
                raise ValueError(f"Source scores changed on page {page}: {actual_scores}")
            rels = ET.fromstring(archive.read(f"ppt/slides/_rels/slide{page}.xml.rels"))
            targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
            pictures = slide.findall(".//p:pic", NS)
            if len(pictures) != 4:
                raise ValueError(f"Expected four evidence panels on page {page}")
            panels = []
            for index, picture in enumerate(pictures):
                blip = picture.find(".//a:blip", NS)
                rid = blip.attrib[f"{{{NS['r']}}}embed"]
                member = posixpath.normpath("ppt/slides/" + targets[rid])
                if not member.startswith("ppt/media/"):
                    raise ValueError("Expected an embedded image")
                data = archive.read(member)
                filename = f"{slug}-{index + 1}{Path(member).suffix}"
                (output / filename).write_bytes(data)
                panels.append(
                    {
                        "image": filename,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "displayed_progress": scores[index],
                    }
                )
            manifest["pages"].append({"source_page": page, "title": texts[0], "panels": panels})
    (output / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Extracted {len(SELECTION) * 4} unmodified evidence panels to {output}")


if __name__ == "__main__":
    main()
