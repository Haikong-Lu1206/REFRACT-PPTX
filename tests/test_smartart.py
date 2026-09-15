from __future__ import annotations

import copy
import json
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

import pytest
from test_extended_contracts import proposal

from refract_pptx.design.compiler import compile_proposal
from refract_pptx.design.proposal import ProposalError
from refract_pptx.evaluation import evaluate_candidate
from refract_pptx.mutation import apply_mutations
from refract_pptx.mutation.ooxml import PackageEditor
from refract_pptx.presentation import object_inventory
from refract_pptx.presentation.smartart import A, D, similarity
from refract_pptx.validation.redteam import run_redteam

DSP = "http://schemas.microsoft.com/office/drawing/2008/diagram"
DATA = "ppt/diagrams/data1.xml"
DRAWING = "ppt/diagrams/drawing1.xml"


def body(parent, namespace, label):
    node = ET.SubElement(
        parent, f"{{{namespace}}}t" if namespace == D else f"{{{namespace}}}txBody"
    )
    ET.SubElement(node, f"{{{A}}}bodyPr")
    ET.SubElement(node, f"{{{A}}}lstStyle")
    run = ET.SubElement(ET.SubElement(node, f"{{{A}}}p"), f"{{{A}}}r")
    ET.SubElement(run, f"{{{A}}}t").text = label


@pytest.fixture
def smartart_deck(synthetic_pptx, workspace_tmp):
    editor = PackageEditor(synthetic_pptx)
    # An original, small editable model; no production tasks or third-party slides.
    data = ET.Element(f"{{{D}}}dataModel")
    points = ET.SubElement(data, f"{{{D}}}ptLst")
    ET.SubElement(points, f"{{{D}}}pt", {"modelId": "root", "type": "doc"})
    edges = ET.SubElement(data, f"{{{D}}}cxnLst")
    drawing = ET.Element(f"{{{DSP}}}drawing")
    tree = ET.SubElement(drawing, f"{{{DSP}}}spTree")
    transform = ET.SubElement(ET.SubElement(tree, f"{{{DSP}}}grpSpPr"), f"{{{A}}}xfrm")
    for name, attrs in [
        ("off", {"x": "0", "y": "0"}),
        ("ext", {"cx": "3000000", "cy": "1000000"}),
        ("chOff", {"x": "0", "y": "0"}),
        ("chExt", {"cx": "3000000", "cy": "1000000"}),
    ]:
        ET.SubElement(transform, f"{{{A}}}{name}", attrs)
    for i, label in enumerate(["Collect 1.0", "Translate", "Store"]):
        node = ET.SubElement(points, f"{{{D}}}pt", {"modelId": f"node{i}"})
        ET.SubElement(node, f"{{{D}}}spPr")
        body(node, D, label)
        pres = ET.SubElement(points, f"{{{D}}}pt", {"modelId": f"pres{i}", "type": "pres"})
        ET.SubElement(pres, f"{{{D}}}prSet", {"presAssocID": f"node{i}"})
        ET.SubElement(
            edges,
            f"{{{D}}}cxn",
            {"modelId": f"edge{i}", "srcId": "root", "destId": f"node{i}", "srcOrd": str(i)},
        )
        shape = ET.SubElement(tree, f"{{{DSP}}}sp", {"modelId": f"pres{i}"})
        props = ET.SubElement(shape, f"{{{DSP}}}spPr")
        xf = ET.SubElement(props, f"{{{A}}}xfrm")
        ET.SubElement(xf, f"{{{A}}}off", {"x": str(i * 1000000), "y": "100000"})
        ET.SubElement(xf, f"{{{A}}}ext", {"cx": "800000", "cy": "500000"})
        ET.SubElement(props, f"{{{A}}}prstGeom", {"prst": "roundRect"})
        ET.SubElement(
            ET.SubElement(props, f"{{{A}}}solidFill"), f"{{{A}}}srgbClr", {"val": "4472C4"}
        )
        body(shape, DSP, label)
    editor.parts[DATA] = ET.tostring(data)
    editor.parts[DRAWING] = ET.tostring(drawing)
    rels = ET.Element("{http://schemas.openxmlformats.org/package/2006/relationships}Relationships")
    ET.SubElement(
        rels,
        "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
        {
            "Id": "drawing",
            "Type": "http://schemas.microsoft.com/office/2007/relationships/diagramDrawing",
            "Target": "drawing1.xml",
        },
    )
    editor.parts["ppt/diagrams/_rels/data1.xml.rels"] = ET.tostring(rels)
    for part in (DRAWING, "ppt/diagrams/_rels/data1.xml.rels"):
        editor.infos[part] = zipfile.ZipInfo(part)
    return editor.write(workspace_tmp / "smartart.pptx")


