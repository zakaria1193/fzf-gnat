# fzf-gnat

Ada-aware search by unit name, file name, or declaration, using fzf.

You want to read `Ada.Strings.Unbounded.Append`. Your GNAT source tree contains files like these:

```text
gnat/
└── libgnat/
    ├── a-strunb.adb
    ├── a-strunb.ads
    ├── a-textio.adb
    ├── a-textio.ads
    ├── s-stoele.adb
    └── s-stoele.ads
```

A file picker shows these shortened names, so you need to know that `a-strunb.ads` contains `Ada.Strings.Unbounded`.
Otherwise, search the source to find the package:

```bash
rg -l 'package Ada\.Strings\.Unbounded' gnat/libgnat
```

Then open the matching file and search for `Append`.

With fzf-gnat, search the Ada declaration directly:

```bash
fzf-gnat -ss -q Ada.Strings.Unbounded.Append gnat
```

The results show the qualified declaration name alongside `a-strunb.ads`.
Preview the overloads, then press Enter to open your selection in `$EDITOR` at its declaration.
Use an editor that supports line arguments, such as Vim, Emacs, or VS Code.

## Examples

Run these commands from an Ada source tree, or append the directory you want to search.

### Find a unit by its Ada name

You know the unit is `Ada.Strings.Unbounded`, but its file is named `a-strunb.ads`:

```bash
fzf-gnat -q Ada.Strings.Unbounded
```

The list shows the unit name beside the file name, so either spelling works:

```bash
fzf-gnat -q strunb
```

### Find a declaration without knowing its file

Search for `Append` in package specs:

```bash
fzf-gnat -ss -q Ada.Strings.Unbounded.Append
```

Preview each declaration, then press Enter to open it in your editor.
The editor starts at the declaration when it supports line arguments.
Use `-s` instead of `-ss` to include declarations in package bodies.

### Find local declarations

Include local variables and nested subprograms when searching for a name such as `Count`:

```bash
fzf-gnat -sa -q Count
```

### Search another source tree

Pass a directory to search without changing your working directory:

```bash
fzf-gnat -ss -q Ada.Strings.Unbounded.Append ~/work/toolchain/gnat
```

## What Ada awareness adds to fzf

fzf matches the text you give it. For example, `find . -type f | fzf` searches file paths.
Those paths do not include the Ada unit names or declarations inside each file.

fzf-gnat parses `.ads` and `.adb` files before passing their names and source locations to fzf.

| Task | File paths passed to fzf | fzf-gnat |
|---|---|---|
| Find `Ada.Strings.Unbounded` | Match text in the path, such as `a-strunb.ads` | Search the full Ada unit name or the file name |
| Find a declaration such as `Append` | Declaration names are absent from the list | Search qualified names such as `Ada.Strings.Unbounded.Append` |
| Restrict results to declarations in specs | Requires preparing a different input list | Use `-ss` |
| Open the editor at a declaration | Requires adding source locations to the input and editor command | Passes the declaration's line number to supported editors |

The parser uses the `tree-sitter` Python bindings and the `tree-sitter-ada` grammar.
pip and pipx install both dependencies automatically.
No compiler or GNAT project file is required.

## Install

Requires Python 3.10 or later and `fzf` on your `PATH`.
On Debian or Ubuntu, install fzf with:

```bash
sudo apt install fzf
```

Install with pip:

```bash
pip install fzf-gnat
```

Or use pipx:

```bash
pipx install fzf-gnat
```

For a local checkout, use `pip install .` or `pipx install .`.
Install `bat` for syntax highlighting in the preview. Without it, the preview uses `cat`.

## Search files

```bash
fzf-gnat ~/work/toolchain/gnat
```

Each row shows the file name, its kind (spec, body, or subunit), the unit name, and the path.
Search any field, for example `strunb` or `Strings.Unb`.
Press Enter to open a file in `$EDITOR`. The default editor is `vi`.
Press Tab to select several files.

The first run parses the source tree with tree-sitter-ada.
Later runs parse only files that changed.
Use `--rebuild` to parse everything again.
Use `--print` to print the index without fzf.
Use `-v` to show warnings.
A file that contains only `pragma No_Body;` has no unit and shows as `?`.

## Search declarations

```bash
fzf-gnat -s  ~/work/toolchain/gnat
fzf-gnat -ss ~/work/toolchain/gnat
fzf-gnat -sa ~/work/toolchain/gnat
```

* `-s` searches package-level declarations in specs and bodies.
* `-ss` searches package-level declarations in specs only.
* `-sa` searches every declaration, including local declarations.

Each row shows the qualified name, kind, unit, and file.
Press Enter to open the editor at the declaration when the editor supports line arguments.
Use `-q TEXT` to start fzf with an initial query.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,release]'
.venv/bin/python -m pytest
.venv/bin/python -m build
.venv/bin/python -m twine check --strict dist/*.whl dist/*.tar.gz
```

The build produces a source archive and a wheel in `dist/`.

## Publish to PyPI

The GitHub Actions workflow `.github/workflows/publish.yml` tests pushes and pull requests on Python 3.10, 3.12, and 3.14.
It builds and checks both distributions after the tests pass.
It tests the installed wheel and checks installation with pipx before publication.
A manual workflow run builds artifacts without publishing.
A published GitHub release publishes to PyPI unless GitHub marks it as a prerelease.

Before the first release:

1. Host this repository on GitHub.
2. Sign in to the PyPI account associated with `zakaria1193@gmail.com`.
3. Register a pending trusted publisher for `fzf-gnat` on PyPI.
4. Enter the GitHub owner, repository name, workflow filename `publish.yml`, and environment name `pypi`.
5. Create the `pypi` environment in the GitHub repository.

See the [PyPI trusted publisher instructions](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
This method does not require a stored PyPI API token.
The author email in the package metadata does not authenticate uploads.

For each release, update `version` in `pyproject.toml` and publish a matching GitHub release.
For version `0.1.0`, use the tag `v0.1.0`.
PyPI does not permit replacement of an existing release file.
