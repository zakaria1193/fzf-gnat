# krunch-fzf Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `krunch-fzf ROOT` command that fuzzy searches the Ada files of a tree by unit name and krunched file name, with a preview, and opens the selection in `$EDITOR`.

**Architecture:** `names.py` asks libadalang for the unit name of one file. `index.py` walks the tree and keeps a per-root TSV cache so only changed files are parsed again. `cli.py` feeds the index to fzf, reads back the selection, and runs the editor.

**Tech Stack:** Python 3.10+, `libadalang` (PyPI wheel), pytest, fzf on `PATH`.

**Spec:** `docs/superpowers/specs/2026-10-03-krunch-fzf-design.md`

## Global Constraints

- Python 3.10 or newer.
- Runtime dependency: `libadalang` only. fzf is a shell dependency, not a Python one.
- Command name: `krunch-fzf`. Package name: `krunch_fzf`, under `src/krunch_fzf/`.
- Index line format: `unit<TAB>kind<TAB>relpath`; kind is `spec`, `body` or `subunit`.
- Cache: `$XDG_CACHE_HOME/krunch-fzf/<sha1 of absolute root>.tsv`, falling back to `~/.cache/krunch-fzf/`. Row: `relpath mtime_ns size unit kind`, tab-separated.
- Exit status 2 for a bad root or missing fzf; 0 when the user presses Esc.
- Commits use `git commit --no-verify` and carry no `Co-Authored-By` trailer.
- Use f-strings, never `%` formatting.
- Comments explain why, never what. Docstrings are one sentence.

## Review Focus

- A file holding only `pragma No_Body;` has no unit: it must still appear, with unit `?`, and not crash.
- Unit names keep their source casing (`Ada.Strings.Unbounded`, not `ada.strings.unbounded`); libadalang symbols are case-folded, so the code must use node text.
- A path containing a tab or newline would break the TSV format: such files are skipped with a warning.
- `$EDITOR` may contain arguments (`code -w`): it must be split with `shlex`, not run as one word.
- The same tree given as `.`, `./`, or an absolute path must hit the same cache file.

Each line above has a test in the task that owns the code.

---

## File structure

```
krunch-fzf/
  pyproject.toml
  README.md
  src/krunch_fzf/__init__.py
  src/krunch_fzf/names.py      # libadalang: file -> UnitName
  src/krunch_fzf/index.py      # tree walk + cache -> list[Entry]
  src/krunch_fzf/cli.py        # argparse, fzf, editor
  tests/conftest.py            # shared tmp tree helper
  tests/test_names.py
  tests/test_index.py
  tests/test_cli.py
```

All commands run from `~/my_repos/krunch-fzf`.

---

### Task 1: Project scaffold and unit names

**Files:**
- Create: `pyproject.toml`, `src/krunch_fzf/__init__.py`, `src/krunch_fzf/names.py`, `tests/conftest.py`, `tests/test_names.py`, `.gitignore`

**Interfaces:**
- Produces: `krunch_fzf.names.UnitName(name: str, kind: str)` (frozen dataclass) and `krunch_fzf.names.unit_name(path: pathlib.Path) -> UnitName | None`.
- Produces: pytest fixture `make_tree(files: dict[str, str]) -> pathlib.Path` that writes the files under `tmp_path` and returns `tmp_path`.

- [ ] **Step 1: Write `pyproject.toml`, `.gitignore`, `__init__.py`**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "krunch-fzf"
version = "0.1.0"
description = "Fuzzy search Ada sources by unit name and krunched file name"
requires-python = ">=3.10"
dependencies = ["libadalang"]

[project.optional-dependencies]
dev = ["pytest>=7"]

[project.scripts]
krunch-fzf = "krunch_fzf.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

`.gitignore`:

```
.venv/
__pycache__/
*.egg-info/
```

`src/krunch_fzf/__init__.py`:

```python
"""Fuzzy search an Ada tree by unit name and krunched file name; start at ``cli.main``."""
```

- [ ] **Step 2: Create the venv and install**

