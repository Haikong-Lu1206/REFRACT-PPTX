import io
import zipfile
from copy import deepcopy
from xml.etree import ElementTree as ET

from PIL import Image

from refract_pptx.build import build_task
from refract_pptx.design import AgentProposal, compile_proposal
from refract_pptx.evaluation import evaluate_candidate
from refract_pptx.mutation import apply_mutations
from refract_pptx.mutation.ooxml import PackageEditor
from refract_pptx.presentation import object_inventory
from refract_pptx.presentation.objects import A_NS, P_NS
from refract_pptx.validation import validate_bundle


def _proposal() -> AgentProposal:
    return AgentProposal.from_dict(
        {
            "proposal_version": "1.0",
            "title": "Restore the project overview alignment",
            "instruction": (
                "Restore the damaged editable elements so the presentation matches its "
                "visible reference while preserving all unrelated content."
            ),
            "deck_summary": (
                "A compact project update with an aligned title, status, image, table, and chart."
            ),
            "mutations": [
                {
                    "mutation_id": "move-title",
                    "family": "spatial_structure_repair",
                    "capability": "object_alignment",
                    "slide": 1,
                    "target": {"shape_id": 2, "kind": "shape"},
                    "operation": {"type": "move_shape", "dx_points": 80, "dy_points": 0},
                    "evidence_tier": "reference_visible",
                    "evidence": [
                        {
                            "source": "reference",
                            "locator": "slide 1 title",
                            "supports": "the title alignment and target position",
                        }
                    ],
                    "rationale": (
                        "The shifted title disrupts a visible alignment shared by the slide layout."
                    ),
                    "accepted_solutions": [
                        "Move the existing title or recreate an equivalent editable title."
                    ],
                    "scoring": {"geometry": 1.0},
                    "weight": 1.0,
                }
            ],
            "preservation_contracts": ["Preserve every unrelated visible object and slide."],
        }
    ).require_valid()


def _picture_proposal() -> AgentProposal:
    return AgentProposal.from_dict(
        {
            "proposal_version": "1.0",
            "title": "Restore the missing project image",
            "instruction": (
                "Restore the missing editable project image from the supplied materials and "
                "match the visible reference while preserving all unrelated content."
            ),
            "deck_summary": (
                "A project update with one supplied image beside native text, table, and chart."
            ),
            "mutations": [
                {
                    "mutation_id": "remove-project-image",
                    "family": "reference_reconstruction",
                    "capability": "picture_restoration",
                    "slide": 1,
                    "target": {"shape_id": 4, "kind": "picture"},
                    "operation": {"type": "remove_shape"},
                    "evidence_tier": "material_grounded",
                    "evidence": [
                        {
                            "source": "materials",
                            "locator": "supplied image asset",
                            "supports": "the image identity and visible content",
                        },
                        {
                            "source": "reference",
                            "locator": "slide 1 image region",
                            "supports": "the target position and size",
                        },
                    ],
                    "rationale": (
                        "Restoring the missing image requires material matching and spatial "
                        "reconstruction."
                    ),
                    "accepted_solutions": [
                        "Insert the supplied image with equivalent visible geometry."
                    ],
                    "scoring": {
                        "existence": 0.2,
                        "media_identity": 0.5,
                        "geometry": 0.3,
                    },
                    "weight": 1.0,
                }
            ],
            "preservation_contracts": ["Preserve all unrelated content and native objects."],
        }
    ).require_valid()


def _chart_proposal(
    mutation_id: str,
    capability: str,
    operation: dict,
    scoring: dict,
) -> AgentProposal:
    return AgentProposal.from_dict(
        {
            "proposal_version": "1.0",
            "title": "Restore one native chart property",
            "instruction": (
                "Restore the damaged native chart property from visible evidence while "
                "preserving the chart's editability and all unrelated content."
            ),
            "deck_summary": "A project update containing one editable native chart.",
            "mutations": [
                {
                    "mutation_id": mutation_id,
                    "family": "native_chart_repair",
                    "capability": capability,
                    "slide": 1,
                    "target": {"shape_id": 6, "kind": "chart"},
                    "operation": operation,
                    "evidence_tier": "reference_visible",
                    "evidence": [
                        {
                            "source": "reference",
                            "locator": "slide 1 native chart",
                            "supports": "the target chart property",
                        }
                    ],
                    "rationale": (
                        "Changing this native property creates a visible and recoverable "
                        "chart error."
                    ),
                    "accepted_solutions": ["Restore the equivalent native chart property."],
                    "scoring": scoring,
                    "weight": 1.0,
                }
            ],
            "preservation_contracts": ["Preserve all unrelated presentation content."],
        }
    ).require_valid()


