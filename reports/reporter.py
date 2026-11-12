"""Filing a bug report together with its left and right screenshots.

The browser engine is hidden behind one function, take_screenshots(left_path,
right_path): each engine has one (SeleniumEngine in el_tester.py, PwEngine in
pw_tester.py), and el_tester.py passes the active engine's. Nothing here
imports an engine.
"""
import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from reports.model import BugReport
from reports.repository import DATA_DIR, BugRepository

log = logging.getLogger(__name__)

# Saves a PNG of the left window to the first path and of the right one to the second
TakeScreenshots = Callable[[Path, Path], None]

DEFAULT_SCREENSHOT_DIR = DATA_DIR / "screenshots"


def bug_screenshot_paths(folder: Path, report_id: int) -> tuple[Path, Path]:
    """bug_00007_left.png and bug_00007_right.png for report 7."""
    stem = f"bug_{report_id:05d}"
    return folder / f"{stem}_left.png", folder / f"{stem}_right.png"


def adhoc_screenshot_paths(folder: Path, taken_at: datetime) -> tuple[Path, Path]:
    """shot_20261108_143005_123_left.png: a pair with no report, named by time.

    Milliseconds are included so two clicks in the same second don't overwrite each other.
    """
    stem = "shot_" + taken_at.strftime("%Y%m%d_%H%M%S_") + f"{taken_at.microsecond // 1000:03d}"
    return folder / f"{stem}_left.png", folder / f"{stem}_right.png"


class BugReporter:
    """Saves reports to a BugRepository and screenshots to a folder."""

    def __init__(self, repository: BugRepository, take_screenshots: TakeScreenshots,
                 folder: Path = DEFAULT_SCREENSHOT_DIR) -> None:
        self.repository = repository
        self.take_screenshots = take_screenshots
        self.folder = folder

    def report(self, report: BugReport) -> BugReport:
        """Save the report, then its screenshots, and return it with id and paths set.

        The report is saved first because the file names need its id. If the
        screenshots fail (a browser closed, for example), the report is kept
        without them: the tester's text matters more than the pictures, and
        the paths staying None shows what is missing.
        """
        saved = self.repository.add(report)
        assert saved.id is not None  # add() always assigns one
        left, right = bug_screenshot_paths(self.folder, saved.id)
        try:
            self._take(left, right)
        except Exception:
            log.exception("Screenshots for bug %d failed; report saved without them", saved.id)
            return saved
        with_paths = replace(saved, screenshot_left=str(left), screenshot_right=str(right))
        self.repository.update(with_paths)
        return with_paths

    def screenshot(self) -> tuple[Path, Path]:
        """The toolbar's Screenshot button: save a pair with no database entry."""
        left, right = adhoc_screenshot_paths(self.folder, datetime.now())
        self._take(left, right)
        return left, right

    def _take(self, left: Path, right: Path) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.take_screenshots(left, right)
