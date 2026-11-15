from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    InvalidSessionIdException, NoSuchWindowException,
)
from urllib3.exceptions import MaxRetryError
import threading
import time
import json
import os
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable
from engine import MISSING_ELEMENT_WAIT_S, WINDOW_HEIGHT, WINDOW_POSITION_JS, WINDOW_WIDTH, Engine, right_window_x
from js_loader import load_js
from reports.model import BugDraft, BugReport
from reports.pdf_exporter import PdfExporter, pdf_path_for
from reports.reporter import BugReporter
from reports.repository import SqliteBugRepository

# Errors that mean the browser or chromedriver is gone, so retrying is pointless.
# ConnectionError covers ConnectionRefusedError when chromedriver has exited.
FATAL_DRIVER_ERRORS: tuple[type[BaseException], ...] = (
    InvalidSessionIdException, NoSuchWindowException, MaxRetryError, ConnectionError,
)
SYNC_GIVE_UP_AFTER_S: float = 30.0  # safety net: this long with only errors -> stop
SYNC_MAX_BACKOFF_S: float = 2.0


def is_driver_gone(exc: BaseException) -> bool:
    """True when exc means the session can't be used any more."""
    return isinstance(exc, FATAL_DRIVER_ERRORS)


def backoff_delay(consecutive_failures: int) -> float:
    """0.2, 0.4, 0.8, 1.6, 2.0, 2.0 ... seconds."""
    return min(0.1 * 2 ** consecutive_failures, SYNC_MAX_BACKOFF_S)


class SyncErrorBreaker:
    """Decides, after an error in a sync loop, whether to retry or stop."""

    def __init__(self, name: str, give_up_after_s: float = SYNC_GIVE_UP_AFTER_S) -> None:
        self.name = name
        self.give_up_after_s = give_up_after_s
        self.failures = 0
        self.first_failure_at = 0.0

    def success(self) -> None:
        """Call after a poll that worked; resets the error streak."""
        self.failures = 0

    def on_error(self, exc: BaseException) -> bool:
        """Log exc. Return True if the loop should stop; otherwise wait the back-off and return False."""
        if is_driver_gone(exc):
            print(f"{self.name} sync stopped, browser is gone: {type(exc).__name__}")
            return True
        if self.failures == 0:
            self.first_failure_at = time.monotonic()
        self.failures += 1
        if time.monotonic() - self.first_failure_at > self.give_up_after_s:
            print(f"{self.name} sync stopped after {self.give_up_after_s:.0f}s of errors: {exc}")
            return True
        print(f"{self.name} error #{self.failures} ({type(exc).__name__}), retrying")
        time.sleep(backoff_delay(self.failures))
        return False


# Scripts from js/ folder that run once per call (the trackers are loaded in selenium_worker)
FIND_SCROLLABLE_JS: str = load_js("find_scrollable.js")
FIND_IN_FRAMES_JS: str = load_js("find_in_frames.js")
TAKE_PENDING_JS: str = load_js("take_pending.js")
DRAG_REPLAY_JS: str = load_js("drag_replay.js")
VIDEO_NOTICE_JS: str = load_js("video_notice.js")

SHUTDOWN_SENTINEL = None  # put on SeleniumEngine.urls to make the worker quit the drivers and return
SHUTDOWN_TIMEOUT_S: float = 15.0  # how long stop() waits for the worker before quitting drivers itself


