import signal
import io
import os

import pytest

from krunch_fzf import cli
from krunch_fzf.index import Entry


@pytest.fixture(autouse=True)
def cache_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))


def test_format_lines_aligns_columns(tmp_path):
    entries = [
        Entry("libgnat/a-strunb.ads", "Ada.Strings.Unbounded", "spec", 40),
        Entry("src/s-textio__pl011.adb", "System.Text_IO", "body", 7),
    ]
    root = cli.Path("/r")
    shown = f"{'/r/libgnat/a-strunb.ads':<{cli.PATH_WIDTH}}"
    shown2 = f"{'/r/src/s-textio__pl011.adb':<{cli.PATH_WIDTH}}"
    assert cli.format_lines(entries, root) == [
        f"a-strunb.ads       \tspec\tAda.Strings.Unbounded\t{shown}\t/r/libgnat/a-strunb.ads\t40",
        f"s-textio__pl011.adb\tbody\tSystem.Text_IO       \t{shown2}\t/r/src/s-textio__pl011.adb\t7",
    ]


def test_long_path_is_cut_in_the_middle():
    path = "/home/me/" + "deep/" * 30 + "a-strunb.ads"
    short = cli.shorten(path, 40)
    assert len(short) == 40
    assert short.startswith("/home/me/") and short.endswith("a-strunb.ads")
    assert "..." in short


def test_short_path_is_kept():
    assert cli.shorten("/r/a.ads", 40) == "/r/a.ads"


def test_path_column_width_is_fixed(tmp_path):
    entries = [
        Entry("a.ads", "A", "spec"),
        Entry("x/" * 60 + "b.ads", "B", "spec"),
    ]
    widths = {len(line.split("\t")[3]) for line in cli.format_lines(entries, tmp_path)}
    assert widths == {cli.PATH_WIDTH}


def test_print_writes_index(make_tree, capsys):
    root = make_tree({"src/s-textio.ads": "package System.Text_IO is\nend System.Text_IO;\n"})
    assert cli.main(["--print", str(root)]) == 0
    assert capsys.readouterr().out == (
        f"s-textio.ads\tspec\tSystem.Text_IO\t"
        f"{cli.shorten(f'{root.resolve()}/src/s-textio.ads', cli.PATH_WIDTH):<{cli.PATH_WIDTH}}\t"
        f"{root.resolve()}/src/s-textio.ads\t1\n"
    )


