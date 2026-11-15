"""Check for Phase 5 item 6 (missing-element report), on index.html vs index2.html.

The left window opens test_pages/index.html, the right index2.html, which is the
same page without Button B. Selenium runs headless; the form opens on the display.

    cd selenium_el_tester
    python3 tests/ui_missing_element.py

What it checks now:
- Button A, which is on both pages, still syncs;
- step 6.3: a click on Button B on the left finds nothing on the right; after
  MISSING_ELEMENT_WAIT_S (not before) the sync puts "Button B" on
  el_tester.missing_elements;
- a button that the right page adds 0.5 s after the click is clicked within
  the wait, and nothing is reported;
- step 6.2: an element name put on el_tester.missing_elements (from another
  thread, as the sync will) makes the real toolbar open Report bug with the
  missing-element title, Summary and Description and the two windows' URLs,
  and Save hands them over unchanged; a second name while the form is open
  opens no second form.
- step 6.4: the same two cases with the Playwright engine (PwTester headless),
  whose on_missing_element callback gets the name.
Exit code 0 when every check passed.
"""
import io
import sys
import threading
import time
import tkinter

from queue import Empty

from helpers import Checks, fixture_server, wait_for  # also puts the project on sys.path
import floating_ui  # the real toolbar; imported first, as install_test_doubles replaces the module for el_tester
from e2e_sync import install_test_doubles

install_test_doubles()  # headless Selenium, no Tk toolbar; before importing el_tester
import el_tester as app  # noqa: E402
from engine import MISSING_ELEMENT_WAIT_S  # noqa: E402
from report_form import MISSING_ELEMENT_TITLE as TITLE, missing_element_texts  # noqa: E402
from reports.model import BugDraft  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from pw_tester import PwTester  # noqa: E402

PORT = 8767
SUMMARY, DESCRIPTION = missing_element_texts("Button B")


class Tee(io.TextIOBase):
    """Prints as usual and keeps a copy, so the check can look for the app's messages."""

    def __init__(self, stream: io.TextIOBase) -> None:
        self.stream = stream
        self.text = ""

    def write(self, s: str) -> int:
        self.text += s
        return self.stream.write(s)

    def flush(self) -> None:
        self.stream.flush()


def check_sync(left_url: str, right_url: str, out: Tee, c: Checks) -> None:
    app.on_load_url(left_url, right_url, "Selenium")
    c.check("both pages loaded", wait_for(lambda: app.active_engine.current_urls() == (left_url, right_url), 40))
    left, right = app.active_engine.drivers
    c.check("right page has no Button B", not right.find_elements(By.ID, "btn-b"))

    left.find_element(By.ID, "btn-a").click()
    c.check("Button A synced (on both pages)",
            wait_for(lambda: right.find_element(By.ID, "btn-a").text == "Button A (1)", 5))

    clicked_at = time.time()
    left.find_element(By.ID, "btn-b").click()
    try:
        name = app.missing_elements.get(timeout=MISSING_ELEMENT_WAIT_S + 5)
    except Empty:
        name = None
    waited = time.time() - clicked_at
    c.check("Button B click: 'Button B' put on missing_elements", name == "Button B", name)
    c.check(f"Button B: reported after the {MISSING_ELEMENT_WAIT_S} s wait, not before",
            waited >= MISSING_ELEMENT_WAIT_S, f"after {waited:.1f} s")
    c.check("Button B click changed nothing on the right",
            right.find_element(By.ID, "btn-a").text == "Button A (1)")

    # A button the right page adds late (still loading): clicked, no report
    add_button = ADD_LATE_BUTTON_JS
    left.execute_script(add_button)
    right.execute_script(f"setTimeout(function () {{ {add_button} }}, 500);")
    left.find_element(By.ID, "btn-late").click()
    c.check("late button: clicked on the right within the wait",
            wait_for(lambda: right.execute_script(LATE_BUTTON_CLICKED_JS) == "yes", 5))
    time.sleep(MISSING_ELEMENT_WAIT_S + 0.5)
    c.check("late button: nothing reported", app.missing_elements.empty())


# Adds a button that remembers it was clicked, at the top of the page
ADD_LATE_BUTTON_JS = ("var b = document.createElement('button'); b.id = 'btn-late'; b.textContent = 'Late';"
                      "b.onclick = function () { b.dataset.clicked = 'yes'; }; document.body.prepend(b);")
LATE_BUTTON_CLICKED_JS = "var b = document.getElementById('btn-late'); return b && b.dataset.clicked;"