class SeleniumEngine:
    """The Selenium version as an Engine: one selenium_worker thread and its two drivers.

    Each instance has its own queue, drivers and quit flag, so after an engine
    switch a new instance starts clean, and the old run's sync threads keep
    their own (quit) drivers and stop.
    """
    name = "selenium"

    def __init__(self) -> None:
        self.urls: "Queue[tuple[str, str] | None]" = Queue()  # (left_url, right_url)
        self.drivers: "tuple[webdriver.Chrome, webdriver.Chrome] | None" = None  # set by the worker
        self._quit_lock = threading.Lock()
        self._quit = False
        # Non-daemon: the process waits for the worker to quit the drivers
        self._thread = threading.Thread(target=selenium_worker, args=(self,), daemon=False, name="selenium-worker")
        self._thread.start()

    def load(self, left_url: str, right_url: str) -> None:
        self.urls.put((left_url, right_url))

    def stop(self) -> None:
        self.urls.put(SHUTDOWN_SENTINEL)  # wakes the worker blocked on urls.get()
        self._thread.join(timeout=SHUTDOWN_TIMEOUT_S)
        if self._thread.is_alive():
            # The worker is stuck (e.g. in a slow driver.get); quitting the drivers from
            # here makes its pending call raise, so the thread ends.
            print("Selenium thread did not stop in time; quitting drivers from this thread")
        # Also covers a worker that died earlier with an exception and never quit them.
        self.quit_drivers()
        self._thread.join(timeout=5)

    def quit_drivers(self) -> None:
        """Close both browser windows and their chromedriver processes.
        Idempotent and thread-safe: the worker and stop() may both call it."""
        with self._quit_lock:
            if self._quit or self.drivers is None:  # None: not started yet, a later call quits them
                return
            self._quit = True
        for name, driver in zip(("left", "right"), self.drivers):
            try:
                driver.quit()
                print(f"Driver {name} quit")
            except Exception as exc:  # already gone, or chromedriver crashed
                print(f"Driver {name} quit failed: {type(exc).__name__}")

    def current_urls(self) -> tuple[str, str]:
        if self.drivers is None:
            return "", ""
        left, right = self.drivers
        return current_url(left), current_url(right)

    def take_screenshots(self, left_path: Path, right_path: Path) -> None:
        """Save a PNG of each browser window's visible page (reporter.TakeScreenshots).

        Raises instead of returning False, so BugReporter can tell that the
        pictures are missing: Selenium's save_screenshot only returns False when
        the file can't be written, and raises when the browser is gone.
        """
        if self.drivers is None:
            raise RuntimeError("The Selenium browsers are not running")
        for name, driver, path in zip(("left", "right"), self.drivers, (left_path, right_path)):
            if not driver.save_screenshot(str(path)):
                raise OSError(f"Could not write the {name} screenshot to {path}")


def current_url(driver: webdriver.Chrome) -> str:
    """The page a window shows now (after any link clicks), or "" if it's gone."""
    try:
        return driver.current_url
    except (WebDriverException, *FATAL_DRIVER_ERRORS):  # a closed browser raises MaxRetryError
        return ""


def align_right_window(driver_left: webdriver.Chrome, driver_right: webdriver.Chrome) -> None:
    """Move the right window so it touches the left one, where the window manager really put it.

    The left window is asked for x=0, but the window manager may move it (past
    a dock, for example), so its position is read back instead of assumed.
    """
    left_x, left_y, left_width = driver_left.execute_script(f"return {WINDOW_POSITION_JS}")
    driver_right.set_window_position(right_window_x(left_x, left_width), left_y)


