"""AST-only surface inventory. Nothing here imports application code.

This is a scar, and it is worth being explicit about why. The obvious way to
enumerate an app's public callables is ``importlib`` plus ``inspect``: it is
shorter, it gets real signature objects, and it resolves decorators properly.
It is also wrong, because a module that raises on import produces *no*
callables, and a completeness count built that way reports "everything is
accounted for" precisely when the code is at its most broken. The guarantee
would fall behind the code exactly when it matters.

So: ``ast.parse`` on bytes, never ``import``. The costs are real and accepted —
we cannot see through decorators, dynamically generated attributes, or
``__all__`` computed at runtime — and every one of those costs is a place
where this module reports *less* confidence rather than more.

A module that will not even parse is recorded with its error and kept in the
inventory. It is never dropped, because dropping it is the same failure as
importing it.
"""

from __future__ import annotations

import ast
import fnmatch
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Config

_ALWAYS_EXCLUDED = ("__pycache__/*", "*/__pycache__/*", "*.pyc")

# Call targets whose presence in a body means the callable is observably doing
# something to the world. Used only as *negative* evidence — see inference.
_EFFECT_CALLS = frozenset(
    {
        "open",
        "print",
        "write",
        "writelines",
        "remove",
        "unlink",
        "mkdir",
        "rmtree",
        "rename",
        "replace",
        "chmod",
        "system",
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
        "post",
        "put",
        "patch",
        "delete",
        "commit",
        "execute",
        "executemany",
        "send",
        "sendall",
        "connect",
        "dump",
        "dumps_to",
        "save",
        "flush",
        "close",
        "spawn",
        "fork",
    }
)


@dataclass(frozen=True, slots=True)
class CallableInfo:
    """One public callable, as seen from the syntax tree alone."""

    module: str
    qualname: str
    name: str
    path: Path
    lineno: int
    is_async: bool = False
    is_method: bool = False
    decorators: tuple[str, ...] = ()
    params: tuple[str, ...] = ()
    has_return_annotation: bool = False
    returns_value: bool = False
    effect_markers: frozenset[str] = frozenset()
    doc_summary: str | None = None

    @property
    def key(self) -> str:
        """Stable identity used as the surface-map key."""
        return f"{self.module}:{self.qualname}"

    @property
    def observably_effectful(self) -> bool:
        return bool(self.effect_markers)


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    """One source module and its public callables."""

    dotted: str
    path: Path
    callables: tuple[CallableInfo, ...] = ()
    parse_error: str | None = None
    exports_all: tuple[str, ...] | None = None
    tree: ast.Module | None = field(default=None, compare=False, repr=False)
    """The parsed tree, retained so downstream engines (complexity, the
    capability gate) do not re-parse the whole source tree. Parsing is the
    dominant cost of the fast stage, and doing it three times would spend the
    entire ~10s budget on redundant work. Excluded from equality so two
    inventories compare on their findings, not their node identities."""

    source: str = field(default="", compare=False, repr=False)

    @property
    def parsed(self) -> bool:
        return self.parse_error is None


@dataclass(frozen=True, slots=True)
class Inventory:
    """Every module under the configured source prefix."""

    root: Path
    source: str
    modules: tuple[ModuleInfo, ...] = ()
    scanned_files: int = 0

    @property
    def unparseable(self) -> tuple[ModuleInfo, ...]:
        """Modules the AST could not read. These make the audit REFUSE."""
        return tuple(m for m in self.modules if not m.parsed)

    def callables(self) -> Iterator[CallableInfo]:
        for module in self.modules:
            yield from module.callables

    def keys(self) -> set[str]:
        return {c.key for c in self.callables()}

    def module_names(self) -> set[str]:
        return {m.dotted for m in self.modules}

    def by_module(self, dotted: str) -> ModuleInfo | None:
        for m in self.modules:
            if m.dotted == dotted:
                return m
        return None

    def module_for_path(self, rel_path: Path) -> ModuleInfo | None:
        for m in self.modules:
            if m.path == rel_path:
                return m
        return None


def inventory(config: Config) -> Inventory:
    """Walk the configured source prefix and classify it, without importing it."""
    source_dir = config.source_dir
    if not source_dir.is_dir():
        return Inventory(root=config.root, source=config.source, modules=(), scanned_files=0)

    excludes = (*_ALWAYS_EXCLUDED, *config.exclude)
    modules: list[ModuleInfo] = []
    scanned = 0
    for path in sorted(source_dir.rglob("*.py")):
        rel = path.relative_to(config.root)
        if _excluded(rel, excludes):
            continue
        scanned += 1
        modules.append(_read_module(path, rel, config))
    return Inventory(
        root=config.root,
        source=config.source,
        modules=tuple(modules),
        scanned_files=scanned,
    )


def _excluded(rel: Path, patterns: tuple[str, ...]) -> bool:
    text = rel.as_posix()
    return any(fnmatch.fnmatch(text, pat) for pat in patterns)


def _read_module(path: Path, rel: Path, config: Config) -> ModuleInfo:
    dotted = dotted_name(rel, config.source)
    try:
        source = path.read_bytes()
    except OSError as exc:
        return ModuleInfo(dotted=dotted, path=rel, parse_error=f"unreadable: {exc}")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return ModuleInfo(
            dotted=dotted,
            path=rel,
            parse_error=f"syntax error at line {exc.lineno}: {exc.msg}",
        )
    except ValueError as exc:  # e.g. source containing null bytes
        return ModuleInfo(dotted=dotted, path=rel, parse_error=f"unparseable: {exc}")

    collector = _Collector(module=dotted, path=rel)
    collector.visit(tree)
    return ModuleInfo(
        dotted=dotted,
        path=rel,
        callables=tuple(collector.found),
        exports_all=collector.dunder_all,
        tree=tree,
        source=source.decode("utf-8", errors="replace"),
    )


