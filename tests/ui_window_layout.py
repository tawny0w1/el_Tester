"""Check where the two browser windows land on the screen, with both engines (Phase 5 point 4).

Starts each engine headed (real windows on the display, as the tester sees
them), opens a fixture page, and reads each window's outer rectangle from the
page (window.screenX/screenY/outerWidth/outerHeight, the same in both engines).
The visible edges must touch: Chromium's frame has an invisible shadow on
each side (engine.FRAME_SHADOW_PX), so the outer rectangles overlap by two
shadows. Same top and height.

    cd selenium_el_tester
    python3 tests/ui_window_layout.py
    python3 tests/ui_window_layout.py --shots /workspace/test_tmp   # also a PNG of the screen strip

About 40 s. Exit code 0 when every check passed.
"""
import argparse
import sys
import threading
import types
from pathlib import Path

from helpers import Checks, fixture_server, wait_for

# No Tk toolbar (the windows are what's measured); real, headed browsers
sys.modules["floating_ui"] = types.SimpleNamespace(start_ui_in_thread=lambda *a, **k: None)  # type: ignore[assignment]
import el_tester as app  # noqa: E402
from engine import FRAME_SHADOW_PX  # noqa: E402

PORT = 8771
RECT_JS = "[window.screenX, window.screenY, window.outerWidth, window.outerHeight]"
Rect = tuple[int, int, int, int]  # x, y, width, height


def selenium_rects() -> tuple[Rect, Rect]:
    left, right = app.active_engine.drivers  # type: ignore[union-attr]
    return tuple(left.execute_script(f"return {RECT_JS}")), tuple(right.execute_script(f"return {RECT_JS}"))  # type: ignore[return-value]


def playwright_rects() -> tuple[Rect, Rect]:
    engine = app.active_engine
    return engine._submit(lambda t: (tuple(t.left.evaluate(RECT_JS)), tuple(t.right.evaluate(RECT_JS)))).result(10)  # type: ignore[union-attr]


def check_engine(name: str, left_url: str, right_url: str, read_rects, c: Checks, shots: Path | None) -> None:
    app.on_load_url(left_url, right_url, name)
    c.check(f"{name}: both windows on their pages", wait_for(
        lambda: app.active_engine.name == name.lower() and app.active_engine.current_urls() == (left_url, right_url), 40))
    left, right = read_rects()
    print(f"  {name}: left {left}, right {right}  (x, y, width, height)", flush=True)
    visible_gap = right[0] - (left[0] + left[2]) + 2 * FRAME_SHADOW_PX
    c.check(f"{name}: visible edges touch (no gap, no overlap)", visible_gap == 0, f"visible gap {visible_gap} px")
    c.check(f"{name}: same top and height", (left[1], left[3]) == (right[1], right[3]), (left, right))
    if shots is not None:
        import xgrab
        xgrab.grab_root(str(shots / f"windows_{name.lower()}.png"), height=300)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shots", type=Path, help="folder for a PNG of the top of the screen")
    args = parser.parse_args()
    c = Checks()
    with fixture_server(PORT) as (left_origin, right_origin):
        threading.Thread(target=app.run_app, daemon=True).start()
        try:
            for name, read_rects in (("Selenium", selenium_rects), ("Playwright", playwright_rects)):
                check_engine(name, f"{left_origin}/index.html", f"{right_origin}/index.html", read_rects, c, args.shots)
        finally:
            app.request_shutdown()
            if app.active_engine is not None:
                app.active_engine.stop()
    return c.exit_code()


if __name__ == "__main__":
    sys.exit(main())
