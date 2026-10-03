"""Find the Ada unit that a source file holds."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_ada
from tree_sitter import Language, Node, Parser

_PARSER = Parser(Language(tree_sitter_ada.language()))

_DOTTED_NAME = re.compile(r"[A-Za-z]\w*(\.[A-Za-z]\w*)*")

# Children of a compilation_unit that come before the unit itself.
_CONTEXT_ITEMS = {"with_clause", "use_clause", "pragma_g", "comment"}


@dataclass(frozen=True)
class UnitName:
    """The unit held by one source file."""

    name: str
    """Fully qualified name as written, such as ``Ada.Strings.Unbounded``."""

    kind: str
    """``spec``, ``body`` or ``subunit``."""

    line: int = field(default=1, compare=False)
    """1-based line of the unit's own name, where a preview should centre."""


def _text(node: Node) -> str:
    # GNAT sources are Latin-1, and the grammar allows spaces around the dots.
    return re.sub(r"\s+", "", node.text.decode("latin-1"))


def _declared_name(node: Node) -> Node | None:
    for field_name in ("name", "defining_program_unit_name"):
        name = node.child_by_field_name(field_name)
        if name is not None:
            return name
    # Generics and subprograms keep the name one level down, in the wrapped
    # package_declaration or in the *_specification.
    for child in node.named_children:
        if child.type.endswith("_specification") or child.type == "package_declaration":
            return _declared_name(child)
    return None


def unit_name(path: Path) -> UnitName | None:
    """Return the first unit in ``path``, or None if the file holds no unit with a valid name."""
    tree = _PARSER.parse(path.read_bytes())
    for unit in tree.root_node.named_children:
        if unit.type != "compilation_unit":
            continue
        for item in unit.named_children:
            if item.type in _CONTEXT_ITEMS:
                continue
            found = _unit_name(item)
            if found is not None and _DOTTED_NAME.fullmatch(found.name):
                return found
            return None
    return None


def _unit_name(item: Node) -> UnitName | None:
    if item.type == "subunit":
        parent = item.child_by_field_name("parent_unit_name")
        body = next(
            (c for c in item.named_children if c != parent and c.type != "comment"), None
        )
        inner = _declared_name(body) if body is not None else None
        if parent is None or inner is None:
            return None
        return UnitName(f"{_text(parent)}.{_text(inner)}", "subunit", _line(inner))
    name = _declared_name(item)
    if name is None:
        return None
    kind = "body" if item.type.endswith("_body") else "spec"
    return UnitName(_text(name), kind, _line(name))


def _line(node: Node) -> int:
    return node.start_point[0] + 1
