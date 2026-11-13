"""UI check of the Phase 5 bug list on the display: EditBugForm, BugListWindow and the toolbar.

Opens the real Tk windows with sample reports in a temporary database
(/workspace/test_tmp/ui_bug_window/), clicks through them like a tester
would, and checks the database, the files and the exported PDFs. The
Yes/No and save dialogs are replaced by fakes. Needs a display (DISPLAY);
windows appear for a few seconds.

    cd selenium_el_tester
    python3 tests/ui_bug_window.py
    python3 tests/ui_bug_window.py --shots /workspace/test_tmp   # also save PNGs of the windows

Exit code 0 when every check passed.
"""
import argparse
import re
import shutil
import sys
import tkinter
from pathlib import Path

from PIL import Image

from helpers import PROJECT_DIR, Checks
import bug_window
import floating_ui
from bug_window import BugListWindow
from report_form import NO_RESOLUTION, EditBugForm
from reports.model import BugReport, Resolution, Severity, Status
from reports.pdf_exporter import pdf_path_for
from reports.reporter import bug_screenshot_paths
from reports.repository import SqliteBugRepository

WORK_DIR = PROJECT_DIR.parent / "test_tmp" / "ui_bug_window"  # emptied at the start of each run


def sample_report() -> BugReport:
    return BugReport(engine="selenium", source_url="http://localhost/a", target_url="http://127.0.0.1/a",
                     summary="Typo on slide 3", description="Missing letter", id=7)


def check_edit_form(root: tkinter.Tk, checks: Checks, shots: Path | None) -> None:
    report = sample_report()
    saved: list[BugReport] = []

    form = EditBugForm(root, report, saved.append)
    form.wait_visibility()
    root.update()
    checks.check("edit form: title has the padded id", form.title() == "Edit bug 00007", form.title())
    checks.check("edit form: fields prefilled, URLs included",
                 (form.summary_var.get(), form.source_url_var.get(), form.target_url_var.get(),
                  form.severity_var.get(), form.status_var.get(),
                  form.resolution_var.get(), form.description_text.get("1.0", "end").strip())
                 == ("Typo on slide 3", "http://localhost/a", "http://127.0.0.1/a",
                     "normal", "UNCONFIRMED", NO_RESOLUTION, "Missing letter"))
    if shots is not None:
        import xgrab
        xgrab.grab("Edit bug 00007", str(shots / "edit_form.png"))

    form.summary_var.set("   ")
    form.save()
    checks.check("edit form: empty summary refused", saved == [] and form.winfo_exists()
                 and form.error_label.cget("text") == "A summary is required")

    form.summary_var.set("Typo on slide 4")
    form.target_url_var.set("http://127.0.0.1/b")
    form.status_var.set(Status.RESOLVED.value)
    form.resolution_var.set(Resolution.FIXED.value)
    form.severity_var.set(Severity.MINOR.value)
    form.description_text.delete("1.0", "end")
    form.description_text.insert("1.0", "Fixed in v2")
    form.save()
    root.update()
    expected = BugReport(engine="selenium", source_url="http://localhost/a", target_url="http://127.0.0.1/b",
                         summary="Typo on slide 4", description="Fixed in v2", severity=Severity.MINOR,
                         status=Status.RESOLVED, resolution=Resolution.FIXED, created_at=report.created_at, id=7)
    checks.check("edit form: Save passes the edited copy", saved == [expected], saved)
    checks.check("edit form: Save closes the form", not form.winfo_exists())
    checks.check("edit form: original report unchanged", report.summary == "Typo on slide 3")

    resolved = BugReport(**{**vars(expected), "status": Status.RESOLVED})
    form = EditBugForm(root, resolved, saved.append)
    form.resolution_var.set(NO_RESOLUTION)
    form.save()
    checks.check("edit form: '---' saves an empty resolution", saved[-1].resolution is Resolution.NONE)

    form = EditBugForm(root, report, saved.append)
    root.update()
    form.event_generate("<Escape>")
    root.update()
    checks.check("edit form: Escape cancels", not form.winfo_exists() and len(saved) == 2)


def pdf_pages(path: Path) -> int:
    """Number of pages in a reportlab PDF (each page object is "/Type /Page", not "/Pages")."""
    return len(re.findall(rb"/Type /Page\b(?!s)", path.read_bytes()))


def make_bugs(repo: SqliteBugRepository, folder: Path) -> list[BugReport]:
    """Three bugs: two with screenshots (blue/orange PNGs), one without; the second is CONFIRMED."""
    bugs = []
    for summary, status, with_shots in (("Typo on slide 3", Status.UNCONFIRMED, True),
                                        ("Button cut off", Status.CONFIRMED, True),
                                        ("Audio too quiet", Status.UNCONFIRMED, False)):
        saved = repo.add(BugReport(engine="selenium", source_url="http://localhost/a",
                                   target_url="http://127.0.0.1/a", summary=summary, status=status))
        if with_shots:
            source, target = bug_screenshot_paths(folder, saved.id)  # type: ignore[arg-type]
            Image.new("RGB", (930, 1000), "#4a90d9").save(source)
            Image.new("RGB", (930, 1000), "#f0ad4e").save(target)
            saved.source_screenshot, saved.target_screenshot = str(source), str(target)
            repo.update(saved)
        bugs.append(saved)
    return bugs