def selenium_worker(engine: SeleniumEngine) -> None:
    """Main Selenium thread - waits for URLs on engine.urls, then runs synchronization.

    driver_left and driver_right are locals of this run: the nested sync
    functions keep this run's drivers, even after a switch starts a new run.
    """

    # Set up Chrome options
    options_left = Options()
    options_left.add_argument(f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}")
    options_left.add_argument("--window-position=0,0")

    options_right = Options()
    options_right.add_argument(f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}")
    options_right.add_argument(f"--window-position={WINDOW_WIDTH},0")  # moved next to the left one below

    # Only inside Docker: the container blocks the user namespaces Chromium's
    # sandbox needs, Docker's /dev/shm is only 64 MB, and there is no GPU
    # (/dev/dri), so GPU rendering draws fully transparent windows. On a normal
    # desktop the sandbox and GPU rendering stay on.
    if os.path.exists("/.dockerenv"):
        for options in (options_left, options_right):
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")

    # Set up the Chrome driver. With no path, Selenium uses chromedriver from
    # PATH (/usr/bin in the container) or Selenium Manager finds/downloads one.
    service = Service()
    driver_left = webdriver.Chrome(service=service, options=options_left)
    driver_right = webdriver.Chrome(service=service, options=options_right)
    engine.drivers = (driver_left, driver_right)
    align_right_window(driver_left, driver_right)

    time.sleep(1)

    # Wait for URL from UI
    print("Selenium thread: waiting for URL from UI...")
    url_to_test = engine.urls.get()  # blocks until URL is available
    if url_to_test is SHUTDOWN_SENTINEL:
        engine.quit_drivers()
        return
    print(f"Selenium thread: received URLs: {url_to_test}")

    # Function to find iframe and extract its src URL
    def find_iframe_src(driver, url, iframe_class):
        try:
            print(f"Opening URL: {url}")
            driver.get(url)

            # Wait for the iframe with the given class to be present
            print(f"Looking for iframe with class '{iframe_class}'...")
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, iframe_class))
            )
            print(f"Found iframe with class '{iframe_class}'.")

            # Extract the src attribute from the iframe
            iframe_src = iframe.get_attribute("src")
            if (iframe_src):
                print(f"Found iframe src: {iframe_src}")
                return iframe_src
            else:
                print("Iframe does not have a src attribute.")
                return None
        except TimeoutException:
            print(f"TimeoutException: Could not find iframe with class '{iframe_class}'.")
            return None
        except Exception as e:
            print(f"Error finding iframe: {e}")
            return None

    # Rise review pages wrap the course in iframe.player; open its src if found.
    # Otherwise (any other page) open the entered URL itself, and keep syncing.
    # Each window gets its own URL: two versions often live at different URLs.
    def open_in_both_panels(left_url: str, right_url: str) -> None:
        iframe_class = "player"
        left_src = find_iframe_src(driver_left, left_url, iframe_class)
        if left_src is None:
            # Both versions have the same structure: no player on the left
            # means none on the right, so skip a second 10 s wait
            print(f"No iframe '{iframe_class}' found; opening the entered URLs directly.")
            left_content, right_content = left_url, right_url
        elif right_url == left_url:
            left_content = right_content = left_src
        else:
            left_content = left_src
            right_content = find_iframe_src(driver_right, right_url, iframe_class) or right_url
        print(f"Opening URLs:\n left:  {left_content}\n right: {right_content}")
        driver_left.get(left_content)
        driver_right.get(right_content)

    open_in_both_panels(*url_to_test)


    # Function to dynamically find the scrollable element
    def get_scrollable_element(driver):
        try:
            # Try to find the scrollable element dynamically
            return driver.execute_script(FIND_SCROLLABLE_JS)
        except Exception as e:
            if is_driver_gone(e):
                raise  # let the sync loop decide to stop
            print(f"Error finding scrollable element: {e}")
            return None

    # Function to synchronize scrolling within the dynamically refreshed scrollable element
    def synchronize_scroll():
        breaker = SyncErrorBreaker("Scroll")
        while True:
            try:
                # Dynamically get the scrollable element in the left panel
                scrollable_element_left = get_scrollable_element(driver_left)
                if not scrollable_element_left:
                    print("Scrollable element not found in the left panel.")
                    time.sleep(0.5)
                    continue

                # Get the scroll position of the scrollable element in the left panel
                scroll_position = driver_left.execute_script("""
                    var element = arguments[0];
                    return element ? element.scrollTop : null;
                """, scrollable_element_left)
                # print(f"Left panel scroll position: {scroll_position}")

                if scroll_position is not None:
                    # Dynamically get the scrollable element in the right panel
                    scrollable_element_right = get_scrollable_element(driver_right)
                    if not scrollable_element_right:
                        print("Scrollable element not found in the right panel.")
                        time.sleep(0.5)
                        continue

                    # Set the scroll position of the scrollable element in the right panel
                    driver_right.execute_script("""
                        var element = arguments[0];
                        if (element) element.scrollTop = arguments[1];
                    """, scrollable_element_right, scroll_position)
                breaker.success()
            except Exception as e:
                if breaker.on_error(e):
                    break
                continue
            time.sleep(0.1)

    # Click, input and in-iframe scroll tracker (js/click_tracker.js)
    click_tracking_script = load_js("xpath.js", "click_tracker.js")

    # Find an element on the right, inside nested same-origin iframes if
    # needed, and run action_js on it (as `el`). Extra args are arguments[2]...
    # Returns False if an iframe or the element is not found; otherwise True,
    # or the value action_js returns (e.g. "return el.href;").
    def run_on_right(frame_xpaths: list[str], xpath: str, action_js: str, *args) -> Any:
        return driver_right.execute_script(
            FIND_IN_FRAMES_JS + action_js + "\nreturn true;", frame_xpaths, xpath, *args)

    # run_on_right, retried every 100 ms for up to MISSING_ELEMENT_WAIT_S,
    # because the right page may still be loading. Returns False if the
    # element never shows up.
    def wait_and_run_on_right(frame_xpaths: list[str], xpath: str, action_js: str) -> Any:
        deadline = time.monotonic() + MISSING_ELEMENT_WAIT_S
        while True:
            result = run_on_right(frame_xpaths, xpath, action_js)
            if result or time.monotonic() >= deadline:
                return result
            time.sleep(0.1)

    # The clicked element is missing on the right: hand its name to the
    # toolbar, which opens a prefilled Report bug form
    def report_missing_element() -> None:
        name = driver_left.execute_script("return window.sessionStorage.getItem('lastClickedName') || '';")
        missing_elements.put(name)

    # Function to synchronize clicks and handle non-URL elements
    def synchronize_clicks():
        last_synced_url = None
        breaker = SyncErrorBreaker("Click")

        while True:
            try:
                # URL clicks (unchanged)
                clicked_url = driver_left.execute_script("return window.sessionStorage.getItem('lastClickedUrl') || null;")
                if clicked_url and clicked_url != last_synced_url:
                    last_synced_url = clicked_url
                    print(f"-------->Click detected (URL): \n {clicked_url}")
                    # The right version may live at a different URL, so open the
                    # href of the same link (same XPath) in the right window
                    link_xpath = driver_left.execute_script("return window.sessionStorage.getItem('lastClickedLinkXPath');")
                    right_url = wait_and_run_on_right([], link_xpath, "return el.href;")
                    if not right_url:
                        print(f"Link {link_xpath} not found on the right; right window stays")
                        report_missing_element()  # before the left navigates: it reads the left's sessionStorage
                    driver_left.get(clicked_url)
                    if right_url:
                        driver_right.get(right_url)
                    time.sleep(1)
                    inject_click_tracking(driver_left)
                    inject_click_tracking(driver_right)
                    driver_left.execute_script("window.sessionStorage.removeItem('lastClickedUrl'); window.sessionStorage.removeItem('lastClickedLinkXPath');")

                # Non-URL clicks using XPath
                clicked_xpath = driver_left.execute_script("return window.sessionStorage.getItem('lastClickedElementXPath') || null;")
                if clicked_xpath:
                    frame_xpaths = json.loads(driver_left.execute_script("return window.sessionStorage.getItem('lastClickedFrameXPaths') || '[]';"))
                    print(f"---------->Click detected (non-URL, xpath):\n {clicked_xpath}" + (f"\n in iframes {frame_xpaths}" if frame_xpaths else ""))

                    try:
                        if not wait_and_run_on_right(frame_xpaths, clicked_xpath, "el.click();"):
                            print(f"Could not click {clicked_xpath} in iframes {frame_xpaths}: not found on the right")
                            report_missing_element()
                    except Exception as e:
                        if is_driver_gone(e):
                            raise  # let the outer handler stop the loop
                        print(f"Could not click {clicked_xpath}\nError: {e}")

                    driver_left.execute_script("window.sessionStorage.removeItem('lastClickedElementXPath'); window.sessionStorage.removeItem('lastClickedFrameXPaths');")
                breaker.success()
            except Exception as e:
                if breaker.on_error(e):
                    break
                continue

            time.sleep(0.1)

    # Function to inject JavaScript on a given driver instance
    def inject_click_tracking(driver):
        driver.execute_script(click_tracking_script)

    # Inject click tracking script initially
    inject_click_tracking(driver_left)

    # Start the initial scroll synchronization thread
    scroll_thread = threading.Thread(target=synchronize_scroll, daemon=True)
    scroll_thread.start()

    # Start the click synchronization thread
    click_thread = threading.Thread(target=synchronize_clicks, daemon=True)
    click_thread.start()

    # Copy typed text and dropdown choices from left to right
    def synchronize_inputs():
        breaker = SyncErrorBreaker("Input")
        while True:
            try:
                # Read and remove in one script: page JS can't run in between,
                # so a keystroke typed right now is not lost
                data = driver_left.execute_script(TAKE_PENDING_JS, "pendingInputs")
                # One {frames, xpath, value} per field changed since the last poll
                for change in json.loads(data or '{}').values():
                    # Set the value, then fire the events the page listens to
                    found = run_on_right(change['frameXPaths'], change['xpath'], """
                        el.value = arguments[2];
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    """, change['value'])
                    if not found:
                        print(f"Input sync: not found on the right: {change['xpath']} in iframes {change['frameXPaths']}")
                breaker.success()
            except Exception as e:
                if breaker.on_error(e):
                    break
                continue
            time.sleep(0.1)

    input_thread = threading.Thread(target=synchronize_inputs, daemon=True)
    input_thread.start()

    # Copy scroll positions inside iframes from left to right
    # (the top page is handled by synchronize_scroll)
    def synchronize_frame_scrolls():
        breaker = SyncErrorBreaker("Frame scroll")
        while True:
            try:
                # Read and remove in one script, like synchronize_inputs
                data = driver_left.execute_script(TAKE_PENDING_JS, "pendingScrolls")
                # One {frameXPaths, xpath, top} per element scrolled since the last poll
                for scroll in json.loads(data or '{}').values():
                    found = run_on_right(scroll['frameXPaths'], scroll['xpath'], "el.scrollTop = arguments[2];", scroll['top'])
                    if not found:
                        print(f"Frame scroll: not found on the right: {scroll['xpath']} in iframes {scroll['frameXPaths']}")
                breaker.success()
            except Exception as e:
                if breaker.on_error(e):
                    break
                continue
            time.sleep(0.1)

    frame_scroll_thread = threading.Thread(target=synchronize_frame_scrolls, daemon=True)
    frame_scroll_thread.start()

    # --- new: compact drag tracking script (inject into left frame) ---
    drag_tracking_script = load_js("xpath.js", "drag_tracker.js")

    def inject_drag_tracking(driver):
        try:
            driver.execute_script(drag_tracking_script)
            ok = False
            try:
                ok = driver.execute_script("return !!window.__dragTracker;")
            except Exception:
                ok = False
            print(f"inject_drag_tracking: installed={ok}")
            return ok
        except Exception as e:
            print(f"inject_drag_tracking error: {e}")
            return False

    # apply drag on right by dispatching pointer events to the matched element
    def apply_drag_on_right(drag):
        try:
            js = DRAG_REPLAY_JS
            result = driver_right.execute_script(js, drag['xpath'], drag['startX'], drag['startY'], drag['lastX'], drag['lastY'])
            # add small settle time after drag completes
            time.sleep(1)
            return result
        except Exception as e:
            if is_driver_gone(e):
                raise  # let synchronize_drag decide to stop
            return {"ok": False, "msg": str(e)}

    # thread that polls left sessionStorage.lastDrag and mirrors on right
    def synchronize_drag():
        last_seen_id = None
        breaker = SyncErrorBreaker("Drag")
        while True:
            try:
                data = driver_left.execute_script("return window.sessionStorage.getItem('lastDrag') || null;")
                if data:
                    try:
                        drag = json.loads(data)
                    except Exception:
                        drag = None
                    if drag:
                        drag_id = drag.get('id')
                        # mirror while active and once on ended
                        if drag.get('active') or (drag.get('ended') and drag_id != last_seen_id):
                            res = apply_drag_on_right(drag)
                            print("mirror drag:", res)
                            if drag.get('ended'):
                                last_seen_id = drag_id
                breaker.success()
            except Exception as e:
                if breaker.on_error(e):
                    break
                continue
            # slightly longer delay to avoid rapid re-firing
            time.sleep(0.06)

    # After pages are loaded and click tracking injected, also inject drag tracking and start thread
    inject_drag_tracking(driver_left)
    inject_drag_tracking(driver_right)  # optional: keeps right page aware if needed

    drag_thread = threading.Thread(target=synchronize_drag, daemon=True)
    drag_thread.start()

    # --- new: video hover detection with popup message on right ---
    video_hover_tracking_script = load_js("xpath.js", "video_hover.js")

    def inject_video_hover_tracking(driver):
        try:
            driver.execute_script(video_hover_tracking_script)
            ok = False
            try:
                ok = driver.execute_script("return !!window.__videoHoverTracker;")
            except Exception:
                ok = False
            print(f"inject_video_hover_tracking: installed={ok}")
            return ok
        except Exception as e:
            print(f"inject_video_hover_tracking error: {e}")
            return False

    # show popup message on right when video hover detected on left
    def show_video_notice_on_right(visible=True):
        try:
            js = VIDEO_NOTICE_JS
            return driver_right.execute_script(js, visible)
        except Exception as e:
            if is_driver_gone(e):
                raise  # let monitor_video_hover decide to stop
            return {"ok": False, "msg": str(e)}

    # polling thread: detect video hover on left and show/hide popup on right
    def monitor_video_hover():
        last_enter_ts = None
        is_hovering = False
        breaker = SyncErrorBreaker("Video")
        while True:
            try:
                # check for enter event
                enter_data = driver_left.execute_script("return window.sessionStorage.getItem('videoHoverEnter') || null;")
                if enter_data:
                    try:
                        enter = json.loads(enter_data)
                        if enter.get('timestamp') != last_enter_ts:
                            last_enter_ts = enter.get('timestamp')
                            is_hovering = True
                            print("Video hover detected on left — showing notice on right")
                            show_video_notice_on_right(True)
                    except Exception as e:
                        if is_driver_gone(e):
                            raise
                
                # check for leave event
                leave_data = driver_left.execute_script("return window.sessionStorage.getItem('videoHoverLeave') || null;")
                if leave_data and is_hovering:
                    try:
                        is_hovering = False
                        print("Video hover ended — hiding notice on right")
                        show_video_notice_on_right(False)
                        driver_left.execute_script("window.sessionStorage.removeItem('videoHoverLeave');")
                    except Exception as e:
                        if is_driver_gone(e):
                            raise
                breaker.success()
            except Exception as e:
                if breaker.on_error(e):
                    break
                continue
            time.sleep(0.1)

    # inject and start video hover monitoring
    inject_video_hover_tracking(driver_left)

    video_hover_thread = threading.Thread(target=monitor_video_hover, daemon=True)
    video_hover_thread.start()

    # Load/Reload: each URL from the UI reloads both panels. The sync threads
    # keep running; only the scripts injected into the pages need reinstalling.
    while True:
        url_to_test = engine.urls.get()
        if url_to_test is SHUTDOWN_SENTINEL:
            engine.quit_drivers()  # the daemon sync threads then stop on InvalidSessionId
            return
        print(f"Selenium thread: received URLs: {url_to_test}")
        open_in_both_panels(*url_to_test)
        inject_click_tracking(driver_left)
        inject_drag_tracking(driver_left)
        inject_drag_tracking(driver_right)
        inject_video_hover_tracking(driver_left)