def _repair_plan(plan: dict, operation: dict) -> dict:
    result = deepcopy(plan)
    result["mutations"][0]["operation"] = operation
    return result


def _with_native_table_and_attached_connector(source, output):
    editor = PackageEditor(source)
    slide1 = editor.xml("ppt/slides/slide1.xml")
    table = next(node for node in slide1.iter() if node.tag.endswith("}tbl"))
    grid = ET.SubElement(table, f"{{{A_NS}}}tblGrid")
    ET.SubElement(grid, f"{{{A_NS}}}gridCol", {"w": "1905000"})
    ET.SubElement(grid, f"{{{A_NS}}}gridCol", {"w": "2540000"})
    row = ET.SubElement(table, f"{{{A_NS}}}tr", {"h": "635000"})
    for text in ("Metric", "Q2"):
        cell = ET.SubElement(row, f"{{{A_NS}}}tc")
        body = ET.SubElement(cell, f"{{{A_NS}}}txBody")
        ET.SubElement(body, f"{{{A_NS}}}bodyPr")
        ET.SubElement(body, f"{{{A_NS}}}lstStyle")
        paragraph = ET.SubElement(body, f"{{{A_NS}}}p")
        run = ET.SubElement(paragraph, f"{{{A_NS}}}r")
        ET.SubElement(run, f"{{{A_NS}}}t").text = text
        properties = ET.SubElement(cell, f"{{{A_NS}}}tcPr")
        solid = ET.SubElement(properties, f"{{{A_NS}}}solidFill")
        ET.SubElement(solid, f"{{{A_NS}}}srgbClr", {"val": "D9EAF7"})

    slide2 = editor.xml("ppt/slides/slide2.xml")
    connector_properties = next(
        node for node in slide2.iter() if node.tag.endswith("}cNvCxnSpPr")
    )
    ET.SubElement(connector_properties, f"{{{A_NS}}}stCxn", {"id": "2", "idx": "1"})
    ET.SubElement(connector_properties, f"{{{A_NS}}}endCxn", {"id": "3", "idx": "0"})
    connector_shape = next(node for node in slide2.iter() if node.tag.endswith("}cxnSp"))
    connector_shape_properties = next(
        node for node in connector_shape if node.tag == f"{{{P_NS}}}spPr"
    )
    line = ET.SubElement(connector_shape_properties, f"{{{A_NS}}}ln")
    ET.SubElement(line, f"{{{A_NS}}}tailEnd", {"type": "triangle"})
    return editor.write(output)


def _native_proposal(family, capability, slide, target, operation, scoring):
    return AgentProposal.from_dict(
        {
            "proposal_version": "1.0",
            "title": "Restore one native presentation relationship",
            "instruction": (
                "Restore the damaged native presentation object from the visible reference "
                "while preserving editability and every unrelated object."
            ),
            "deck_summary": "A project update with a native table and connected process objects.",
            "mutations": [
                {
                    "mutation_id": "native-repair",
                    "family": family,
                    "capability": capability,
                    "slide": slide,
                    "target": target,
                    "operation": operation,
                    "evidence_tier": "reference_visible",
                    "evidence": [
                        {
                            "source": "reference",
                            "locator": f"slide {slide} target object",
                            "supports": "the visible native structure",
                        }
                    ],
                    "rationale": (
                        "The mutation damages a visible native property without flattening it."
                    ),
                    "accepted_solutions": ["Restore an equivalent editable native object."],
                    "scoring": scoring,
                    "weight": 1.0,
                }
            ],
            "preservation_contracts": ["Preserve all unrelated visible objects."],
        }
    ).require_valid()


def test_inventory_exposes_editable_objects_and_native_chart(synthetic_pptx):
    inventory = object_inventory(synthetic_pptx)

    assert inventory.slide_count == 2
    assert {(item.slide, item.shape_id) for item in inventory.objects} >= {
        (1, 2),
        (1, 4),
        (1, 6),
        (2, 2),
    }
    chart = next(item for item in inventory.objects if item.kind == "chart")
    assert chart.chart["plot"] == "barChart"
    assert chart.chart["series"][0]["values"] == ["12", "18", "27"]


