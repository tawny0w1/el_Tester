from tkinter import Tk, Frame, Button, Label, LEFT, BOTH, Entry, OptionMenu, StringVar, DISABLED, NORMAL
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog
from typing import Any, Callable, Sequence
import shutil
import threading
import traceback

from bug_window import BugListWindow, default_save_dir
from report_form import ReportBugForm
from reports.model import Severity
from reports.repository import BugRepository

# The app's work for the Screenshot and Report bug buttons. Each returns a
# short result ("Saved", "Bug 00007 ✓") that the button shows for a moment.
OnScreenshot = Callable[[], str]
OnReport = Callable[[str, str, Severity], str]  # (summary, description, severity)
# Like OnReport, and also builds the bug's PDF: returns (result text, PDF path or None if it failed)
OnReportPdf = Callable[[str, str, Severity], tuple[str, Path | None]]
RESULT_SHOWN_MS = 3000
DEFAULT_ENGINES: tuple[str, ...] = ("Selenium", "Playwright")  # first = default

WIDTH = 1331  # 30% wider than the first 1024 px, for longer URL fields
HEIGHT = 82   # title bar + two URL rows
TITLE_BAR_HEIGHT = 22  # the grey bar with "EL Tester"; drag it to move the toolbar
URL_ENTRY_CHARS = 74   # 30% wider than 57; leaves room for the tool menu and buttons in WIDTH

