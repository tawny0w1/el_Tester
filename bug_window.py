"""The bug list: the saved reports, with edit, delete, PDF export and a screenshot preview.

Opened from the toolbar's "Bugs" button, as a window of the toolbar's Tk
root (Tk widgets may only be used from the one thread that runs Tk).
Run it alone to look at the database without the browsers:

    python3 bug_window.py [path/to/bugs.db]
"""
import base64
import io
import os
from pathlib import Path
from tkinter import Button, Frame, Label, Misc, PhotoImage, StringVar, Tk, Toplevel, filedialog, messagebox, ttk

from PIL import Image

from report_form import EditBugForm
from reports.model import BugReport, Status
from reports.pdf_exporter import DEFAULT_PDF_DIR, PdfExporter, pdf_path_for
from reports.reporter import delete_report
from reports.repository import BugRepository

ALL_STATUSES = "All"
PREVIEW_SIZE = (480, 300)  # the most a screenshot is shrunk to, in pixels (it keeps its proportions)
COLUMNS = (("id", "ID", 60), ("created", "Created", 140), ("severity", "Severity", 90),
           ("status", "Status", 110), ("summary", "Summary", 560))  # (name, heading, width)


def default_save_dir() -> Path:
    """Where save dialogs start: the workspace in the container (the host sees it), else home."""
    return Path(__file__).resolve().parent.parent if os.path.exists("/.dockerenv") else Path.home()


def load_preview(path: str | None) -> bytes | None:
    """The PNG at path, shrunk to PREVIEW_SIZE, as base64 for Tk's PhotoImage; None if there is no file.

    Pillow does the shrinking (Tk can only shrink by whole numbers), and Tk
    reads the result as PNG data, so Pillow's ImageTk module isn't needed
    (Debian ships it as a separate package, python3-pil.imagetk).
    """
    if not path or not Path(path).exists():
        return None
    with Image.open(path) as image:
        image.thumbnail(PREVIEW_SIZE)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue())


