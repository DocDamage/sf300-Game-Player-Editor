from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from sf3000.archive_utils import inspect_restore_archive


class RestoreArchiveInspectionTests(unittest.TestCase):
    def test_filters_unsafe_restore_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "backup.zip"
            with zipfile.ZipFile(archive_path, "w") as bundle:
                bundle.writestr("games/one.rom", b"rom")
                bundle.writestr("../evil.txt", b"bad")
                bundle.writestr("/absolute.txt", b"bad")
                bundle.writestr("folder/", b"")

            with zipfile.ZipFile(archive_path, "r") as bundle:
                inspection = inspect_restore_archive(bundle)

        self.assertEqual(
            [(info.filename, rel.as_posix()) for info, rel in inspection.valid_members],
            [("games/one.rom", "games/one.rom")],
        )
        self.assertEqual(sorted(inspection.skipped_members), ["../evil.txt", "/absolute.txt"])


if __name__ == "__main__":
    unittest.main()
