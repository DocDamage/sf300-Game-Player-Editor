from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from sf3000.layout import sanitize_zip_member


@dataclass
class RestoreArchiveInspection:
    valid_members: List[Tuple[zipfile.ZipInfo, Path]] = field(default_factory=list)
    skipped_members: List[str] = field(default_factory=list)


def inspect_restore_archive(bundle: zipfile.ZipFile) -> RestoreArchiveInspection:
    inspection = RestoreArchiveInspection()
    for info in bundle.infolist():
        if info.is_dir():
            continue
        relative_path = sanitize_zip_member(info.filename)
        if relative_path is None:
            inspection.skipped_members.append(info.filename)
            continue
        inspection.valid_members.append((info, relative_path))
    return inspection


__all__ = ["RestoreArchiveInspection", "inspect_restore_archive"]
