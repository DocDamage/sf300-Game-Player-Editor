from __future__ import annotations

import shutil
from tkinter import messagebox

from sf3000.app_constants import RUNTIME_LOG_FILE
from sf3000.runtime_env import append_runtime_log, log_exception_details


class SF3000LifecycleMixin:
    def report_callback_exception(self, exc_type, exc_value, exc_traceback):
        detail = log_exception_details(
            "Tkinter callback exception",
            exc_type,
            exc_value,
            exc_traceback,
        )
        try:
            self._log_event("error", "Tkinter callback exception.", detail)
        except Exception:
            pass
        try:
            self._set_status("The app hit an internal error. See the runtime log for details.")
        except Exception:
            pass
        try:
            self._show_toast(
                "The app hit an internal error. See the runtime log.",
                kind="error",
                duration_ms=4200,
            )
        except Exception:
            pass
        messagebox.showerror(
            "Unexpected Error",
            "The app hit an unexpected internal error.\n\n"
            f"Runtime log:\n{RUNTIME_LOG_FILE}\n\n"
            "The details were captured automatically.",
        )

    def _on_close_app(self):
        self._ui_state.is_closing = True
        self._log_event("session", "Application closed.")
        append_runtime_log("Application closed.")
        self._hide_toast()
        self._save_settings()
        shutil.rmtree(self._session_state.undo_cache_root, ignore_errors=True)
        self.destroy()
