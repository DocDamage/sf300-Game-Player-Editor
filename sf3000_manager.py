#!/usr/bin/env python3
"""
SF3000 Game Manager
Browse and manage games and emulators on your SF3000 SD card.

Requirements: Python 3.8+, no external packages needed.
Optional: Install tkinterdnd2 to enable drag-and-drop import.
Optional: If Windows cannot read the SD card directly, the app can try mounting it
          through WSL for you.
"""

from __future__ import annotations

from sf3000.app_bootstrap import SF3000BootstrapMixin
from sf3000.app_browser_controller import SF3000BrowserControllerMixin
from sf3000.app_browser_views import SF3000BrowserViewsMixin
from sf3000.app_device_tools import SF3000DeviceToolsMixin
from sf3000.app_duplicates import SF3000DuplicateMixin
from sf3000.app_file_ops import SF3000FileOpsMixin
from sf3000.app_history import SF3000HistoryMixin
from sf3000.app_input_shell import SF3000InputShellMixin
from sf3000.app_lifecycle import SF3000LifecycleMixin
from sf3000.app_metadata import SF3000MetadataMixin
from sf3000.app_state import SF3000StateMixin
from sf3000.app_support import SF3000SupportMixin
from sf3000.app_ui_scaffold import SF3000UIScaffoldMixin
from sf3000.app_validation_editing import SF3000ValidationEditingMixin
from sf3000.runtime_env import TkBase


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------
class SF3000GameManager(
    SF3000BootstrapMixin,
    SF3000LifecycleMixin,
    SF3000SupportMixin,
    SF3000HistoryMixin,
    SF3000StateMixin,
    SF3000BrowserControllerMixin,
    SF3000BrowserViewsMixin,
    SF3000UIScaffoldMixin,
    SF3000ValidationEditingMixin,
    SF3000InputShellMixin,
    SF3000DeviceToolsMixin,
    SF3000FileOpsMixin,
    SF3000DuplicateMixin,
    SF3000MetadataMixin,
    TkBase,
):
    pass
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SF3000GameManager()
    app.mainloop()
