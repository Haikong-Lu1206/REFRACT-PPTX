"""Concrete package variants for every compiled SmartArt target."""

from __future__ import annotations

import copy
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from refract_pptx.mutation.ooxml import PackageEditor
from refract_pptx.presentation.smartart import A, D, model


def variants(source: Path, mutation: dict, directory: Path):
    contract = mutation["oracle_target"]["smartart"]
    for name in ("data_only", "cache_only", "duplicate_drawing", "recreated_ids"):
        editor = PackageEditor(source)
        data, drawing = editor.xml(contract["data_part"]), editor.xml(contract["drawing_part"])
        nodes, semantic, mapped = model(data, drawing, contract["frame_size"])
        key = nodes[0]["id"]
        if name in {"data_only", "cache_only"}:
            target = semantic[key] if name == "data_only" else mapped[key][0]
            next(target.iter(f"{{{A}}}t")).text = "Incorrect node label"
        elif name == "duplicate_drawing":
            original = mapped[key][0]
            parent = next(n for n in drawing.iter() if original in list(n))
            parent.append(copy.deepcopy(original))
        else:
            for root in (data, drawing):
                for element in root.iter():
                    for attr in (
                        "modelId",
                        "srcId",
                        "destId",
                        "presAssocID",
                        "parTransId",
                        "sibTransId",
                        "cxnId",
                    ):
                        if element.get(attr):
                            element.set(
                                attr, "{" + str(uuid5(NAMESPACE_URL, element.get(attr))) + "}"
                            )
            # Rebuilding diagram node IDs does not require retaining the frame ID.
            for point in data.findall(f"{{{D}}}ptLst/{{{D}}}pt"):
                assert point.get("modelId", "").startswith("{")
        yield (
            name,
            editor.write(directory / f"{mutation['mutation_id']}-{name}.pptx"),
            name == "recreated_ids",
        )
