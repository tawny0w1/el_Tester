"""End-to-end check of engine switching in el_tester.run_app (Phase 4 step 4).

Drives the app like the toolbar does: Load with Selenium, Reload, Load with
Playwright, Load with Selenium again, Close. Checks that the browsers start on
the first Load, a Reload keeps them, a switch quits the old pair and its sync
threads, sync works after each switch, and no browser is left after Close.
Headless, no toolbar.

    cd selenium_el_tester
    python3 tests/e2e_engine_switch.py

About 90 s. Exit code 0 when every check passed.
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image

from e2e_sync import install_test_doubles
from helpers import Checks, fixture_server, live_chromium_processes, wait_for

install_test_doubles()  # headless Selenium, no Tk toolbar; before importing el_tester
import el_tester as app  # noqa: E402
from pw_tester import PwEngine  # noqa: E402

PORT = 8768
app.ENGINES["Playwright"] = lambda: PwEngine(headless=True)


def sync_threads() -> int:
    """Selenium click-sync threads alive (one per running Selenium engine)."""
    return sum("synchronize_clicks" in t.name for t in threading.enumerate() if t.is_alive())


def selenium_ready(engine: "app.SeleniumEngine", left: str, right: str) -> bool:
    if engine.drivers is None:
        return False
    l_driver, r_driver = engine.drivers
    return (l_driver.current_url, r_driver.current_url) == (left, right) \
        and l_driver.execute_script("return !!window.__dragTracker")  # scripts injected


def selenium_click_synced(engine: "app.SeleniumEngine", expected_count: int) -> bool:
    l_driver, r_driver = engine.drivers
    l_driver.find_element("id", "btn-a").click()
    return wait_for(lambda: r_driver.find_element("id", "btn-a").get_attribute("data-count") == str(expected_count), 5)


def run(left: str, right: str, c: Checks) -> None:
    # 1. Selenium (default) starts on the first Load, not before
    c.check("no browsers before the first Load", app.active_engine is None)
    app.on_load_url(left, right, "Selenium")
    c.check("Selenium: started on Load",
            wait_for(lambda: app.active_engine is not None and selenium_ready(app.active_engine, left, right), 40))
    sel1 = app.active_engine
    c.check("Selenium: click sync", selenium_click_synced(sel1, 1))

    # 2. Reload with the same engine keeps the browsers
    app.on_load_url(left, right, "Selenium")
    time.sleep(12)  # the Selenium Load waits ~10 s for a Rise player first
    c.check("Reload with the same engine keeps the same browsers",
            app.active_engine is sel1 and selenium_ready(sel1, left, right))

    # 3. Switch to Playwright
    app.on_load_url(left, right, "Playwright")
    c.check("Playwright: started", wait_for(lambda: app.active_engine.name == "playwright", 40))
    pw = app.active_engine
    c.check("Playwright: both windows on their URLs", wait_for(lambda: pw.current_urls() == (left, right), 30),
            pw.current_urls())
    c.check("Selenium: old browsers quit", wait_for(lambda: not app.SeleniumEngine.current_urls(sel1)[0]))
    c.check("Selenium: old sync threads stopped", wait_for(lambda: sync_threads() == 0, 40), f"{sync_threads()} alive")
    pw._submit(lambda t: t.left.click("#btn-b")).result(10)
    c.check("Playwright: click sync", wait_for(
        lambda: pw._submit(lambda t: t.right.locator("#btn-b").get_attribute("data-count")).result(10) == "1", 5))
    # The toolbar's Screenshot button calls the active engine's take_screenshots from a worker thread
    shots = Path(tempfile.mkdtemp(prefix="engine_switch_"))
    shot_thread = threading.Thread(target=lambda: app.require_engine().take_screenshots(shots / "l.png", shots / "r.png"))
    shot_thread.start(); shot_thread.join(60)
    sizes = [Image.open(shots / n).size for n in ("l.png", "r.png") if (shots / n).exists()]
    c.check("Playwright: screenshots from another thread, both windows", len(sizes) == 2 and all(w > 0 for w, _ in sizes), sizes)

    # 4. Back to Selenium: a fresh engine with one set of sync threads
    app.on_load_url(left, right, "Selenium")
    c.check("Selenium again: started", wait_for(
        lambda: app.active_engine.name == "selenium" and app.active_engine is not sel1
        and selenium_ready(app.active_engine, left, right), 60))
    sel2 = app.active_engine
    c.check("Playwright: thread stopped", wait_for(lambda: not pw._thread.is_alive()))
    c.check("Selenium again: click sync (fresh page, count 1)", selenium_click_synced(sel2, 1))
    c.check("Selenium again: exactly one click sync thread", sync_threads() == 1, sync_threads())
    c.check("bug reports get the active engine's name and URLs",
            (sel2.name, sel2.current_urls()) == ("selenium", (left, right)))


def main() -> int:
    c = Checks()
    before = live_chromium_processes()
    with fixture_server(PORT) as (left_origin, right_origin):
        app_thread = threading.Thread(target=app.run_app, daemon=True)
        app_thread.start()
        try:
            run(f"{left_origin}/index.html", f"{right_origin}/index.html", c)
        except Exception as e:
            c.check(f"no error ({type(e).__name__}: {e})", False)
        finally:
            app.request_shutdown()  # the toolbar's Close
            app_thread.join(40)
    c.check("Close: app loop ended", not app_thread.is_alive())
    c.check("Close: no browser processes left", wait_for(lambda: live_chromium_processes() <= before, 15),
            f"{live_chromium_processes()} live vs {before} before")
    return c.exit_code()


if __name__ == "__main__":
    sys.exit(main())
