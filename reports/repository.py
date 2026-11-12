"""Storage for BugReport records.

BugRepository is the contract the rest of the app depends on; SqliteBugRepository
is the one implementation for now. Code that saves reports (the toolbar form,
later the main window and the PDF export) only sees BugRepository, so the
storage can change without touching it.
"""
import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from reports.model import BugReport, Resolution, Severity, Status

# bug_data/ in the project folder (git-ignored): it survives a container
# rebuild, unlike the home folder. Built from __file__, so it doesn't depend
# on the folder the app is started from.
DATA_DIR = Path(__file__).resolve().parent.parent / "bug_data"
DEFAULT_DB_PATH = DATA_DIR / "bugs.db"


class BugRepository(ABC):
    """Create, read, update and delete bug reports.

    A missing id is an expected case (the report was deleted from another
    window, for example), so it is a return value, not an exception.
    """

    @abstractmethod
    def add(self, report: BugReport) -> BugReport:
        """Save a new report. Returns a copy with the id the storage assigned."""

    @abstractmethod
    def get(self, report_id: int) -> BugReport | None:
        """The report with this id, or None if there is none."""

    @abstractmethod
    def list_all(self, status: Status | None = None) -> list[BugReport]:
        """All reports, oldest first; only those with this status if one is given."""

    @abstractmethod
    def update(self, report: BugReport) -> bool:
        """Overwrite the stored report that has report.id. False if there is none."""

    @abstractmethod
    def delete(self, report_id: int) -> bool:
        """Remove the report with this id. False if there was none."""


# Every BugReport field except id, in table column order
_COLUMNS = (
    "created_at", "engine", "url_left", "url_right", "summary", "description",
    "severity", "status", "resolution", "screenshot_left", "screenshot_right",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bugs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       TEXT NOT NULL,
    engine           TEXT NOT NULL,
    url_left         TEXT NOT NULL,
    url_right        TEXT NOT NULL,
    summary          TEXT NOT NULL,
    description      TEXT NOT NULL,
    severity         TEXT NOT NULL,
    status           TEXT NOT NULL,
    resolution       TEXT NOT NULL,
    screenshot_left  TEXT,
    screenshot_right TEXT
)
"""


class SqliteBugRepository(BugRepository):
    """Bug reports in one SQLite table, `bugs`, in the file at db_path.

    AUTOINCREMENT keeps SQLite from reusing the id of a deleted report, so a
    new report never takes over the old one's screenshot file names.

    Each call opens its own short connection. A sqlite3 connection may only be
    used by the thread that created it, and the toolbar (Tk thread) and the
    Selenium worker both save reports; a connection per call costs well under
    a millisecond for a local file.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._execute(_SCHEMA)

    def add(self, report: BugReport) -> BugReport:
        placeholders = ", ".join("?" for _ in _COLUMNS)
        cursor = self._execute(
            f"INSERT INTO bugs ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
            self._to_row(report),
        )
        return replace(report, id=cursor.lastrowid)

    def get(self, report_id: int) -> BugReport | None:
        rows = self._query("SELECT * FROM bugs WHERE id = ?", (report_id,))
        return self._from_row(rows[0]) if rows else None

    def list_all(self, status: Status | None = None) -> list[BugReport]:
        if status is None:
            rows = self._query("SELECT * FROM bugs ORDER BY id")
        else:
            rows = self._query("SELECT * FROM bugs WHERE status = ? ORDER BY id", (status.value,))
        return [self._from_row(row) for row in rows]

    def update(self, report: BugReport) -> bool:
        if report.id is None:
            return False
        assignments = ", ".join(f"{column} = ?" for column in _COLUMNS)
        cursor = self._execute(
            f"UPDATE bugs SET {assignments} WHERE id = ?",
            (*self._to_row(report), report.id),
        )
        return cursor.rowcount == 1

    def delete(self, report_id: int) -> bool:
        cursor = self._execute("DELETE FROM bugs WHERE id = ?", (report_id,))
        return cursor.rowcount == 1

    # --- helpers -----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row  # rows readable by column name
        return connection

    def _execute(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
        """Run one write statement and commit it."""
        with closing(self._connect()) as connection:
            with connection:  # commits on success, rolls back on an exception
                return connection.execute(sql, params)

    def _query(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        with closing(self._connect()) as connection:
            return connection.execute(sql, params).fetchall()

    @staticmethod
    def _to_row(report: BugReport) -> tuple[object, ...]:
        """BugReport -> column values in _COLUMNS order."""
        return (
            report.created_at.isoformat(), report.engine, report.url_left, report.url_right,
            report.summary, report.description, report.severity.value, report.status.value,
            report.resolution.value, report.screenshot_left, report.screenshot_right,
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> BugReport:
        return BugReport(
            id=row["id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            engine=row["engine"],
            url_left=row["url_left"],
            url_right=row["url_right"],
            summary=row["summary"],
            description=row["description"],
            severity=Severity(row["severity"]),
            status=Status(row["status"]),
            resolution=Resolution(row["resolution"]),
            screenshot_left=row["screenshot_left"],
            screenshot_right=row["screenshot_right"],
        )
