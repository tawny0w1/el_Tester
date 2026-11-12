"""Playwright version of the tester (Phase 4): clicks, inputs, scroll, Rise
review links, screenshots.

    python3 pw_tester.py <left_url> [right_url] [--headless]

Clicks, typing and scrolls in the left window are pushed to Python by a
binding and replayed on the element at the same XPath, in the same frame, in
the right window.
Everything runs on one thread: Playwright's sync API is bound to it.
PwEngine wraps PwTester in that thread for el_tester.py (the toolbar).
"""
import argparse
import threading
from concurrent.futures import Future
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable

from playwright.sync_api import Browser, BrowserContext, Frame, Page, Playwright, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from js_loader import load_js

SYSTEM_CHROMIUM = "/usr/bin/chromium"  # no Playwright browser download in the container
REPLAY_TIMEOUT_MS = 2000  # how long the right waits for a missing element or frame
SCREENSHOT_TIMEOUT_MS = 10000  # per window; Playwright waits for web fonts before capturing
# Playwright wraps each init script in its own scope, so getXPath is not a
# global there: evaluate calls bring their own copy
GET_XPATH_FN = "el => {\n" + load_js("xpath.js") + "\nreturn getXPath(el);\n}"

# How the right window replays each action type of js/pw_tracker.js:
# (el, action) => ..., run in the right frame on the element at action.xpath.
# A new action type is one more entry here and one more listener in the JS.
REPLAY_JS: dict[str, str] = {
    # el.click(), like the Selenium version: no scrolling the right window,
    # and no wait for the element to be "clickable"
    "click": "el => el.click()",
    "input": """(el, a) => {
        el.value = a.value;
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""",
    "scroll": "(el, a) => { el.scrollTop = a.top; }",
}
QUIET_ACTIONS = {"scroll"}  # too frequent to print

# Review360 pages show the course in an iframe.player, added by JS about 2.5 s
# after "load" (measured 2026-11-10). Waiting stops when the player is there,
# or PLAYER_GRACE_MS after "load" without one (any non-Rise page).
PLAYER_GRACE_MS = 5000
PLAYER_MAX_WAIT_MS = 20000  # a page that never finishes loading
FIND_PLAYER_JS = """grace => {
    const player = document.querySelector('iframe.player');
    if (player && player.src) return {src: player.src};
    const nav = performance.getEntriesByType('navigation')[0];
    if (nav && nav.loadEventEnd > 0 && performance.now() - nav.loadEventEnd > grace) return {src: null};
    return null;  // keep waiting
}"""


class PwTester:
    """Two Chromium windows; the left page's actions are replayed on the right."""

    def __init__(self, playwright: Playwright, headless: bool = False) -> None:
        self._browsers: list[Browser] = [self._launch(playwright, x, headless) for x in (0, 990)]
        # no_viewport: the page follows the window size, as in the Selenium version
        left_context: BrowserContext = self._browsers[0].new_context(no_viewport=True)
        left_context.expose_binding("reportAction", self._on_action)
        left_context.add_init_script(script=load_js("xpath.js", "pw_tracker.js"))
        self.left: Page = left_context.new_page()
        self.right: Page = self._browsers[1].new_context(no_viewport=True).new_page()

    @staticmethod
    def _launch(playwright: Playwright, x: int, headless: bool) -> Browser:
        args = [f"--window-position={x},0", "--window-size=930,1080"]
        ignored_defaults: list[str] = []
        if Path("/.dockerenv").exists():  # same reasons as selenium_worker
            args += ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            # Playwright adds --enable-unsafe-swiftshader by default. Together with
            # --disable-gpu, a headed window then draws no frames: it stays
            # invisible, and pages that wait for a frame (Review360) hang.
            # Headless is not affected. Found 2026-11-10.
            ignored_defaults.append("--enable-unsafe-swiftshader")
        exe = SYSTEM_CHROMIUM if Path(SYSTEM_CHROMIUM).exists() else None
        return playwright.chromium.launch(executable_path=exe, headless=headless, args=args,
                                          ignore_default_args=ignored_defaults)

    def open(self, left_url: str, right_url: str = "") -> None:
        """Open each window's URL; for a Review360 link, the course inside it.

        The course is unwrapped (its iframe.player src opened in the whole
        window), as in the Selenium version, so it gets the full width.
        Right empty = same as left.
        """
        right_url = right_url or left_url
        left_src = self._player_src(self.left, left_url)
        if left_src is None:
            # Same structure in both versions: no player on the left means
            # none on the right, so skip a second wait. Left is already open.
            print("No iframe.player; opening the entered URLs directly.")
            self.right.goto(right_url)
            return
        right_src = left_src if right_url == left_url else self._player_src(self.right, right_url)
        print(f"Opening courses:\n left:  {left_src}\n right: {right_src or right_url}")
        self.left.goto(left_src)
        if right_src:
            self.right.goto(right_src)
        else:  # the right stays on its review page: one iframe deeper than the left
            print("No iframe.player on the right; it stays on its review page, so sync won't match.")

    @staticmethod
    def _player_src(page: Page, url: str) -> str | None:
        """Open url in page and return its iframe.player src, or None."""
        page.goto(url)
        try:
            found = page.wait_for_function(FIND_PLAYER_JS, arg=PLAYER_GRACE_MS,
                                           timeout=PLAYER_MAX_WAIT_MS, polling=200)
            return found.json_value()["src"]
        except PlaywrightTimeoutError:
            return None

    def _on_action(self, source: dict, action: dict) -> None:
        """Called by the left page's window.reportAction, on this thread."""
        # Everything inside try: an exception here only rejects the JS promise
        # of reportAction, so it would never show up in this terminal
        try:
            frame_xpaths = self._frame_xpaths(source["frame"])
            if action["type"] not in QUIET_ACTIONS:
                print(f"{action['type']}: {action['xpath']}" + (f" in iframes {frame_xpaths}" if frame_xpaths else ""))
            frame = self._right_frame(frame_xpaths)
            frame.locator(f"xpath={action['xpath']}").evaluate(
                REPLAY_JS[action["type"]], action, timeout=REPLAY_TIMEOUT_MS)
        except Exception as e:  # a missing element must not stop the sync
            print(f"Could not replay {action.get('type')} on {action.get('xpath')} on the right: {e}")

    @staticmethod
    def _frame_xpaths(frame: Frame) -> list[str]:
        """XPaths of the iframes around a left frame, outer to inner. [] on the top page.

        Each iframe element is named by getXPath, run in its parent frame. Unlike
        the JS getFrameXPaths, this also crosses cross-origin frames.
        """
        path: list[str] = []
        while frame.parent_frame:
            path.insert(0, frame.frame_element().evaluate(GET_XPATH_FN))
            frame = frame.parent_frame
        return path

    def _right_frame(self, frame_xpaths: list[str]) -> Frame:
        """Walk the same iframes in the right page, outer to inner."""
        frame = self.right.main_frame
        for xpath in frame_xpaths:
            inner = frame.locator(f"xpath={xpath}").element_handle(timeout=REPLAY_TIMEOUT_MS).content_frame()
            if inner is None:
                raise LookupError(f"{xpath} is not a loaded iframe")
            frame = inner
        return frame

    def take_screenshots(self, left_path: Path, right_path: Path) -> None:
        """Save a PNG of each window's visible page, like Selenium's save_screenshot.

        Raises if a page can't be captured, so BugReporter records the bug
        without screenshots instead of with missing files.
        """
        for page, path in ((self.left, left_path), (self.right, right_path)):
            page.screenshot(path=str(path), timeout=SCREENSHOT_TIMEOUT_MS)

    def wait_until_closed(self) -> None:
        """Block until the left window closes; bindings run while waiting."""
        self.left.wait_for_event("close", timeout=0)

    def close(self) -> None:
        for browser in self._browsers:
            browser.close()


