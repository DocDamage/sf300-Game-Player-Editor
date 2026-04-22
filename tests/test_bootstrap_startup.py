from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sf3000_manager import SF3000GameManager


class BootstrapStartupTests(unittest.TestCase):
    def test_app_can_be_constructed_without_running_startup_side_effects(self):
        with patch.object(SF3000GameManager, "_load_settings", return_value={}), patch.object(
            SF3000GameManager, "_scan_all"
        ) as scan_all, patch.object(
            SF3000GameManager, "_auto_detect_drive"
        ) as auto_detect, patch.object(
            SF3000GameManager, "_refresh_drive_choices"
        ), patch.object(
            SF3000GameManager, "_prune_old_metadata_cache"
        ), patch.object(
            SF3000GameManager, "_log_event"
        ):
            app = SF3000GameManager(auto_startup=False)
            try:
                self.assertFalse(app._ui_state.startup_complete)
                self.assertFalse(scan_all.called)
                self.assertFalse(auto_detect.called)

                app._bootstrap_finish_startup()

                self.assertTrue(app._ui_state.startup_complete)
                scan_all.assert_not_called()
                auto_detect.assert_called_once_with()
            finally:
                app.destroy()

    def test_default_startup_scans_when_saved_path_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing_path = Path(tmp)
            with patch.object(
                SF3000GameManager,
                "_load_settings",
                return_value={"sd_path": str(existing_path)},
            ), patch.object(SF3000GameManager, "_scan_all") as scan_all, patch.object(
                SF3000GameManager, "_auto_detect_drive"
            ) as auto_detect, patch.object(
                SF3000GameManager, "_refresh_drive_choices"
            ), patch.object(
                SF3000GameManager, "_prune_old_metadata_cache"
            ), patch.object(
                SF3000GameManager, "_log_event"
            ):
                app = SF3000GameManager()
                try:
                    self.assertTrue(app._ui_state.startup_complete)
                    scan_all.assert_called_once_with()
                    auto_detect.assert_not_called()
                finally:
                    app.destroy()

    def test_bootstrap_finish_startup_is_idempotent(self):
        with patch.object(SF3000GameManager, "_load_settings", return_value={}), patch.object(
            SF3000GameManager, "_scan_all"
        ) as scan_all, patch.object(
            SF3000GameManager, "_auto_detect_drive"
        ) as auto_detect, patch.object(
            SF3000GameManager, "_refresh_drive_choices"
        ), patch.object(
            SF3000GameManager, "_prune_old_metadata_cache"
        ), patch.object(
            SF3000GameManager, "_log_event"
        ):
            app = SF3000GameManager(auto_startup=False)
            try:
                app._bootstrap_finish_startup()
                app._bootstrap_finish_startup()

                self.assertTrue(app._ui_state.startup_complete)
                scan_all.assert_not_called()
                auto_detect.assert_called_once_with()
            finally:
                app.destroy()

    def test_browser_session_state_is_initialized_explicitly(self):
        with patch.object(SF3000GameManager, "_load_settings", return_value={}), patch.object(
            SF3000GameManager, "_refresh_drive_choices"
        ), patch.object(
            SF3000GameManager, "_prune_old_metadata_cache"
        ), patch.object(
            SF3000GameManager, "_log_event"
        ):
            app = SF3000GameManager(auto_startup=False)
            try:
                self.assertEqual(app._browser_state.current_game_key, "__all__")
                app._browser_state.current_game_label = "GBA"
                self.assertEqual(app._browser_state.current_game_label, "GBA")
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
