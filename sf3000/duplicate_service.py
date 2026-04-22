from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Sequence

from sf3000.layout import normalize_game_lookup_title, safe_exists, safe_stat
from sf3000.models import DuplicateGroup, FileRecord


def find_duplicate_groups(
    records: Sequence[FileRecord],
    *,
    hash_getter: Callable[[Path], str],
    progress: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> List[DuplicateGroup]:
    size_map: Dict[int, List[Path]] = {}
    seen = set()
    for record in records:
        key = str(record.path.resolve(strict=False)).casefold()
        if key in seen or not safe_exists(record.path) or not record.path.is_file():
            continue
        seen.add(key)
        size_map.setdefault(record.size, []).append(record.path)

    candidate_groups = [paths for size, paths in size_map.items() if size > 0 and len(paths) > 1]
    total = sum(len(paths) for paths in candidate_groups)
    processed = 0
    duplicate_groups: List[DuplicateGroup] = []

    for paths in candidate_groups:
        hash_map: Dict[str, List[Path]] = {}
        for path in paths:
            if is_cancelled and is_cancelled():
                return []
            processed += 1
            if progress is not None:
                progress(processed, total, str(path))
            digest = hash_getter(path)
            hash_map.setdefault(digest, []).append(path)

        for digest, matching_paths in hash_map.items():
            if len(matching_paths) < 2:
                continue
            matching_paths.sort(
                key=lambda item: (
                    -(safe_stat(item).st_mtime if safe_stat(item) else 0),
                    item.name.casefold(),
                )
            )
            first_stat = safe_stat(matching_paths[0])
            size = first_stat.st_size if first_stat else 0
            duplicate_groups.append(
                DuplicateGroup(
                    key=digest,
                    label=normalize_game_lookup_title(matching_paths[0].name),
                    files=matching_paths,
                    size=size,
                    duplicate_bytes=max(0, size * (len(matching_paths) - 1)),
                )
            )

    duplicate_groups.sort(key=lambda group: (-group.duplicate_bytes, group.label.casefold()))
    return duplicate_groups
