"""The "Report bug" form: a small window over the toolbar.

It only collects what the tester types. Saving (screenshots, URLs, the
database) is the on_save callback's job, so the form works with any engine.
"""
from dataclasses import replace
from tkinter import END, Event, Frame, Label, Misc, Text, Toplevel, Tk, Button, Entry, StringVar
from tkinter import ttk
from typing import Callable

from reports.model import BugDraft, BugReport, Resolution, Severity, Status

# Called with the form's fields when the tester clicks Save
OnSave = Callable[[BugDraft], None]
# Called with the edited copy of the report when the tester clicks Save
OnEdit = Callable[[BugReport], None]

NO_RESOLUTION = "---"  # how Bugzilla shows an open bug's empty resolution

# Window title of the form that opens when a clicked element is missing on the Target
MISSING_ELEMENT_TITLE = "Clicked element not found on Target site. Please report a bug."


def missing_element_texts(element_name: str) -> tuple[str, str]:
    """Summary and Description of a missing-element report (Reqirements.md, Phase 5 element 6)."""
    summary = f"Element {element_name} not found"
    description = (f"Test Result:\nOn target page element {element_name} cannot be found.\n\n"
                   "Expected Result:\nClickable element should be present on target page.")
    return summary, description


def add_url_field(form: Toplevel, row: int, label: str, url: str) -> StringVar:
    """A label and an editable URL entry in this row of the form's grid; returns the entry's variable.

    Long URLs scroll inside the entry; the end (a lesson's #/lessons/...) is
    shown first, as it tells the pages apart.
    """
    Label(form, text=label).grid(row=row, column=0, sticky="w")
    var = StringVar(value=url)
    entry = Entry(form, textvariable=var, width=60)
    entry.grid(row=row, column=1, sticky="we", pady=2)
    entry.xview_moveto(1.0)
    return var


class ReportBugForm(Toplevel):
    """Summary, Source and Target URL, severity and description, with Save, Save and create PDF, and Cancel.

    Save is refused while the summary is empty (Bugzilla requires one, and
    the bug list will show it). Enter in the summary saves, Escape cancels.
    """

    def __init__(self, master: Tk, on_save: OnSave, on_save_pdf: OnSave | None = None,
                 urls: tuple[str, str] = ("", ""), title: str = "Report bug",
                 summary: str = "", description: str = "") -> None:
        """on_save_pdf: same fields, for the "Save and create PDF" button (hidden when None).

        urls: (source, target) to prefill, normally the pages open in the two windows.
        title, summary, description: the window title and prefilled texts; the
        defaults are the toolbar's empty Report bug form. The missing-element
        report passes its own (see missing_element_texts).
        """
        super().__init__(master)
        self.on_save = on_save
        self.on_save_pdf = on_save_pdf
        self.title(title)
        self.attributes("-topmost", True)  # stay above the browser windows
        self.resizable(False, False)
        self.configure(padx=10, pady=8)

        Label(self, text="Summary").grid(row=0, column=0, sticky="w")
        self.summary_var = StringVar(value=summary)
        self.summary_entry = Entry(self, textvariable=self.summary_var, width=60)
        self.summary_entry.grid(row=0, column=1, sticky="we", pady=2)

        self.source_url_var = add_url_field(self, 1, "Source URL", urls[0])
        self.target_url_var = add_url_field(self, 2, "Target URL", urls[1])

        Label(self, text="Severity").grid(row=3, column=0, sticky="w")
        self.severity_var = StringVar(value=Severity.NORMAL.value)
        ttk.Combobox(self, textvariable=self.severity_var, state="readonly", width=14,
                     values=[severity.value for severity in Severity]
                     ).grid(row=3, column=1, sticky="w", pady=2)

        Label(self, text="Description").grid(row=4, column=0, sticky="nw")
        self.description_text = Text(self, width=60, height=8, wrap="word")
        self.description_text.insert("1.0", description)
        self.description_text.grid(row=4, column=1, pady=2)

        self.error_label = Label(self, text="", fg="#c00")
        self.error_label.grid(row=5, column=1, sticky="w")

        buttons = Frame(self)
        buttons.grid(row=6, column=1, sticky="e", pady=(4, 0))
        Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        if on_save_pdf is not None:
            Button(buttons, text="Save and create PDF", command=lambda: self.save(create_pdf=True),
                   bg="#4CAF50", fg="#fff").pack(side="right", padx=(0, 6))
        Button(buttons, text="Save", command=self.save, bg="#4CAF50", fg="#fff").pack(side="right", padx=(0, 6))

        self.summary_entry.bind("<Return>", lambda _event: self.save())
        self.bind("<Escape>", lambda _event: self.destroy())
        self._place_below(master)
        self.summary_entry.focus_force()  # the toolbar is a dock, so ask for focus explicitly

    def save(self, create_pdf: bool = False) -> None:
        summary = self.summary_var.get().strip()
        if not summary:
            self.error_label.config(text="A summary is required")
            self.summary_entry.focus_set()
            return
        draft = BugDraft(
            summary=summary,
            description=self.description_text.get("1.0", END).strip(),
            severity=Severity(self.severity_var.get()),
            source_url=self.source_url_var.get().strip(),
            target_url=self.target_url_var.get().strip(),
        )
        self.destroy()  # close first: the callback may take a moment (screenshots)
        callback = self.on_save_pdf if create_pdf and self.on_save_pdf else self.on_save
        callback(draft)

    def _place_below(self, master: Tk) -> None:
        """Open just below the toolbar, so it doesn't cover the left page's top."""
        master.update_idletasks()
        self.geometry(f"+{master.winfo_x()}+{master.winfo_y() + master.winfo_height() + 4}")


