"""Index the Ada files of a tree, keeping a per-root cache of unit names."""

import csv
import hashlib
import logging
import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from krunch_fzf.names import unit_name

log = logging.getLogger(__name__)

SKIP_DIRS = {".git", "obj", "lib"}

# dekrunch builds these views of a tree, with unit-named links back to the
# sources, so indexing them would list every file twice.
SKIP_DIR_SUFFIX = ".dekrunched"


# mtime_ns, size, unit, kind, line
Row = tuple[int, int, str, str, int]


@dataclass(frozen=True)
class Entry:
    """One line of the search list."""

    relpath: str
    unit: str
    kind: str
    line: int = field(default=1, compare=False)


def cache_path(root: Path) -> Path:
    """Return the cache file for ``root``, the same for every spelling of it."""
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    key = hashlib.sha1(str(root.resolve()).encode()).hexdigest()
    return base / "krunch-fzf" / f"{key}.tsv"


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.endswith(SKIP_DIR_SUFFIX)
        ]
        for name in filenames:
            if not name.endswith((".ads", ".adb")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            if "\t" in rel or "\n" in rel:
                log.warning(f"skipping {rel!r}: tab or newline in path")
                continue
            yield rel


def _read_cache(path: Path) -> dict[str, Row] | None:
    try:
        with path.open(newline="") as f:
            return {
                rel: (int(mtime), int(size), unit, kind, int(line))
                for rel, mtime, size, unit, kind, line in csv.reader(f, delimiter="\t")
            }
    except (OSError, ValueError):
        return None


def _find_store(root: Path) -> tuple[Path, str, dict[str, Row]]:
    """Return the nearest readable cache of ``root`` or an ancestor, root's path prefix in it, and its rows."""
    for tree in (root, *root.parents):
        path = cache_path(tree)
        if tree != root and not path.exists():
            continue
        rows = _read_cache(path)
        if rows is not None:
            prefix = root.relative_to(tree).as_posix()
            return path, "" if prefix == "." else f"{prefix}/", rows
    return cache_path(root), "", {}


def _write_cache(path: Path, rows: dict[str, Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # A unique temp name, so that two runs on the same root never write the
    # same file; the last rename wins.
    with tempfile.NamedTemporaryFile(
        "w", newline="", dir=path.parent, suffix=".tmp", delete=False
    ) as f:
        try:
            writer = csv.writer(f, delimiter="\t", lineterminator="\n")
            for rel, row in sorted(rows.items()):
                writer.writerow([rel, *row])
        except BaseException:
            os.unlink(f.name)
            raise
    os.replace(f.name, path)


def _parse(root: Path, rel: str, st: os.stat_result, namer) -> Row | None:
    try:
        found = namer(root / rel)
    except OSError as e:
        log.warning(f"skipping {rel}: {e.strerror}")
        return None
    if found is None:
        log.warning(f"{rel}: no Ada unit found")
        return (st.st_mtime_ns, st.st_size, "?", "body" if rel.endswith(".adb") else "spec", 1)
    return (st.st_mtime_ns, st.st_size, found.name, found.kind, found.line)


def build_index(
    root: Path, rebuild: bool = False, namer=unit_name, progress=None
) -> list[Entry]:
    """Return the entries of ``root`` sorted by unit then path, parsing only new or changed files.

    ``progress(done, total)`` is called before the first parse and after each
    one, where ``total`` counts only the files that need parsing.
    """
    root = root.resolve()
    # A tree inside an already indexed one shares its cache, so that moving
    # into a subdirectory does not mean parsing it all again.
    cache, prefix, stored = _find_store(root)
    old = {} if rebuild else {
        rel[len(prefix):]: row for rel, row in stored.items() if rel.startswith(prefix)
    }
    rows = {}
    todo = []
    for rel in _walk(root):
        try:
            st = (root / rel).stat()
        except OSError as e:
            log.warning(f"skipping {rel}: {e.strerror}")
            continue
        # Reading a FIFO or a device never returns.
        if not stat.S_ISREG(st.st_mode):
            log.warning(f"skipping {rel}: not a regular file")
            continue
        hit = old.get(rel)
        if hit and hit[:2] == (st.st_mtime_ns, st.st_size):
            rows[rel] = hit
        else:
            todo.append((rel, st))

    if todo and progress:
        progress(0, len(todo))
    try:
        for done, (rel, st) in enumerate(todo, start=1):
            try:
                row = _parse(root, rel, st, namer)
            except KeyboardInterrupt:
                log.error(f"interrupted while parsing {rel}")
                raise
            if row is not None:
                rows[rel] = row
            if progress:
                progress(done, len(todo))
    finally:
        # Also on Ctrl-C, so that the next run resumes instead of starting over.
        merged = {rel: row for rel, row in stored.items() if not rel.startswith(prefix)}
        merged.update((f"{prefix}{rel}", row) for rel, row in rows.items())
        _write_cache(cache, merged)
    return sorted(
        (Entry(rel, unit, kind, line) for rel, (_, _, unit, kind, line) in rows.items()),
        key=lambda e: (e.unit, e.relpath),
    )
