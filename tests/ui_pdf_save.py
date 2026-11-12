"""UI check of "Save and create PDF" on the display: toolbar -> Report bug form -> save dialog.

Drives the real Tk toolbar (floating_ui) with a fake app callback: opens the
Report bug form, fills it, clicks "Save and create PDF", and in the save
dialog picks a temporary file. Checks the buttons, the dialog (file name,
start folder, hidden files off), the copied PDF and the result text.
Needs a display (DISPLAY); windows appear for a few seconds.

    cd selenium_el_tester
    python3 tests/ui_pdf_save.py
    python3 tests/ui_pdf_save.py --shots /some/dir   # also save PNGs of the form and the dialog

About 10 s. Exit code 0 when every check passed.
"""
import argparse
import os
import shutil
import sys
import tempfile
import threading
import time
import tkinter
from pathlib import Path

from helpers import PROJECT_DIR, Checks
import floating_ui
from reports.model import BugReport, Severity
from reports.pdf_exporter import PdfExporter

TIMEOUT_S = 40


def widgets(w: tkinter.Misc):
    yield w
    for child in w.winfo_children():
        yield from widgets(child)


def find(root: tkinter.Misc, cls: str, text: str | None = None) -> list[tkinter.Widget]:
    return [w for w in widgets(root) if w.winfo_class() == cls and (text is None or w.cget("text") == text)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shots", type=Path, help="folder for PNGs of the form and the dialog")
    args = parser.parse_args()
    if args.shots:
        import xgrab
        args.shots.mkdir(parents=True, exist_ok=True)

    c = Checks()
    tmp = Path(tempfile.mkdtemp(prefix="ui_pdf_"))
    pdf = tmp / "bug_00099.pdf"
    PdfExporter().export([BugReport(engine="selenium", source_url="a", target_url="b", summary="sample", id=99)], pdf)
    target = tmp / "chosen" / "copy.pdf"
    target.parent.mkdir()
    calls: list[tuple[str, str, str]] = []

    def fake_report_pdf(summary: str, description: str, severity: Severity) -> tuple[str, Path | None]:
        calls.append((summary, description, severity.value))
        time.sleep(0.5)  # like the real save: screenshots take a moment
        return "Bug 00099 ✓", pdf

    def drive(root: tkinter.Tk) -> None:
        """Runs on the Tk thread, step by step with after()."""
        find(root, "Button", "Report bug")[0].invoke()

        def fill_form() -> None:
            form = next(w for w in root.winfo_children() if w.winfo_class() == "Toplevel")
            find(form, "Entry")[0].insert(0, "Zły przycisk Dalej")
            find(form, "Text")[0].insert("1.0", "Opis błędu")
            buttons = [b.cget("text") for b in find(form, "Button")]
            c.check("form: Save and create PDF next to Save", buttons == ["Cancel", "Save and create PDF", "Save"], buttons)
            if args.shots:
                root.update()
                xgrab.grab("Report bug", str(args.shots / "report_form.png"))
            find(form, "Button", "Save and create PDF")[0].invoke()
            root.after(2500, in_dialog)

        def in_dialog() -> None:
            # Tk's file dialog is Tcl code: Python's widget tree doesn't see it
            tcl, entry = root.tk.eval, ".__tk_filedialog.contents.f2.ent"
            c.check("dialog: opens with the PDF's file name", tcl(f"{entry} get") == pdf.name, tcl(f"{entry} get"))
            start = tcl("set ::tk::dialog::file::__tk_filedialog(selectPath)")
            expected = str(PROJECT_DIR.parent) if os.path.exists("/.dockerenv") else str(Path.home())
            c.check("dialog: starts in the workspace (container) or home folder", start == expected, start)
            c.check("dialog: hidden files off", tcl("set ::tk::dialog::file::showHiddenVar") == "0")
            if args.shots:
                xgrab.grab("Save the bug report PDF", str(args.shots / "save_dialog.png"))
            tcl(f"{entry} delete 0 end")
            tcl(f"{entry} insert 0 {{{target}}}")
            tcl(".__tk_filedialog.contents.f2.ok invoke")
            root.after(800, after_save)

        def after_save() -> None:
            c.check("copy written where chosen", target.exists() and target.read_bytes() == pdf.read_bytes())
            c.check("toolbar shows PDF saved", find(root, "Button", "PDF saved ✓") != [],
                    [b.cget("text") for b in find(root, "Button")])
            c.check("app callback got the form's fields", calls == [("Zły przycisk Dalej", "Opis błędu", "normal")], calls)
            root.destroy()

        root.after(800, fill_form)

    original_mainloop = tkinter.Tk.mainloop

    def mainloop_with_driver(self: tkinter.Tk, n: int = 0) -> None:
        self.after(500, lambda: drive(self))
        original_mainloop(self, n)

    tkinter.Tk.mainloop = mainloop_with_driver  # type: ignore[method-assign]
    watchdog = threading.Timer(TIMEOUT_S, lambda: (print(f"TIMEOUT after {TIMEOUT_S} s", flush=True), os._exit(1)))
    watchdog.start()
    try:
        floating_ui.create_floating_ui(on_report_callback=lambda *fields: "unused",
                                       on_report_pdf_callback=fake_report_pdf)
    finally:
        watchdog.cancel()
        shutil.rmtree(tmp, ignore_errors=True)
    return c.exit_code()


if __name__ == "__main__":
    sys.exit(main())
