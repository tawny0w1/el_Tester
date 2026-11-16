"""Check of drag and drop in the Playwright engine, on test_pages/drag.html.

drag.html behaves like a Rise matching exercise in the ways that matter here:
a piece dropped on a card shows "Matched with Card n", a plain click selects
a piece, a click on a matched piece unmatches it, and the click the browser
fires at the end of a drag is ignored. Each check compares the piece's state
(data-state) in both windows after a real mouse drag or click on the left.

    cd selenium_el_tester
    python3 tests/pw_drag.py              # headless
    python3 tests/pw_drag.py --headed     # visible windows on the display

About 15 s. Exit code 0 when every check passed.
"""
import argparse
import sys

from playwright.sync_api import FrameLocator, Page, sync_playwright

from helpers import Checks, fixture_server
from pw_tester import PwTester

PORT = 8767


def drag(page: Page, where: Page | FrameLocator, piece: str, card: str) -> None:
    """Drag a piece onto a card with the real mouse, slowly, holding it by its grip.

    bounding_box is in page coordinates, also for an element in an iframe.
    """
    p, c = where.locator(piece).bounding_box(), where.locator(card).bounding_box()
    page.mouse.move(p["x"] + 12, p["y"] + p["height"] / 2)
    page.mouse.down()
    page.mouse.move(c["x"] + c["width"] / 2, c["y"] + c["height"] / 2, steps=15)
    page.mouse.up()
    page.wait_for_timeout(800)


def states(where: Page | FrameLocator) -> dict[str, str]:
    """data-state of each piece: '', 'selected' or 'matched:card-n'."""
    return {p: where.locator(f"#{p}").get_attribute("data-state") for p in ("piece-a", "piece-b", "piece-c")}


def run(t: PwTester, left: str, right: str, c: Checks) -> None:
    L, R = t.left, t.right

    t.open(f"{left}/drag.html", f"{right}/drag.html")
    drag(L, L, "#piece-a", "#card-2")
    c.check("left: Piece A matched with Card 2 (the fixture works)", states(L)["piece-a"] == "matched:card-2", states(L))
    c.check("right: Piece A matched with Card 2", states(R)["piece-a"] == "matched:card-2", states(R))

    L.click("#piece-b"); L.wait_for_timeout(800)
    c.check("plain click on Piece B: selected on both sides, not a drag",
            states(L)["piece-b"] == states(R)["piece-b"] == "selected", f"left {states(L)}, right {states(R)}")
    c.check("both windows end in the same state", states(L) == states(R), f"left {states(L)}, right {states(R)}")

    t.open(f"{left}/drag_in_frame.html", f"{right}/drag_in_frame.html"); L.wait_for_timeout(1000)
    lf, rf = L.frame_locator("#frame-cross"), R.frame_locator("#frame-cross")
    drag(L, lf, "#piece-c", "#card-1")
    c.check("cross-origin iframe: Piece C matched with Card 1 on both sides",
            states(lf)["piece-c"] == states(rf)["piece-c"] == "matched:card-1", f"left {states(lf)}, right {states(rf)}")


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
