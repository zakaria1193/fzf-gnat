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
