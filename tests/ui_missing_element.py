"""Check for Phase 5 item 6 (missing-element report), on index.html vs index2.html.

The left window opens test_pages/index.html, the right index2.html, which is the
same page without Button B. Selenium runs headless; the form opens on the display.

    cd selenium_el_tester
    python3 tests/ui_missing_element.py

What it checks now:
- Button A, which is on both pages, still syncs;
- a click on Button B on the left finds nothing on the right, and the sync
  reports it as "not found" (today only a printed line);
- step 6.2: an element name put on el_tester.missing_elements (from another
  thread, as the sync will) makes the real toolbar open Report bug with the
  missing-element title, Summary and Description and the two windows' URLs,
  and Save hands them over unchanged; a second name while the form is open
  opens no second form.
Steps 6.3-6.4 make the engines put the name on the queue themselves.
Exit code 0 when every check passed.
"""
import io
import sys
import threading
import time
import tkinter

from helpers import Checks, fixture_server, wait_for  # also puts the project on sys.path
import floating_ui  # the real toolbar; imported first, as install_test_doubles replaces the module for el_tester
from e2e_sync import install_test_doubles

install_test_doubles()  # headless Selenium, no Tk toolbar; before importing el_tester
import el_tester as app  # noqa: E402
from report_form import MISSING_ELEMENT_TITLE as TITLE, missing_element_texts  # noqa: E402
from reports.model import BugDraft  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402

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

    left.find_element(By.ID, "btn-b").click()
    c.check("Button B click: not found on the right",
            wait_for(lambda: 'btn-b' in out.text and "not found on the right" in out.text, 5),
            "no 'not found' line printed")
    c.check("Button B click changed nothing on the right",
            right.find_element(By.ID, "btn-a").text == "Button A (1)")


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
        except Exception as e:
            c.check(f"no error ({type(e).__name__}: {e})", False)
        finally:
            app.request_shutdown()
            app_thread.join(40)
    sys.stdout = out.stream
    return c.exit_code()


if __name__ == "__main__":
    sys.exit(main())
