"""The "Report bug" form: a small window over the toolbar.

It only collects what the tester types. Saving (screenshots, URLs, the
database) is the on_save callback's job, so the form works with any engine.
"""
from tkinter import END, Event, Frame, Label, Text, Toplevel, Tk, Button, Entry, StringVar
from tkinter import ttk
from typing import Callable

from reports.model import Severity

# Called with (summary, description, severity) when the tester clicks Save
OnSave = Callable[[str, str, Severity], None]


class ReportBugForm(Toplevel):
    """Summary, severity and description, with Save, Save and create PDF, and Cancel.

    Save is refused while the summary is empty (Bugzilla requires one, and
    the bug list will show it). Enter in the summary saves, Escape cancels.
    """

    def __init__(self, master: Tk, on_save: OnSave, on_save_pdf: OnSave | None = None) -> None:
        """on_save_pdf: same fields, for the "Save and create PDF" button (hidden when None)."""
        super().__init__(master)
        self.on_save = on_save
        self.on_save_pdf = on_save_pdf
        self.title("Report bug")
        self.attributes("-topmost", True)  # stay above the browser windows
        self.resizable(False, False)
        self.configure(padx=10, pady=8)

        Label(self, text="Summary").grid(row=0, column=0, sticky="w")
        self.summary_var = StringVar()
        self.summary_entry = Entry(self, textvariable=self.summary_var, width=60)
        self.summary_entry.grid(row=0, column=1, sticky="we", pady=2)

        Label(self, text="Severity").grid(row=1, column=0, sticky="w")
        self.severity_var = StringVar(value=Severity.NORMAL.value)
        ttk.Combobox(self, textvariable=self.severity_var, state="readonly", width=14,
                     values=[severity.value for severity in Severity]
                     ).grid(row=1, column=1, sticky="w", pady=2)

        Label(self, text="Description").grid(row=2, column=0, sticky="nw")
        self.description_text = Text(self, width=60, height=8, wrap="word")
        self.description_text.grid(row=2, column=1, pady=2)

        self.error_label = Label(self, text="", fg="#c00")
        self.error_label.grid(row=3, column=1, sticky="w")

        buttons = Frame(self)
        buttons.grid(row=4, column=1, sticky="e", pady=(4, 0))
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
        description = self.description_text.get("1.0", END).strip()
        severity = Severity(self.severity_var.get())
        self.destroy()  # close first: the callback may take a moment (screenshots)
        callback = self.on_save_pdf if create_pdf and self.on_save_pdf else self.on_save
        callback(summary, description, severity)

    def _place_below(self, master: Tk) -> None:
        """Open just below the toolbar, so it doesn't cover the left page's top."""
        master.update_idletasks()
        self.geometry(f"+{master.winfo_x()}+{master.winfo_y() + master.winfo_height() + 4}")


if __name__ == "__main__":
    # Run the form alone for layout testing
    root = Tk()
    root.withdraw()
    form = ReportBugForm(root, lambda *fields: print("Saved:", fields),
                         lambda *fields: print("Saved, PDF requested:", fields))
    root.wait_window(form)  # returns on Save, Cancel or Escape
