from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sf3000.app_file_ops import SF3000FileOpsMixin
from sf3000.app_history import SF3000HistoryMixin
from sf3000.models import (
    BrowserSessionState,
    DeleteHistoryPayload,
    FileRecord,
    OperationSessionState,
    TransferHistoryPayload,
    TransferItem,
)


class DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class FileWorkflowHarness(SF3000HistoryMixin, SF3000FileOpsMixin):
    def __init__(self, root: Path, *, copy_mode: str = "copy", delete_to_recycle: bool = False):
        self._copy_mode = DummyVar(copy_mode)
        self._delete_to_recycle = DummyVar(delete_to_recycle)
        self._browser_state = BrowserSessionState()
        undo_root = root / "undo-cache"
        undo_root.mkdir(parents=True, exist_ok=True)
        self._session_state = OperationSessionState(undo_cache_root=undo_root)
        self.scan_calls = 0
        self.invalidated_paths = []
        self.logged_events = []
        self.toasts = []

    def _ensure_writable(self, _action_name: str) -> bool:
        return True

    def _show_toast(self, message: str, **kwargs):
        self.toasts.append((message, kwargs))

    def _log_event(self, *args):
        self.logged_events.append(args)

    def _invalidate_hash_cache(self, paths):
        self.invalidated_paths.extend(paths)

    def _scan_all(self):
        self.scan_calls += 1

    def _queue_ui(self, callback, *args, **kwargs):
        callback(*args, **kwargs)

    def _run_background_task(self, worker, *, on_success=None, on_error=None, on_finally=None):
        try:
            result = worker()
        except Exception as exc:
            if on_error is not None:
                on_error(exc)
        else:
            if on_success is not None:
                on_success(result)
        finally:
            if on_finally is not None:
                on_finally()


class FakeProgressDialog:
    def __init__(self, *_args, **_kwargs):
        self.cancelled = False
        self.updates = []

    def update_progress(self, value, maximum, path, stage):
        self.updates.append((value, maximum, path, stage))


def make_record(path: Path) -> FileRecord:
    stat = path.stat()
    return FileRecord(
        path=path,
        display_name=path.stem,
        raw_name=path.name,
        size=stat.st_size,
        modified_text="",
        modified_ts=stat.st_mtime,
        file_type=path.suffix.lstrip(".").upper(),
        parent_name=path.parent.name,
        warning="",
    )