class EditBugForm(Toplevel):
    """Change a saved report: summary, Source and Target URL, severity, status, resolution and description.

    Opened from the bug list. Like ReportBugForm, it only collects the fields;
    on_save gets an edited copy of the report and does the saving. The
    original report object is not changed, so Cancel needs no undo.
    """

    def __init__(self, master: Misc, report: BugReport, on_save: OnEdit) -> None:
        super().__init__(master)
        self.report = report
        self.on_save = on_save
        self.title(f"Edit bug {report.id:05d}")
        self.transient(master)  # stays above the bug list
        self.attributes("-topmost", True)  # and above the always-on-top toolbar, like the Report bug form
        self.resizable(False, False)
        self.configure(padx=10, pady=8)

        Label(self, text="Summary").grid(row=0, column=0, sticky="w")
        self.summary_var = StringVar(value=report.summary)
        self.summary_entry = Entry(self, textvariable=self.summary_var, width=60)
        self.summary_entry.grid(row=0, column=1, sticky="we", pady=2)

        self.source_url_var = add_url_field(self, 1, "Source URL", report.source_url)
        self.target_url_var = add_url_field(self, 2, "Target URL", report.target_url)

        self.severity_var = self._add_choice(3, "Severity", report.severity.value, [s.value for s in Severity])
        self.status_var = self._add_choice(4, "Status", report.status.value, [s.value for s in Status])
        self.resolution_var = self._add_choice(5, "Resolution", report.resolution.value or NO_RESOLUTION,
                                               [r.value or NO_RESOLUTION for r in Resolution])

        Label(self, text="Description").grid(row=6, column=0, sticky="nw")
        self.description_text = Text(self, width=60, height=8, wrap="word")
        self.description_text.insert("1.0", report.description)
        self.description_text.grid(row=6, column=1, pady=2)

        self.error_label = Label(self, text="", fg="#c00")
        self.error_label.grid(row=7, column=1, sticky="w")

        buttons = Frame(self)
        buttons.grid(row=8, column=1, sticky="e", pady=(4, 0))
        Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        Button(buttons, text="Save", command=self.save, bg="#4CAF50", fg="#fff").pack(side="right", padx=(0, 6))

        self.summary_entry.bind("<Return>", lambda _event: self.save())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.summary_entry.focus_set()

    def _add_choice(self, row: int, label: str, value: str, values: list[str]) -> StringVar:
        """A label and a read-only drop-down list in this row; returns the list's variable."""
        Label(self, text=label).grid(row=row, column=0, sticky="w")
        var = StringVar(value=value)
        ttk.Combobox(self, textvariable=var, state="readonly", width=14, values=values
                     ).grid(row=row, column=1, sticky="w", pady=2)
        return var

    def save(self) -> None:
        summary = self.summary_var.get().strip()
        if not summary:
            self.error_label.config(text="A summary is required")
            self.summary_entry.focus_set()
            return
        resolution = self.resolution_var.get()
        edited = replace(
            self.report,
            summary=summary,
            source_url=self.source_url_var.get().strip(),
            target_url=self.target_url_var.get().strip(),
            description=self.description_text.get("1.0", END).strip(),
            severity=Severity(self.severity_var.get()),
            status=Status(self.status_var.get()),
            resolution=Resolution("" if resolution == NO_RESOLUTION else resolution),
        )
        self.destroy()
        self.on_save(edited)


if __name__ == "__main__":
    # Run a form alone for layout testing: python3 report_form.py [edit | missing]
    import sys

    root = Tk()
    if sys.argv[1:] == ["missing"]:
        root.withdraw()
        summary, description = missing_element_texts("Button B")
        form: Toplevel = ReportBugForm(root, lambda draft: print("Saved:", draft),
                                       lambda draft: print("Saved, PDF requested:", draft),
                                       urls=("http://localhost:8000/index.html", "http://127.0.0.1:8000/index2.html"),
                                       title=MISSING_ELEMENT_TITLE, summary=summary, description=description)
    elif sys.argv[1:] == ["edit"]:
        # root stays visible: X hides a transient window while its parent is hidden
        sample = BugReport(engine="selenium", source_url="http://localhost/a", target_url="http://127.0.0.1/a",
                           summary="Typo on slide 3", description="Missing letter", id=7)
        form = EditBugForm(root, sample, lambda edited: print("Saved:", edited))
    else:
        root.withdraw()
        form = ReportBugForm(root, lambda draft: print("Saved:", draft),
                             lambda draft: print("Saved, PDF requested:", draft),
                             urls=("http://localhost:8000/index.html", "http://127.0.0.1:8000/index.html"))
    root.wait_window(form)  # returns on Save, Cancel or Escape