def test_native_table_and_connector_semantics_are_mutatable_and_scorable(
    synthetic_pptx, workspace_tmp
):
    source = _with_native_table_and_attached_connector(
        synthetic_pptx, workspace_tmp / "native-source.pptx"
    )
    inventory = object_inventory(source)
    table = next(item for item in inventory.objects if item.kind == "table")
    connector = next(item for item in inventory.objects if item.kind == "connector")
    assert table.table["column_widths"] == [150.0, 200.0]
    assert [cell["text"] for cell in table.table["rows"][0]["cells"]] == ["Metric", "Q2"]
    assert connector.connector["start_semantic_key"]
    assert connector.connector["end_semantic_key"]

    table_plan = compile_proposal(
        _native_proposal(
            "native_table_repair",
            "table_content_repair",
            1,
            {"shape_id": 5, "kind": "table"},
            {"type": "set_table_cell_text", "row": 0, "column": 1, "text": "Wrong"},
            {"table_content": 1.0},
        ),
        inventory,
    )
    table_init = apply_mutations(source, table_plan, workspace_tmp / "table-init.pptx")
    assert evaluate_candidate(table_init, table_init, table_plan).score == 0.0
    assert evaluate_candidate(source, table_init, table_plan).score == 1.0

    connector_plan = compile_proposal(
        _native_proposal(
            "spatial_structure_repair",
            "connector_alignment",
            2,
            {"shape_id": 4, "kind": "connector"},
            {"type": "reverse_connector"},
            {"connector_targets": 1.0},
        ),
        inventory,
    )
    connector_init = apply_mutations(
        source, connector_plan, workspace_tmp / "connector-init.pptx"
    )
    assert evaluate_candidate(connector_init, connector_init, connector_plan).score == 0.0
    assert evaluate_candidate(source, connector_init, connector_plan).score == 1.0


def test_compile_mutate_and_evaluate_monotonic_progress(synthetic_pptx, workspace_tmp):
    plan = compile_proposal(_proposal(), object_inventory(synthetic_pptx))
    initial = apply_mutations(synthetic_pptx, plan, workspace_tmp / "initial.pptx")
    partial = apply_mutations(
        initial,
        _repair_plan(
            plan.to_dict(),
            {"type": "move_shape", "dx_points": -55, "dy_points": 0},
        ),
        workspace_tmp / "partial.pptx",
    )

    initial_score = evaluate_candidate(initial, initial, plan)
    partial_score = evaluate_candidate(partial, initial, plan)
    oracle_score = evaluate_candidate(synthetic_pptx, initial, plan)

    assert initial_score.score == 0.0
    assert 0.1 < partial_score.score < 0.9
    assert oracle_score.score == 1.0


def test_protected_content_damage_is_not_hidden_by_stable_shape_id(
    synthetic_pptx, workspace_tmp
):
    plan = compile_proposal(_proposal(), object_inventory(synthetic_pptx))
    initial = apply_mutations(synthetic_pptx, plan, workspace_tmp / "initial.pptx")
    candidate_plan = _repair_plan(
        plan.to_dict(), {"type": "set_text", "text": "Corrupted status"}
    )
    candidate_plan["mutations"][0]["target_shape_id"] = 3
    candidate = apply_mutations(
        synthetic_pptx,
        candidate_plan,
        workspace_tmp / "damaged-protected.pptx",
    )

    result = evaluate_candidate(candidate, initial, plan)

    assert result.raw_progress == 1.0
    assert result.preservation_multiplier < 1.0
    assert result.score < 1.0
    assert result.violations["protected"]


def test_enlarged_legitimate_picture_cannot_bypass_full_page_gate(
    synthetic_pptx, workspace_tmp
):
    plan = compile_proposal(_proposal(), object_inventory(synthetic_pptx))
    initial = apply_mutations(synthetic_pptx, plan, workspace_tmp / "initial.pptx")
    candidate_plan = deepcopy(plan.to_dict())
    candidate_plan["mutations"][0]["target_shape_id"] = 4
    candidate_plan["mutations"][0]["operation"] = {
        "type": "resize_shape",
        "scale_x": 3.0,
        "scale_y": 3.0,
    }
    candidate = apply_mutations(
        synthetic_pptx, candidate_plan, workspace_tmp / "full-page-picture.pptx"
    )

    result = evaluate_candidate(candidate, initial, plan)

    assert not result.hard_gates["unauthorized_full_page_picture"]
    assert result.score == 0.0


