# krunch-fzf design

## Goal

GNAT gives Ada source files short "krunched" names, such as `a-strunb.ads`.
You cannot tell the unit from the name. `krunch-fzf` lets you fuzzy search an
Ada source tree by the unit name and the file name at the same time. It shows
a preview of the file, and Enter opens it.

## Usage

```bash
krunch-fzf                       # index the current directory
krunch-fzf ~/work/toolchain/gnat # index another tree
krunch-fzf --rebuild ROOT        # ignore the cache and parse every file
krunch-fzf --print ROOT          # write the index to stdout, no fzf
```

## Requirements

- Python 3.10 or newer.
- The `tree-sitter` and `tree-sitter-ada` wheels from PyPI, declared as
  package dependencies. libadalang has no wheel on PyPI.
- `fzf` on `PATH`. The tool exits with a clear error if it is missing.
- `bat` is optional. The preview uses it when it is on `PATH`, and `cat`
  otherwise.

## Display

The tool shows one line per file. Each line has three tab-separated fields:

```
Ada.Strings.Unbounded	spec	libgnat/a-strunb.ads
Ada.Strings.Unbounded	body	libgnat/a-strunb.adb
System.Text_IO	body	src/s-textio__pl011.adb
```

- Field 1 is the fully qualified unit name. A subunit shows as
  `Parent.Child`.
- Field 2 is `spec`, `body` or `subunit`.
- Field 3 is the path relative to the root.

fzf searches all three fields. Lines are sorted by unit name, then by path.

## Keys

- Enter opens the selected files in `$EDITOR`, or `vi` if `$EDITOR` is not
  set. `--multi` is on, so Tab selects several files.
- The preview pane shows the file under the cursor.

## Modules

The package is `krunch_fzf`, in `src/krunch_fzf/`.

- `names.py`: `unit_name(path) -> UnitName | None`. It parses one file with
  tree-sitter-ada. It reads only that file.
  It returns the name and the kind. It returns `None` if the file has no
  compilation unit, or if the parser gives no valid name.
- `index.py`: `build_index(root, rebuild=False) -> list[Entry]`. It walks the
  tree, reads and updates the cache, and calls `unit_name` only for new or
  changed files.
- `cli.py`: parses arguments, builds the fzf command and runs it. The
  `krunch-fzf` console script points here.

## Tree walk

- Include files that end in `.ads` or `.adb`.
- Skip `.git`, and skip any directory named `obj` or `lib`.
- Skip any directory whose name ends in `.dekrunched`. These are views that
  dekrunch generates, and they would list every file twice.
- Do not follow directory symlinks, so a symlink loop cannot hang the walk.

## Cache

- Location: `$XDG_CACHE_HOME/krunch-fzf/`, or `~/.cache/krunch-fzf/` if that
  variable is not set.
- One file per root: `<sha1 of the absolute root path>.tsv`.
- One row per file: `relpath`, `mtime_ns`, `size`, `unit`, `kind`.
- On each run, a file is parsed again only if it is new, or if its `mtime_ns`
  or `size` changed. Rows for deleted files are dropped.
- The cache is written to a temporary file and then renamed, so an
  interrupted run cannot leave a half-written cache.
- A cache file that cannot be read is ignored and rebuilt.
- `--rebuild` ignores the existing cache.

## Errors

- A file that the parser cannot name still gets a line, with unit `?`. The
  tool logs one warning per such file to stderr.
- A root that does not exist or is not a directory: exit with status 2 and a
  message.
- fzf not found: exit with status 2 and a message.
- The user pressing Esc in fzf: exit with status 0 and open nothing.

## Testing

pytest, with small fixture trees under `tests/fixtures/`.

- `names`: a package spec, a package body, a child package, a generic
  package, a library procedure, a subunit, a `__variant` file, and a file
  with a syntax error.
- `index`: the first run parses every file. A second run with no change
  parses none. After one file is touched, only that file is parsed again. A
  deleted file disappears from the index.
- `cli`: `--print` output matches the expected lines. The fzf argv is checked
  without running fzf.

## Repository

- A new GitLab project, `krunch-fzf`, in the user's personal namespace,
  created with `glab`. It is private.
- The local clone lives in `~/my_repos/krunch-fzf`.

## Out of scope

- Resolving or showing dependencies between units.
- Watching the tree for changes.
- Any editor integration beyond running `$EDITOR`.
