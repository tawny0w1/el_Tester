"""Tests for the PDF export, written ahead of it (Phase 6).

Skipped until reports/pdf_exporter.py exists and pypdf is installed. The test
fixes the interface the exporter must have:
    PdfExporter().export(reports: list[BugReport], path: Path) -> None
and the meaning of an "entry": one PDF bookmark (outline item) per bug report,
titled "Bug 00007: <summary>", which a reader sees in the PDF viewer's sidebar.
"""
from pathlib import Path

import pytest

from reports.model import BugReport

pdf_exporter = pytest.importorskip("reports.pdf_exporter")
pypdf = pytest.importorskip("pypdf")  # reads the PDF back to check it


def make_saved_report(report_id: int) -> BugReport:
    return BugReport(engine="selenium", source_url="http://localhost/a", target_url="http://127.0.0.1/a",
                     summary=f"bug {report_id}", id=report_id)


# WHEN a user generates PDF THE system SHALL create a PDF with one entry
# per bug report (user's meaning of "one entry point", 2026-11-08).

@pytest.mark.parametrize("count", [0, 1, 3])
def test_pdf_has_one_entry_per_bug_report(tmp_path: Path, count: int) -> None:
    reports = [make_saved_report(n) for n in range(1, count + 1)]
    path = tmp_path / "bugs.pdf"

    pdf_exporter.PdfExporter().export(reports, path)

    entries = [item.title for item in pypdf.PdfReader(path).outline]
    assert entries == [f"Bug {r.id:05d}: {r.summary}" for r in reports]