def test_missing_root_exits_2(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_missing_fzf_exits_2(make_tree, monkeypatch, capsys):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.main([str(root)]) == 2
    assert "fzf" in capsys.readouterr().err


def test_fzf_argv_searches_all_fields():
    argv = cli.fzf_argv("cat {5}")
    assert argv[0] == "fzf"
    assert "--multi" in argv
    assert argv[argv.index("--delimiter") + 1] == "\t"
    assert argv[argv.index("--preview") + 1] == "cat {5}"
    window = argv[argv.index("--preview-window") + 1]
    assert window.startswith("up") and "+{6}" in window
    assert argv[argv.index("--with-nth") + 1] == "1..4"


def test_preview_falls_back_to_cat(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.preview_command() == "cat {5}"


def test_editor_with_arguments(monkeypatch):
    monkeypatch.setenv("EDITOR", "code -w")
    assert cli.editor_argv([("/r/a.ads", 7)]) == ["code", "-w", "-g", "/r/a.ads:7"]


def test_editor_defaults_to_vi(monkeypatch):
    monkeypatch.delenv("EDITOR", raising=False)
    assert cli.editor_argv([("/r/a.ads", 7)]) == ["vi", "+7", "/r/a.ads"]


def test_editor_with_a_path_opens_at_line(monkeypatch):
    monkeypatch.setenv("EDITOR", "/usr/bin/nvim")
    assert cli.editor_argv([("/r/a.ads", 3), ("/r/b.ads", 9)]) == [
        "/usr/bin/nvim", "+3", "/r/a.ads", "/r/b.ads"
    ]


def test_unknown_editor_gets_only_paths(monkeypatch):
    monkeypatch.setenv("EDITOR", "ed")
    assert cli.editor_argv([("/r/a.ads", 3)]) == ["ed", "/r/a.ads"]


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
    run = FakeRun(0, f"a.ads\tspec\tA\tshort\t{root.resolve()}/a.ads\t1\n")
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main([str(root)]) == 0
    assert run.calls[-1] == ["vi", "+1", str(root.resolve() / "a.ads")]


def test_escape_opens_nothing(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = FakeRun(130, "")
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main([str(root)]) == 0
    assert len(run.calls) == 1


def test_missing_editor_exits_2(make_tree, monkeypatch, capsys):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("EDITOR", "no-such-editor")

    def run(argv, **kwargs):
        if argv[0] != "fzf":
            raise FileNotFoundError(argv[0])
        return cli.subprocess.CompletedProcess(argv, 0, stdout=f"a.ads\tspec\tA\tshort\t{root.resolve()}/a.ads\t1\n")

    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main([str(root)]) == 2
    assert "no-such-editor" in capsys.readouterr().err


def test_print_into_closed_pipe(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})

    class ClosedPipe:
        def __init__(self):
            self.fd = os.open(os.devnull, os.O_WRONLY)

        def write(self, text):
            raise BrokenPipeError

        def flush(self):
            pass

        def fileno(self):
            return self.fd

    monkeypatch.setattr(cli.sys, "stdout", ClosedPipe())
    assert cli.main(["--print", str(root)]) == 0


def test_progress_bar_draws_and_clears():
    out = io.StringIO()
    bar = cli.ProgressBar(out, width=10)
    bar(0, 4)
    bar(2, 4)
    bar(4, 4)
    text = out.getvalue()
    assert "\r[#####     ]    2/4 " in text
    assert text.endswith("\r\x1b[K")


def test_no_progress_bar_without_a_terminal(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    seen = {}

    def fake_build_index(root, rebuild=False, progress=None):
        seen["progress"] = progress
        return []

    monkeypatch.setattr(cli, "build_index", fake_build_index)
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: False)
    cli.main(["--print", str(root)])
    assert seen["progress"] is None


def test_warnings_hidden_by_default(make_tree, capsys):
    root = make_tree({"x.adb": "pragma No_Body;\n"})
    cli.main(["--print", str(root)])
    assert "no Ada unit" not in capsys.readouterr().err


def test_verbose_shows_warnings(make_tree, capsys):
    root = make_tree({"x.adb": "pragma No_Body;\n"})
    cli.main(["-v", "--print", str(root)])
    assert "x.adb: no Ada unit found" in capsys.readouterr().err


def test_ctrl_c_exits_130_quietly(make_tree, monkeypatch, capsys):
    root = make_tree({"a.ads": "package A is\nend A;\n"})

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "build_index", interrupted)
    assert cli.main(["--print", str(root)]) == 130
    assert "Traceback" not in capsys.readouterr().err


def test_ctrl_c_works_even_if_parent_ignored_it(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    old = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        cli.main(["--print", str(root)])
        assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    finally:
        signal.signal(signal.SIGINT, old)


SYMBOL_TREE = {
    "p.ads": "package P is\n   procedure Q;\nend P;\n",
    "p.adb": "package body P is\n   procedure Q is\n      L : Integer;\n   begin\n      null;\n   end Q;\nend P;\n",
}


def printed_symbols(make_tree, capsys, flag):
    root = make_tree(SYMBOL_TREE)
    assert cli.main([flag, "--print", str(root)]) == 0
    return [line.split("\t") for line in capsys.readouterr().out.splitlines()]


def test_s_lists_package_level_symbols(make_tree, capsys):
    rows = printed_symbols(make_tree, capsys, "-s")
    assert [(r[0].strip(), r[1].strip(), r[2].strip(), r[5]) for r in rows] == [
        ("P", "package", "p.adb", "1"),
        ("P", "package", "p.ads", "1"),
        ("P.Q", "procedure", "p.adb", "2"),
        ("P.Q", "procedure", "p.ads", "2"),
    ]
    assert rows[0][4].endswith("/p.adb")


def test_ss_lists_spec_symbols_only(make_tree, capsys):
    rows = printed_symbols(make_tree, capsys, "-ss")
    assert {r[2].strip() for r in rows} == {"p.ads"}


def test_sa_includes_locals(make_tree, capsys):
    rows = printed_symbols(make_tree, capsys, "-sa")
    assert "P.Q.L" in [r[0].strip() for r in rows]


def test_symbol_modes_exclude_each_other(make_tree, capsys):
    with pytest.raises(SystemExit):
        cli.main(["-s", "-sa", "--print", "."])


def test_query_prefills_fzf(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = FakeRun(130, "")
    monkeypatch.setattr(cli.subprocess, "run", run)
    cli.main(["-q", "System", str(root)])
    argv = run.calls[0]
    assert argv[argv.index("--query") + 1] == "System"


def test_fzf_output_is_ignored_when_it_fails(make_tree, monkeypatch):
    root = make_tree({"a.ads": "package A is\nend A;\n"})
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = FakeRun(130, "not a line of ours\n")
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main([str(root)]) == 0
    assert len(run.calls) == 1
