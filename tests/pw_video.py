"""Check of the video warning in the Playwright engine, on test_pages/video.html.

Moving the mouse over the <video> on the left shows the "not synchronized"
popup on the right; leaving the video hides it; after OK it stays hidden.

    cd selenium_el_tester
    python3 tests/pw_video.py              # headless
    python3 tests/pw_video.py --headed     # visible windows on the display

About 10 s. Exit code 0 when every check passed.
"""
import argparse
import sys

from playwright.sync_api import Page, sync_playwright

from helpers import Checks, fixture_server
from pw_tester import PwTester

PORT = 8768
POPUP_DISPLAY_JS = "() => { const p = document.getElementById('videoNoticePopup'); return p && p.style.display; }"


def hover_video(page: Page) -> None:
    box = page.locator("#vid").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(500)


def leave_video(page: Page) -> None:
    page.mouse.move(5, 5)
    page.wait_for_timeout(500)


def run(t: PwTester, left: str, right: str, c: Checks) -> None:
    L, R = t.left, t.right
    t.open(f"{left}/video.html", f"{right}/video.html")

    hover_video(L)
    c.check("notice shown on the right", R.evaluate(POPUP_DISPLAY_JS) == "block")
    leave_video(L)
    c.check("notice hidden when the mouse leaves the video", R.evaluate(POPUP_DISPLAY_JS) == "none")

    hover_video(L)
    R.click("#videoNoticePopup button")  # OK: don't show it again in this session
    leave_video(L); hover_video(L)
    c.check("no notice after OK, on the next hover", R.evaluate(POPUP_DISPLAY_JS) == "none")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="visible windows instead of headless")
    args = parser.parse_args()
    c = Checks()
    with fixture_server(PORT) as (left, right), sync_playwright() as p:
        t = PwTester(p, headless=not args.headed)
        try:
            run(t, left, right, c)
        finally:
            t.close()
    return c.exit_code()


if __name__ == "__main__":
    sys.exit(main())
