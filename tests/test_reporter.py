"""Tests for BugReporter, with a fake take_screenshots instead of a browser.

Requirement (Reqirements.md): both left and right browser screenshots saved to
a local folder, with the ID of the bug report from the database in the filename.
"""
from datetime import datetime
from pathlib import Path

import pytest

from reports.model import BugReport
from reports.reporter import BugReporter, adhoc_screenshot_paths, bug_screenshot_paths
from reports.repository import SqliteBugRepository


def make_report() -> BugReport:
    return BugReport(engine="selenium", source_url="http://localhost/a", target_url="http://127.0.0.1/a",
                     summary="Typo on slide 3")


def fake_take_screenshots(left: Path, right: Path) -> None:
    left.write_bytes(b"left png")
    right.write_bytes(b"right png")


def failing_take_screenshots(left: Path, right: Path) -> None:
    raise RuntimeError("browser window closed")


@pytest.fixture
def repo(tmp_path: Path) -> SqliteBugRepository:
    return SqliteBugRepository(tmp_path / "bugs.db")


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "screenshots"  # not created yet: the reporter must create it


# File names

def test_bug_paths_contain_the_padded_id(folder: Path) -> None:
    assert bug_screenshot_paths(folder, 7) == (folder / "bug_00007_source.png", folder / "bug_00007_target.png")


def test_adhoc_paths_are_named_by_time_to_the_millisecond(folder: Path) -> None:
    left, right = adhoc_screenshot_paths(folder, datetime(2026, 11, 8, 14, 30, 5, 123456))
    assert (left.name, right.name) == ("shot_20261108_143005_123_source.png", "shot_20261108_143005_123_target.png")


# Both screenshots saved to a local folder, with the bug's database ID in the file name

def test_report_saves_both_screenshots_named_with_the_id(repo: SqliteBugRepository, folder: Path) -> None:
    saved = BugReporter(repo, fake_take_screenshots, folder).report(make_report())
    assert saved.id is not None
    left, right = bug_screenshot_paths(folder, saved.id)
    assert left.read_bytes() == b"left png"
    assert right.read_bytes() == b"right png"


def test_report_stores_the_screenshot_paths_in_the_database(repo: SqliteBugRepository, folder: Path) -> None:
    saved = BugReporter(repo, fake_take_screenshots, folder).report(make_report())
    stored = repo.get(saved.id)  # type: ignore[arg-type]
    assert stored == saved
    assert stored is not None and stored.source_screenshot and stored.target_screenshot
    assert Path(stored.source_screenshot).exists() and Path(stored.target_screenshot).exists()


def test_report_is_kept_without_paths_when_screenshots_fail(repo: SqliteBugRepository, folder: Path) -> None:
    saved = BugReporter(repo, failing_take_screenshots, folder).report(make_report())
    stored = repo.get(saved.id)  # type: ignore[arg-type]
    assert stored is not None
    assert stored.source_screenshot is None and stored.target_screenshot is None


# The toolbar's Screenshot button: a pair with no database entry

def test_screenshot_saves_a_pair_without_a_report(repo: SqliteBugRepository, folder: Path) -> None:
    left, right = BugReporter(repo, fake_take_screenshots, folder).screenshot()
    assert left.exists() and right.exists()
    assert left.name.startswith("shot_") and left.name.endswith("_source.png")
    assert repo.list_all() == []
