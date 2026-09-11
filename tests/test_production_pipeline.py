from __future__ import annotations

import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pypdf import PdfWriter

from refract_pptx.build import build_task
from refract_pptx.design import AgentProposal
from refract_pptx.pipeline import BatchRunner, RunState, TaskRegistry, load_batch_manifest
from refract_pptx.validation import (
    record_blind_review,
    record_office_roundtrip,
    validate_production,
)


def _proposal_dict() -> dict:
    return {
        "proposal_version": "1.0",
        "title": "Restore the title alignment",
        "instruction": (
            "Restore the damaged editable title so the presentation matches the visible "
            "reference while preserving all unrelated content."
        ),
        "deck_summary": "A two-slide project update with editable native content.",
        "mutations": [
            {
                "mutation_id": "move-title",
                "family": "spatial_structure_repair",
                "capability": "object_alignment",
                "slide": 1,
                "target": {"shape_id": 2, "kind": "shape"},
                "operation": {"type": "move_shape", "dx_points": 60, "dy_points": 0},
                "evidence_tier": "reference_visible",
                "evidence": [
                    {
                        "source": "reference",
                        "locator": "slide 1 title",
                        "supports": "the target title position",
                    }
                ],
                "rationale": "The shifted title visibly breaks the page alignment.",
                "accepted_solutions": ["Move or recreate an equivalent editable title."],
                "scoring": {"geometry": 1.0},
                "weight": 1.0,
            }
        ],
        "preservation_contracts": ["Preserve all unrelated visible content."],
    }


def _bundle(synthetic_pptx: Path, root: Path) -> Path:
    reference = root / "reference.pdf"
    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=960, height=540)
    writer.write(reference)
    target = root / "bundle"
    build_task(
        synthetic_pptx,
        reference,
        AgentProposal.from_dict(_proposal_dict()).require_valid(),
        target,
        task_id="production-test-task",
        source_uri="synthetic://production-test",
        license_name="CC0-1.0",
    )
    return target


def test_build_records_redteam_and_production_requires_external_receipts(
    synthetic_pptx, workspace_tmp
):
    bundle = _bundle(synthetic_pptx, workspace_tmp)
    redteam = json.loads((bundle / "validation" / "redteam.json").read_text())
    assert redteam["valid"]
    assert redteam["coverage"]["valid"]
    assert (
        redteam["source_sha256"] == json.loads((bundle / "provenance.json").read_text())["sha256"]
    )
    assert redteam["single_repairs"][0]["score"] == 1.0

    pending = validate_production(bundle)
    assert not pending.valid
    assert "missing blind-review receipt" in pending.issues
    assert "missing office-roundtrip receipt" in pending.issues

    record_blind_review(bundle, reviewer="blind-reviewer", decision="pass")
    record_office_roundtrip(
        bundle,
        synthetic_pptx,
        synthetic_pptx,
        office_suite="synthetic roundtrip",
    )
    assert validate_production(bundle).valid


def test_receipt_is_invalidated_when_bundle_identity_changes(synthetic_pptx, workspace_tmp):
    bundle = _bundle(synthetic_pptx, workspace_tmp)
    record_blind_review(bundle, reviewer="blind-reviewer", decision="pass")
    record_office_roundtrip(
        bundle,
        synthetic_pptx,
        synthetic_pptx,
        office_suite="synthetic roundtrip",
    )
    with (bundle / "reference.pdf").open("ab") as stream:
        stream.write(b"\n% revised reference\n")
    result = validate_production(bundle)
    assert not result.valid
    assert any("different bundle revision" in issue for issue in result.issues)


def test_expired_stage_lease_is_reclaimed(workspace_tmp):
    state = RunState(workspace_tmp / "run.sqlite")
    assert state.start("deck", "build", "hash", owner="worker-a")
    assert not state.start("deck", "build", "hash", owner="worker-b")
    with sqlite3.connect(state.path) as connection:
        connection.execute("UPDATE stage_receipts SET lease_until='2000-01-01T00:00:00+00:00'")
    assert state.start("deck", "build", "hash", owner="worker-b")
    assert state.receipt("deck", "build").attempts == 2
    for action in (
        lambda: state.complete("deck", "build", {}, owner="worker-a"),
        lambda: state.fail("deck", "build", "stale failure", owner="worker-a"),
        lambda: state.heartbeat("deck", "build", owner="worker-a"),
    ):
        with pytest.raises(RuntimeError):
            action()
    assert not state.start("deck", "build", "different-input", owner="worker-c")
    assert not state.reset("deck", "build")
    state.complete("deck", "build", {"fresh": True}, owner="worker-b")
    assert state.receipt("deck", "build").output == {"fresh": True}


