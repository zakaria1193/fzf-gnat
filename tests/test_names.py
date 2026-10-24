import pytest

from fzf_gnat.names import UnitName, unit_name

CASES = {
    "a-strunb.ads": (
        "package Ada.Strings.Unbounded is\nend Ada.Strings.Unbounded;\n",
        UnitName("Ada.Strings.Unbounded", "spec"),
    ),
    "a-strunb.adb": (
        "package body Ada.Strings.Unbounded is\nend Ada.Strings.Unbounded;\n",
        UnitName("Ada.Strings.Unbounded", "body"),
    ),
    "s-textio__pl011.adb": (
        "package body System.Text_IO is\nend System.Text_IO;\n",
        UnitName("System.Text_IO", "body"),
    ),
    "g-list.ads": (
        "generic\n   type T is private;\npackage GNAT.List is\nend GNAT.List;\n",
        UnitName("GNAT.List", "spec"),
    ),
    "p-priv.ads": (
        "private package P.Priv is\nend P.Priv;\n",
        UnitName("P.Priv", "spec"),
    ),
    "main.adb": (
        "procedure Main is\nbegin\n   null;\nend Main;\n",
        UnitName("Main", "body"),
    ),
    "hello.ads": (
        "function Hello return Integer;\n",
        UnitName("Hello", "spec"),
    ),
    "p-sub.adb": (
        "separate (P)\nprocedure Sub is\nbegin\n   null;\nend Sub;\n",
        UnitName("P.Sub", "subunit"),
    ),
    "with.ads": (
        "with Ada.Text_IO;\npragma Pure;\npackage W is\nend W;\n",
        UnitName("W", "spec"),
    ),
    "inst.ads": (
        "with G;\npackage X.Inst is new G (Integer);\n",
        UnitName("X.Inst", "spec"),
    ),
    "a-calclo.adb": (
        "with X;\nseparate (Ada.Calendar)\n--  note\nfunction Clock return Time is\nbegin\n   return 0;\nend Clock;\n",
        UnitName("Ada.Calendar.Clock", "subunit"),
    ),
    "directio.ads": (
        "with Ada.Direct_IO;\ngeneric package Direct_IO renames Ada.Direct_IO;\n",
        UnitName("Direct_IO", "spec"),
    ),
    "a-ren.ads": (
        "with Ada.Text_IO;\npackage A.Ren renames Ada.Text_IO;\n",
        UnitName("A.Ren", "spec"),
    ),
}


@pytest.mark.parametrize("rel", sorted(CASES))
def test_unit_name(make_tree, rel):
    text, expected = CASES[rel]
    root = make_tree({rel: text})
    assert unit_name(root / rel) == expected


def test_no_body_file_has_no_name(make_tree):
    root = make_tree({"x.adb": "pragma No_Body;\n"})
    assert unit_name(root / "x.adb") is None


def test_garbage_has_no_name(make_tree):
    root = make_tree({"x.ads": "@@@ this is not Ada @@@\n"})
    assert unit_name(root / "x.ads") is None


def test_line_of_the_unit_name(make_tree):
    root = make_tree({"p.adb": "with X;\n--  note\n\npackage body P is\nend P;\n"})
    assert unit_name(root / "p.adb").line == 4


def test_line_of_a_subunit(make_tree):
    root = make_tree({"p-s.adb": "separate (P)\n\nprocedure S is\nbegin\n   null;\nend S;\n"})
    assert unit_name(root / "p-s.adb").line == 3