def dotted_name(rel_path: Path, source_prefix: str) -> str:
    """Turn ``src/pkg/mod.py`` into ``pkg.mod``.

    The source prefix is stripped so the dotted name matches what the app
    itself would import, which is what an adopter writes in their ledgers.
    ``__init__.py`` collapses to its package.
    """
    parts = list(rel_path.with_suffix("").parts)
    prefix_parts = [p for p in Path(source_prefix).parts if p not in (".", "")]
    if parts[: len(prefix_parts)] == prefix_parts:
        parts = parts[len(prefix_parts) :]
    if parts and parts[-1] == "__init__":
        parts.pop()
    if not parts:
        # The root ``__init__.py`` of a package the source prefix points *at*
        # (e.g. source = "src/press", file = "src/press/__init__.py"). Stripping
        # the prefix leaves nothing, but the module is real and public — it is
        # the package itself. Name it by the package, never the empty string,
        # which would surface as a confusing `module ''` in the completeness gate.
        return prefix_parts[-1] if prefix_parts else ""
    return ".".join(parts)


class _Collector(ast.NodeVisitor):
    """Collects public callables, tracking class nesting for qualnames.

    Nested functions (closures, inner helpers) are deliberately not collected:
    they are not part of the module's surface, cannot be called by another
    module, and including them would inflate the ratification burden with rows
    no gate can key on.
    """

    def __init__(self, module: str, path: Path) -> None:
        self.module = module
        self.path = path
        self.found: list[CallableInfo] = []
        self.dunder_all: tuple[str, ...] | None = None
        self._class_stack: list[str] = []
        self._depth = 0

    # -- module level -------------------------------------------------------

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            self._maybe_read_dunder_all(stmt)
        self.generic_visit(node)

    def _maybe_read_dunder_all(self, stmt: ast.stmt) -> None:
        if not isinstance(stmt, ast.Assign):
            return
        names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
        if "__all__" not in names:
            return
        if isinstance(stmt.value, ast.List | ast.Tuple):
            self.dunder_all = tuple(
                el.value
                for el in stmt.value.elts
                if isinstance(el, ast.Constant) and isinstance(el.value, str)
            )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if _private(node.name) or self._depth > 0:
            return
        self._class_stack.append(node.name)
        for child in node.body:
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                self._record(child, is_method=True)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record(node, is_method=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record(node, is_method=False)

    # -- recording ----------------------------------------------------------

    def _record(self, node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_method: bool) -> None:
        if self._depth > 0:
            return
        # Dunders are deliberately not surface: `__init__` and friends are
        # proved through their class, not on a row of their own.
        if _private(node.name):
            return
        qualname = ".".join([*self._class_stack, node.name])
        self.found.append(
            CallableInfo(
                module=self.module,
                qualname=qualname,
                name=node.name,
                path=self.path,
                lineno=node.lineno,
                is_async=isinstance(node, ast.AsyncFunctionDef),
                is_method=is_method,
                decorators=tuple(_decorator_name(d) for d in node.decorator_list),
                params=tuple(_param_names(node)),
                has_return_annotation=node.returns is not None,
                returns_value=_returns_value(node),
                effect_markers=_effect_markers(node),
                doc_summary=_doc_summary(node),
            )
        )


def _private(name: str) -> bool:
    return name.startswith("_")


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_decorator_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return "<expr>"


def _param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    a = node.args
    names = [arg.arg for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    if a.vararg:
        names.append(f"*{a.vararg.arg}")
    if a.kwarg:
        names.append(f"**{a.kwarg.arg}")
    return names


def _returns_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            return True
        if isinstance(child, ast.Yield | ast.YieldFrom):
            return True
    return False


def _effect_marker_for(child: ast.AST) -> str | None:
    """The effect this single node evidences, if any."""
    if isinstance(child, ast.Global | ast.Nonlocal):
        return "global-rebind"
    if isinstance(child, ast.Call):
        leaf = _decorator_name(child.func).rsplit(".", 1)[-1]
        return f"call:{leaf}" if leaf in _EFFECT_CALLS else None
    if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Store):
        return "attribute-store"
    if isinstance(child, ast.Subscript) and isinstance(child.ctx, ast.Store):
        return "item-store"
    if isinstance(child, ast.With | ast.AsyncWith):
        return "context-manager"
    return None


def _effect_markers(node: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    """Syntactic evidence that the callable touches the world.

    Deliberately shallow and deliberately one-directional. A hit here is
    evidence of effects; a miss is *not* evidence of purity, because effects
    can hide behind any indirection AST cannot follow. Inference relies on that
    asymmetry: it uses hits, never misses.
    """
    found = (_effect_marker_for(child) for child in ast.walk(node))
    return frozenset(marker for marker in found if marker is not None)


def _doc_summary(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    doc = ast.get_docstring(node, clean=True)
    if not doc:
        return None
    first = doc.strip().splitlines()[0].strip()
    return first or None


def callable_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Map qualname -> def node, using the same scheme as :class:`CallableInfo`.

    Lives here rather than beside its callers because two check modules had
    grown identical private copies. Two copies of a qualname scheme is one
    scheme and one latent disagreement — the day they drift, a gate silently
    stops matching half the callables it is supposed to judge.
    """
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found[node.name] = node
        elif isinstance(node, ast.ClassDef):
            found.update(_methods_of(node))
    return found


def _methods_of(node: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        f"{node.name}.{child.name}": child
        for child in node.body
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
    }
