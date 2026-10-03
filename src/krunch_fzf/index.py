"""Index the Ada files of a tree, keeping a per-root cache of unit names."""

import csv
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from krunch_fzf.names import unit_name

log = logging.getLogger(__name__)

SKIP_DIRS = {".git", "obj", "lib"}


@dataclass(frozen=True)
class Entry:
    """One line of the search list."""

    relpath: str
    unit: str
    kind: str


def cache_path(root: Path) -> Path:
    """Return the cache file for ``root``, the same for every spelling of it."""
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    key = hashlib.sha1(str(root.resolve()).encode()).hexdigest()
    return base / "krunch-fzf" / f"{key}.tsv"


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith((".ads", ".adb")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            if "\t" in rel or "\n" in rel:
                log.warning(f"skipping {rel!r}: tab or newline in path")
                continue
            yield rel


def _read_cache(path: Path) -> dict[str, tuple[int, int, str, str]]:
    try:
        with path.open(newline="") as f:
            return {
                rel: (int(mtime), int(size), unit, kind)
                for rel, mtime, size, unit, kind in csv.reader(f, delimiter="\t")
            }
    except (OSError, ValueError):
        return {}


def _write_cache(path: Path, rows: dict[str, tuple[int, int, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        for rel, row in sorted(rows.items()):
            writer.writerow([rel, *row])
    tmp.replace(path)


def build_index(root: Path, rebuild: bool = False, namer=unit_name) -> list[Entry]:
    """Return the entries of ``root`` sorted by unit then path, parsing only new or changed files."""
    cache = cache_path(root)
    old = {} if rebuild else _read_cache(cache)
    rows = {}
    for rel in _walk(root):
        try:
            st = (root / rel).stat()
            hit = old.get(rel)
            if hit and hit[:2] == (st.st_mtime_ns, st.st_size):
                rows[rel] = hit
                continue
            found = namer(root / rel)
        except OSError as e:
            log.warning(f"skipping {rel}: {e.strerror}")
            continue
        if found is None:
            log.warning(f"{rel}: no Ada unit found")
            unit, kind = "?", "body" if rel.endswith(".adb") else "spec"
        else:
            unit, kind = found.name, found.kind
        rows[rel] = (st.st_mtime_ns, st.st_size, unit, kind)
    _write_cache(cache, rows)
    return sorted(
        (Entry(rel, unit, kind) for rel, (_, _, unit, kind) in rows.items()),
        key=lambda e: (e.unit, e.relpath),
    )
