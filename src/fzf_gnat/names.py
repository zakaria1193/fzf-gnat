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


@dataclass(frozen=True)
class Symbol:
    """One declaration found in a source file."""

    name: str
    """Name qualified by the enclosing units, such as ``Ada.Strings.Unbounded.Append``."""

    kind: str
    """``package``, ``procedure``, ``function``, ``type``, ``subtype``, ``object``,
    ``constant``, ``exception``, ``task``, ``protected`` or ``entry``."""

    line: int
    """1-based line of the name."""


_KINDS = {
    "full_type_declaration": "type",
    "private_type_declaration": "type",
    "private_extension_declaration": "type",
    "incomplete_type_declaration": "type",
    "subtype_declaration": "subtype",
    "object_declaration": "object",
    "object_renaming_declaration": "object",
    "number_declaration": "constant",
    "exception_declaration": "exception",
    "exception_renaming_declaration": "exception",
    "package_declaration": "package",
    "package_body": "package",
    "package_body_stub": "package",
    "package_renaming_declaration": "package",
    "generic_renaming_declaration": "package",
    "task_type_declaration": "task",
    "single_task_declaration": "task",
    "task_body": "task",
    "task_body_stub": "task",
    "protected_type_declaration": "protected",
    "single_protected_declaration": "protected",
    "protected_body": "protected",
    "protected_body_stub": "protected",
    "entry_declaration": "entry",
    "entry_body": "entry",
}

# Their kind comes from the procedure_specification or function_specification
# they hold.
_SUBPROGRAMS = {
    "subprogram_declaration",
    "subprogram_body",
    "subprogram_body_stub",
    "expression_function_declaration",
    "null_procedure_declaration",
    "abstract_subprogram_declaration",
    "subprogram_renaming_declaration",
    "generic_subprogram_declaration",
}

# The grammar wraps task and protected declarations in a type or object
# declaration; the inner one carries the name.
_WRAPPERS = {"full_type_declaration", "object_declaration"}
_WRAPPED = {
    "task_type_declaration",
    "protected_type_declaration",
    "single_task_declaration",
    "single_protected_declaration",
}

# Declarations below these are local, not package level.
_LOCAL_SCOPES = {
    "subprogram_body",
    "task_body",
    "entry_body",
    "expression_function_declaration",
    "handled_sequence_of_statements",
}


def _kind(node: Node) -> str | None:
    if node.type in _SUBPROGRAMS:
        for child in node.named_children:
            if child.type == "procedure_specification":
                return "procedure"
            if child.type == "function_specification":
                return "function"
        return None
    if node.type == "generic_instantiation":
        for child in node.children:
            if child.type in ("package", "procedure", "function"):
                return child.type
        return None
    if node.type == "object_declaration" and any(c.type == "constant" for c in node.children):
        return "constant"
    return _KINDS.get(node.type)


def _names(node: Node) -> list[Node]:
    named = [
        child
        for i, child in enumerate(node.named_children)
        if node.field_name_for_named_child(i) == "name"
    ]
    if named:
        return named
    found = _declared_name(node)
    if found is not None:
        return [found]
    for child in node.named_children:
        if child.type in ("identifier", "selected_component"):
            return [child]
    return []


def symbols(path: Path, local: bool) -> list[Symbol]:
    """Return the declarations of the unit in ``path`` in source order, with locals of subprograms and blocks only when ``local`` is set."""
    tree = _PARSER.parse(path.read_bytes())
    for unit in tree.root_node.named_children:
        if unit.type != "compilation_unit":
            continue
        for item in unit.named_children:
            if item.type in _CONTEXT_ITEMS:
                continue
            found = []
            scope = ""
            if item.type == "subunit":
                parent = item.child_by_field_name("parent_unit_name")
                if parent is not None:
                    scope = _text(parent)
            _collect(item, scope, False, local, found)
            return found
    return []


def _collect(node: Node, scope: str, in_local: bool, want_local: bool, out: list[Symbol]) -> None:
    kind = _kind(node)
    wrapper = node.type in _WRAPPERS and any(
        child.type in _WRAPPED for child in node.named_children
    )
    if kind is not None and not wrapper:
        names = _names(node)
        for name in names:
            if not in_local or want_local:
                full = f"{scope}.{_text(name)}" if scope else _text(name)
                out.append(Symbol(full, kind, _line(name)))
        if names:
            scope = f"{scope}.{_text(names[0])}" if scope else _text(names[0])
    if node.type in _LOCAL_SCOPES:
        in_local = True
        if not want_local:
            return
    for child in node.named_children:
        if child.type in ("identifier", "selected_component", "comment"):
            continue
        _collect(child, scope, in_local, want_local, out)
