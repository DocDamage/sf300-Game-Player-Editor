from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from sf3000.app_browser_views import SF3000BrowserViewsMixin
from sf3000.app_state import SF3000StateMixin
from sf3000.app_support import SF3000SupportMixin
from sf3000.models import BrowserSessionState, DiagnosticsContextSnapshot, OperationSessionState, UIRuntimeState


class _Var:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class DiagnosticsHarness(SF3000SupportMixin, SF3000BrowserViewsMixin, SF3000StateMixin):
    def __init__(self):
        self._sd_path = _Var(r"H:\\")
        self._read_only_mode = _Var(False)
        self._copy_mode = _Var("copy")
        self._delete_to_recycle = _Var(True)
        self._status = _Var("Ready")
        self._browser_state = BrowserSessionState()
        self._session_state = OperationSessionState(undo_cache_root=Path("undo-cache"))
        self._ui_state = UIRuntimeState()
        self._dev_reference_repo = None

    def _queue_ui(self, callback, *args, **kwargs):
        callback(*args, **kwargs)


class DiagnosticsAsyncTests(unittest.TestCase):
    def test_build_diagnostics_text_uses_snapshot_and_patched_helpers(self):
        harness = DiagnosticsHarness()
        snapshot = harness._capture_diagnostics_context()

        with patch("sf3000.app_support.list_wsl_distros", return_value=["Ubuntu"]), patch(
            "sf3000.app_support.discover_mount_candidates",
            return_value=[],
        ), patch(
            "sf3000.app_support.choose_auto_mount_candidate",
            return_value=None,
        ), patch(
            "sf3000.app_support.get_drive_volume_state",
            return_value={"HealthStatus": "Healthy", "FileSystem": "", "FileSystemLabel": ""},
        ), patch(
            "sf3000.app_support.inspect_device_layout",
            return_value=None,
        ), patch(
            "sf3000.app_support.safe_exists",
            return_value=False,
        ):
            text = harness._build_diagnostics_text(snapshot)

        self.assertIn("Current path: H:\\\\", text)
        self.assertIn("WSL distros: Ubuntu", text)
        self.assertIn("Drive health: Healthy", text)

    def test_request_diagnostics_text_uses_cached_value_immediately(self):
        harness = DiagnosticsHarness()
        harness._session_state.diagnostics_text_cache = "cached diagnostics"
        values = []

        harness._request_diagnostics_text(values.append)

        self.assertEqual(values, ["cached diagnostics"])

    def test_request_diagnostics_text_builds_in_background_and_caches(self):
        harness = DiagnosticsHarness()
        values = []
        done = threading.Event()

        def build(snapshot: DiagnosticsContextSnapshot) -> str:
            return f"fresh:{snapshot.path_text}"

        with patch.object(harness, "_build_diagnostics_text", side_effect=build):
            harness._request_diagnostics_text(
                lambda value: (values.append(value), done.set()),
                force_refresh=True,
            )

        self.assertTrue(done.wait(2))
        self.assertEqual(values, [r"fresh:H:\\"])
        self.assertEqual(harness._session_state.diagnostics_text_cache, r"fresh:H:\\")

    def test_stale_diagnostics_request_result_is_dropped(self):
        harness = DiagnosticsHarness()
        values = []
        completed = threading.Event()
        first_started = threading.Event()
        second_started = threading.Event()
        release_first = threading.Event()
        release_second = threading.Event()

        first_snapshot = DiagnosticsContextSnapshot(
            generated_text="now",
            path_text="first",
            read_only_mode=False,
            copy_mode="copy",
            delete_to_recycle=True,
            current_status="A",
            roms_root=None,
            emu_root=None,
            dev_reference_repo=None,
            device_layout=None,
            core_catalog=None,
            activity_log=[],
        )
        second_snapshot = DiagnosticsContextSnapshot(
            generated_text="later",
            path_text="second",
            read_only_mode=False,
            copy_mode="copy",
            delete_to_recycle=True,
            current_status="B",
            roms_root=None,
            emu_root=None,
            dev_reference_repo=None,
            device_layout=None,
            core_catalog=None,
            activity_log=[],
        )

        def build(snapshot: DiagnosticsContextSnapshot) -> str:
            if snapshot.path_text == "first":
                first_started.set()
                release_first.wait(2)
                return "first-result"
            second_started.set()
            release_second.wait(2)
            return "second-result"

        with patch.object(
            harness,
            "_capture_diagnostics_context",
            side_effect=[first_snapshot, second_snapshot],
        ), patch.object(harness, "_build_diagnostics_text", side_effect=build):
            harness._request_diagnostics_text(values.append, force_refresh=True)
            self.assertTrue(first_started.wait(2))
            harness._request_diagnostics_text(
                lambda value: (values.append(value), completed.set()),
                force_refresh=True,
            )
            self.assertTrue(second_started.wait(2))
            release_second.set()
        self.assertTrue(completed.wait(2))
        release_first.set()
        time.sleep(0.05)

        self.assertEqual(values, ["second-result"])
        self.assertEqual(harness._session_state.diagnostics_text_cache, "second-result")

    def test_status_and_activity_changes_invalidate_diagnostics_cache(self):
        harness = DiagnosticsHarness()
        harness._session_state.diagnostics_text_cache = "stale"

        harness._log_event("scan", "Refreshed")
        self.assertEqual(harness._session_state.diagnostics_text_cache, "")

        harness._session_state.diagnostics_text_cache = "stale again"
        harness._set_status("Scanning")

        self.assertEqual(harness._session_state.diagnostics_text_cache, "")


if __name__ == "__main__":
    unittest.main()
