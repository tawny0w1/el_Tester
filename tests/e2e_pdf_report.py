"""End-to-end check of el_tester.on_report_bug_pdf ("Save and create PDF") with both engines.

Runs the app headless, files a bug with each engine and reads the PDF back:
both must have both screenshots (Playwright's since Phase 4 step 5).
Uses a temporary database and folders, so bug_data/ is not touched.

    cd selenium_el_tester
    python3 tests/e2e_pdf_report.py

About 60 s. Exit code 0 when every check passed.
"""
import shutil
import sys
import tempfile
import threading
from pathlib import Path

import pypdf

from e2e_sync import install_test_doubles
from helpers import Checks, fixture_server, wait_for

install_test_doubles()  # headless Selenium, no Tk toolbar; before importing el_tester
import el_tester as app  # noqa: E402
from pw_tester import PwEngine  # noqa: E402
from reports import pdf_exporter  # noqa: E402
from reports.model import BugDraft, Severity  # noqa: E402
from reports.reporter import BugReporter  # noqa: E402
from reports.repository import SqliteBugRepository  # noqa: E402

PORT = 8769


def images_drawn(page: pypdf.PageObject) -> int:
    """Images drawn on the page. Not page.images: identical PNGs are stored once."""
    return page.get_contents().get_data().count(b" Do")


def run(left: str, right: str, c: Checks) -> None:
    app.on_load_url(left, right, "Selenium")
    wait_for(lambda: app.active_engine.current_urls() == (left, right), 40)
    message, pdf = app.on_report_bug_pdf(BugDraft("Zły przycisk", "Opis: ąęł", Severity.MAJOR, *app.current_urls()))
    c.check("Selenium: bug saved with screenshots", message == "Bug 00001 ✓", message)
    reader = pypdf.PdfReader(pdf)
    c.check("Selenium: bug_00001.pdf, one page, one bookmark",
            pdf.name == "bug_00001.pdf" and len(reader.pages) == 1
            and [o.title for o in reader.outline] == ["Bug 00001: Zły przycisk"])
    text = reader.pages[0].extract_text().replace("\n", "")
    c.check("Selenium: both screenshots, the URLs and Polish text in the PDF",
            images_drawn(reader.pages[0]) == 2 and left in text and "ąęł" in text,
            f"{images_drawn(reader.pages[0])} images drawn")

    app.on_load_url(left, right, "Playwright")
    wait_for(lambda: app.active_engine.name == "playwright" and app.active_engine.current_urls() == (left, right), 40)
    message, pdf = app.on_report_bug_pdf(BugDraft("Playwright bug", "", Severity.NORMAL, *app.current_urls()))
    c.check("Playwright: bug saved with screenshots", message == "Bug 00002 ✓", message)
    page = pypdf.PdfReader(pdf).pages[0]
    text = page.extract_text().replace("\n", "")
    c.check("Playwright: both screenshots, the engine and the URLs in the PDF",
            images_drawn(page) == 2 and "playwright" in text and right in text and "(no screenshot)" not in text,
            f"{images_drawn(page)} images drawn")


def main() -> int:
    c = Checks()
    tmp = Path(tempfile.mkdtemp(prefix="e2e_pdf_"))
    app.bug_reporter = BugReporter(SqliteBugRepository(tmp / "bugs.db"),
                                   lambda l, r: app.require_engine().take_screenshots(l, r), tmp / "screenshots")
    app.pdf_path_for = lambda report: pdf_exporter.pdf_path_for(report, tmp / "pdf")
    app.ENGINES["Playwright"] = lambda: PwEngine(headless=True)
    with fixture_server(PORT) as (left_origin, right_origin):
        app_thread = threading.Thread(target=app.run_app, daemon=True)
        app_thread.start()
        try:
            run(f"{left_origin}/index.html", f"{right_origin}/index.html", c)
        except Exception as e:
            c.check(f"no error ({type(e).__name__}: {e})", False)
        finally:
            app.request_shutdown()
            app_thread.join(40)
            shutil.rmtree(tmp, ignore_errors=True)
    return c.exit_code()


if __name__ == "__main__":
    sys.exit(main())
