# fzf-gnat

Search Ada source trees by unit name, file name, or declaration with fzf.
Find `Ada.Strings.Unbounded` even when GNAT names its source file `a-strunb.ads`.
Preview the source, then open your selection in `$EDITOR`.

## Install

Requires Python 3.10 or later and `fzf` on your `PATH`.
On Debian or Ubuntu, install fzf with:

```bash
sudo apt install fzf
```

After the first PyPI release, install `fzf-gnat` in a virtual environment:

```bash
python3 -m venv ~/.venvs/fzf-gnat
~/.venvs/fzf-gnat/bin/python -m pip install fzf-gnat
~/.venvs/fzf-gnat/bin/fzf-gnat --help
```

Activate that environment to use the command examples below:

```bash
source ~/.venvs/fzf-gnat/bin/activate
```

For a local checkout, replace `fzf-gnat` with `.` in the pip install command.
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

## Debian package

Build on the target Debian or Ubuntu release with Python, pip, `dpkg`, and `dpkg-deb`:

```bash
python3 packaging/build_deb.py
sudo apt install ./dist/fzf-gnat_*.deb
```

The package includes its Python dependencies in a private directory.
It depends on the build interpreter's Python minor version, `libc6`, and `fzf`.
It recommends `bat`.
Rebuild for a different architecture, Python minor version, or distribution release.

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

The GitHub Actions workflow `.github/workflows/publish.yml` builds and checks both distributions.
It tests the installed wheel before publication.
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
