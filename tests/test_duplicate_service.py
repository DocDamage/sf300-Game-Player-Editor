from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from sf3000.duplicate_service import find_duplicate_groups
from sf3000.layout import file_sha1
from sf3000.models import FileRecord


def make_record(path: Path, parent_name: str = "GBA") -> FileRecord:
    stat = path.stat()
    return FileRecord(
        path=path,
        display_name=path.stem,
        raw_name=path.name,
        size=stat.st_size,
        modified_text="",
        modified_ts=stat.st_mtime,
        file_type=path.suffix.lstrip(".").upper(),
        parent_name=parent_name,
        warning="",
    )


class DuplicateServiceTests(unittest.TestCase):
    def test_find_duplicate_groups_skips_zero_byte_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "empty-a.gba"
            second = root / "empty-b.gba"
            first.write_bytes(b"")
            second.write_bytes(b"")

            groups = find_duplicate_groups(
                [make_record(first), make_record(second)],
                hash_getter=file_sha1,
            )

            self.assertEqual(groups, [])

    def test_find_duplicate_groups_uses_content_hash_and_sorts_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            newest = root / "Mario (USA).gba"
            oldest = root / "Mario (Europe).gba"
            unique = root / "Zelda.gba"
            for path, payload in (
                (newest, b"same-rom"),
                (oldest, b"same-rom"),
                (unique, b"different"),
            ):
                path.write_bytes(payload)

            now = time.time()
            oldest.touch()
            newest.touch()
            unique.touch()
            oldest_time = now - 120
            newest_time = now - 30
            unique_time = now - 10
            os.utime(oldest, (oldest_time, oldest_time))
            os.utime(newest, (newest_time, newest_time))
            os.utime(unique, (unique_time, unique_time))

            groups = find_duplicate_groups(
                [make_record(newest), make_record(oldest), make_record(unique)],
                hash_getter=file_sha1,
            )

            self.assertEqual(len(groups), 1)
            group = groups[0]
            self.assertEqual(group.files, [newest, oldest])
            self.assertEqual(group.label, "Mario")
            self.assertEqual(group.size, len(b"same-rom"))
            self.assertEqual(group.duplicate_bytes, len(b"same-rom"))

    def test_find_duplicate_groups_skips_duplicate_paths_and_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate_a = root / "same-a.gba"
            duplicate_b = root / "same-b.gba"
            missing = root / "missing.gba"
            duplicate_a.write_bytes(b"same")
            duplicate_b.write_bytes(b"same")
            older_time = time.time() - 60
            newer_time = time.time() - 10
            os.utime(duplicate_a, (older_time, older_time))
            os.utime(duplicate_b, (newer_time, newer_time))

            progress_calls = []
            records = [
                make_record(duplicate_a),
                make_record(duplicate_a),
                make_record(duplicate_b),
                FileRecord(
                    path=missing,
                    display_name="missing",
                    raw_name="missing.gba",
                    size=4,
                    modified_text="",
                    modified_ts=0,
                    file_type="GBA",
                    parent_name="GBA",
                    warning="",
                ),
            ]

            groups = find_duplicate_groups(
                records,
                hash_getter=file_sha1,
                progress=lambda value, maximum, path: progress_calls.append((value, maximum, path)),
            )

            self.assertEqual(len(groups), 1)
            self.assertEqual(progress_calls[-1][:2], (2, 2))
            self.assertEqual(groups[0].files, [duplicate_b, duplicate_a])

    def test_find_duplicate_groups_returns_empty_when_cancelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.gba"
            second = root / "second.gba"
            first.write_bytes(b"same")
            second.write_bytes(b"same")

            calls = {"count": 0}

            def is_cancelled():
                calls["count"] += 1
                return calls["count"] >= 2

            groups = find_duplicate_groups(
                [make_record(first), make_record(second)],
                hash_getter=file_sha1,
                is_cancelled=is_cancelled,
            )

            self.assertEqual(groups, [])


if __name__ == "__main__":
    unittest.main()
