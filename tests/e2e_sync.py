"""End-to-end regression test for el_tester.py.

Runs the real app with headless browsers and no toolbar, does scripted actions
in the left window and checks that the right window followed. The left loads
the fixtures from localhost, the right from 127.0.0.1 (two different URLs).

    cd selenium_el_tester
    python3 tests/e2e_sync.py            # test this checkout
    python3 tests/e2e_sync.py <dir>      # test another copy, e.g. an old version

Takes about a minute. Exit code 0 when every check passed.
"""
import importlib
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from typing import Callable

PROJECT_DIR = Path(__file__).resolve().parent.parent
PORT = 8765


def install_test_doubles() -> None:
    """No Tk toolbar, and every Chrome window headless."""
    fake_ui = types.ModuleType("floating_ui")
    fake_ui.start_ui_in_thread = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules["floating_ui"] = fake_ui

    from selenium.webdriver.chrome.options import Options
    original_init = Options.__init__

    def headless_init(self: Options, *args: object, **kwargs: object) -> None:
        original_init(self, *args, **kwargs)
        self.add_argument("--headless=new")

    Options.__init__ = headless_init  # type: ignore[method-assign]


class E2ETest:
    """Starts el_tester in a thread and checks the sync features one by one."""

    def __init__(self, app_dir: Path) -> None:
        sys.path.insert(0, str(app_dir))
        install_test_doubles()
        # run_app is el_tester's main loop; the Selenium engine starts on the first load()
        self.app = importlib.import_module("el_tester")
        self.app_thread = threading.Thread(target=self.app.run_app, daemon=True)
        self.app_thread.start()
        self.left = self.right = None  # the Selenium drivers, set by the first load()
        self.results: list[tuple[str, bool]] = []

    def check(self, name: str, condition: Callable[[], bool], timeout: float = 4.0) -> None:
        """Wait up to timeout for condition to be true; record PASS or FAIL."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                if condition():
                    self.results.append((name, True))
                    print("PASS", name)
                    return
            except Exception:
                pass  # e.g. the page is still loading
            time.sleep(0.2)
        self.results.append((name, False))
        print("FAIL", name)

    def load(self, page: str) -> None:
        """Click Load with the left on localhost and the right on 127.0.0.1."""
        self.app.on_load_url(f"http://localhost:{PORT}/{page}", f"http://127.0.0.1:{PORT}/{page}", "Selenium")
        while self.left is None:  # first load: wait until the engine has started its drivers
            engine = self.app.active_engine
            if engine is not None and engine.drivers is not None:
                self.left, self.right = engine.drivers
            time.sleep(0.2)
        L, R = self.left, self.right
        # About 10 s: the app first waits for a Rise iframe.player
        self.check(f"load {page}", lambda: R.current_url.endswith(page) and L.current_url.endswith(page)
                   and L.execute_script("return !!window.__dragTracker"), timeout=20)
        time.sleep(1)

    def run(self) -> bool:
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.by import By
        self.load("index.html")  # starts the Selenium engine, so the drivers exist after it
        L, R = self.left, self.right

        L.execute_script("window.scrollTo(0, 300)")
        self.check("page scroll", lambda: R.execute_script("return document.scrollingElement.scrollTop") == 300)

        L.find_element(By.ID, "btn-a").click()
        self.check("top-page click", lambda: R.find_element(By.ID, "btn-a").text == L.find_element(By.ID, "btn-a").text
                   and "1" in R.find_element(By.ID, "btn-a").text)

        # Drag: the same piece on both pages; the right records the pointer events it gets
        add_piece = """var p = document.createElement('div'); p.id = 'piece'; p.className = 'matching-interaction-piece';
        p.style.cssText = 'position:fixed;top:100px;left:100px;width:80px;height:40px;background:orange;z-index:9999';
        document.body.appendChild(p); window.__got = [];
        p.addEventListener('pointerdown', e => window.__got.push(e.type));
        p.addEventListener('pointerup', e => window.__got.push(e.type));"""
        L.execute_script(add_piece)
        R.execute_script(add_piece)
        ActionChains(L).drag_and_drop_by_offset(L.find_element(By.ID, "piece"), 60, 30).perform()
        self.check("drag mirrored", lambda: {"pointerdown", "pointerup"} <= set(R.execute_script("return window.__got")))

        # Video hover: a <video> on the left, the notice popup on the right
        L.execute_script("""var v = document.createElement('video'); v.id = 'vid';
        v.style.cssText = 'position:fixed;top:300px;left:300px;width:300px;height:200px;background:black;z-index:9999';
        document.body.appendChild(v);""")
        ActionChains(L).move_to_element(L.find_element(By.ID, "vid")).perform()
        popup_display = "var p = document.getElementById('videoNoticePopup'); return p && p.style.display"
        self.check("video notice shown", lambda: R.execute_script(popup_display) == "block")
        ActionChains(L).move_by_offset(0, 300).perform()
        self.check("video notice hidden", lambda: R.execute_script(popup_display) == "none")

        # Link: each window follows its own href, so each stays on its own host
        L.find_element(By.ID, "link-page2").click()
        self.check("link: left on localhost", lambda: L.current_url == f"http://localhost:{PORT}/page2.html", timeout=8)
        self.check("link: right on 127.0.0.1", lambda: R.current_url == f"http://127.0.0.1:{PORT}/page2.html", timeout=8)

        self.load("nested.html")

        # Click and type two iframes deep on the left
        L.switch_to.frame(L.find_element(By.ID, "frame1"))
        L.switch_to.frame(L.find_element(By.ID, "frame2"))
        L.find_element(By.ID, "btn-l2").click()
        L.find_element(By.ID, "text-l2").send_keys("hello")
        L.switch_to.default_content()
        frame2_doc = ("var d = document.getElementById('frame1').contentDocument"
                      ".getElementById('frame2').contentDocument; ")
        self.check("nested click", lambda: "1" in R.execute_script(frame2_doc + "return d.getElementById('btn-l2').textContent"))
        self.check("nested input", lambda: R.execute_script(frame2_doc + "return d.getElementById('text-l2').value") == "hello")

        box_l1 = "document.getElementById('frame1').contentDocument.getElementById('box-l1')"
        L.execute_script(box_l1 + ".scrollTop = 50")
        self.check("in-frame scroll", lambda: R.execute_script("return " + box_l1 + ".scrollTop") == 50)

        js_errors = [e["message"] for d in (L, R) for e in d.get_log("browser")
                     if e["level"] == "SEVERE" and "favicon" not in e["message"]]
        print("JS errors:", js_errors or "none")
        passed = sum(ok for _, ok in self.results)
        print(f"\n{passed}/{len(self.results)} passed")
        return passed == len(self.results) and not js_errors

    def stop(self) -> None:
        self.app.request_shutdown()
        self.app_thread.join(timeout=30)  # run_app stops the engine, which quits both drivers


def main() -> int:
    app_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else PROJECT_DIR
    server = subprocess.Popen([sys.executable, "-m", "http.server", "-d", str(PROJECT_DIR / "test_pages"), str(PORT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        test = E2ETest(app_dir)
        try:
            ok = test.run()
        finally:
            test.stop()
    finally:
        server.terminate()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
