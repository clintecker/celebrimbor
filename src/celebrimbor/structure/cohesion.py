"""Cohesion: how many separate domains live in one module?

The naive rule is "one public class per file." It is wrong, and celebrimbor's
own source falsified it within a minute of the gate first running:
``result.py`` defines ``Tier``, ``Verdict``, ``Finding``, ``CheckResult`` and
``GateReport``. Five classes, *one* domain — a value vocabulary whose members
are meaningless apart from each other. Splitting them into five files would
make the code worse, and the rule would have demanded it.

What matters is whether the things in a module are *about each other*. Two
definitions are judged related when either holds:

**Reference.** One mentions the other, anywhere in its body, bases, decorators
or annotations. Module-level assignments count as connectors too — a table
like ``OBLIGATIONS = {Role.X: Obligation(...)}`` ties two classes together as
firmly as a method call would.

**Shared vocabulary.** Both mention the same imported name. This is the edge
that took a second pass to find: ``check_falsifiers`` and
``check_registry_shape`` never call each other, but both take a ``Context``,
return a ``CheckResult`` and build ``Finding``s. Two functions speaking the
same type language are about the same thing whether or not either calls the
other, and without this edge every module of sibling functions reads as a pile
of unrelated domains.

Vocabulary edges exclude :data:`_NEUTRAL` — ``Path``, ``dataclass``, ``Any``
and friends. Those appear everywhere and carry no domain signal, so linking on
them would make every module trivially cohesive and the gate useless.

What survives is the count of domains. One is the target. The metric is
deliberately blind to *what* the domains are: two clusters that never mention
each other and share no vocabulary are two reasons for the file to change,
whether they are two classes, two families of functions, or one of each —
which is exactly the "domains of functions" case a class count cannot see.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_EXCEPTION_SUFFIXES = ("Error", "Exception", "Warning")

# Names that appear in every module and therefore imply nothing about domain.
# Linking on these would collapse every file to one domain and the gate would
# never fire.
_NEUTRAL = frozenset(
    {
        "annotations",
        "dataclass",
        "dataclasses",
        "field",
        "fields",
        "replace",
        "Path",
        "PurePath",
        "Any",
        "TYPE_CHECKING",
        "Optional",
        "Union",
        "Literal",
        "Iterable",
        "Iterator",
        "Sequence",
        "Mapping",
        "Callable",
        "Collection",
        "TypeVar",
        "Generic",
        "Protocol",
        "Final",
        "ClassVar",
        "overload",
        "abstractmethod",
        "ABC",
        "Enum",
        "IntEnum",
        "StrEnum",
        "auto",
        "enum",
        "cached_property",
        "wraps",
        "partial",
        "dedent",
        "os",
        "sys",
        "logging",
        "warnings",
        "typing",
        "collections",
        "itertools",
        "functools",
        "copy",
        "textwrap",
        "traceback",
        "contextlib",
        "Self",
        "NamedTuple",
        "TypedDict",
    }
)


@dataclass(frozen=True, slots=True)
class Domain:
    """One connected cluster of definitions within a module."""

    members: tuple[str, ...]

    @property
    def public(self) -> tuple[str, ...]:
        return tuple(m for m in self.members if not m.startswith("_"))

    @property
    def label(self) -> str:
        names = self.public or self.members
        head = ", ".join(names[:3])
        return head + (f", … (+{len(names) - 3})" if len(names) > 3 else "")


@dataclass(frozen=True, slots=True)
class Cohesion:
    """The domain decomposition of one module."""

    dotted: str
    path: Path
    domains: tuple[Domain, ...]

    @property
    def count(self) -> int:
        return len(self.domains)

    def describe(self) -> str:
        return " | ".join(f"{{{d.label}}}" for d in self.domains)


class _Union:
    """Minimal union-find. Enough for a few dozen nodes per module."""

    def __init__(self, items: list[str]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def union_all(self, items: list[str]) -> None:
        for other in items[1:]:
            self.union(items[0], other)

    def components(self) -> list[list[str]]:
        groups: dict[str, list[str]] = {}
        for item in self.parent:
            groups.setdefault(self.find(item), []).append(item)
        return [sorted(g) for g in groups.values()]


def _is_exception(node: ast.ClassDef) -> bool:
    if node.name.endswith(_EXCEPTION_SUFFIXES):
        return True
    return any(
        str(base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")).endswith(
            _EXCEPTION_SUFFIXES
        )
        for base in node.bases
    )


def _referenced_names(node: ast.AST) -> set[str]:
    """Every bare name referenced under ``node``; attribute chains give their root."""
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Attribute):
            base: ast.expr = child
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                found.add(base.id)
    return found


def _imported_names(tree: ast.Module) -> set[str]:
    """Names this module pulls in — its vocabulary of external concepts."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
    return names - _NEUTRAL


def _collect_definitions(tree: ast.Module) -> tuple[dict[str, ast.stmt], set[str]]:
    definitions: dict[str, ast.stmt] = {}
    exceptions: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            definitions[node.name] = node
            if _is_exception(node):
                exceptions.add(node.name)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            definitions[node.name] = node
    return definitions, exceptions


def _link_by_reference(union: _Union, definitions: dict[str, ast.stmt], tree: ast.Module) -> None:
    local = set(definitions)
    for name, node in definitions.items():
        for referenced in _referenced_names(node) & local:
            if referenced != name:
                union.union(name, referenced)
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AnnAssign):
            union.union_all(sorted(_referenced_names(node) & local))


def _link_by_vocabulary(
    union: _Union, definitions: dict[str, ast.stmt], vocabulary: set[str]
) -> None:
    users: dict[str, list[str]] = {}
    for name, node in definitions.items():
        for term in _referenced_names(node) & vocabulary:
            users.setdefault(term, []).append(name)
    for sharers in users.values():
        union.union_all(sorted(sharers))


def _keep(members: tuple[str, ...], exceptions: set[str]) -> bool:
    """Is this component a real domain?

    Dropped: clusters with no public member (private helpers serving only each
    other are implementation detail), and exception-only clusters (an exception
    type belongs to whatever raises it, and frequently references nothing at
    all, so counting it separately punishes a normal pattern).
    """
    if not any(not m.startswith("_") for m in members):
        return False
    return not all(m in exceptions for m in members)


def analyze(tree: ast.Module, dotted: str, path: Path) -> Cohesion:
    """Decompose a module into its independent domains."""
    definitions, exceptions = _collect_definitions(tree)
    if not definitions:
        return Cohesion(dotted=dotted, path=path, domains=())

    union = _Union(list(definitions))
    _link_by_reference(union, definitions, tree)
    _link_by_vocabulary(union, definitions, _imported_names(tree))

    domains = [
        Domain(members=tuple(component))
        for component in union.components()
        if _keep(tuple(component), exceptions)
    ]
    return Cohesion(
        dotted=dotted, path=path, domains=tuple(sorted(domains, key=lambda d: d.members))
    )