# ---------------------------------------------------------------------------
# The app: the toolbar sends (left, right, engine) on Load; the main thread
# owns the engines and switches them, so a slow stop() never blocks the toolbar.


def start_playwright() -> Engine:
    from pw_tester import PwEngine  # imported only when chosen: Selenium works without Playwright
    return PwEngine(on_missing_element=missing_elements.put)


ENGINES: dict[str, Callable[[], Engine]] = {"Selenium": SeleniumEngine, "Playwright": start_playwright}

app_queue: "Queue[tuple[str, str, str] | None]" = Queue()  # (left_url, right_url, engine), None = quit
# Names of elements clicked on the Source but missing on the Target; the toolbar
# opens a prefilled Report bug form for each (Phase 5 item 6)
missing_elements: "Queue[str]" = Queue()
shutdown_requested = threading.Event()
active_engine: Engine | None = None  # set by the main thread only


def request_shutdown() -> None:
    """Called from the UI (Close) or on Ctrl+C. Idempotent."""
    if shutdown_requested.is_set():
        return
    shutdown_requested.set()
    app_queue.put(None)  # wakes the main loop


def on_load_url(left_url: str, right_url: str, engine_name: str = "Selenium") -> None:
    """Called by the UI when Load is clicked. An empty right URL means: same as left."""
    if not left_url:
        print("No URL provided")
        return
    print(f"UI sent URLs to the {engine_name} engine: {(left_url, right_url or left_url)}")
    app_queue.put((left_url, right_url or left_url, engine_name))