COMMAND_POLL_MS = 50  # PwEngine: how often its thread checks for work from other threads
STOP_TIMEOUT_S = 15.0
CALL_TIMEOUT_S = 10.0  # current_urls: waits behind a running open(), which can take ~25 s at worst
SCREENSHOT_WAIT_S = 60.0  # take_screenshots: may wait behind open() (~25 s), plus 2 x SCREENSHOT_TIMEOUT_MS

Task = tuple[Callable[[PwTester], Any], "Future[Any]"]


class PwEngine:
    """The Playwright version as an Engine (engine.py), for el_tester.py.

    PwTester lives on this engine's own thread, because Playwright's sync API
    only works on the thread that started it. Other threads (the app, the
    toolbar's buttons) hand it work as functions of the PwTester and get the
    result through a Future.
    """
    name = "playwright"

    def __init__(self, headless: bool = False) -> None:
        self._tasks: "Queue[Task | None]" = Queue()  # None = stop
        self._thread = threading.Thread(target=self._run, args=(headless,), daemon=True, name="playwright")
        self._thread.start()

    def _run(self, headless: bool) -> None:
        with sync_playwright() as p:
            tester = PwTester(p, headless=headless)
            try:
                while True:
                    try:
                        task = self._tasks.get_nowait()
                    except Empty:
                        # A short wait in Playwright, not time.sleep: the left
                        # page's reportAction bindings only run while this
                        # thread is inside a Playwright call
                        tester.left.wait_for_timeout(COMMAND_POLL_MS)
                        continue
                    if task is None:
                        break
                    fn, future = task
                    try:
                        future.set_result(fn(tester))
                    except Exception as e:  # e.g. a URL that doesn't load; the engine keeps running
                        print(f"Playwright: {type(e).__name__}: {e}")
                        future.set_exception(e)
            except Exception as e:  # e.g. the user closed a browser window
                print(f"Playwright engine stopped: {type(e).__name__}: {e}")
            finally:
                try:
                    tester.close()
                except Exception:
                    pass  # already closed
                print("Playwright browsers closed")

    def _submit(self, fn: Callable[[PwTester], Any]) -> "Future[Any]":
        if not self._thread.is_alive():
            raise RuntimeError("The Playwright browsers are not running")
        future: "Future[Any]" = Future()
        self._tasks.put((fn, future))
        return future

    def load(self, left_url: str, right_url: str) -> None:
        self._submit(lambda t: t.open(left_url, right_url))  # no wait: errors are printed by _run

    def stop(self) -> None:
        self._tasks.put(None)
        self._thread.join(timeout=STOP_TIMEOUT_S)
        if self._thread.is_alive():
            print("Playwright thread did not stop in time")

    def current_urls(self) -> tuple[str, str]:
        try:
            return self._submit(lambda t: (t.left.url, t.right.url)).result(timeout=CALL_TIMEOUT_S)
        except Exception:
            return "", ""

    def take_screenshots(self, left_path: Path, right_path: Path) -> None:
        """Called from the toolbar's worker threads: runs on the engine's thread, waits for it."""
        self._submit(lambda t: t.take_screenshots(left_path, right_path)).result(timeout=SCREENSHOT_WAIT_S)


def main() -> None:
    parser = argparse.ArgumentParser(description="Playwright click sync prototype")
    parser.add_argument("left_url")
    parser.add_argument("right_url", nargs="?", default="", help="empty = same as left")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    with sync_playwright() as p:
        tester = PwTester(p, headless=args.headless)
        try:
            tester.open(args.left_url, args.right_url)
            tester.wait_until_closed()
        finally:
            tester.close()


if __name__ == "__main__":
    main()
