import json
import shutil
from pathlib import Path

from refract_pptx.validation import validate_bundle


def test_bundle_requires_declared_assets(workspace_tmp, synthetic_pptx):
    root = workspace_tmp / "bundle"
    root.mkdir()
    spec_source = Path("examples/synthetic_demo/task_spec.json")
    payload = json.loads(spec_source.read_text(encoding="utf-8"))
    (root / "task_spec.json").write_text(json.dumps(payload), encoding="utf-8")
    (root / "instruction.md").write_text(payload["instruction"], encoding="utf-8")
    (root / "provenance.json").write_text(json.dumps(payload["source"]), encoding="utf-8")
    shutil.copy2(synthetic_pptx, root / "init.pptx")
    (root / "reference.pdf").write_bytes(b"synthetic reference")
    (root / "materials").mkdir()

    result = validate_bundle(root)
    assert result.valid, result.issues
