from __future__ import annotations

import sys
import threading
import traceback
import tkinter as tk
from datetime import datetime

from sf3000.app_constants import APP_CACHE_DIR, APP_WINDOW_TITLE, RUNTIME_LOG_FILE

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    TKDND_AVAILABLE = True
    TkBase = TkinterDnD.Tk
except ImportError:
    DND_FILES = None
    TKDND_AVAILABLE = False
    TkBase = tk.Tk


def running_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def current_window_title() -> str:
    return APP_WINDOW_TITLE if running_frozen() else f"{APP_WINDOW_TITLE} [Live Debug]"


def append_runtime_log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        APP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with RUNTIME_LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message.rstrip()}\n")
    except Exception:
        pass


def log_exception_details(context: str, exc_type, exc_value, exc_traceback):
    detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)).strip()
    append_runtime_log(f"{context}\n{detail}\n")
    return detail


_RUNTIME_MONITOR_INSTALLED = False


def install_runtime_monitoring():
    global _RUNTIME_MONITOR_INSTALLED
    if _RUNTIME_MONITOR_INSTALLED:
        return
    _RUNTIME_MONITOR_INSTALLED = True

    previous_excepthook = sys.excepthook

    def runtime_excepthook(exc_type, exc_value, exc_traceback):
        log_exception_details("Unhandled exception", exc_type, exc_value, exc_traceback)
        if previous_excepthook:
            previous_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = runtime_excepthook

    if hasattr(threading, "excepthook"):
        previous_thread_hook = threading.excepthook

        def runtime_thread_excepthook(args):
            log_exception_details(
                f"Unhandled thread exception in {getattr(args.thread, 'name', 'thread')}",
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
            )
            if previous_thread_hook:
                previous_thread_hook(args)

        threading.excepthook = runtime_thread_excepthook
