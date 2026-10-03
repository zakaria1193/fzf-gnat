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

from krunch_fzf.index import Entry, build_index


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
        description="Fuzzy search Ada sources by unit name and krunched file name.",
    )
    parser.add_argument("root", nargs="?", default=".", help="tree to search (default: .)")
    parser.add_argument("--rebuild", action="store_true", help="ignore the cache")
    parser.add_argument("--print", action="store_true", help="print the index, do not run fzf")
    parser.add_argument("-v", "--verbose", action="store_true", help="show warnings")
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
    entries = build_index(root, rebuild=args.rebuild, progress=progress)
    lines = "".join(f"{format_line(e)}\n" for e in entries)
    if args.print:
        try:
            sys.stdout.write(lines)
            sys.stdout.flush()
        except BrokenPipeError:
            # The reader quit early, as `head` does. Point stdout at devnull
            # so that the flush at interpreter exit does not fail again.
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0

    # fzf runs in the root so that the preview can use the relative path field.
    result = subprocess.run(
        fzf_argv(preview_command()), input=lines, stdout=subprocess.PIPE, text=True, cwd=root
    )
    selected = [line.split("\t")[2] for line in result.stdout.splitlines() if line]
    if result.returncode != 0 or not selected:
        return 0
    editor = editor_argv([str(root / rel) for rel in selected])
    try:
        subprocess.run(editor)
    except FileNotFoundError:
        print(f"krunch-fzf: editor not found: {editor[0]}", file=sys.stderr)
        return 2
    return 0
