import json

from refract_pptx.reports import render_report


def test_html_report_escapes_input(workspace_tmp):
    source = workspace_tmp / "records.jsonl"
    source.write_text(
        json.dumps(
            {
                "path": "<unsafe>",
                "accepted": True,
                "quality_score": 0.8,
                "recommended_families": ["spatial_structure_repair"],
                "reasons": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    output = render_report(source, workspace_tmp / "report.html")
    text = output.read_text(encoding="utf-8")
    assert "&lt;unsafe&gt;" in text
    assert "<unsafe>" not in text
