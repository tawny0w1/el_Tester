"""End-to-end check of the Playwright engine (pw_tester.PwTester) on the fixtures.

Clicks, inputs and scroll in the left window must reach the right one: top
page, nested iframes, a cross-origin iframe, form fields, and a link click
(left on localhost, right on 127.0.0.1, so each window opens its own href).

    cd selenium_el_tester
    python3 tests/pw_e2e_sync.py              # headless
    python3 tests/pw_e2e_sync.py --headed     # visible windows on the display

About 30 s. Exit code 0 when every check passed.
"""
import argparse
import sys

from playwright.sync_api import FrameLocator, Locator, Page, sync_playwright

from helpers import Checks, fixture_server
from pw_tester import PwTester

PORT = 8766


def count(loc: Locator) -> str | None:
    return loc.get_attribute("data-count")  # common.js counts clicks per button


def scroll_to(loc: Locator, top: int) -> None:
    loc.evaluate("(el, t) => { el.scrollTop = t; }", top)


def scroll_top(loc: Locator) -> int:
    return loc.evaluate("el => el.scrollTop")


def run(t: PwTester, left: str, right: str, c: Checks) -> None:
    L, R = t.left, t.right

    # Clicks and page scroll on the top page
    t.open(f"{left}/index.html", f"{right}/index.html")
    L.click("#btn-a"); L.click("#btn-a"); L.click("#btn-b"); L.wait_for_timeout(500)
    c.check("click: index Button A x2, B x1", (count(R.locator("#btn-a")), count(R.locator("#btn-b"))) == ("2", "1"))
    L.mouse.move(5, 5); L.mouse.wheel(0, 600); L.wait_for_timeout(600)
    lt, rt = L.evaluate("scrollY"), R.evaluate("scrollY")
    c.check("scroll: index page (mouse wheel)", lt > 0 and lt == rt, f"left {lt}, right {rt}")

    # A link: the right window clicks its own link, so it stays on its own host
    L.click("#link-nested"); L.wait_for_timeout(1500)
    c.check("click: link, right opens its own href", R.url == f"{right}/nested.html", R.url)

    # Nested same-origin iframes
    f1l, f1r = L.frame_locator("#frame1"), R.frame_locator("#frame1")
    f2l, f2r = f1l.frame_locator("iframe").first, f1r.frame_locator("iframe").first
    L.click("#btn-top"); f1l.locator("#btn-l1").click(); f2l.locator("#btn-l2").click(); L.wait_for_timeout(800)
    c.check("click: nested top / level 1 / level 2",
            (count(R.locator("#btn-top")), count(f1r.locator("#btn-l1")), count(f2r.locator("#btn-l2"))) == ("1", "1", "1"))
    f2l.locator("#text-l2").fill("hello L2"); L.wait_for_timeout(500)
    c.check("input: nested level 2 text field", f2r.locator("#text-l2").input_value() == "hello L2")
    for name, l_box, r_box, top in [("box-top div on the top page", L.locator("#box-top"), R.locator("#box-top"), 120),
                                    ("box in iframe level 1", f1l.locator("#box-l1"), f1r.locator("#box-l1"), 90),
                                    ("box in iframe level 2", f2l.locator("#box-l2"), f2r.locator("#box-l2"), 70)]:
        scroll_to(l_box, top); L.wait_for_timeout(400)
        c.check(f"scroll: {name}", scroll_top(r_box) == top, f"right {scroll_top(r_box)}")
    # (nested.html itself has no page scroll: its content fits the window)

    # Same-origin and cross-origin iframes
    t.open(f"{left}/cross_origin.html", f"{right}/cross_origin.html"); L.wait_for_timeout(1000)
    sl, sr = L.frame_locator("#frame-same"), R.frame_locator("#frame-same")
    cl, cr = L.frame_locator("#frame-cross"), R.frame_locator("#frame-cross")
    sl.locator("#btn-l2").click(); cl.locator("#btn-l2").click(); L.wait_for_timeout(800)
    c.check("click: same-origin and cross-origin frame",
            (count(sr.locator("#btn-l2")), count(cr.locator("#btn-l2"))) == ("1", "1"))
    cl.locator("#text-l2").fill("cross"); scroll_to(cl.locator("#box-l2"), 50); L.wait_for_timeout(500)
    c.check("input: cross-origin frame", cr.locator("#text-l2").input_value() == "cross")
    c.check("scroll: box in cross-origin frame", scroll_top(cr.locator("#box-l2")) == 50)

    # Form fields: text, textarea, select, radio, checkbox
    t.open(f"{left}/form.html", f"{right}/form.html")
    L.fill("#name", "Ala"); L.fill("#comment", "line 1\nline 2")
    L.select_option("#lang", index=1); L.click("#lvl-2"); L.click("#agree"); L.wait_for_timeout(600)
    got = (R.input_value("#name"), R.input_value("#comment"), R.input_value("#lang"),
           R.is_checked("#lvl-2"), R.is_checked("#agree"))
    want = ("Ala", "line 1\nline 2", L.input_value("#lang"), True, True)
    c.check("input: form name / textarea / select / radio / checkbox", got == want, f"{got} != {want}")


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
