from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from refract_pptx.cli import main
from refract_pptx.demo import create_demo
from refract_pptx.evaluation.progress import (
    _chart_data_similarity,
    _table_content_similarity,
    _text_similarity,
)
from refract_pptx.office import render_pdf
from refract_pptx.pipeline.locking import task_lock
from refract_pptx.validation import validate_production


def test_demo_builds_real_scored_candidates(workspace_tmp):
    result = create_demo(workspace_tmp / "demo")
    assert result["scores"] == {"initial": 0.0, "one_repair": 0.5, "oracle": 1.0}
    bundle = Path(result["output"]) / "bundle"
    assert not validate_production(bundle).valid  # Never manufacture Office/review evidence.
    output = workspace_tmp / "release"
    assert (
        main(["release-desktop", str(bundle), "--profile", "missing.json", "--output", str(output)])
        == 1
    )
    assert not output.exists()


def test_numeric_content_is_not_fuzzy():
    assert _text_similarity("Revenue 100.0%", "Revenue 100%") == 0
    assert _text_similarity("Revenue 100", "Revenue 101") == 0
    assert _text_similarity("Revenue 100", "Revenue   100") == 1


def test_table_cell_coordinates_matter():
    expected = {"rows": [{"cells": [{"text": "A"}, {"text": "B"}]}]}
    reshaped = {"rows": [{"cells": [{"text": "A"}]}, {"cells": [{"text": "B"}]}]}
    assert _table_content_similarity(reshaped, expected) < 0.5


def test_chart_categories_and_extra_series_are_scored():
    target = {
        "series": [{"name": "Revenue", "values": ["10", "20"], "categories": ["East", "West"]}]
    }
    candidate = json.loads(json.dumps(target))
    candidate["series"][0]["categories"].reverse()
    assert _chart_data_similarity(candidate, target) < 1
    candidate = {"series": target["series"] * 2}
    assert _chart_data_similarity(candidate, target) <= 0.5


def test_output_lock_releases_after_exception(workspace_tmp):
    lock = workspace_tmp / "task.lock"
    try:
        with task_lock(lock) as acquired:
            assert acquired
            with task_lock(lock) as competing:
                assert not competing
            raise RuntimeError("worker failed")
    except RuntimeError:
        pass
    with task_lock(lock) as acquired:
        assert acquired


@pytest.mark.parametrize("invalid_pdf", [True, False])
def test_release_rejects_invalid_reference(workspace_tmp, invalid_pdf):
    result = create_demo(workspace_tmp / "demo")
    bundle = Path(result["output"]) / "bundle"
    reference = bundle / "reference.pdf"
    if invalid_pdf:
        reference.write_bytes(b"not a PDF")
    else:
        writer = PdfWriter()
        writer.add_blank_page(width=720, height=405)
        writer.write(reference)
    result = validate_production(bundle)
    assert not result.valid
    assert any("PDF" in issue or "page per slide" in issue for issue in result.issues)


def test_render_never_overwrites_existing_reference(workspace_tmp):
    source = workspace_tmp / "source.pptx"
    source.write_bytes(b"placeholder")
    output = workspace_tmp / "reference.pdf"
    output.write_bytes(b"keep me")
    with pytest.raises(ValueError, match="overwrite"):
        render_pdf(source, output, executable="unused")
    assert output.read_bytes() == b"keep me"
