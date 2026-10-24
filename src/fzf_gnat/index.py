"""Index the Ada files of a tree, keeping a per-root cache of unit names."""

import csv
import hashlib
import logging
import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from fzf_gnat.names import symbols, unit_name

log = logging.getLogger(__name__)

SKIP_DIRS = {".git", "obj", "lib"}

# dekrunch builds these views of a tree, with unit-named links back to the
# sources, so indexing them would list every file twice.
SKIP_DIR_SUFFIX = ".dekrunched"


# What a cache keeps for one file: mtime_ns, size, and its records. A record
# is a tuple of strings, such as (unit, kind, line) for the file index.
Record = tuple[str, ...]
Stored = tuple[int, int, list[Record]]


@dataclass(frozen=True)
class Entry:
    """One line of the file search list."""

    relpath: str
    unit: str
    kind: str
    line: int = field(default=1, compare=False)


@dataclass(frozen=True)
class SymbolEntry:
    """One line of the symbol search list."""

    relpath: str
    name: str
    kind: str
    line: int
    unit: str
    """The unit of the file the symbol is in."""


def cache_path(root: Path, variant: str = "") -> Path:
    """Return the cache file of ``variant`` for ``root``, the same for every spelling of it."""
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    key = hashlib.sha1(str(root.resolve()).encode()).hexdigest()
    suffix = f".{variant}" if variant else ""
    return base / "fzf-gnat" / f"{key}{suffix}.tsv"


def _walk(root: Path):
    # Symlinked directories are followed, but each real directory is entered
    # only once, so a link loop ends and a linked copy is not listed twice.
    seen = set()

    def first_visit(path: str) -> bool:
        try:
            st = os.stat(path)
        except OSError:
            return False
        key = (st.st_dev, st.st_ino)
        if key in seen:
            return False
        seen.add(key)
        return True

    first_visit(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SKIP_DIRS
            and not d.endswith(SKIP_DIR_SUFFIX)
            and first_visit(os.path.join(dirpath, d))
        ]
        for name in filenames:
            if not name.endswith((".ads", ".adb")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            if "\t" in rel or "\n" in rel:
                log.warning(f"skipping {rel!r}: tab or newline in path")
                continue
            yield rel


def _read_cache(path: Path) -> dict[str, Stored] | None:
    # One line per record; a file without records keeps a line with only
    # its path, mtime and size, so that it is not parsed again.
    rows: dict[str, Stored] = {}
    try:
        with path.open(newline="") as f:
            for rel, mtime, size, *record in csv.reader(f, delimiter="\t"):
                stored = rows.setdefault(rel, (int(mtime), int(size), []))
                if record:
                    stored[2].append(tuple(record))
    except (OSError, ValueError):
        return None
    return rows


def _find_store(root: Path, variant: str) -> tuple[Path, str, dict[str, Stored]]:
    """Return the nearest readable cache of ``root`` or an ancestor, root's path prefix in it, and its rows."""
    for tree in (root, *root.parents):
        path = cache_path(tree, variant)
        if tree != root and not path.exists():
            continue
        rows = _read_cache(path)
        if rows is not None:
            prefix = root.relative_to(tree).as_posix()
            return path, "" if prefix == "." else f"{prefix}/", rows
    return cache_path(root, variant), "", {}


def _write_cache(path: Path, rows: dict[str, Stored]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # A unique temp name, so that two runs on the same root never write the
    # same file; the last rename wins.
    with tempfile.NamedTemporaryFile(
        "w", newline="", dir=path.parent, suffix=".tmp", delete=False
    ) as f:
        try:
            writer = csv.writer(f, delimiter="\t", lineterminator="\n")
            for rel, (mtime, size, records) in sorted(rows.items()):
                for record in records or [()]:
                    writer.writerow([rel, mtime, size, *record])
        except BaseException:
            os.unlink(f.name)
            raise
    os.replace(f.name, path)


def _scan(root: Path, variant: str, rebuild: bool, progress, extract) -> dict[str, list[Record]]:
    """Return the records of every Ada file under ``root``, calling ``extract(path)`` only for new or changed files.

    ``extract`` returns None to leave a file out. ``progress(done, total)`` is
    called before the first parse and after each one, where ``total`` counts
    only the files that need parsing.
    """
    root = root.resolve()
    # A tree inside an already indexed one shares its cache, so that moving
    # into a subdirectory does not mean parsing it all again.
    cache, prefix, stored = _find_store(root, variant)
    old = {} if rebuild else {
        rel[len(prefix):]: row for rel, row in stored.items() if rel.startswith(prefix)
    }
    rows: dict[str, Stored] = {}
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
                records = extract(root / rel)
            except KeyboardInterrupt:
                log.error(f"interrupted while parsing {rel}")
                raise
            except OSError as e:
                log.warning(f"skipping {rel}: {e.strerror}")
                records = None
            if records is not None:
                rows[rel] = (st.st_mtime_ns, st.st_size, records)
            if progress:
                progress(done, len(todo))
    finally:
        # Also on Ctrl-C, so that the next run resumes instead of starting over.
        merged = {rel: row for rel, row in stored.items() if not rel.startswith(prefix)}
        merged.update((f"{prefix}{rel}", row) for rel, row in rows.items())
        _write_cache(cache, merged)
    return {rel: records for rel, (_, _, records) in rows.items()}


def build_index(
    root: Path, rebuild: bool = False, namer=unit_name, progress=None
) -> list[Entry]:
    """Return the file entries of ``root`` sorted by unit then path; see ``_scan`` for caching and ``progress``."""

    def extract(path: Path) -> list[Record]:
        found = namer(path)
        if found is None:
            log.warning(f"{path.relative_to(root.resolve())}: no Ada unit found")
            return [("?", "body" if path.suffix == ".adb" else "spec", "1")]
        return [(found.name, found.kind, str(found.line))]

    rows = _scan(root, "", rebuild, progress, extract)
    return sorted(
        (
            Entry(rel, unit, kind, int(line))
            for rel, records in rows.items()
            for unit, kind, line in records
        ),
        key=lambda e: (e.unit, e.relpath),
    )


def build_symbol_index(
    root: Path, local: bool, rebuild: bool = False, progress=None
) -> list[SymbolEntry]:
    """Return the declarations under ``root``, with locals only if ``local``, sorted by name, path and line."""

    def extract(path: Path) -> list[Record]:
        return [(s.name, s.kind, str(s.line)) for s in symbols(path, local)]

    variant = "symbols-all" if local else "symbols"
    rows = _scan(root, variant, rebuild, progress, extract)
    return sorted(
        (
            # symbols() lists the unit itself first.
            SymbolEntry(rel, name, kind, int(line), records[0][0])
            for rel, records in rows.items()
            for name, kind, line in records
        ),
        key=lambda e: (e.name, e.relpath, e.line),
    )