Run:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -c "import libadalang; print(libadalang.__file__)"
```

Expected: the last command prints a path. If `pip` cannot find a `libadalang` wheel, stop and report to the user; do not switch to another parser.

- [ ] **Step 3: Write the fixture and failing tests**

`tests/conftest.py`:

```python
import pytest


@pytest.fixture
def make_tree(tmp_path):
    def make(files):
        for rel, text in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return tmp_path

    return make
```

`tests/test_names.py`:

```python
import pytest

from krunch_fzf.names import UnitName, unit_name

CASES = {
    "a-strunb.ads": (
        "package Ada.Strings.Unbounded is\nend Ada.Strings.Unbounded;\n",
        UnitName("Ada.Strings.Unbounded", "spec"),
    ),
    "a-strunb.adb": (
        "package body Ada.Strings.Unbounded is\nend Ada.Strings.Unbounded;\n",
        UnitName("Ada.Strings.Unbounded", "body"),
    ),
    "s-textio__pl011.adb": (
        "package body System.Text_IO is\nend System.Text_IO;\n",
        UnitName("System.Text_IO", "body"),
    ),
    "g-list.ads": (
        "generic\n   type T is private;\npackage GNAT.List is\nend GNAT.List;\n",
        UnitName("GNAT.List", "spec"),
    ),
    "p-priv.ads": (
        "private package P.Priv is\nend P.Priv;\n",
        UnitName("P.Priv", "spec"),
    ),
    "main.adb": (
        "procedure Main is\nbegin\n   null;\nend Main;\n",
        UnitName("Main", "body"),
    ),
    "hello.ads": (
        "function Hello return Integer;\n",
        UnitName("Hello", "spec"),
    ),
    "p-sub.adb": (
        "separate (P)\nprocedure Sub is\nbegin\n   null;\nend Sub;\n",
        UnitName("P.Sub", "subunit"),
    ),
}


@pytest.mark.parametrize("rel", sorted(CASES))
def test_unit_name(make_tree, rel):
    text, expected = CASES[rel]
    root = make_tree({rel: text})
    assert unit_name(root / rel) == expected


def test_no_body_file_has_no_name(make_tree):
    root = make_tree({"x.adb": "pragma No_Body;\n"})
    assert unit_name(root / "x.adb") is None


def test_garbage_has_no_name(make_tree):
    root = make_tree({"x.ads": "@@@ this is not Ada @@@\n"})
    assert unit_name(root / "x.ads") is None
```

- [ ] **Step 4: Run the tests to see them fail**

Run: `.venv/bin/pytest tests/test_names.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'krunch_fzf.names'`.

- [ ] **Step 5: Write `src/krunch_fzf/names.py`**

```python
"""Find the Ada unit that a source file holds."""

from dataclasses import dataclass
from pathlib import Path

import libadalang as lal


@dataclass(frozen=True)
class UnitName:
    """The unit held by one source file."""

    name: str
    """Fully qualified name in source casing, such as ``Ada.Strings.Unbounded``."""

    kind: str
    """``spec``, ``body`` or ``subunit``."""


def unit_name(path: Path) -> UnitName | None:
    """Return the first unit in ``path``, or None if libadalang finds no unit there."""
    # A fresh context per file keeps memory flat over trees of thousands of
    # files; the context would otherwise keep every parsed unit alive.
    root = lal.AnalysisContext().get_from_file(str(path)).root
    if isinstance(root, lal.CompilationUnitList):
        root = root[0] if len(root) > 0 else None
    if not isinstance(root, lal.CompilationUnit):
        return None

    # Node text, not p_syntactic_fully_qualified_name: libadalang symbols are
    # case-folded, and the search list should show names as written.
    body = root.f_body
    if isinstance(body, lal.Subunit):
        inner = body.f_body.p_defining_name
        if inner is None:
            return None
        return UnitName(f"{body.f_name.text}.{inner.text}", "subunit")
    if isinstance(body, lal.LibraryItem):
        item = body.f_item
        name = item.p_defining_name
        if name is None:
            return None
        return UnitName(name.text, "body" if isinstance(item, lal.Body) else "spec")
    return None
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `.venv/bin/pytest tests/test_names.py -v`
Expected: 10 passed. If `test_garbage_has_no_name` fails because error recovery builds a unit with a junk name, add a check that returns None when the analysis unit has diagnostics and the name is not a valid dotted identifier (`re.fullmatch(r"[A-Za-z]\w*(\.[A-Za-z]\w*)*", name)`), then rerun.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore src tests
git commit --no-verify -m "Find Ada unit names with libadalang"
```

---

### Task 2: Tree walk and cache

**Files:**
- Create: `src/krunch_fzf/index.py`, `tests/test_index.py`

**Interfaces:**
- Consumes: `unit_name(path: Path) -> UnitName | None` from Task 1; fixture `make_tree`.
- Produces: `Entry(relpath: str, unit: str, kind: str)` (frozen dataclass), `cache_path(root: Path) -> Path`, and `build_index(root: Path, rebuild: bool = False, namer=unit_name) -> list[Entry]`, sorted by `(unit, relpath)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_index.py`:

```python
import os

