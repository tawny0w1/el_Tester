"""Tests for SqliteBugRepository, one group per database specification in Reqirements.md.

    cd selenium_el_tester
    python3 -m pytest

Each test gets its own empty database in pytest's tmp_path folder, so the
real bug_data/bugs.db is never touched.
"""
from pathlib import Path

import pytest

from reports.model import BugReport
from reports.repository import SqliteBugRepository


def make_report(summary: str = "Typo on slide 3") -> BugReport:
    return BugReport(engine="selenium", url_left="http://localhost/a", url_right="http://127.0.0.1/a",
                     summary=summary)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "bugs.db"


@pytest.fixture
def repo(db_path: Path) -> SqliteBugRepository:
    return SqliteBugRepository(db_path)


# WHEN a user saves bug report THE system SHALL add it to database with the new ID.

def test_save_assigns_an_id(repo: SqliteBugRepository) -> None:
    saved = repo.add(make_report())
    assert saved.id is not None


def test_save_stores_the_report_under_its_id(repo: SqliteBugRepository) -> None:
    saved = repo.add(make_report("Button missing"))
    assert repo.get(saved.id) == saved  # type: ignore[arg-type]
    assert repo.list_all() == [saved]


def test_each_saved_report_gets_a_new_id(repo: SqliteBugRepository) -> None:
    ids = [repo.add(make_report(f"bug {n}")).id for n in range(3)]
    assert len(set(ids)) == 3


# WHEN a user deletes bug report THE system SHALL remove it from database
# AND not allow to create new bug report with the same ID.

def test_delete_removes_the_report(repo: SqliteBugRepository) -> None:
    saved = repo.add(make_report())
    assert repo.delete(saved.id) is True  # type: ignore[arg-type]
    assert repo.get(saved.id) is None  # type: ignore[arg-type]
    assert repo.list_all() == []


def test_delete_leaves_other_reports(repo: SqliteBugRepository) -> None:
    kept = repo.add(make_report("kept"))
    deleted = repo.add(make_report("deleted"))
    repo.delete(deleted.id)  # type: ignore[arg-type]
    assert repo.list_all() == [kept]


def test_deleted_id_is_not_reused(repo: SqliteBugRepository) -> None:
    # Delete the newest report: without AUTOINCREMENT, SQLite would give
    # the next report this same id (max id + 1).
    repo.add(make_report("first"))
    newest = repo.add(make_report("newest"))
    repo.delete(newest.id)  # type: ignore[arg-type]
    assert repo.add(make_report("after delete")).id != newest.id


def test_deleted_id_is_not_reused_after_restart(db_path: Path) -> None:
    deleted = SqliteBugRepository(db_path).add(make_report())
    SqliteBugRepository(db_path).delete(deleted.id)  # type: ignore[arg-type]
    reopened = SqliteBugRepository(db_path)  # like starting the app again
    assert reopened.add(make_report()).id != deleted.id


def test_cannot_save_a_report_with_a_deleted_id(repo: SqliteBugRepository) -> None:
    deleted = repo.add(make_report())
    repo.delete(deleted.id)  # type: ignore[arg-type]
    saved = repo.add(deleted)  # still carries the old id; "add" ignores it
    assert saved.id != deleted.id
    assert repo.update(deleted) is False  # an update can't bring it back either
    assert repo.get(deleted.id) is None  # type: ignore[arg-type]