class BugListWindow(Toplevel):
    """The saved bug reports in a table, filtered by status, with the selected bug's screenshots.

    Several rows can be selected (Ctrl/Shift-click) for Delete and Export PDF.
    Edit (or a double-click) opens the first selected bug.
    """

    def __init__(self, master: Misc, repository: BugRepository, pdf_folder: Path = DEFAULT_PDF_DIR) -> None:
        super().__init__(master)
        self.repository = repository
        self.pdf_folder = pdf_folder
        self.reports: dict[int, BugReport] = {}  # the rows shown, by id
        self.previews: list[PhotoImage] = []  # keeps the images alive (Tk drops unreferenced images)
        self.save_dir = default_save_dir()
        self.title("Bug reports")
        self.geometry("1000x720")
        self.attributes("-topmost", True)  # above the always-on-top toolbar, which would cover its top

        bar = Frame(self, padx=8, pady=6)
        bar.pack(fill="x")
        Label(bar, text="Status").pack(side="left")
        self.status_var = StringVar(value=ALL_STATUSES)
        status_box = ttk.Combobox(bar, textvariable=self.status_var, state="readonly", width=14,
                                  values=[ALL_STATUSES, *(status.value for status in Status)])
        status_box.pack(side="left", padx=(4, 12))
        status_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        for text, command in (("Edit", self.edit_selected), ("Delete", self.delete_selected),
                              ("Export PDF", self.export_pdf)):
            Button(bar, text=text, command=command, width=10).pack(side="left", padx=2)
        self.message_label = Label(bar, text="", fg="#555")
        self.message_label.pack(side="left", padx=12)

        self.table = ttk.Treeview(self, columns=[name for name, _, _ in COLUMNS], show="headings",
                                  selectmode="extended", height=10)
        for name, heading, width in COLUMNS:
            self.table.heading(name, text=heading, anchor="w")
            self.table.column(name, width=width, stretch=(name == "summary"))
        self.table.pack(fill="both", expand=True, padx=8)
        self.table.bind("<<TreeviewSelect>>", lambda _event: self.show_preview())
        self.table.bind("<Double-1>", lambda _event: self.edit_selected())

        preview = Frame(self, padx=8, pady=8)
        preview.pack(fill="x")
        self.preview_labels: list[Label] = []
        for column, caption in enumerate(("Source", "Target")):
            Label(preview, text=caption).grid(row=0, column=column)
            # A fixed-size box, so the layout doesn't jump between an image and "No screenshot"
            box = Frame(preview, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], bg="#eee")
            box.grid(row=1, column=column, padx=4)
            box.pack_propagate(False)
            label = Label(box, bg="#eee")
            label.pack(fill="both", expand=True)
            self.preview_labels.append(label)

        self.refresh()

    # --- list --------------------------------------------------------------

    def refresh(self) -> None:
        """Reload the rows from the repository, keeping the selection where the bugs still exist."""
        selected = self.table.selection()
        status = self.status_var.get()
        reports = self.repository.list_all(None if status == ALL_STATUSES else Status(status))
        self.reports = {report.id: report for report in reports if report.id is not None}
        self.table.delete(*self.table.get_children())
        for report_id, report in self.reports.items():
            self.table.insert("", "end", iid=str(report_id), values=(
                f"{report_id:05d}", report.created_at.strftime("%Y-%m-%d %H:%M"),
                report.severity.value, report.status.value, report.summary))
        self.table.selection_set([iid for iid in selected if self.table.exists(iid)])
        self.show_preview()

    def selected_reports(self) -> list[BugReport]:
        return [self.reports[int(iid)] for iid in self.table.selection()]

    def show_preview(self) -> None:
        """Both screenshots of the first selected bug, or a note when there are none."""
        selected = self.selected_reports()
        self.previews.clear()
        for label, path in zip(self.preview_labels, self._screenshot_paths(selected[0] if selected else None)):
            data = load_preview(path)
            if data is None:
                label.config(image="", text="No screenshot" if selected else "")
                continue
            image = PhotoImage(master=self, data=data)
            self.previews.append(image)
            label.config(image=image, text="")

    @staticmethod
    def _screenshot_paths(report: BugReport | None) -> tuple[str | None, str | None]:
        return (report.source_screenshot, report.target_screenshot) if report else (None, None)

    # --- actions -----------------------------------------------------------

    def edit_selected(self) -> None:
        selected = self.selected_reports()
        if not selected:
            self.show_message("Select a bug to edit")
            return
        EditBugForm(self, selected[0], on_save=self._save_edit)

    def _save_edit(self, edited: BugReport) -> None:
        if self.repository.update(edited):
            self.show_message(f"Bug {edited.id:05d} saved")
        else:
            self.show_message(f"Bug {edited.id:05d} no longer exists")
        self.refresh()

    def delete_selected(self) -> None:
        selected = self.selected_reports()
        if not selected:
            self.show_message("Select the bugs to delete")
            return
        names = ", ".join(f"{report.id:05d}" for report in selected)
        if not messagebox.askyesno("Delete bugs", f"Delete bug {names} with its screenshots and PDF?",
                                   parent=self):
            return
        for report in selected:
            delete_report(self.repository, report, self.pdf_folder)
        self.show_message(f"Deleted {names}")
        self.refresh()

    def export_pdf(self) -> None:
        """The selected bugs, or all shown when none is selected, as one PDF where the tester picks."""
        reports = self.selected_reports() or list(self.reports.values())
        if not reports:
            self.show_message("No bugs to export")
            return
        name = pdf_path_for(reports[0]).name if len(reports) == 1 else "bug_reports.pdf"
        target = filedialog.asksaveasfilename(
            parent=self, title="Export bugs as PDF", initialdir=str(self.save_dir), initialfile=name,
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf"), ("All files", "*")])
        if not target:
            return
        PdfExporter().export(reports, Path(target))
        self.save_dir = Path(target).parent
        self.show_message(f"{len(reports)} bug(s) exported to {Path(target).name}")

    def show_message(self, text: str) -> None:
        self.message_label.config(text=text)


if __name__ == "__main__":
    import sys

    from reports.repository import SqliteBugRepository

    root = Tk()
    root.withdraw()
    window = BugListWindow(root, SqliteBugRepository(*sys.argv[1:2]))
    window.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
