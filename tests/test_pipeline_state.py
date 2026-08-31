from refract_pptx.pipeline import RunState, StageStatus


def test_stage_receipts_are_reusable(workspace_tmp):
    state = RunState(workspace_tmp / "run.sqlite")

    assert state.start("deck-a", "inspect", "input-v1")
    state.complete("deck-a", "inspect", {"slides": 12})
    assert state.start("deck-a", "inspect", "input-v1") is False

    receipt = state.receipt("deck-a", "inspect")
    assert receipt is not None
    assert receipt.status is StageStatus.COMPLETE
    assert receipt.output == {"slides": 12}

    assert state.start("deck-a", "inspect", "input-v2")
