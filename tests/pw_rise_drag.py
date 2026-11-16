"""Check of drag and drop in the Playwright engine on the real Review360 course (needs internet).

Like a tester: START COURSE and CONTINUE are clicked on the left only (the
right follows through the click sync), the left is scrolled with the mouse
wheel to the matching exercise, and a piece is dragged onto a right-hand card.
Rise shuffles the pieces on every load, so the two windows may show them in
a different order; the check is that a piece is matched on both sides.

    cd selenium_el_tester
    python3 tests/pw_rise_drag.py --headed     # the real case: visible windows
    python3 tests/pw_rise_drag.py              # headless

About 30 s. Exit code 0 when every check passed.
"""
import argparse
import sys

from playwright.sync_api import Page, sync_playwright

from helpers import REVIEW_URL, Checks
from pw_tester import PwTester

PIECE = ".matching-interaction-piece"
MATCHED_JS = f"() => [...document.querySelectorAll('{PIECE}')].filter(e => e.innerText.includes('Matched with')).length"


def go_to_matching(page: Page) -> bool:
    """Click START COURSE, then CONTINUE until a lesson with a matching exercise opens."""
    page.get_by_text("START COURSE").first.click()
    page.wait_for_timeout(3000)
    for _ in range(5):
        if page.locator(PIECE).count():
            return True
        page.locator("a:has-text('CONTINUE'), button:has-text('CONTINUE')").last.click()
        page.wait_for_timeout(3000)
    return page.locator(PIECE).count() > 0


def wheel_to_first_piece(page: Page) -> None:
    """Scroll with the mouse wheel until the first piece is in the upper half of the window."""
    page.mouse.move(600, 400)
    for _ in range(80):
        top = page.locator(PIECE).first.bounding_box()["y"]
        if 250 < top < 450:
            break
        page.mouse.wheel(0, 200 if top > 450 else -100)
        page.wait_for_timeout(150)
    page.wait_for_timeout(1500)  # the right window's scroll follows


def run(t: PwTester, url: str, c: Checks) -> None:
    L, R = t.left, t.right
    t.open(url)
    c.check("matching exercise found on both sides",
            go_to_matching(L) and R.locator(PIECE).count() == L.locator(PIECE).count() > 0)
    wheel_to_first_piece(L)
    left_top, right_top = (w.locator(PIECE).first.bounding_box()["y"] for w in (L, R))
    c.check("both windows scrolled to the same place", abs(left_top - right_top) < 2, f"left {left_top}, right {right_top}")

    # The first piece onto the second right-hand card (pieces 0-3 left, 4-7 right), held by its grip
    piece, card = L.locator(PIECE).first.bounding_box(), L.locator(PIECE).nth(5).bounding_box()
    L.mouse.move(piece["x"] + 10, piece["y"] + piece["height"] / 2)
    L.mouse.down()
    L.wait_for_timeout(200)
    L.mouse.move(card["x"] + 20, card["y"] + card["height"] / 2, steps=25)
    L.mouse.up()
    L.wait_for_timeout(3000)
    left, right = L.evaluate(MATCHED_JS), R.evaluate(MATCHED_JS)
    c.check("left: a piece matched (the real drag worked)", left > 0, left)
    c.check("right: a piece matched too", right == left, f"left {left}, right {right}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="visible windows instead of headless")
    parser.add_argument("--url", default=REVIEW_URL, help="Review360 link")
    args = parser.parse_args()
    c = Checks()
    with sync_playwright() as p:
        t = PwTester(p, headless=not args.headed)
        try:
            run(t, args.url, c)
        finally:
            t.close()
    return c.exit_code()


if __name__ == "__main__":
    sys.exit(main())
