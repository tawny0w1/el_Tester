"""Check of the Playwright engine on a real Review360 course (needs internet).

Runs PwEngine on its own thread, as el_tester.run_app does. The review link is
unwrapped (both windows open the course in iframe.player), START COURSE and a
scroll in the left window must reach the right one, and take_screenshots must
save two non-blank pictures of the same lesson. With --headed it also
checks that both windows draw frames: in the container, Playwright's default
--enable-unsafe-swiftshader plus --disable-gpu once left headed windows
invisible and Review360 hanging (fixed in PwTester._launch).

    cd selenium_el_tester
    python3 tests/pw_review360.py --headed         # the real case: visible windows
    python3 tests/pw_review360.py                  # headless
    python3 tests/pw_review360.py --url <review link>

About 20 s. Exit code 0 when every check passed.
"""
import argparse
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from helpers import REVIEW_URL, Checks
from pw_tester import PwEngine, PwTester

# A frame is drawn within 1.5 s, or the window draws nothing
FRAME_DRAWN_JS = """new Promise(r => {
    const t = setTimeout(() => r(false), 1500);
    requestAnimationFrame(() => { clearTimeout(t); r(true); });
})"""
# Sum of all scroll positions on the page: Rise may scroll the page or an inner element
TOTAL_SCROLL_JS = """Math.round(document.scrollingElement.scrollTop
    + [...document.querySelectorAll('*')].reduce((sum, el) => sum + el.scrollTop, 0))"""


def run(engine: PwEngine, url: str, headed: bool, c: Checks) -> None:
    def call(fn, timeout: float = 15):  # run fn(tester) on the engine's thread
        return engine._submit(fn).result(timeout=timeout)

    started = time.time()
    engine.load(url, url)
    urls = call(lambda t: (t.left.url, t.right.url), timeout=60)  # waits behind open()
    print(f"open() took {time.time() - started:.1f} s")
    c.check("unwrapped: both windows open the course itself",
            "articulateusercontent" in urls[0] and urls[0] == urls[1], urls)
    if headed:
        c.check("both windows draw frames",
                call(lambda t: (t.left.evaluate(FRAME_DRAWN_JS), t.right.evaluate(FRAME_DRAWN_JS))) == (True, True))

    call(lambda t: t.left.get_by_text("START COURSE").first.click())
    time.sleep(3)
    urls = engine.current_urls()
    c.check("click: START COURSE, right follows to the lesson", urls[0] == urls[1] and "#/" in urls[0], urls)

    def wheel(t: PwTester) -> None:
        t.left.mouse.move(400, 500)
        t.left.mouse.wheel(0, 900)
    call(wheel)
    time.sleep(1.5)
    tops = call(lambda t: [page.evaluate(TOTAL_SCROLL_JS) for page in (t.left, t.right)])
    c.check("scroll: lesson", tops[0] > 0 and tops[0] == tops[1], tops)

    # Screenshots, as the toolbar takes them: from another thread, through the engine
    shots = Path(tempfile.mkdtemp(prefix="pw_review360_"))
    engine.take_screenshots(shots / "left.png", shots / "right.png")
    left, right = (Image.open(shots / name).convert("RGB") for name in ("left.png", "right.png"))
    blank = [name for name, im in (("left", left), ("right", right)) if max(ImageStat.Stat(im).stddev) < 5]
    c.check("screenshots: both saved and not blank", not blank, f"blank: {blank}, sizes {left.size} {right.size}")
    # Same lesson, same scroll: the two pictures should be (almost) the same
    diff = ImageStat.Stat(ImageChops.difference(left, right)).mean
    c.check("screenshots: left and right show the same view", left.size == right.size and max(diff) < 10,
            f"mean difference {[round(d, 1) for d in diff]}")
    print(f"Screenshots kept for a look: {shots}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="visible windows instead of headless")
    parser.add_argument("--url", default=REVIEW_URL, help="Review360 link")
    args = parser.parse_args()
    c = Checks()
    engine = PwEngine(headless=not args.headed)
    try:
        run(engine, args.url, args.headed, c)
    except Exception as e:
        c.check(f"no error ({type(e).__name__}: {e})", False)
    finally:
        engine.stop()
    return c.exit_code()


if __name__ == "__main__":
    sys.exit(main())
