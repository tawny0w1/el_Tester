"""What the app needs from a browser engine (Selenium or Playwright).

el_tester.py only talks to this interface, so it can switch engines without
knowing how each one drives the browsers.
"""
from pathlib import Path
from typing import Protocol


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