import pytest

from krunch_fzf import index
from krunch_fzf.index import Entry, build_index, cache_path
from krunch_fzf.names import unit_name

TREE = {
    "libgnat/a-strunb.ads": "package Ada.Strings.Unbounded is\nend Ada.Strings.Unbounded;\n",
    "libgnat/a-strunb.adb": "package body Ada.Strings.Unbounded is\nend Ada.Strings.Unbounded;\n",
    "src/s-textio.ads": "package System.Text_IO is\nend System.Text_IO;\n",
    "src/notes.md": "not Ada\n",
    "obj/b~main.ads": "package Ada_Main is\nend Ada_Main;\n",
    ".git/x.ads": "package Hidden is\nend Hidden;\n",
}


@pytest.fixture(autouse=True)
def cache_home(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("cache")
    monkeypatch.setenv("XDG_CACHE_HOME", str(home))
    return home


class CountingNamer:
    def __init__(self):
        self.calls = []

    def __call__(self, path):
        self.calls.append(path.name)
        return unit_name(path)


def test_first_run_parses_all_ada_files(make_tree):
    root = make_tree(TREE)
    namer = CountingNamer()
    assert build_index(root, namer=namer) == [
        Entry("libgnat/a-strunb.adb", "Ada.Strings.Unbounded", "body"),
        Entry("libgnat/a-strunb.ads", "Ada.Strings.Unbounded", "spec"),
        Entry("src/s-textio.ads", "System.Text_IO", "spec"),
    ]
    assert sorted(namer.calls) == ["a-strunb.adb", "a-strunb.ads", "s-textio.ads"]


def test_second_run_parses_nothing(make_tree):
    root = make_tree(TREE)
    first = build_index(root)
    namer = CountingNamer()
    assert build_index(root, namer=namer) == first
    assert namer.calls == []


def test_changed_file_is_parsed_again(make_tree):
    root = make_tree(TREE)
    build_index(root)
    path = root / "src/s-textio.ads"
    path.write_text("package System.Text_IO_2 is\nend System.Text_IO_2;\n")
    namer = CountingNamer()
    entries = build_index(root, namer=namer)
    assert namer.calls == ["s-textio.ads"]
    assert Entry("src/s-textio.ads", "System.Text_IO_2", "spec") in entries


def test_deleted_file_leaves_index(make_tree):
    root = make_tree(TREE)
    build_index(root)
    (root / "src/s-textio.ads").unlink()
    assert all(e.relpath != "src/s-textio.ads" for e in build_index(root))


def test_rebuild_parses_everything(make_tree):
    root = make_tree(TREE)
    build_index(root)
    namer = CountingNamer()
    build_index(root, rebuild=True, namer=namer)
    assert len(namer.calls) == 3


def test_unnamed_file_gets_question_mark(make_tree):
    root = make_tree({"x.adb": "pragma No_Body;\n"})
    assert build_index(root) == [Entry("x.adb", "?", "body")]


def test_tab_in_path_is_skipped(make_tree):
    root = make_tree({"a\tb.ads": "package A is\nend A;\n"})
    assert build_index(root) == []


def test_root_spelling_shares_cache(make_tree, monkeypatch):
    root = make_tree(TREE)
    monkeypatch.chdir(root)
    assert cache_path(root) == cache_path(type(root)(".")) == cache_path(type(root)("./"))


def test_corrupt_cache_is_rebuilt(make_tree):
    root = make_tree(TREE)
    path = cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("garbage line\n")
    assert len(build_index(root)) == 3


def test_symlinked_dir_is_not_followed(make_tree):
    root = make_tree(TREE)
    os.symlink(root, root / "loop")
    assert len(build_index(root)) == 3
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/pytest tests/test_index.py -v`
Expected: FAIL with `ImportError: cannot import name 'Entry'` (module missing).

- [ ] **Step 3: Write `src/krunch_fzf/index.py`**

```python
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
        st = (root / rel).stat()
        hit = old.get(rel)
        if hit and hit[:2] == (st.st_mtime_ns, st.st_size):
            rows[rel] = hit
            continue
        found = namer(root / rel)
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
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/pytest -v`
Expected: all tests in `test_names.py` and `test_index.py` pass.

- [ ] **Step 5: Commit**

```bash
git add src/krunch_fzf/index.py tests/test_index.py
git commit --no-verify -m "Index Ada trees with a per-root cache"
```

---

### Task 3: Command line and fzf

**Files:**
- Create: `src/krunch_fzf/cli.py`, `tests/test_cli.py`, `README.md`

**Interfaces:**
- Consumes: `build_index(root: Path, rebuild: bool = False) -> list[Entry]` from Task 2.
- Produces: `format_line(entry: Entry) -> str`, `preview_command() -> str`, `fzf_argv(preview: str) -> list[str]`, `editor_argv(paths: list[str]) -> list[str]`, `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
import pytest

from krunch_fzf import cli
from krunch_fzf.index import Entry


@pytest.fixture(autouse=True)
def cache_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))


