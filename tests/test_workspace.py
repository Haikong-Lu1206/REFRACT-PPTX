from __future__ import annotations

import shutil

import pytest

from refract_pptx.demo import create_demo
from refract_pptx.workspace import (
    build_workspace,
    init_workspace,
    prepare_task,
    workspace_status,
)


def test_workspace_handoff_build_and_resume(workspace_tmp):
    demo = workspace_tmp / "demo"
    create_demo(demo)
    root = init_workspace(workspace_tmp / "workspace")
    design = prepare_task(
        demo / "source.pptx",
        root / "designs" / "example",
        reference=demo / "reference.pdf",
        source_uri="synthetic://example",
        license_name="CC0-1.0",
    )
    assert workspace_status(root)["ready"] == 0
    with pytest.raises(ValueError, match="workspace-status"):
        build_workspace(root)
    assert not (root / "runs" / "batch").exists()
    shutil.copy2(demo / "proposal.json", design / "proposal.json")
    assert workspace_status(root)["ready"] == 1
    first, second = build_workspace(root), build_workspace(root)
    assert first["successful"] == second["successful"] == 1
    assert first["items"][0]["task_id"] == second["items"][0]["task_id"]


def test_prepare_is_non_destructive_and_invalid_pdf_leaves_no_design(workspace_tmp):
    demo = workspace_tmp / "demo"
    create_demo(demo)
    root = init_workspace(workspace_tmp / "workspace")
    with pytest.raises(FileExistsError):
        init_workspace(root)
    wrong = workspace_tmp / "bad.pdf"
    wrong.write_bytes(b"invalid")
    output = root / "designs" / "bad"
    with pytest.raises(ValueError, match="PDF"):
        prepare_task(
            demo / "source.pptx",
            output,
            reference=wrong,
            source_uri="synthetic://example",
            license_name="CC0-1.0",
        )
    assert not output.exists()
    assert not list((root / "designs").glob(".prepare-*"))