def check_bug_list(root: tkinter.Tk, checks: Checks, shots: Path | None) -> None:
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    (WORK_DIR / "screenshots").mkdir(parents=True)
    repo = SqliteBugRepository(WORK_DIR / "bugs.db")
    first, second, third = make_bugs(repo, WORK_DIR / "screenshots")
    ids = [str(bug.id) for bug in (first, second, third)]

    window = BugListWindow(root, repo, pdf_folder=WORK_DIR / "pdf")
    window.wait_visibility()
    root.update()
    table = window.table
    checks.check("list: all three bugs, oldest first", list(table.get_children()) == ids, table.get_children())
    # table.set() returns the cells as text; table.item() would turn "00002" into the number 2
    row = [table.set(ids[1], name) for name, _, _ in bug_window.COLUMNS]
    checks.check("list: row shows padded id, severity, status, summary",
                 [row[0], *row[2:]] == ["00002", "normal", "CONFIRMED", "Button cut off"], row)

    window.status_var.set("CONFIRMED")
    window.refresh()
    checks.check("filter: CONFIRMED shows one bug", list(table.get_children()) == [ids[1]])
    window.status_var.set(bug_window.ALL_STATUSES)
    window.refresh()

    table.selection_set(ids[0])
    root.update()
    source_label, target_label = window.preview_labels
    checks.check("preview: both screenshots shown", bool(source_label.cget("image")) and bool(target_label.cget("image")))
    image_size = (window.previews[0].width(), window.previews[0].height())
    checks.check("preview: shrunk to fit the box", image_size[0] <= 480 and image_size[1] <= 300, image_size)
    if shots is not None:
        import xgrab
        xgrab.grab("Bug reports", str(shots / "bug_window.png"))
    table.selection_set(ids[2])
    root.update()
    checks.check("preview: bug without screenshots", source_label.cget("text") == "No screenshot"
                 and not source_label.cget("image"))

    # Edit: double-click opens the form for the selected bug; Save writes to the database
    table.selection_set(ids[2])
    window.edit_selected()
    root.update()
    forms = [w for w in window.winfo_children() if isinstance(w, EditBugForm)]
    checks.check("edit: form opened for the selected bug", len(forms) == 1 and forms[0].report.id == third.id)
    if forms:
        forms[0].status_var.set(Status.CONFIRMED.value)
        forms[0].save()
        root.update()
    stored = repo.get(third.id)  # type: ignore[arg-type]
    checks.check("edit: saved to the database", stored is not None and stored.status is Status.CONFIRMED)
    checks.check("edit: row updated, selection kept", table.set(ids[2], "status") == "CONFIRMED"
                 and table.selection() == (ids[2],))

    # Export: nothing selected -> every bug shown; one selected -> that bug
    saved_to: list[str] = []
    def fake_save_dialog(**options: object) -> str:
        saved_to.append(str(options["initialfile"]))
        return str(WORK_DIR / str(options["initialfile"]))
    bug_window.filedialog.asksaveasfilename = fake_save_dialog  # type: ignore[assignment]
    table.selection_set(())
    window.export_pdf()
    all_pdf = WORK_DIR / "bug_reports.pdf"
    checks.check("export: nothing selected -> all shown, one page each",
                 all_pdf.exists() and pdf_pages(all_pdf) == 3, saved_to)
    table.selection_set(ids[0])
    window.export_pdf()
    one_pdf = WORK_DIR / pdf_path_for(first).name
    checks.check("export: one selected -> bug_00001.pdf, one page", one_pdf.exists() and pdf_pages(one_pdf) == 1,
                 saved_to)

    # Delete: No keeps everything; Yes removes the rows and their files
    (WORK_DIR / "pdf").mkdir()
    bug_pdf = pdf_path_for(first, WORK_DIR / "pdf")
    bug_pdf.write_bytes(b"pdf")
    answers = [False, True]
    bug_window.messagebox.askyesno = lambda *a, **k: answers.pop(0)  # type: ignore[assignment]
    table.selection_set(ids[0], ids[1])
    window.delete_selected()
    checks.check("delete: No keeps the bugs", len(repo.list_all()) == 3)
    window.delete_selected()
    root.update()
    checks.check("delete: Yes removes both rows", [b.id for b in repo.list_all()] == [third.id]
                 and list(table.get_children()) == [ids[2]])
    checks.check("delete: screenshots and PDF removed",
                 not any(Path(p).exists() for p in (first.source_screenshot, first.target_screenshot,
                                                    second.source_screenshot, bug_pdf)))
    checks.check("delete: message shown", window.message_label.cget("text") == "Deleted 00001, 00002",
                 window.message_label.cget("text"))
    window.destroy()