def test_geometry_swap_requires_both_objects_to_be_restored(synthetic_pptx, workspace_tmp):
    proposal = AgentProposal.from_dict(
        {
            "proposal_version": "1.0",
            "title": "Restore two aligned text objects",
            "instruction": (
                "Restore both misplaced editable text objects from the visible reference and "
                "preserve all other presentation content."
            ),
            "deck_summary": (
                "A project slide whose title and status occupy distinct aligned positions."
            ),
            "mutations": [
                {
                    "mutation_id": "swap-text-geometry",
                    "family": "spatial_structure_repair",
                    "capability": "object_alignment",
                    "slide": 1,
                    "target": {"shape_id": 2},
                    "operation": {
                        "type": "swap_geometry",
                        "other_target": {"shape_id": 3},
                    },
                    "evidence_tier": "reference_visible",
                    "evidence": [
                        {
                            "source": "reference",
                            "locator": "slide 1 title and status",
                            "supports": "the separate target positions of both objects",
                        }
                    ],
                    "rationale": (
                        "Swapping the two positions creates a meaningful but recoverable "
                        "hierarchy error."
                    ),
                    "accepted_solutions": ["Restore both objects to their visible positions."],
                    "scoring": {"geometry": 1.0},
                    "weight": 1.0,
                }
            ],
            "preservation_contracts": ["Preserve all unrelated slide objects."],
        }
    ).require_valid()
    plan = compile_proposal(proposal, object_inventory(synthetic_pptx))
    initial = apply_mutations(synthetic_pptx, plan, workspace_tmp / "swap-initial.pptx")
    one_sided_plan = deepcopy(plan.to_dict())
    one_sided_plan["mutations"][0]["operation"] = {
        "type": "move_shape",
        "dx_points": 0,
        "dy_points": -90,
    }
    one_sided = apply_mutations(
        initial, one_sided_plan, workspace_tmp / "one-sided-repair.pptx"
    )

    result = evaluate_candidate(one_sided, initial, plan)

    assert 0.45 <= result.raw_progress <= 0.55
    assert result.components[0]["matched_shape_ids"] == [2, 3]


def test_native_chart_value_mutation_changes_chart_snapshot(synthetic_pptx, workspace_tmp):
    plan = compile_proposal(
        AgentProposal.from_dict(
            {
                "proposal_version": "1.0",
                "title": "Restore native chart values",
                "instruction": (
                    "Restore the native chart data from the visible reference and preserve its "
                    "editable structure and all unrelated presentation content."
                ),
                "deck_summary": (
                    "A project update containing one native revenue chart with three values."
                ),
                "mutations": [
                    {
                        "mutation_id": "change-chart-value",
                        "family": "native_chart_repair",
                        "capability": "chart_data_repair",
                        "slide": 1,
                        "target": {"shape_id": 6, "kind": "chart"},
                        "operation": {
                            "type": "set_chart_value",
                            "series_index": 0,
                            "point_index": 1,
                            "value": "99",
                        },
                        "evidence_tier": "reference_visible",
                        "evidence": [
                            {
                                "source": "reference",
                                "locator": "slide 1 revenue chart",
                                "supports": "the visible series values",
                            }
                        ],
                        "rationale": (
                            "A wrong middle value changes the native chart's visible data "
                            "narrative."
                        ),
                        "accepted_solutions": ["Restore the editable chart value to 18."],
                        "scoring": {"chart_data": 1.0},
                        "weight": 1.0,
                    }
                ],
                "preservation_contracts": ["Preserve all non-chart content."],
            }
        ).require_valid(),
        object_inventory(synthetic_pptx),
    )
    initial = apply_mutations(synthetic_pptx, plan, workspace_tmp / "chart-initial.pptx")

    changed = next(item for item in object_inventory(initial).objects if item.kind == "chart")
    assert changed.chart["series"][0]["values"] == ["12", "99", "27"]
    assert evaluate_candidate(initial, initial, plan).score == 0.0
    assert evaluate_candidate(synthetic_pptx, initial, plan).score == 1.0


