import pytest

from krunch_fzf.names import Symbol, symbols

SPEC = """with X;
package P is
   type T is range 1 .. 10;
   subtype S is T;
   A, B : Integer := 0;
   C : constant := 3;
   E : exception;
   function F (X : T) return T;
   procedure Q;
   package Inner is
      I : Integer;
   end Inner;
   task type TT is
      entry Go;
   end TT;
   protected PO is
      procedure Set;
   end PO;
   generic
      type G is private;
   procedure GP;
   package IP is new Gen (T);
   procedure Ren renames Q;
private
   type Hidden is null record;
end P;
"""

BODY = """package body P is
   Count : Integer := 0;
   procedure Q is
      L : Integer;
   begin
      declare
         D : Integer;
      begin
         null;
      end;
   end Q;
   function F (X : T) return T is (X);
end P;
"""


def names(found):
    return [(s.name, s.kind) for s in found]


@pytest.fixture
def spec(make_tree):
    return make_tree({"p.ads": SPEC}) / "p.ads"


@pytest.fixture
def body(make_tree):
    return make_tree({"p.adb": BODY}) / "p.adb"


def test_package_level_spec_symbols(spec):
    assert names(symbols(spec, local=False)) == [
        ("P", "package"),
        ("P.T", "type"),
        ("P.S", "subtype"),
        ("P.A", "object"),
        ("P.B", "object"),
        ("P.C", "constant"),
        ("P.E", "exception"),
        ("P.F", "function"),
        ("P.Q", "procedure"),
        ("P.Inner", "package"),
        ("P.Inner.I", "object"),
        ("P.TT", "task"),
        ("P.TT.Go", "entry"),
        ("P.PO", "protected"),
        ("P.PO.Set", "procedure"),
        ("P.GP", "procedure"),
        ("P.IP", "package"),
        ("P.Ren", "procedure"),
        ("P.Hidden", "type"),
    ]


def test_lines_point_at_the_name(spec):
    by_name = {s.name: s for s in symbols(spec, local=False)}
    assert by_name["P"].line == 2
    assert by_name["P.T"].line == 3
    assert by_name["P.Inner.I"].line == 11


def test_package_level_skips_locals(body):
    assert names(symbols(body, local=False)) == [
        ("P", "package"),
        ("P.Count", "object"),
        ("P.Q", "procedure"),
        ("P.F", "function"),
    ]


def test_all_includes_locals(body):
    assert names(symbols(body, local=True)) == [
        ("P", "package"),
        ("P.Count", "object"),
        ("P.Q", "procedure"),
        ("P.Q.L", "object"),
        ("P.Q.D", "object"),
        ("P.F", "function"),
    ]


def test_subunit_symbols_are_qualified_by_parent(make_tree):
    root = make_tree({"p-q.adb": "separate (P)\nprocedure Q is\n   L : Integer;\nbegin\n   null;\nend Q;\n"})
    assert names(symbols(root / "p-q.adb", local=True)) == [
        ("P.Q", "procedure"),
        ("P.Q.L", "object"),
    ]


def test_no_unit_no_symbols(make_tree):
    root = make_tree({"x.adb": "pragma No_Body;\n"})
    assert symbols(root / "x.adb", local=True) == []


def test_generic_package_with_nested_package(make_tree):
    root = make_tree({"g.ads": "generic\n   type T is private;\npackage G is\n   package N is\n   end N;\nend G;\n"})
    assert names(symbols(root / "g.ads", local=False)) == [("G", "package"), ("G.N", "package")]