def build(source, directory, operation=None):
    op = operation or {"type": "swap_smartart_text", "node_index": 0, "other_node_index": 1}
    plan = compile_proposal(
        proposal(op, "smartart_structure", 7, capability="smartart_semantic_repair"),
        object_inventory(source),
    )
    initial = apply_mutations(source, plan, directory / "initial.pptx")
    return plan, initial


@pytest.mark.parametrize(
    "operation",
    [
        {"type": "swap_smartart_text", "node_index": 0, "other_node_index": 1},
        {"type": "set_smartart_text", "node_index": 0, "text": ""},
        {"type": "set_smartart_fill", "node_index": 0, "rgb": "CC8833"},
    ],
)
def test_end_to_end(smartart_deck, workspace_tmp, operation):
    plan, init = build(smartart_deck, workspace_tmp, operation)
    assert evaluate_candidate(init, init, plan).score == 0
    assert evaluate_candidate(smartart_deck, init, plan).score == 1
    assert run_redteam(smartart_deck, init, plan.to_dict(), work_directory=workspace_tmp)["valid"]


@pytest.mark.parametrize("repaired_part", [DATA, DRAWING])
def test_fixing_only_one_representation_does_not_earn_credit(
    smartart_deck, workspace_tmp, repaired_part
):
    plan, init = build(smartart_deck, workspace_tmp)
    editor = PackageEditor(init)
    source = PackageEditor(smartart_deck)
    editor.parts[repaired_part] = source.parts[repaired_part]
    candidate = editor.write(workspace_tmp / "cache-only.pptx")
    assert evaluate_candidate(candidate, init, plan).score == 0


def test_rebuilt_ids_run_splits_and_coordinate_units(smartart_deck, workspace_tmp):
    plan, init = build(smartart_deck, workspace_tmp)
    editor = PackageEditor(smartart_deck)
    for part in (DATA, DRAWING):
        root = editor.xml(part)
        for node in root.iter():
            for key in ("modelId", "srcId", "destId", "presAssocID"):
                if node.get(key):
                    node.set(key, "new-" + node.get(key))
        for p in root.iter(f"{{{A}}}p"):
            run = p.find(f"{{{A}}}r")
            t = run.find(f"{{{A}}}t")
            value = t.text
            t.text = value[:2]
            ET.SubElement(ET.SubElement(p, f"{{{A}}}r"), f"{{{A}}}t").text = value[2:]
    for node in editor.xml(DRAWING).iter():
        parent_transform = editor.xml(DRAWING).find(f"{{{DSP}}}spTree/{{{DSP}}}grpSpPr/{{{A}}}xfrm")
        if node in list(parent_transform) and node.tag in {f"{{{A}}}off", f"{{{A}}}ext"}:
            continue
        if node.tag in {f"{{{A}}}{name}" for name in ("off", "ext", "chOff", "chExt")}:
            for key, value in list(node.attrib.items()):
                node.set(key, str(int(value) * 2))
    slide = editor.xml("ppt/slides/slide1.xml")
    for n in slide.iter():
        if n.tag.endswith("}cNvPr") and n.get("id") == "7":
            n.set("id", "777")
            n.set("name", "Recreated diagram")
    assert evaluate_candidate(editor.write(workspace_tmp / "rebuilt.pptx"), init, plan).score == 1


def test_honest_partial_repair_has_gradient(smartart_deck, workspace_tmp):
    plan, init = build(smartart_deck, workspace_tmp)
    editor = PackageEditor(init)
    for part in (DATA, DRAWING):
        root = editor.xml(part)
        first = next(root.iter(f"{{{A}}}t"))
        first.text = "Collect 1.0"
    result = evaluate_candidate(editor.write(workspace_tmp / "partial.pptx"), init, plan)
    assert 0.45 < result.score < 0.55


@pytest.mark.parametrize(
    "attack", ["extra_node", "wrong_parent", "missing_cache", "cover", "flatten"]
)
def test_structural_attacks_do_not_pass(smartart_deck, workspace_tmp, attack):
    plan, init = build(smartart_deck, workspace_tmp)
    editor = PackageEditor(smartart_deck)
    if attack == "extra_node":
        points = editor.xml(DATA).find(f"{{{D}}}ptLst")
        ET.SubElement(points, f"{{{D}}}pt", {"modelId": "extra"})
    elif attack == "wrong_parent":
        edges = editor.xml(DATA).find(f"{{{D}}}cxnLst")
        edges[-1].set("srcId", "node0")
    elif attack == "missing_cache":
        editor.parts.pop(DRAWING)
        editor.infos.pop(DRAWING)
    elif attack == "cover":
        tree = editor.xml(DRAWING).find(f"{{{DSP}}}spTree")
        cover = copy.deepcopy(tree[-1])
        cover.set("modelId", "cover")
        for t in cover.iter(f"{{{A}}}t"):
            t.text = ""
        tree.append(cover)
    else:
        root = editor.xml("ppt/slides/slide1.xml")
        for data in root.iter(f"{{{A}}}graphicData"):
            if "diagram" in data.get("uri", ""):
                data.clear()
    assert evaluate_candidate(editor.write(workspace_tmp / "attack.pptx"), init, plan).score < 1