def check_playwright(left_url: str, right_url: str, c: Checks) -> None:
    """Step 6.4: the same cases with PwTester; its callback records (name, time)."""
    reported: list[tuple[str, float]] = []
    with sync_playwright() as p:
        t = PwTester(p, headless=True, on_missing_element=lambda name: reported.append((name, time.time())))
        try:
            t.open(left_url, right_url)
            L, R = t.left, t.right
            L.click("#btn-a"); L.wait_for_timeout(500)
            c.check("pw: Button A synced", R.locator("#btn-a").get_attribute("data-count") == "1")

            clicked_at = time.time()
            L.click("#btn-b")
            L.wait_for_timeout(int(MISSING_ELEMENT_WAIT_S * 1000) + 1500)  # bindings run during Playwright calls
            c.check("pw: Button B reported once as 'Button B'", [r[0] for r in reported] == ["Button B"], reported)
            waited = reported[0][1] - clicked_at if reported else 0.0
            c.check(f"pw: Button B reported after the {MISSING_ELEMENT_WAIT_S} s wait, not before",
                    waited >= MISSING_ELEMENT_WAIT_S, f"after {waited:.1f} s")

            reported.clear()
            fn = "() => {" + ADD_LATE_BUTTON_JS + "}"
            L.evaluate(fn)
            R.evaluate(f"() => setTimeout({fn}, 500)")
            L.click("#btn-late")
            L.wait_for_timeout(int(MISSING_ELEMENT_WAIT_S * 1000) + 500)
            c.check("pw: late button clicked on the right within the wait",
                    R.evaluate("() => { " + LATE_BUTTON_CLICKED_JS + " }") == "yes")
            c.check("pw: late button: nothing reported", reported == [], reported)
        finally:
            t.close()


def toplevels(root: tkinter.Tk) -> list[tkinter.Toplevel]:
    return [w for w in root.winfo_children() if isinstance(w, tkinter.Toplevel)]


def check_toolbar(urls: tuple[str, str], c: Checks) -> None:
    """The real toolbar: a name put on app.missing_elements from another thread (like
    the sync thread) opens the prefilled form. Runs Tk on this thread, step by step."""
    saved: list[BugDraft] = []

    def drive(root: tkinter.Tk) -> None:
        put_at = time.time()
        threading.Thread(target=app.missing_elements.put, args=("Button B",)).start()

        def form_open() -> None:
            forms = toplevels(root)
            c.check("toolbar: queue opens one form within 1 s", len(forms) == 1 and time.time() - put_at < 1.5,
                    f"{len(forms)} forms after {time.time() - put_at:.1f} s")
            if not forms:
                root.destroy()
                return
            form = forms[0]
            c.check("form: window title", form.title() == TITLE, form.title())
            c.check("form: summary prefilled", form.summary_var.get() == SUMMARY, form.summary_var.get())
            c.check("form: description prefilled", form.description_text.get("1.0", "end").strip() == DESCRIPTION)
            c.check("form: Source/Target URLs prefilled",
                    (form.source_url_var.get(), form.target_url_var.get()) == urls)
            app.missing_elements.put("Button C")  # while the form is open
            root.after(800, lambda: second_report(form))

        def second_report(form: tkinter.Toplevel) -> None:
            c.check("toolbar: a second report while the form is open opens no second form",
                    toplevels(root) == [form] and form.summary_var.get() == SUMMARY)
            form.save()
            root.after(800, after_save)

        def after_save() -> None:
            draft = saved[0] if saved else None
            c.check("form: Save hands over the prefilled texts and URLs",
                    draft is not None and (draft.summary, draft.description, draft.source_url, draft.target_url)
                    == (SUMMARY, DESCRIPTION, *urls), draft)
            root.destroy()

        root.after(1000, form_open)

    original_mainloop = tkinter.Tk.mainloop

    def mainloop_with_driver(self: tkinter.Tk, n: int = 0) -> None:
        self.after(500, lambda: drive(self))
        original_mainloop(self, n)

    tkinter.Tk.mainloop = mainloop_with_driver  # type: ignore[method-assign]
    try:
        floating_ui.create_floating_ui(on_report_callback=lambda draft: saved.append(draft) or "Bug ✓",
                                       current_urls_callback=lambda: urls,
                                       missing_element_queue=app.missing_elements)
    finally:
        tkinter.Tk.mainloop = original_mainloop  # type: ignore[method-assign]


def main() -> int:
    c = Checks()
    out = Tee(sys.stdout)
    sys.stdout = out
    with fixture_server(PORT) as (left_origin, right_origin):
        app_thread = threading.Thread(target=app.run_app, daemon=True)
        app_thread.start()
        try:
            left_url, right_url = f"{left_origin}/index.html", f"{right_origin}/index2.html"
            check_sync(left_url, right_url, out, c)
            check_toolbar(app.current_urls(), c)
            check_playwright(left_url, right_url, c)
        except Exception as e:
            c.check(f"no error ({type(e).__name__}: {e})", False)
        finally:
            app.request_shutdown()
            app_thread.join(40)
    sys.stdout = out.stream
    return c.exit_code()


if __name__ == "__main__":
    sys.exit(main())
