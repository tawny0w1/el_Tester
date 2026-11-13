"""What the app needs from a browser engine (Selenium or Playwright).

el_tester.py only talks to this interface, so it can switch engines without
knowing how each one drives the browsers.
"""
from pathlib import Path
from typing import Protocol

# Both engines open two windows of this size side by side (measured on the
# tester's screen, 2026-11-13: a 1200 px high display with a top bar and a dock)
WINDOW_WIDTH = 930
WINDOW_HEIGHT = 1080
# Chromium draws its own window frame on Linux, with an invisible 16 px shadow
# on each side: a window reported at x=50, 930 wide, is visible from 66 to 964.
FRAME_SHADOW_PX = 16
WINDOW_POSITION_JS = "[window.screenX, window.screenY, window.outerWidth]"  # where the window really is


def right_window_x(left_x: int, left_width: int) -> int:
    """x for the right window so its visible edge touches the left window's visible edge.

    The outer rectangles overlap by both shadows: the left one's right shadow
    and the right one's left shadow.
    """
    return left_x + left_width - 2 * FRAME_SHADOW_PX


class Engine(Protocol):
    name: str  # "selenium" or "playwright", stored in BugReport.engine

    def load(self, left_url: str, right_url: str) -> None:
        """Open both URLs (Load/Reload). Returns at once; the engine's own thread opens them."""

    def stop(self) -> None:
        """Quit both browsers and end the engine's threads. Blocks until done (or timed out)."""

    def current_urls(self) -> tuple[str, str]:
        """The pages the two windows show now; "" for a window that's gone."""

    def take_screenshots(self, left_path: Path, right_path: Path) -> None:
        """Save a PNG of each window's visible page; raise if one can't be taken."""
