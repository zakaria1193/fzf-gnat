import pytest

from krunch_fzf import cli
from krunch_fzf.index import Entry


@pytest.fixture(autouse=True)
def cache_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))


def test_format_line():
    entry = Entry("libgnat/a-strunb.ads", "Ada.Strings.Unbounded", "spec")
    assert cli.format_line(entry) == "Ada.Strings.Unbounded\tspec\tlibgnat/a-strunb.ads"


def test_print_writes_index(make_tree, capsys):
    root = make_tree({"src/s-textio.ads": "package System.Text_IO is\nend System.Text_IO;\n"})
    assert cli.main(["--print", str(root)]) == 0
    assert capsys.readouterr().out == "System.Text_IO\tspec\tsrc/s-textio.ads\n"


def test_missing_root_exits_2(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_missing_fzf_exits_2(make_tree, monkeypatch, capsys):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.main([str(root)]) == 2
    assert "fzf" in capsys.readouterr().err


def test_fzf_argv_searches_all_fields():
    argv = cli.fzf_argv("cat {3}")
    assert argv[0] == "fzf"
    assert "--multi" in argv
    assert argv[argv.index("--delimiter") + 1] == "\t"
    assert argv[argv.index("--preview") + 1] == "cat {3}"


def test_preview_falls_back_to_cat(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.preview_command() == "cat {3}"


def test_editor_with_arguments(monkeypatch):
    monkeypatch.setenv("EDITOR", "code -w")
    assert cli.editor_argv(["/r/a.ads"]) == ["code", "-w", "/r/a.ads"]


def test_editor_defaults_to_vi(monkeypatch):
    monkeypatch.delenv("EDITOR", raising=False)
    assert cli.editor_argv(["/r/a.ads"]) == ["vi", "/r/a.ads"]


class FakeRun:
    def __init__(self, fzf_status, fzf_out):
        self.calls = []
        self.fzf_status = fzf_status
        self.fzf_out = fzf_out

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        out = self.fzf_out if argv[0] == "fzf" else ""
        status = self.fzf_status if argv[0] == "fzf" else 0
        return cli.subprocess.CompletedProcess(argv, status, stdout=out)


def test_enter_opens_selection(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("EDITOR", "vi")
    run = FakeRun(0, "A\tspec\ta.ads\n")
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main([str(root)]) == 0
    assert run.calls[-1] == ["vi", str(root.resolve() / "a.ads")]


def test_escape_opens_nothing(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = FakeRun(130, "")
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main([str(root)]) == 0
    assert len(run.calls) == 1