def require_engine() -> Engine:
    engine = active_engine
    if engine is None:
        raise RuntimeError("No browsers are running yet; click Load first")
    return engine


# Bug reports go to bug_data/bugs.db, screenshots to bug_data/screenshots/.
# The screenshots come from whichever engine is running when the button is clicked.
bug_reporter = BugReporter(SqliteBugRepository(),
                           lambda left, right: require_engine().take_screenshots(left, right))


def on_screenshot() -> str:
    """Toolbar Screenshot: save a pair of PNGs with no bug report. Runs off the Tk thread."""
    left, right = bug_reporter.screenshot()
    print(f"Screenshots saved:\n {left}\n {right}")
    return "Saved ✓"


def current_urls() -> tuple[str, str]:
    """The pages open in the two windows, to prefill the Report bug form. Runs off the Tk thread."""
    engine = active_engine
    return engine.current_urls() if engine else ("", "")


def save_bug(draft: BugDraft) -> tuple[BugReport, str]:
    """Store the report with the form's URLs and both screenshots; also the text the toolbar shows."""
    engine = active_engine
    report = bug_reporter.report(BugReport(
        engine=engine.name if engine else "none", source_url=draft.source_url, target_url=draft.target_url,
        summary=draft.summary, description=draft.description, severity=draft.severity,
    ))
    if report.source_screenshot is None:
        print(f"Bug {report.id:05d} saved WITHOUT screenshots (see the error above)")
        return report, f"Bug {report.id:05d} ⚠"
    print(f"Bug {report.id:05d} saved: {draft.summary}\n {report.source_screenshot}\n {report.target_screenshot}")
    return report, f"Bug {report.id:05d} ✓"


