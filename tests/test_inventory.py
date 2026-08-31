from refract_pptx.presentation import inspect_pptx


def test_inspect_package(synthetic_pptx):
    inventory = inspect_pptx(synthetic_pptx)

    assert inventory.slide_count == 2
    assert inventory.slide_width == 12192000
    assert inventory.media_files == 1
    assert inventory.notes_slides == 1
    assert inventory.slides[0].pictures == 1
    assert inventory.slides[0].tables == 1
    assert inventory.slides[0].charts == 1
    assert inventory.slides[0].diagrams == 1
    assert inventory.slides[0].has_transition
    assert inventory.slides[1].has_timing
    assert "chart" in inventory.native_object_types

