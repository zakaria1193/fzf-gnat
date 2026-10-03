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

Each line shows the file name, its kind (spec, body or subunit), the unit
name and the full path. Type part of any of them (`strunb` or `Strings.Unb`).
The pane above the list shows the file. Press Enter to open it in `$EDITOR`. Press Tab to select several
files first.

The first run on a tree parses every file with tree-sitter-ada. Later runs
parse only files that changed. Use `--rebuild` to parse everything again, and
`--print` to write the list to stdout without fzf. Warnings, such as files
with no unit, only show with `-v`.

A file that holds only `pragma No_Body;` has no unit, so it shows as `?`.

## Search declarations

```bash
krunch-fzf -s  ROOT   # package-level declarations, specs and bodies
krunch-fzf -ss ROOT   # package-level declarations, specs only
krunch-fzf -sa ROOT   # every declaration, locals included
```

Each line shows the qualified name, such as `Ada.Strings.Unbounded.Append`,
its kind and its file. Enter opens the editor at the declaration.

Use `-q TEXT` to start fzf with a query already typed.
