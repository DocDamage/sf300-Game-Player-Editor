from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sf3000.app_browser_controller import SF3000BrowserControllerMixin
from sf3000.app_history import SF3000HistoryMixin
from sf3000.models import (
    BrowserSessionState,
    CreateFoldersHistoryPayload,
    OperationSessionState,
    RenameHistoryPair,
    RenameHistoryPayload,
    ScanPayload,
    TransferHistoryItem,
    TransferHistoryPayload,
)


class ScanHarness(SF3000BrowserControllerMixin):
    pass


class DummyHistoryHarness(SF3000HistoryMixin):
    def __init__(self, root: Path):
        undo_root = root / "undo-cache"
        undo_root.mkdir(parents=True, exist_ok=True)
        self._session_state = OperationSessionState(undo_cache_root=undo_root)
        self._browser_state = BrowserSessionState()
        self.invalidated = []
        self.logged = []
        self.scans = 0

    def _ensure_writable(self, _action_name: str) -> bool:
        return True

    def _invalidate_hash_cache(self, paths):
        self.invalidated.extend(paths)

    def _log_event(self, *args):
        self.logged.append(args)

    def _show_toast(self, *_args, **_kwargs):
        pass

    def _scan_all(self):
        self.scans += 1


class TypedPayloadTests(unittest.TestCase):
    def test_collect_scan_payload_returns_typed_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom_folder = root / "GBA"
            rom_folder.mkdir()
            (rom_folder / "test.gba").write_bytes(b"rom")

            payload = ScanHarness()._collect_scan_payload(root)

        self.assertIsInstance(payload, ScanPayload)
        self.assertEqual(payload.root, root)
        self.assertEqual(payload.games.total_files, 1)
        self.assertEqual(payload.games.folder_rows[0].name, "GBA")
        self.assertIn("__all__", payload.games.records_by_key)

    def test_history_entry_keeps_typed_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = DummyHistoryHarness(root)
            payload = RenameHistoryPayload(
                pairs=[RenameHistoryPair(source=root / "from.rom", destination=root / "to.rom")]
            )

            entry = harness._record_history_entry(
                "change",
                "Rename one file",
                undoable=True,
                undo_type="rename_files",
                payload=payload,
            )

        self.assertIs(entry.payload, payload)

    def test_transfer_history_payload_drives_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "device" / "game.rom"
            backup = root / "undo-cache" / "backup.rom"
            destination.parent.mkdir(parents=True, exist_ok=True)
            backup.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"new")
            backup.write_bytes(b"old")

            harness = DummyHistoryHarness(root)
            entry = harness._record_history_entry(
                "change",
                "Transfer one file",
                undoable=True,
                undo_type="transfer_files",
                payload=TransferHistoryPayload(
                    workspace=backup.parent,
                    mode="copy",
                    items=[
                        TransferHistoryItem(
                            destination=destination,
                            created=False,
                            backup=backup,
                            source_origin=None,
                        )
                    ],
                ),
            )

            harness._undo_history_entry(entry)

            self.assertTrue(entry.undone)
            self.assertEqual(destination.read_bytes(), b"old")
            self.assertEqual(harness.scans, 1)

    def test_create_folders_payload_drives_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "created-folder"
            folder.mkdir()
            harness = DummyHistoryHarness(root)
            entry = harness._record_history_entry(
                "change",
                "Create folder",
                undoable=True,
                undo_type="create_folders",
                payload=CreateFoldersHistoryPayload(paths=[folder]),
            )

            harness._undo_history_entry(entry)

            self.assertTrue(entry.undone)
            self.assertFalse(folder.exists())


if __name__ == "__main__":
    unittest.main()
