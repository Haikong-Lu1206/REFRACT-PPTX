from pathlib import Path

import pytest

from refract_pptx.models import ContractError, TaskSpec, load_task_spec


def test_synthetic_spec_is_valid():
    path = Path("examples/synthetic_demo/task_spec.json")
    spec = load_task_spec(path)

    assert spec.validate() == []
    assert spec.task_id == "synthetic-layout-demo"


def test_hidden_evaluator_weight_error():
    payload = {
        "spec_version": "1.0",
        "task_id": "bad-spec",
        "title": "Bad",
        "instruction": (
            "Restore the damaged editable slide from the visible reference and materials."
        ),
        "family": "native_chart_repair",
        "source": {"uri": "synthetic://bad", "sha256": "a" * 64, "license": "CC0"},
        "episodes": [
            {
                "episode_id": "e1",
                "family": "native_chart_repair",
                "capability": "chart_data_repair",
                "slides": [1],
                "mutation": "Remove one series.",
                "evidence_tier": "reference_visible",
                "observable_evidence": ["reference"],
                "weight": 1,
                "evaluator": {"data": 0.9},
                "acceptance": ["Series is restored."],
            }
        ],
        "preservation_contracts": ["Preserve other content."],
        "assets": {"initial_presentation": "init.pptx", "reference_render": "ref.pdf"},
    }
    spec = TaskSpec.from_dict(payload)

    assert any("evaluator weights must sum" in issue for issue in spec.validate())
    with pytest.raises(ContractError):
        spec.require_valid()
