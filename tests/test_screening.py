from refract_pptx.corpus.screening import screen_presentation


def test_screening_rejects_structurally_small_deck(synthetic_pptx):
    result = screen_presentation(synthetic_pptx)

    assert not result.accepted
    assert result.quality_score >= 0
    assert any("too few slides" in reason for reason in result.reasons)

