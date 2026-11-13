"""Tests for the window layout arithmetic shared by both engines (engine.py)."""
from engine import FRAME_SHADOW_PX, right_window_x


def test_right_window_overlaps_the_left_by_both_shadows() -> None:
    # Measured 2026-11-13: left at x=50, 930 wide, visible 66..964 -> right at 948, visible from 964
    assert FRAME_SHADOW_PX == 16
    assert right_window_x(50, 930) == 948