def check_toolbar(checks: Checks, shots: Path | None) -> None:
    """The toolbar's size and title bar (Phase 5 point 3), and its Bugs button."""
    repo = SqliteBugRepository(WORK_DIR / "bugs.db")  # left by check_bug_list: one bug

    def drive(root: tkinter.Tk) -> None:
        """Runs on the Tk thread once the toolbar is up."""
        root.update()
        checks.check("toolbar: 1331 x 82 px", (root.winfo_width(), root.winfo_height()) == (1331, 82),
                     (root.winfo_width(), root.winfo_height()))
        titles = [w for w in widgets(root) if w.winfo_class() == "Label" and w.cget("text") == "EL Tester"]
        checks.check("toolbar: 'EL Tester' in a 22 px title bar",
                     len(titles) == 1 and titles[0].master.winfo_height() == 22)
        close = button(root, "Close")
        checks.check("toolbar: all buttons fit", close.winfo_rootx() + close.winfo_width()
                     <= root.winfo_rootx() + root.winfo_width())
        if shots is not None:
            import xgrab
            xgrab.grab(root.title(), str(shots / "toolbar.png"))

        button(root, "Bugs").invoke()
        root.update()
        lists = [w for w in root.winfo_children() if isinstance(w, BugListWindow)]
        checks.check("Bugs: opens the bug list", len(lists) == 1 and len(lists[0].reports) == 1)
        # The Edit form is drawn above the always-on-top toolbar, like the Report bug form
        lists[0].table.selection_set(lists[0].table.get_children()[0])
        lists[0].edit_selected()
        edit_form = next(w for w in lists[0].winfo_children() if isinstance(w, EditBugForm))
        edit_form.wait_visibility()
        root.update()
        # Control: an ordinary window stays under the toolbar, so this check can tell the difference
        plain = tkinter.Toplevel(root)
        plain.wait_visibility()
        root.update()
        order = list(root.tk.splitlist(root.tk.call("wm", "stackorder", ".")))  # bottom to top
        checks.check("stacking control: an ordinary window is under the toolbar",
                     str(plain) in order and order.index(str(plain)) < order.index("."), order)
        plain.destroy()
        root.update()
        order = list(root.tk.splitlist(root.tk.call("wm", "stackorder", ".")))
        names = [".", str(lists[0]), str(edit_form)]  # toolbar, bug list, Edit form
        checks.check("stacking: bug list above the toolbar, Edit form above both",
                     all(name in order for name in names) and order.index(names[0]) < order.index(names[1])
                     < order.index(names[2]), order)
        edit_form.destroy()

        # Delete's Yes/No question and Export's save dialog open above the bug list (real dialogs,
        # inspected from after() while they wait for an answer, then cancelled)
        def dialog_on_top(dialog: str, close: str, name: str) -> None:
            order = list(root.tk.splitlist(root.tk.call("wm", "stackorder", ".")))
            checks.check(f"stacking: {name} above the bug list",
                         dialog in order and order.index(dialog) > order.index(str(lists[0])), order)
            root.tk.call(close, "invoke")

        bug_list = lists[0]
        root.after(800, lambda: dialog_on_top(f"{bug_list}.__tk__messagebox", f"{bug_list}.__tk__messagebox.no",
                                              "Delete's Yes/No question"))
        bug_list.delete_selected()  # returns when the question is answered (No)
        checks.check("Delete: No keeps the bug", len(repo.list_all()) == 2)
        root.after(800, lambda: dialog_on_top(".__tk_filedialog", ".__tk_filedialog.contents.f2.cancel",
                                              "Export's save dialog"))
        bug_list.export_pdf()  # returns when the dialog is cancelled
        repo.add(BugReport(engine="selenium", source_url="a", target_url="b", summary="Reported later"))
        button(root, "Bugs").invoke()
        root.update()
        lists = [w for w in root.winfo_children() if isinstance(w, BugListWindow)]
        checks.check("Bugs: second click keeps one window, with the new bug",
                     len(lists) == 1 and len(lists[0].reports) == 2)
        root.destroy()

    original_mainloop = tkinter.Tk.mainloop

    def mainloop_with_driver(self: tkinter.Tk, n: int = 0) -> None:
        self.after(500, lambda: drive(self))
        original_mainloop(self, n)

    tkinter.Tk.mainloop = mainloop_with_driver  # type: ignore[method-assign]
    try:
        floating_ui.create_floating_ui(bug_repository=repo)
    finally:
        tkinter.Tk.mainloop = original_mainloop  # type: ignore[method-assign]


def widgets(w: tkinter.Misc):
    yield w
    for child in w.winfo_children():
        yield from widgets(child)


def button(root: tkinter.Misc, text: str) -> tkinter.Button:
    return next(w for w in widgets(root) if w.winfo_class() == "Button" and w.cget("text") == text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shots", type=Path, help="folder for PNGs of the windows")
    args = parser.parse_args()
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)

    checks = Checks()
    # A visible root: the form is transient, and X hides a transient window
    # while its parent is hidden (in the app the parent is the bug list)
    root = tkinter.Tk()
    root.title("ui_bug_window test")
    check_edit_form(root, checks, args.shots)
    check_bug_list(root, checks, args.shots)
    root.destroy()
    check_toolbar(checks, args.shots)
    return checks.exit_code()


if __name__ == "__main__":
    sys.exit(main())