def test_format_line():
    entry = Entry("libgnat/a-strunb.ads", "Ada.Strings.Unbounded", "spec")
    assert cli.format_line(entry) == "Ada.Strings.Unbounded\tspec\tlibgnat/a-strunb.ads"


def test_print_writes_index(make_tree, capsys):
    root = make_tree({"src/s-textio.ads": "package System.Text_IO is\nend System.Text_IO;\n"})
    assert cli.main(["--print", str(root)]) == 0
    assert capsys.readouterr().out == "System.Text_IO\tspec\tsrc/s-textio.ads\n"


def test_missing_root_exits_2(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_missing_fzf_exits_2(make_tree, monkeypatch, capsys):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.main([str(root)]) == 2
    assert "fzf" in capsys.readouterr().err


def test_fzf_argv_searches_all_fields():
    argv = cli.fzf_argv("cat {3}")
    assert argv[0] == "fzf"
    assert "--multi" in argv
    assert argv[argv.index("--delimiter") + 1] == "\t"
    assert argv[argv.index("--preview") + 1] == "cat {3}"


def test_preview_falls_back_to_cat(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.preview_command() == "cat {3}"


def test_editor_with_arguments(monkeypatch):
    monkeypatch.setenv("EDITOR", "code -w")
    assert cli.editor_argv(["/r/a.ads"]) == ["code", "-w", "/r/a.ads"]


def test_editor_defaults_to_vi(monkeypatch):
    monkeypatch.delenv("EDITOR", raising=False)
    assert cli.editor_argv(["/r/a.ads"]) == ["vi", "/r/a.ads"]


class FakeRun:
    def __init__(self, fzf_status, fzf_out):
        self.calls = []
        self.fzf_status = fzf_status
        self.fzf_out = fzf_out

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        out = self.fzf_out if argv[0] == "fzf" else ""
        status = self.fzf_status if argv[0] == "fzf" else 0
        return cli.subprocess.CompletedProcess(argv, status, stdout=out)


def test_enter_opens_selection(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("EDITOR", "vi")
    run = FakeRun(0, "A\tspec\ta.ads\n")
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main([str(root)]) == 0
    assert run.calls[-1] == ["vi", str(root.resolve() / "a.ads")]


def test_escape_opens_nothing(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = FakeRun(130, "")
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main([str(root)]) == 0
    assert len(run.calls) == 1
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL with `ImportError: cannot import name 'cli'`.

- [ ] **Step 3: Write `src/krunch_fzf/cli.py`**

```python
"""The ``krunch-fzf`` command."""

import argparse
import logging
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from krunch_fzf.index import Entry, build_index


def format_line(entry: Entry) -> str:
    return f"{entry.unit}\t{entry.kind}\t{entry.relpath}"


def preview_command() -> str:
    """Return the fzf preview command, using bat when it is installed."""
    # Debian and Ubuntu install bat as batcat.
    for bat in ("bat", "batcat"):
        if shutil.which(bat):
            return f"{bat} --color=always --style=numbers {{3}}"
    return "cat {3}"


def fzf_argv(preview: str) -> list[str]:
    return [
        "fzf",
        "--multi",
        "--delimiter", "\t",
        "--tabstop", "4",
        "--preview", preview,
        "--preview-window", "right,60%",
    ]


def editor_argv(paths: list[str]) -> list[str]:
    return [*shlex.split(os.environ.get("EDITOR") or "vi"), *paths]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="krunch-fzf",
        description="Fuzzy search Ada sources by unit name and krunched file name.",
    )
    parser.add_argument("root", nargs="?", default=".", help="tree to search (default: .)")
    parser.add_argument("--rebuild", action="store_true", help="ignore the cache")
    parser.add_argument("--print", action="store_true", help="print the index, do not run fzf")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="krunch-fzf: %(message)s")

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"krunch-fzf: {args.root}: not a directory", file=sys.stderr)
        return 2
    if not args.print and not shutil.which("fzf"):
        print("krunch-fzf: fzf not found on PATH", file=sys.stderr)
        return 2

    lines = "".join(f"{format_line(e)}\n" for e in build_index(root, rebuild=args.rebuild))
    if args.print:
        sys.stdout.write(lines)
        return 0

    # fzf runs in the root so that the preview can use the relative path field.
    result = subprocess.run(
        fzf_argv(preview_command()), input=lines, stdout=subprocess.PIPE, text=True, cwd=root
    )
    selected = [line.split("\t")[2] for line in result.stdout.splitlines() if line]
    if result.returncode != 0 or not selected:
        return 0
    subprocess.run(editor_argv([str(root / rel) for rel in selected]))
    return 0
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Smoke test on a real tree**

Run:

```bash
.venv/bin/krunch-fzf --print ~/work/toolchain/gnat | head
.venv/bin/krunch-fzf --print ~/work/toolchain/gnat | grep -c '^?'
time .venv/bin/krunch-fzf --print ~/work/toolchain/gnat > /dev/null
```

Expected: lines like `Ada.Assertions	spec	libgnat/a-assert.ads`. The second run is much faster than the first. Report the count of `?` lines and the two timings to the user.

- [ ] **Step 6: Write `README.md`**

````markdown
# krunch-fzf

GNAT gives Ada source files short names, such as `a-strunb.ads`. This tool
lets you fuzzy search a tree by unit name and file name at the same time.

## Install

fzf must be on your `PATH`.

```bash
pip install .
```

## Use

```bash
krunch-fzf ~/work/toolchain/gnat
```

Type part of a unit name (`strunb` or `Strings.Unb`). The right pane shows
the file. Press Enter to open it in `$EDITOR`. Press Tab to select several
files first.

The first run on a tree parses every file with libadalang. Later runs parse
only files that changed. Use `--rebuild` to parse everything again, and
`--print` to write the list to stdout without fzf.
````

- [ ] **Step 7: Commit**

```bash
git add src/krunch_fzf/cli.py tests/test_cli.py README.md
git commit --no-verify -m "Add the krunch-fzf command"
```

---

### Task 4: GitLab project

Creating the project publishes the code. Ask the user to confirm before Step 1.

- [ ] **Step 1: Create the project and push**

Run:

```bash
glab repo create krunch-fzf --private --defaultBranch main
git remote -v
git push -u origin main
```

Expected: `git remote -v` shows `origin` pointing at the new project. If `glab repo create` did not add the remote, add it with the URL it printed: `git remote add origin <url>`.

- [ ] **Step 2: Verify**

Run: `glab repo view krunch-fzf`
Expected: the project exists and is private.
