import os

import pytest

from krunch_fzf import index
from krunch_fzf.index import Entry, SymbolEntry, build_index, build_symbol_index, cache_path
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


def test_symlink_loop_does_not_hang(make_tree):
    root = make_tree(TREE)
    os.symlink(root, root / "loop")
    os.symlink(root / "src", root / "src/again")
    assert len(build_index(root)) == 3


def test_symlinked_dir_is_followed(make_tree, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "o.ads").write_text("package O is\nend O;\n")
    root = make_tree(TREE)
    os.symlink(outside, root / "linked")
    assert Entry("linked/o.ads", "O", "spec") in build_index(root)


def test_cache_write_survives_another_writers_temp_file(make_tree):
    root = make_tree(TREE)
    path = cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Stands in for the temp file of a concurrent run on the same root.
    path.with_suffix(".tmp").mkdir()
    assert len(build_index(root)) == 3


@pytest.mark.parametrize("mount", [".dekrunched", "gnat.dekrunched"])
def test_dekrunched_views_are_skipped(make_tree, mount):
    root = make_tree({**TREE, f"{mount}/Ada/Strings/Unbounded.ads": TREE["libgnat/a-strunb.ads"]})
    assert len(build_index(root)) == 3


def test_progress_counts_parsed_files_only(make_tree):
    root = make_tree(TREE)
    build_index(root)
    (root / "src/s-textio.ads").write_text("package System.Text_IO_2 is\nend System.Text_IO_2;\n")
    calls = []
    build_index(root, progress=lambda done, total: calls.append((done, total)))
    assert calls == [(0, 1), (1, 1)]


def test_progress_on_rebuild_covers_every_file(make_tree):
    root = make_tree(TREE)
    calls = []
    build_index(root, rebuild=True, progress=lambda done, total: calls.append((done, total)))
    assert calls == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_interrupt_keeps_parsed_files_in_cache(make_tree):
    root = make_tree(TREE)

    def namer(path):
        if namer.calls:
            raise KeyboardInterrupt
        namer.calls += 1
        return unit_name(path)

    namer.calls = 0
    with pytest.raises(KeyboardInterrupt):
        build_index(root, namer=namer)
    counting = CountingNamer()
    build_index(root, namer=counting)
    assert len(counting.calls) == 2


def test_subdir_reuses_parent_cache(make_tree):
    root = make_tree(TREE)
    build_index(root)
    namer = CountingNamer()
    assert build_index(root / "libgnat", namer=namer) == [
        Entry("a-strunb.adb", "Ada.Strings.Unbounded", "body"),
        Entry("a-strunb.ads", "Ada.Strings.Unbounded", "spec"),
    ]
    assert namer.calls == []
    assert not cache_path(root / "libgnat").exists()


def test_grandchild_reuses_grandparent_cache(make_tree):
    root = make_tree({**TREE, "src/deep/x.ads": "package X is\nend X;\n"})
    build_index(root)
    namer = CountingNamer()
    assert build_index(root / "src/deep", namer=namer) == [Entry("x.ads", "X", "spec")]
    assert namer.calls == []


def test_subdir_changes_go_into_parent_cache(make_tree):
    root = make_tree(TREE)
    build_index(root)
    (root / "src/s-textio.ads").write_text("package System.Text_IO_2 is\nend System.Text_IO_2;\n")
    (root / "src/new.ads").write_text("package New_One is\nend New_One;\n")
    assert len(build_index(root / "src")) == 2
    namer = CountingNamer()
    entries = build_index(root, namer=namer)
    assert namer.calls == []
    assert Entry("src/s-textio.ads", "System.Text_IO_2", "spec") in entries
    assert Entry("src/new.ads", "New_One", "spec") in entries
    assert Entry("libgnat/a-strunb.ads", "Ada.Strings.Unbounded", "spec") in entries


def test_subdir_rebuild_leaves_rest_of_parent_cache(make_tree):
    root = make_tree(TREE)
    build_index(root)
    build_index(root / "src", rebuild=True)
    namer = CountingNamer()
    assert len(build_index(root, namer=namer)) == 3
    assert namer.calls == []


def test_corrupt_parent_cache_is_left_alone(make_tree):
    root = make_tree(TREE)
    parent = cache_path(root)
    parent.parent.mkdir(parents=True, exist_ok=True)
    parent.write_text("garbage line\n")
    assert len(build_index(root / "src")) == 1
    assert parent.read_text() == "garbage line\n"


def test_fifo_is_skipped(make_tree):
    root = make_tree(TREE)
    os.mkfifo(root / "src/pipe.adb")
    assert len(build_index(root)) == 3


def test_interrupt_names_the_file(make_tree, caplog):
    root = make_tree({"a.ads": "package A is\nend A;\n"})

    def namer(path):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        build_index(root, namer=namer)
    assert "interrupted while parsing a.ads" in caplog.text


def test_line_survives_the_cache(make_tree):
    root = make_tree({"p.ads": "with X;\npackage P is\nend P;\n"})
    assert build_index(root)[0].line == 2
    namer = CountingNamer()
    assert build_index(root, namer=namer)[0].line == 2
    assert namer.calls == []


SYMBOL_TREE = {
    "p.ads": "package P is\n   procedure Q;\nend P;\n",
    "p.adb": "package body P is\n   procedure Q is\n      L : Integer;\n   begin\n      null;\n   end Q;\nend P;\n",
}


def test_symbol_index_package_level(make_tree):
    root = make_tree(SYMBOL_TREE)
    assert build_symbol_index(root, local=False) == [
        SymbolEntry("p.adb", "P", "package", 1, "P"),
        SymbolEntry("p.ads", "P", "package", 1, "P"),
        SymbolEntry("p.adb", "P.Q", "procedure", 2, "P"),
        SymbolEntry("p.ads", "P.Q", "procedure", 2, "P"),
    ]


def test_symbol_index_with_locals(make_tree):
    root = make_tree(SYMBOL_TREE)
    assert SymbolEntry("p.adb", "P.Q.L", "object", 3, "P") in build_symbol_index(root, local=True)


def test_symbol_caches_are_separate_and_reused(make_tree, monkeypatch):
    root = make_tree(SYMBOL_TREE)
    build_index(root)
    build_symbol_index(root, local=False)
    build_symbol_index(root, local=True)
    assert cache_path(root).exists()
    assert cache_path(root, "symbols").exists()
    assert cache_path(root, "symbols-all").exists()
    calls = []
    monkeypatch.setattr(index, "symbols", lambda path, local: calls.append(path) or [])
    assert len(build_symbol_index(root, local=False)) == 4
    assert calls == []


def test_file_without_symbols_is_not_parsed_again(make_tree, monkeypatch):
    root = make_tree({"x.adb": "pragma No_Body;\n"})
    assert build_symbol_index(root, local=False) == []
    calls = []
    monkeypatch.setattr(index, "symbols", lambda path, local: calls.append(path) or [])
    build_symbol_index(root, local=False)
    assert calls == []


def test_symbol_unit_of_a_subunit(make_tree):
    root = make_tree({"p-q.adb": "separate (P)\nprocedure Q is\n   L : Integer;\nbegin\n   null;\nend Q;\n"})
    assert {e.unit for e in build_symbol_index(root, local=True)} == {"P.Q"}