def test_unsupported_source_rejected(synthetic_pptx):
    with pytest.raises(ProposalError, match="unsupported SmartArt"):
        compile_proposal(
            proposal(
                {"type": "set_smartart_text", "node_index": 0, "text": "x"},
                "smartart_structure",
                7,
                capability="smartart_semantic_repair",
            ),
            object_inventory(synthetic_pptx),
        )


def test_numerical_format_and_style_are_not_ignored(smartart_deck):
    expected = object_inventory(smartart_deck).objects[5].smartart
    assert expected["supported"]
    for field, value in [
        ("text", "Collect 1"),
        ("fill", "FF00FF"),
        ("preset", "ellipse"),
        ("rotation", 90),
    ]:
        observed = copy.deepcopy(expected)
        observed["nodes"][0][field] = value
        assert similarity(observed, expected) < 1


def test_packaged_runtime_scores_native_diagram(smartart_deck, workspace_tmp):
    from refract_pptx.adapters.desktop import _runtime_archive

    plan, init = build(smartart_deck, workspace_tmp)
    archive = workspace_tmp / "runtime.zip"
    _runtime_archive(archive)
    plan_path = workspace_tmp / "plan.json"
    plan_path.write_text(json.dumps(plan.to_dict()), encoding="utf-8")
    script = (
        "import sys,json;sys.path.insert(0,sys.argv[1]);"
        "from _refract_runtime.evaluation import evaluate_candidate;"
        "plan=json.load(open(sys.argv[2],encoding='utf-8'));"
        "print(json.dumps([evaluate_candidate(sys.argv[3],sys.argv[3],plan).score,"
        "evaluate_candidate(sys.argv[4],sys.argv[3],plan).score]))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(archive.resolve()),
            str(plan_path.resolve()),
            str(init.resolve()),
            str(smartart_deck.resolve()),
        ],
        cwd=workspace_tmp,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == [0, 1]


@pytest.mark.parametrize(
    "operation",
    [
        {"type": "set_smartart_text", "node_index": -1, "text": "wrong"},
        {"type": "set_smartart_text", "node_index": 0, "text": "\u0000"},
        {"type": "set_smartart_fill", "node_index": 0, "rgb": "pink"},
        {"type": "swap_smartart_text", "node_index": 0, "other_node_index": 0},
    ],
)
def test_invalid_operations_rejected_before_write(smartart_deck, workspace_tmp, operation):
    with pytest.raises(ProposalError):
        build(smartart_deck, workspace_tmp, operation)


def test_shared_diagram_parts_rejected(smartart_deck, workspace_tmp):
    editor = PackageEditor(smartart_deck)
    root = editor.xml("ppt/slides/slide1.xml")
    tree = root.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}spTree")
    diagram = copy.deepcopy(tree[-1])
    for node in diagram.iter():
        if node.tag.endswith("}cNvPr"):
            node.set("id", "99")
    tree.append(diagram)
    source = editor.write(workspace_tmp / "shared.pptx")
    with pytest.raises(ProposalError, match="shared SmartArt"):
        build(source, workspace_tmp)


def test_cache_parent_shift_cannot_hide_behind_correct_frame(smartart_deck, workspace_tmp):
    plan, init = build(smartart_deck, workspace_tmp)
    editor = PackageEditor(smartart_deck)
    offset = editor.xml(DRAWING).find(f"{{{DSP}}}spTree/{{{DSP}}}grpSpPr/{{{A}}}xfrm/{{{A}}}off")
    offset.set("x", "1000000")
    candidate = editor.write(workspace_tmp / "shifted-cache.pptx")
    assert evaluate_candidate(candidate, init, plan).score == 0


def test_implicit_identity_cache_transform(smartart_deck, workspace_tmp):
    plan, init = build(smartart_deck, workspace_tmp)
    editor = PackageEditor(smartart_deck)
    props = editor.xml(DRAWING).find(f"{{{DSP}}}spTree/{{{DSP}}}grpSpPr")
    props.clear()
    candidate = editor.write(workspace_tmp / "identity-cache.pptx")
    assert evaluate_candidate(candidate, init, plan).score == 1
