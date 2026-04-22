from __future__ import annotations

import unittest

from sf3000.device_mount import (
    build_wsl_unc_paths,
    choose_auto_mount_candidate,
    extract_mount_signature,
    format_wsl_command_failure,
)
from sf3000.models import MountCandidate


class DeviceMountHelperTests(unittest.TestCase):
    def test_extract_mount_signature_reads_disk_and_partition(self):
        self.assertEqual(
            extract_mount_signature(r"\\wsl$\Ubuntu\mnt\wsl\sf3000-disk7-part1"),
            (7, 1),
        )
        self.assertEqual(extract_mount_signature(r"H:\\"), (None, None))

    def test_choose_auto_mount_candidate_prefers_exact_signature_match(self):
        candidates = [
            MountCandidate(
                disk_number=3,
                partition_number=1,
                physical_drive=r"\\.\PHYSICALDRIVE3",
                friendly_name="Other",
                drive_letter="E",
                filesystem="RAW",
                size=8_000_000_000,
                bus_type="USB",
                mount_name="sf3000-disk3-part1",
                score=120,
            ),
            MountCandidate(
                disk_number=7,
                partition_number=1,
                physical_drive=r"\\.\PHYSICALDRIVE7",
                friendly_name="Target",
                drive_letter="H",
                filesystem="RAW",
                size=16_000_000_000,
                bus_type="USB",
                mount_name="sf3000-disk7-part1",
                score=100,
            ),
        ]

        chosen = choose_auto_mount_candidate(
            candidates,
            r"\\wsl$\Ubuntu\mnt\wsl\sf3000-disk7-part1",
        )

        self.assertIsNotNone(chosen)
        self.assertEqual((chosen.disk_number, chosen.partition_number), (7, 1))

    def test_choose_auto_mount_candidate_uses_clear_score_gap(self):
        candidates = [
            MountCandidate(
                disk_number=4,
                partition_number=1,
                physical_drive=r"\\.\PHYSICALDRIVE4",
                friendly_name="Likely",
                drive_letter="",
                filesystem="RAW",
                size=32_000_000_000,
                bus_type="USB",
                mount_name="sf3000-disk4-part1",
                score=150,
            ),
            MountCandidate(
                disk_number=5,
                partition_number=1,
                physical_drive=r"\\.\PHYSICALDRIVE5",
                friendly_name="Less Likely",
                drive_letter="",
                filesystem="RAW",
                size=16_000_000_000,
                bus_type="USB",
                mount_name="sf3000-disk5-part1",
                score=90,
            ),
        ]

        chosen = choose_auto_mount_candidate(candidates, "")

        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.disk_number, 4)

    def test_build_wsl_unc_paths_returns_both_supported_prefixes(self):
        paths = build_wsl_unc_paths("Ubuntu", "sf3000-disk7-part1")
        self.assertEqual(
            [str(path) for path in paths],
            [
                r"\\wsl$\Ubuntu\mnt\wsl\sf3000-disk7-part1",
                r"\\wsl.localhost\Ubuntu\mnt\wsl\sf3000-disk7-part1",
            ],
        )

    def test_format_wsl_command_failure_translates_common_cases(self):
        self.assertEqual(
            format_wsl_command_failure("mount the SD card", 1223),
            "The Windows elevation prompt was canceled.",
        )
        self.assertIn(
            "WSL rejected the mount command",
            format_wsl_command_failure(
                "mount the SD card",
                1,
                stderr="Invalid command line argument",
            ),
        )


if __name__ == "__main__":
    unittest.main()
