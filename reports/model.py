"""The BugReport record and the fixed choices for its fields.

Severity, Status and Resolution use Bugzilla's default values (ENUM_DEFAULTS
in Bugzilla/DB.pm, versions 5.0 and 5.2), so a report can later be exported
to Bugzilla. The values are str Enums, so SQLite stores them as plain text.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Severity(str, Enum):
    """How bad the bug is, from worst to mildest (Bugzilla's order)."""
    BLOCKER = "blocker"
    CRITICAL = "critical"
    MAJOR = "major"
    NORMAL = "normal"
    MINOR = "minor"
    TRIVIAL = "trivial"
    ENHANCEMENT = "enhancement"


class Status(str, Enum):
    """Where the bug is in its life cycle. The first three are open, the last two closed."""
    UNCONFIRMED = "UNCONFIRMED"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"


class Resolution(str, Enum):
    """Why a closed bug was closed. NONE ("") while the bug is open."""
    NONE = ""
    FIXED = "FIXED"
    INVALID = "INVALID"
    WONTFIX = "WONTFIX"
    DUPLICATE = "DUPLICATE"
    WORKSFORME = "WORKSFORME"


@dataclass
class BugReport:
    """One bug found while comparing the left and right course versions.

    id is None until the repository saves the report; the database then
    assigns it. Screenshot paths stay None until the screenshots are saved,
    because their file names contain the id.
    """
    engine: str  # "selenium" or "playwright"
    url_left: str
    url_right: str
    summary: str  # one line, like Bugzilla's summary
    description: str = ""
    severity: Severity = Severity.NORMAL
    status: Status = Status.UNCONFIRMED  # a tester's report is not triaged yet
    resolution: Resolution = Resolution.NONE
    screenshot_left: str | None = None
    screenshot_right: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    id: int | None = None