def on_report_bug(draft: BugDraft) -> str:
    """Report bug form's Save. Runs off the Tk thread."""
    return save_bug(draft)[1]


def on_report_bug_pdf(draft: BugDraft) -> tuple[str, Path | None]:
    """Report bug form's "Save and create PDF": save, then write bug_data/pdf/bug_00007.pdf.

    Returns the PDF's path (None if it failed; the bug is saved anyway). The
    toolbar then asks, on the Tk thread, where to save a copy.
    """
    report, message = save_bug(draft)
    pdf = pdf_path_for(report)
    try:
        PdfExporter().export([report], pdf)
    except Exception as exc:
        print(f"Bug {report.id:05d}: PDF failed: {type(exc).__name__}: {exc}")
        return message, None
    print(f"Bug {report.id:05d} PDF: {pdf}")
    return message, pdf


def run_app() -> None:
    """Main thread: start, switch and stop engines as Load requests arrive.

    The engine starts on the first Load, so the windows of the engine not
    chosen are never opened. A Load with another engine quits the current
    browser pair, then starts the chosen one.
    """
    global active_engine
    try:
        while True:
            try:
                request = app_queue.get(timeout=1)  # the timeout keeps Ctrl+C responsive
            except Empty:
                continue
            if request is None:
                break
            left_url, right_url, engine_name = request
            if active_engine is None or active_engine.name != engine_name.lower():
                if active_engine is not None:
                    print(f"Switching engine: {active_engine.name} -> {engine_name.lower()}")
                    old, active_engine = active_engine, None
                    old.stop()
                print(f"Starting the {engine_name} engine...")
                active_engine = ENGINES[engine_name]()
            active_engine.load(left_url, right_url)
    except KeyboardInterrupt:
        pass
    print("Exiting...")
    if active_engine is not None:
        active_engine.stop()


if __name__ == "__main__":
    print("Starting UI thread...")
    from floating_ui import start_ui_in_thread
    start_ui_in_thread(on_load_callback=on_load_url, on_close_callback=request_shutdown,
                       on_screenshot_callback=on_screenshot, on_report_callback=on_report_bug,
                       engine_names=list(ENGINES), on_report_pdf_callback=on_report_bug_pdf,
                       bug_repository=bug_reporter.repository, current_urls_callback=current_urls,
                       missing_element_queue=missing_elements)
    run_app()
