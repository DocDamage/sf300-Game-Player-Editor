from pathlib import Path

import tkinter as tk
from tkinter import ttk


def format_size(value: int) -> str:
    n = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class ProgressDialog(tk.Toplevel):
    def __init__(self, parent, title: str = "Processing Files"):
        super().__init__(parent)
        self.title(title)
        self.geometry("460x140")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.cancelled = False
        self._filename_var = tk.StringVar(value="Preparing...")
        self._count_var = tk.StringVar(value="")

        ttk.Label(self, textvariable=self._filename_var, wraplength=430).pack(
            pady=(15, 4), padx=12, anchor="w"
        )
        self._bar = ttk.Progressbar(self, length=430, mode="determinate")
        self._bar.pack(pady=4, padx=12)
        ttk.Label(self, textvariable=self._count_var).pack()
        ttk.Button(self, text="Cancel", command=self._on_close).pack(pady=8)

    def update_progress(self, value: int, maximum: int, filepath: str, verb: str):
        if self.cancelled or not self.winfo_exists():
            return
        self._bar["maximum"] = maximum
        self._bar["value"] = value
        self._filename_var.set(f"{verb}: {Path(filepath).name}")
        self._count_var.set(f"{value} of {maximum}")
        self.update_idletasks()

    def _on_close(self):
        self.cancelled = True
        if self.winfo_exists():
            self.destroy()


class ToolTip:
    def __init__(self, widget, text, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._tip = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _resolve_text(self) -> str:
        value = self.text() if callable(self.text) else self.text
        return str(value).strip()

    def _schedule(self, _event=None):
        self._cancel()
        if not self._resolve_text():
            return
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        self._cancel()
        text = self._resolve_text()
        if not text:
            return
        if self._tip and self._tip.winfo_exists():
            self._tip.destroy()

        self._tip = tk.Toplevel(self.widget)
        self._tip.withdraw()
        self._tip.overrideredirect(True)
        self._tip.attributes("-topmost", True)
        label = tk.Label(
            self._tip,
            text=text,
            justify="left",
            bg="#0f172a",
            fg="#f8fafc",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            wraplength=360,
            font=("Segoe UI", 9),
        )
        label.pack()

        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._tip.geometry(f"+{x}+{y}")
        self._tip.deiconify()

    def _hide(self, _event=None):
        self._cancel()
        if self._tip and self._tip.winfo_exists():
            self._tip.destroy()
        self._tip = None
