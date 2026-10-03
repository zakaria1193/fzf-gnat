import os

import pytest

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