def create_floating_ui(width=WIDTH, height=HEIGHT, on_load_callback=None, on_close_callback=None,
                       on_screenshot_callback: OnScreenshot | None = None,
                       on_report_callback: OnReport | None = None,
                       engine_names: Sequence[str] = DEFAULT_ENGINES,
                       on_report_pdf_callback: OnReportPdf | None = None,
                       bug_repository: BugRepository | None = None):
    root = Tk()
    if root.tk.call("tk", "windowingsystem") == "x11":
        # A "dock" window has no decorations, and unlike an override-redirect
        # window it can get keyboard focus (Tk never sets X focus on those)
        root.attributes("-type", "dock")
        # Tk's own file dialog (X11) lists hidden files (.git, ...) by default.
        # Hide them, with a "Show hidden files" option in the dialog. The bad
        # option makes Tk load the dialog's code, which defines these variables.
        root.tk.eval("catch {tk_getOpenFile -no-such-option}; "
                     "set ::tk::dialog::file::showHiddenBtn 1; set ::tk::dialog::file::showHiddenVar 0")
    else:
        root.overrideredirect(True)           # no window decorations
    root.attributes("-topmost", True)         # always on top
    root.geometry(f"{width}x{height}+50+50")  # initial position

    # Top title bar (light gray) with the app name; it is also the drag handle
    top_handle = Frame(root, bg="#dddddd", height=TITLE_BAR_HEIGHT)
    top_handle.pack(fill='x', side='top')
    top_handle.pack_propagate(False)  # keep the fixed height, whatever the label's size
    title = Label(top_handle, text="EL Tester", bg="#dddddd", fg="#222", font=("TkDefaultFont", 10, "bold"))
    title.pack()

    # make background frame (for button area)
    frame = Frame(root, bg="#222", bd=0)
    frame.pack(fill=BOTH, expand=True)

    # Drag handling bound to top_handle
    offset_x = offset_y = 0
    def on_press(event):
        nonlocal offset_x, offset_y
        offset_x = event.x_root
        offset_y = event.y_root

    def on_drag(event):
        nonlocal offset_x, offset_y
        dx = event.x_root - offset_x
        dy = event.y_root - offset_y
        x = root.winfo_x() + dx
        y = root.winfo_y() + dy
        root.geometry(f"+{x}+{y}")
        offset_x = event.x_root
        offset_y = event.y_root

    for handle in (top_handle, title):  # the title covers part of the bar, so it drags too
        handle.bind("<ButtonPress-1>", on_press)
        handle.bind("<B1-Motion>", on_drag)

    # Two URL rows: Left, and Right (empty = same URL as Left), to compare two
    # versions of a course that live at different URLs
    left_var = StringVar(value="https://360.eu.articulate.com/review/content/1e64fc6d-b59c-4abf-8e4e-dfdbfd41838b/review")
    right_var = StringVar(value="")
    url_rows = Frame(frame, bg="#222")
    url_rows.pack(side=LEFT, padx=(6, 4), pady=2)
    for row, (label, var) in enumerate((("Source", left_var), ("Target", right_var))):
        Label(url_rows, text=label, bg="#222", fg="#fff").grid(row=row, column=0, sticky="w", padx=(0, 4))
        entry = Entry(url_rows, textvariable=var, width=URL_ENTRY_CHARS)
        entry.grid(row=row, column=1, pady=1)
        # the WM doesn't focus a dock window on click; request focus explicitly
        entry.bind("<Button-1>", lambda e: e.widget.focus_force())
        entry.bind("<KeyRelease>", lambda e: on_entry_change())

    # last loaded (left, right) pair, and the engine it was loaded with
    last_urls = ("", "")
    last_engine = ""

    # Test tool (engine), read when Load is clicked. Another engine on Load
    # quits the current browser pair and starts the chosen one.
    engine_var = StringVar(value=engine_names[0])
    tool_box = Frame(frame, bg="#222")
    tool_box.pack(side=LEFT, padx=(4, 4))
    Label(tool_box, text="Test tool", bg="#222", fg="#fff").pack(anchor="w")
    tool_menu = OptionMenu(tool_box, engine_var, *engine_names)
    tool_menu.config(bg="#fff", fg="#222", bd=0, highlightthickness=0, width=9)
    tool_menu.pack()

    # create Load button (command set after definition)
    load_btn = Button(frame, text="Load", bg="#4CAF50", fg="#fff", bd=0)
    load_btn.pack(side=LEFT, padx=(4,4), pady=6)

    # update button text to "Load" when a URL or the engine changes from the last Load
    def on_entry_change():
        if (left_var.get().strip(), right_var.get().strip()) != last_urls or engine_var.get() != last_engine:
            load_btn.config(text="Load", bg="#4CAF50")

    engine_var.trace_add("write", lambda *_: on_entry_change())

    def on_load():
        nonlocal last_urls, last_engine
        left, right = left_var.get().strip(), right_var.get().strip()
        if not left and not last_urls[0]:
            print("No URL entered")
            return
        if left:
            last_urls = (left, right)
        last_engine = engine_var.get()
        if load_btn['text'] == 'Load':
            load_btn.config(text='Reload', bg='#f0ad4e')
            print(f"Load requested: {last_urls}")
        else:
            print(f"Reload requested: {last_urls}")
        # Send both URLs and the chosen engine to the app
        if on_load_callback:
            on_load_callback(*last_urls, last_engine)

    load_btn.config(command=on_load)

    # Screenshots can take seconds (the driver waits while a page loads), so
    # the work runs off the Tk thread and the toolbar stays responsive. Only
    # the Tk thread may touch widgets: the worker puts its result on a queue
    # and the Tk thread polls it with after(). on_done, if given, runs on the
    # Tk thread with the work's result (e.g. to show a dialog) and returns the
    # text to show; without it the result is that text.
    def run_in_background(button: Button, work: Callable[[], Any],
                          on_done: Callable[[Any], str] | None = None) -> None:
        label = button.cget("text")
        button.config(text="Saving…", state=DISABLED)  # also blocks a double click
        results: "Queue[Any]" = Queue()
        failed = object()  # put by the worker when work() raised

        def worker() -> None:
            try:
                results.put(work())
            except Exception:
                traceback.print_exc()
                results.put(failed)

        def show_result() -> None:
            try:
                result = results.get_nowait()
            except Empty:
                root.after(100, show_result)
                return
            if result is failed:
                message = "Failed"
            elif on_done is not None:
                try:
                    message = on_done(result)
                except Exception:
                    traceback.print_exc()
                    message = "Failed"
            else:
                message = result
            button.config(text=message, state=NORMAL)
            root.after(RESULT_SHOWN_MS, lambda: button.config(text=label))

        threading.Thread(target=worker, daemon=True).start()
        root.after(100, show_result)

    def on_screenshot() -> None:
        if on_screenshot_callback is None:
            print("Screenshot: no browser engine connected")
            return
        run_in_background(btn_shot, on_screenshot_callback)

    # Where the last PDF copy was saved, so the next dialog opens there
    pdf_dir: Path | None = None

    def save_pdf_copy(result: tuple[str, Path | None]) -> str:
        """Tk thread, after "Save and create PDF": ask where to save a copy of the bug's PDF."""
        nonlocal pdf_dir
        message, pdf = result
        if pdf is None:  # the bug was saved, the PDF failed (see the terminal)
            return message
        if pdf_dir is None:
            pdf_dir = default_save_dir()
        target = filedialog.asksaveasfilename(
            parent=root, title="Save the bug report PDF", initialdir=str(pdf_dir), initialfile=pdf.name,
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf"), ("All files", "*")])
        if not target:  # Cancel: the PDF stays in bug_data/pdf
            print(f"PDF not copied; it stays in {pdf}")
            return message
        shutil.copyfile(pdf, target)
        pdf_dir = Path(target).parent
        print(f"PDF saved: {target}")
        return "PDF saved ✓"

    # One form at a time: a second click brings the open one to the front
    report_form: ReportBugForm | None = None

    def open_report_form() -> None:
        nonlocal report_form
        if report_form is not None and report_form.winfo_exists():
            report_form.lift()
            report_form.summary_entry.focus_force()
            return

        def save(summary: str, description: str, severity: Severity) -> None:
            if on_report_callback is None:
                print(f"Report bug: no app connected; not saved: {summary!r} ({severity.value})")
                return
            run_in_background(btn_report, lambda: on_report_callback(summary, description, severity))

        def save_with_pdf(summary: str, description: str, severity: Severity) -> None:
            if on_report_pdf_callback is None:
                print(f"Report bug: no app connected; not saved: {summary!r} ({severity.value})")
                return
            run_in_background(btn_report, lambda: on_report_pdf_callback(summary, description, severity),
                              on_done=save_pdf_copy)

        report_form = ReportBugForm(root, on_save=save, on_save_pdf=save_with_pdf)

    # One bug list at a time: a second click brings it to the front with fresh rows
    # (bugs reported since it was opened appear)
    bug_list: BugListWindow | None = None

    def open_bug_list() -> None:
        nonlocal bug_list
        if bug_repository is None:
            print("Bugs: no bug database connected")
            return
        if bug_list is not None and bug_list.winfo_exists():
            bug_list.refresh()
            bug_list.lift()
            return
        bug_list = BugListWindow(root, bug_repository)

    # Fixed width (in characters), so the result text doesn't shift the buttons
    btn_shot = Button(frame, text="Screenshot", command=on_screenshot,
                      bg="#fff", fg="#222", bd=0, width=11)
    btn_report = Button(frame, text="Report bug", command=open_report_form,
                        bg="#fff", fg="#222", bd=0, width=11)
    btn_bugs = Button(frame, text="Bugs", command=open_bug_list,
                      bg="#fff", fg="#222", bd=0, width=6)

    # Close button: destroys the toolbar, then tells the app to shut down
    # (quit both browsers and end the process)
    def on_close():
        try:
            root.destroy()
            print("Floating UI closed")
        except Exception:
            pass
        if on_close_callback:
            on_close_callback()

    btn_close = Button(frame, text="Close", command=on_close,
                       bg="#ff6666", fg="#fff", bd=0)

    # Layout: remaining buttons
    btn_shot.pack(side=LEFT, padx=(6,4), pady=6)
    btn_report.pack(side=LEFT, padx=(4,4), pady=6)
    btn_bugs.pack(side=LEFT, padx=(4,4), pady=6)
    btn_close.pack(side=LEFT, padx=(4,6), pady=6)

    # start mainloop (blocking)
    root.mainloop()

def start_ui_in_thread(width=WIDTH, height=HEIGHT, on_load_callback=None, on_close_callback=None,
                       on_screenshot_callback: OnScreenshot | None = None,
                       on_report_callback: OnReport | None = None,
                       engine_names: Sequence[str] = DEFAULT_ENGINES,
                       on_report_pdf_callback: OnReportPdf | None = None,
                       bug_repository: BugRepository | None = None):
    t = threading.Thread(target=create_floating_ui,
                         args=(width, height, on_load_callback, on_close_callback,
                               on_screenshot_callback, on_report_callback, engine_names,
                               on_report_pdf_callback, bug_repository), daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    # Run standalone for quick test
    create_floating_ui()