@pytest.mark.parametrize("corruption", ["empty_gates", "nan", "loss", "malformed", "material"])
def test_production_rejects_corrupted_evidence(synthetic_pptx, workspace_tmp, corruption):
    bundle = _bundle(synthetic_pptx, workspace_tmp)
    record_blind_review(bundle, reviewer="reviewer", decision="pass")
    receipt_path = record_office_roundtrip(
        bundle, synthetic_pptx, synthetic_pptx, office_suite="synthetic test"
    )
    assert validate_production(bundle).valid
    receipt = json.loads(receipt_path.read_text())
    if corruption == "empty_gates":
        receipt["hard_gates"] = {}
    elif corruption == "nan":
        receipt["baseline_score"] = float("nan")
    elif corruption == "loss":
        receipt["roundtrip_score"] = 0.2
        receipt["score_loss"] = 0.0
    elif corruption == "material":
        (bundle / "materials" / "new-asset.txt").write_text("changed evidence")
    receipt_path.write_text("{" if corruption == "malformed" else json.dumps(receipt))
    assert not validate_production(bundle).valid


def test_task_registry_allocates_stable_unique_ids_concurrently(workspace_tmp):
    registry = TaskRegistry(workspace_tmp / "registry.sqlite")
    digest = "a" * 64

    def allocate(index: int) -> str:
        return registry.allocate(digest, f"design-{index}")

    with ThreadPoolExecutor(max_workers=6) as executor:
        identifiers = list(executor.map(allocate, range(12)))
    assert len(set(identifiers)) == 12
    assert registry.allocate(digest, "design-3") == identifiers[3]


def test_batch_build_is_resumable_and_content_identified(synthetic_pptx, workspace_tmp):
    reference = workspace_tmp / "reference.pdf"
    reference.write_bytes(b"%PDF-1.4\n% batch test\n")
    proposal_a = workspace_tmp / "proposal-a.json"
    proposal_a.write_text(json.dumps(_proposal_dict()), encoding="utf-8")
    proposal_b_value = _proposal_dict()
    proposal_b_value["mutations"][0]["operation"]["dx_points"] = 90
    proposal_b = workspace_tmp / "proposal-b.json"
    proposal_b.write_text(json.dumps(proposal_b_value), encoding="utf-8")
    manifest = workspace_tmp / "batch.jsonl"
    manifest.write_text(
        "\n".join(
            json.dumps(
                {
                    "key": f"design-{index}",
                    "presentation": str(synthetic_pptx.resolve()),
                    "reference": str(reference.resolve()),
                    "proposal": str(proposal.resolve()),
                    "source_uri": "synthetic://batch-test",
                    "license": "CC0-1.0",
                }
            )
            for index, proposal in enumerate((proposal_a, proposal_b), start=1)
        )
        + "\n",
        encoding="utf-8",
    )
    output = workspace_tmp / "batch-output"
    runner = BatchRunner(
        output,
        state_path=output / "state.sqlite",
        registry_path=output / "registry.sqlite",
        workers=2,
    )
    items = load_batch_manifest(manifest)
    first = runner.run(items)
    second = runner.run(items)
    assert first.successful == second.successful == 2
    assert {item.task_id for item in first.items} == {item.task_id for item in second.items}
    assert all(item.attempts == 1 for item in runner.state.receipts())

    missing = Path(first.items[0].bundle)
    shutil.rmtree(missing)
    recovered = runner.run(items)
    assert recovered.successful == 2
    assert missing.is_dir()
    (missing / "materials" / "changed.txt").write_text("unexpected new material")
    changed = runner.run(items)
    assert changed.failed == 1
    assert changed.successful == 1