class TransferAndUndoTests(unittest.TestCase):
    def test_build_transfer_plan_tracks_same_path_identical_and_overwrite_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "source"
            dest_dir = root / "dest"
            source_dir.mkdir()
            dest_dir.mkdir()

            identical_source = source_dir / "same-content.rom"
            identical_dest = dest_dir / "same-content.rom"
            identical_source.write_bytes(b"abc")
            identical_dest.write_bytes(b"abc")

            same_path_file = dest_dir / "already-there.rom"
            same_path_file.write_bytes(b"same")

            overwrite_source = source_dir / "overwrite.rom"
            overwrite_dest = dest_dir / "overwrite.rom"
            overwrite_source.write_bytes(b"new")
            overwrite_dest.write_bytes(b"old")

            harness = FileWorkflowHarness(root, copy_mode="copy")
            plan = harness._build_transfer_plan(
                [str(identical_source), str(same_path_file), str(overwrite_source)],
                dest_dir,
            )

            self.assertEqual(plan.skipped_identical, ["same-content.rom"])
            self.assertEqual(plan.skipped_same_path, ["already-there.rom"])
            self.assertEqual([item.source.name for item in plan.items], ["overwrite.rom"])
            self.assertEqual(plan.overwrites, ["overwrite.rom"])
            self.assertEqual(plan.total_bytes, len(b"new"))
            self.assertEqual(plan.required_bytes, len(b"new"))

    def test_execute_copy_overwrite_can_be_undone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "new.rom"
            destination = root / "device" / "game.rom"
            destination.parent.mkdir()
            source.write_bytes(b"new-data")
            destination.write_bytes(b"old-data")

            harness = FileWorkflowHarness(root, copy_mode="copy")
            action_id, action_dir = harness._begin_history_action("transfer")
            history_item = harness._execute_transfer_item(
                TransferItem(source=source, destination=destination, size=source.stat().st_size, overwrite=True),
                "copy",
                action_dir,
                1,
            )
            entry = harness._record_history_entry(
                "change",
                "Copied 1 file.",
                entry_id=action_id,
                undoable=True,
                undo_type="transfer_files",
                payload=TransferHistoryPayload(
                    workspace=action_dir,
                    mode="copy",
                    items=[history_item],
                ),
            )

            self.assertEqual(destination.read_bytes(), b"new-data")
            self.assertTrue(source.exists())
            self.assertIsInstance(entry.payload, TransferHistoryPayload)
            self.assertIsNotNone(history_item.backup)
            self.assertTrue(history_item.backup.exists())

            harness._undo_history_entry(entry)

            self.assertTrue(entry.undone)
            self.assertEqual(destination.read_bytes(), b"old-data")
            self.assertTrue(source.exists())
            self.assertEqual(harness.scan_calls, 1)

    def test_execute_move_can_be_undone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "library" / "move-me.rom"
            destination = root / "device" / "move-me.rom"
            source.parent.mkdir()
            destination.parent.mkdir()
            source.write_bytes(b"payload")

            harness = FileWorkflowHarness(root, copy_mode="move")
            action_id, action_dir = harness._begin_history_action("transfer")
            history_item = harness._execute_transfer_item(
                TransferItem(source=source, destination=destination, size=source.stat().st_size, overwrite=False),
                "move",
                action_dir,
                1,
            )
            entry = harness._record_history_entry(
                "change",
                "Moved 1 file.",
                entry_id=action_id,
                undoable=True,
                undo_type="transfer_files",
                payload=TransferHistoryPayload(
                    workspace=action_dir,
                    mode="move",
                    items=[history_item],
                ),
            )

            self.assertFalse(source.exists())
            self.assertEqual(destination.read_bytes(), b"payload")
            self.assertIsInstance(entry.payload, TransferHistoryPayload)

            harness._undo_history_entry(entry)

            self.assertTrue(entry.undone)
            self.assertEqual(source.read_bytes(), b"payload")
            self.assertFalse(destination.exists())

    def test_delete_records_creates_undoable_history_and_restores_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "device" / "delete-me.rom"
            target.parent.mkdir()
            target.write_bytes(b"keep-me")

            harness = FileWorkflowHarness(root, delete_to_recycle=False)
            record = make_record(target)

            with patch("sf3000.app_file_ops.messagebox.showerror") as showerror:
                deleted = harness._delete_records([record], "game file", confirm=False)

            self.assertTrue(deleted)
            self.assertFalse(target.exists())
            self.assertFalse(showerror.called)
            self.assertEqual(len(harness._session_state.history_entries), 1)
            self.assertIsInstance(
                harness._session_state.history_entries[0].payload,
                DeleteHistoryPayload,
            )

            harness._undo_history_entry(harness._session_state.history_entries[0])

            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(), b"keep-me")

    def test_copy_files_to_runs_through_shared_background_helper_and_records_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "library" / "import-me.rom"
            destination_dir = root / "device"
            source.parent.mkdir()
            destination_dir.mkdir()
            source.write_bytes(b"payload")

            harness = FileWorkflowHarness(root, copy_mode="copy")
            done_calls = []

            with patch("sf3000.app_file_ops.messagebox.askyesno", return_value=True), patch(
                "sf3000.app_file_ops.messagebox.showinfo"
            ), patch(
                "sf3000.app_file_ops.messagebox.showerror"
            ) as showerror, patch(
                "sf3000.app_file_ops.ProgressDialog",
                FakeProgressDialog,
            ):
                harness._copy_files_to([str(source)], destination_dir, lambda: done_calls.append("done"))

            destination = destination_dir / source.name
            self.assertTrue(destination.exists())
            self.assertEqual(destination.read_bytes(), b"payload")
            self.assertEqual(done_calls, ["done"])
            self.assertFalse(showerror.called)
            self.assertEqual(len(harness._session_state.history_entries), 1)
            self.assertIsInstance(
                harness._session_state.history_entries[0].payload, TransferHistoryPayload
            )
            self.assertEqual(harness.scan_calls, 0)
            self.assertTrue(any(path == destination for path in harness.invalidated_paths))


if __name__ == "__main__":
    unittest.main()