def test_native_chart_element_and_style_mutators(synthetic_pptx, workspace_tmp):
    inventory = object_inventory(synthetic_pptx)
    cases = (
        (
            "remove-chart-title",
            "chart_layout_repair",
            {"type": "remove_chart_title"},
            {"chart_elements": 1.0},
            lambda chart: chart["title"] == "",
        ),
        (
            "remove-chart-legend",
            "chart_layout_repair",
            {"type": "remove_chart_legend"},
            {"chart_elements": 1.0},
            lambda chart: chart["legend"] is False,
        ),
        (
            "change-series-color",
            "chart_style_repair",
            {"type": "set_series_color", "series_index": 0, "rgb": "FF00AA"},
            {"series_style": 1.0},
            lambda chart: chart["series"][0]["color"] == "srgbClr:FF00AA",
        ),
    )
    for mutation_id, capability, operation, scoring, predicate in cases:
        plan = compile_proposal(
            _chart_proposal(mutation_id, capability, operation, scoring), inventory
        )
        output = apply_mutations(
            synthetic_pptx, plan, workspace_tmp / f"{mutation_id}.pptx"
        )
        chart = next(
            item.chart for item in object_inventory(output).objects if item.kind == "chart"
        )
        assert predicate(chart)


def test_build_task_publishes_only_a_validated_bundle(synthetic_pptx, workspace_tmp):
    reference = workspace_tmp / "reference-input.pdf"
    reference.write_bytes(b"%PDF-1.4\n% synthetic test reference\n")
    output = workspace_tmp / "built-task"

    result = build_task(
        synthetic_pptx,
        reference,
        _proposal(),
        output,
        task_id="synthetic-built-task",
        source_uri="synthetic://unit-test-deck",
        license_name="CC0-1.0",
    )

    assert result.valid
    assert result.initial_score == 0.0
    assert result.oracle_score == 1.0
    assert (output / "evaluator" / "plan.json").is_file()
    assert (output / "validation" / "build.json").is_file()
    assert validate_bundle(output).valid


def test_picture_identity_survives_lossless_editor_reencoding(
    synthetic_pptx, workspace_tmp
):
    plan = compile_proposal(_picture_proposal(), object_inventory(synthetic_pptx))
    initial = apply_mutations(synthetic_pptx, plan, workspace_tmp / "picture-initial.pptx")
    with zipfile.ZipFile(initial) as package:
        assert "ppt/media/image1.png" not in package.namelist()
        assert b"rId3" not in package.read("ppt/slides/_rels/slide1.xml.rels")
    editor = PackageEditor(synthetic_pptx)
    original = editor.parts["ppt/media/image1.png"]
    buffer = io.BytesIO()
    with Image.open(io.BytesIO(original)) as image:
        image.convert("RGB").save(buffer, format="PNG", compress_level=0)
    editor.parts["ppt/media/image1.png"] = buffer.getvalue()
    candidate = editor.write(workspace_tmp / "reencoded-picture.pptx")

    assert original != buffer.getvalue()
    result = evaluate_candidate(candidate, initial, plan)
    assert result.score == 1.0


def test_picture_removal_build_extracts_anonymous_material(synthetic_pptx, workspace_tmp):
    reference = workspace_tmp / "picture-reference.pdf"
    reference.write_bytes(b"%PDF-1.4\n% synthetic test reference\n")
    output = workspace_tmp / "picture-task"

    build_task(
        synthetic_pptx,
        reference,
        _picture_proposal(),
        output,
        task_id="synthetic-picture-task",
        source_uri="synthetic://picture-deck",
        license_name="CC0-1.0",
    )

    materials = list((output / "materials").glob("asset-*.png"))
    assert len(materials) == 1


def test_slide_reorder_is_a_catastrophic_gate(synthetic_pptx, workspace_tmp):
    plan = compile_proposal(_proposal(), object_inventory(synthetic_pptx))
    initial = apply_mutations(synthetic_pptx, plan, workspace_tmp / "initial.pptx")
    editor = PackageEditor(synthetic_pptx)
    root = editor.xml("ppt/presentation.xml")
    slide_list = root.find(f".//{{{P_NS}}}sldIdLst")
    assert slide_list is not None
    children = list(slide_list)
    slide_list.remove(children[0])
    slide_list.append(children[0])
    candidate = editor.write(workspace_tmp / "reordered.pptx")

    result = evaluate_candidate(candidate, initial, plan)

    assert not result.hard_gates["slide_order"]
    assert result.score == 0.0
