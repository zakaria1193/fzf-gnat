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

The first run on a tree parses every file with tree-sitter-ada. Later runs
parse only files that changed. Use `--rebuild` to parse everything again, and
`--print` to write the list to stdout without fzf.

A file that holds only `pragma No_Body;` has no unit, so it shows as `?`.
