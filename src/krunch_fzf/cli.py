"""The ``krunch-fzf`` command."""

import argparse
import logging
import os
import shlex
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from krunch_fzf.index import Entry, SymbolEntry, build_index, build_symbol_index


class ProgressBar:
    """Draw a one-line progress bar on a terminal, and erase it when done."""

    def __init__(self, out, width: int = 40):
        self.out = out
        self.width = width

    def __call__(self, done: int, total: int) -> None:
        filled = self.width * done // total
        bar = "#" * filled + " " * (self.width - filled)
        self.out.write(f"\r[{bar}] {done:4}/{total} ")
        if done == total:
            self.out.write("\r\x1b[K")
        self.out.flush()


PATH_WIDTH = 50


def shorten(path: str, width: int) -> str:
    """Return ``path``, cut in the middle with ``...`` if it is longer than ``width``."""
    if len(path) <= width:
        return path
    # Keep more of the end, which holds the directory and file names.
    keep = width - 3
    head = keep // 3
    return f"{path[:head]}...{path[len(path) - (keep - head):]}"


def _columns(rows: list[tuple[str, str, str, Path, int]]) -> list[str]:
    # The shown path has a fixed width so that a deep tree cannot push the
    # columns around. The full path and the line follow, hidden, for the
    # preview and the editor.
    widths = [max((len(row[i]) for row in rows), default=0) for i in range(3)]
    return [
        f"{a:<{widths[0]}}\t{b:<{widths[1]}}\t{c:<{widths[2]}}\t"
        f"{shorten(str(path), PATH_WIDTH):<{PATH_WIDTH}}\t{path}\t{line}"
        for a, b, c, path, line in rows
    ]


def format_lines(entries: list[Entry], root: Path) -> list[str]:
    """Return one fzf line per entry: file name, kind, unit and shortened path, then the hidden full path and unit line."""
    return _columns(
        [(Path(e.relpath).name, e.kind, e.unit, root / e.relpath, e.line) for e in entries]
    )


def format_symbol_lines(entries: list[SymbolEntry], root: Path) -> list[str]:
    """Return one fzf line per symbol: name, kind, file name and shortened path, then the hidden full path and line."""
    return _columns(
        [(e.name, e.kind, Path(e.relpath).name, root / e.relpath, e.line) for e in entries]
    )


def preview_command() -> str:
    """Return the fzf preview command, using bat when it is installed."""
    # Debian and Ubuntu install bat as batcat.
    for bat in ("bat", "batcat"):
        if shutil.which(bat):
            return f"{bat} --color=always --style=numbers {{5}} --highlight-line {{6}}"
    return "cat {5}"


def fzf_argv(preview: str, query: str = "") -> list[str]:
    return [
        "fzf",
        "--multi",
        "--delimiter", "\t",
        "--tabstop", "4",
        "--preview", preview,
        # Fields 5 and 6, the full path and the line, stay hidden; the line
        # centres the preview.
        "--with-nth", "1..4",
        "--preview-window", "up,60%,+{6}/2",
        "--query", query,
    ]


# Editors that take +LINE before a file. With several files, it applies to
# the first one only.
_PLUS_LINE_EDITORS = {"vi", "vim", "nvim", "gvim", "view", "nano", "emacs", "emacsclient", "micro"}
_GOTO_EDITORS = {"code", "codium"}


def editor_argv(files: list[tuple[str, int]]) -> list[str]:
    """Return the $EDITOR command that opens ``files``, at the given line of the first one when the editor supports it."""
    editor = shlex.split(os.environ.get("EDITOR") or "vi")
    name = os.path.basename(editor[0])
    (first, line), rest = files[0], [path for path, _ in files[1:]]
    if name in _PLUS_LINE_EDITORS:
        return [*editor, f"+{line}", first, *rest]
    if name in _GOTO_EDITORS:
        return [*editor, "-g", f"{first}:{line}", *rest]
    return [*editor, first, *rest]


def main(argv: list[str] | None = None) -> int:
    # Python keeps SIGINT ignored when the parent ignored it, which leaves
    # Ctrl-C dead during a long parse.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        return _main(argv)
    except KeyboardInterrupt:
        if sys.stderr.isatty():
            sys.stderr.write("\r\x1b[K")
        return 130


def _main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(
        prog="krunch-fzf",
        description="Fuzzy search Ada sources by unit name and krunched file name, or by declaration.",
    )
    parser.add_argument("root", nargs="?", default=".", help="tree to search (default: .)")
    parser.add_argument("--rebuild", action="store_true", help="ignore the cache")
    parser.add_argument("--print", action="store_true", help="print the index, do not run fzf")
    parser.add_argument("-v", "--verbose", action="store_true", help="show warnings")
    parser.add_argument("-q", "--query", default="", help="start fzf with this query")
    symbols = parser.add_mutually_exclusive_group()
    symbols.add_argument(
        "-s", dest="symbols", action="store_const", const="package",
        help="search declarations at package level instead of files",
    )
    symbols.add_argument(
        "-ss", dest="symbols", action="store_const", const="spec",
        help="search declarations at package level in specs only",
    )
    symbols.add_argument(
        "-sa", dest="symbols", action="store_const", const="all",
        help="search all declarations, including locals",
    )
    args = parser.parse_args(argv)
    tty = sys.stderr.isatty()
    # On a terminal, a warning first erases the progress bar it would
    # otherwise be printed over.
    erase = "\r\x1b[K" if tty else ""
    logging.basicConfig(
        level=logging.WARNING if args.verbose else logging.ERROR,
        format=f"{erase}krunch-fzf: %(message)s",
        force=True,
    )

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"krunch-fzf: {args.root}: not a directory", file=sys.stderr)
        return 2
    if not args.print and not shutil.which("fzf"):
        print("krunch-fzf: fzf not found on PATH", file=sys.stderr)
        return 2

    progress = ProgressBar(sys.stderr) if tty else None
    if args.symbols:
        found = build_symbol_index(
            root, local=args.symbols == "all", rebuild=args.rebuild, progress=progress
        )
        if args.symbols == "spec":
            found = [e for e in found if e.relpath.endswith(".ads")]
        formatted = format_symbol_lines(found, root)
    else:
        formatted = format_lines(build_index(root, rebuild=args.rebuild, progress=progress), root)
    lines = "".join(f"{line}\n" for line in formatted)
    if args.print:
        try:
            sys.stdout.write(lines)
            sys.stdout.flush()
        except BrokenPipeError:
            # The reader quit early, as `head` does. Point stdout at devnull
            # so that the flush at interpreter exit does not fail again.
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0

    result = subprocess.run(
        fzf_argv(preview_command(), args.query), input=lines, stdout=subprocess.PIPE, text=True, cwd=root
    )
    selected = [
        (fields[4], int(fields[5]))
        for fields in (line.split("\t") for line in result.stdout.splitlines() if line)
    ]
    if result.returncode != 0 or not selected:
        return 0
    editor = editor_argv(selected)
    try:
        subprocess.run(editor)
    except FileNotFoundError:
        print(f"krunch-fzf: editor not found: {editor[0]}", file=sys.stderr)
        return 2
    return 0
