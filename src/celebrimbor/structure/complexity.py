"""Function and file complexity, measured from the AST.

Measured here rather than delegated wholesale to ruff for one reason: these
numbers feed a ratchet, and a ratchet needs a metric whose definition is
pinned to *this* codebase rather than to whatever a tool's next release
decides McCabe means. A baseline that shifts when a dependency upgrades is a
baseline that reddens CI for reasons nobody changed.

Ruff still runs the equivalent lint rules in Tier 0 — they are faster and give
better inline messages. This module exists so the *ratchet* has a stable
denominator, and so the numbers survive a toolchain that is not installed.

Complexity here is McCabe: one, plus one per decision point. Boolean operators
count per additional operand, because ``if a and b and c`` has the same three
paths as three nested ifs and hiding them behind an operator should not buy a
lower score.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..limits import Limits


@dataclass(frozen=True, slots=True)
class CallableMetrics:
    """Measured structure of one callable."""

    qualname: str
    lineno: int
    end_lineno: int
    complexity: int
    nesting: int
    statements: int
    params: int
    """Positional (and positional-or-keyword) parameters, less self/cls."""

    keyword_params: int
    """Keyword-only parameters, counted separately: see `Limits.max_params`."""

    returns: int

    @property
    def lines(self) -> int:
        return max(1, self.end_lineno - self.lineno + 1)

    def breaches(self, limits: Limits) -> list[tuple[str, int, int]]:
        """``(metric, actual, limit)`` for each budget this callable exceeds."""
        pairs = (
            ("cyclomatic complexity", self.complexity, limits.complexity),
            ("nesting depth", self.nesting, limits.nesting),
            ("statements", self.statements, limits.max_statements),
            ("positional parameters", self.params, limits.max_params),
            ("keyword-only parameters", self.keyword_params, limits.max_keyword_params),
            ("return statements", self.returns, limits.max_returns),
            ("lines", self.lines, limits.max_function_lines),
        )
        return [(name, actual, limit) for name, actual, limit in pairs if actual > limit]


@dataclass(frozen=True, slots=True)
class ModuleMetrics:
    """Measured structure of one module."""

    dotted: str
    path: Path
    lines: int
    public_classes: tuple[str, ...] = ()
    public_callables: int = 0
    callables: tuple[CallableMetrics, ...] = field(default_factory=tuple)

    def breaches(self, limits: Limits) -> list[tuple[str, int, int]]:
        pairs = (
            ("file lines", self.lines, limits.max_file_lines),
            ("public callables", self.public_callables, limits.max_public_callables),
        )
        return [(name, actual, limit) for name, actual, limit in pairs if actual > limit]


# Nodes that introduce a decision point. `ast.Try` is counted per handler
# rather than once, since each `except` is a distinct path.
_BRANCHING = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.IfExp,
    ast.comprehension,
    ast.Assert,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)


def cyclomatic(node: ast.AST) -> int:
    """McCabe complexity of a function body."""
    score = 1
    for child in ast.walk(node):
        if isinstance(child, _BRANCHING):
            score += 1
        elif isinstance(child, ast.BoolOp):
            # `a and b and c` is two decisions, not one.
            score += len(child.values) - 1
        elif isinstance(child, ast.ExceptHandler | ast.match_case):
            score += 1
    return score


def nesting_depth(node: ast.AST) -> int:
    """Deepest block nesting inside a callable.

    Depth is what actually makes code unreadable — a flat function with twelve
    sequential ifs scores badly on complexity but reads fine, while four levels
    of nesting does not. Both are measured because they fail differently.
    """

    def walk(n: ast.AST, depth: int) -> int:
        deepest = depth
        for child in ast.iter_child_nodes(n):
            step = 1 if isinstance(child, _NESTING) else 0
            deepest = max(deepest, walk(child, depth + step))
        return deepest

    return walk(node, 0)


_NESTING = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
)


def measure_callable(
    node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str
) -> CallableMetrics:
    args = node.args
    params = len(args.posonlyargs) + len(args.args)
    if args.vararg:
        params += 1
    # `self`/`cls` is not a parameter the caller supplies.
    if params and args.args and args.args[0].arg in {"self", "cls"}:
        params -= 1
    # `**kwargs` is counted as keyword-side: it is the shape that *replaces* a
    # long positional list, so charging it to the positional budget would
    # penalise the fix.
    keyword_params = len(args.kwonlyargs) + (1 if args.kwarg else 0)

    statements = sum(1 for c in ast.walk(node) if isinstance(c, ast.stmt)) - 1
    returns = sum(1 for c in ast.walk(node) if isinstance(c, ast.Return))

    return CallableMetrics(
        qualname=qualname,
        lineno=node.lineno,
        end_lineno=node.end_lineno or node.lineno,
        complexity=cyclomatic(node),
        nesting=nesting_depth(node),
        statements=max(0, statements),
        params=params,
        keyword_params=keyword_params,
        returns=returns,
    )


def _measure_class(node: ast.ClassDef) -> tuple[list[CallableMetrics], int]:
    """Metrics for a class's methods, and how many of them are public."""
    metrics = [
        measure_callable(child, f"{node.name}.{child.name}")
        for child in node.body
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    public = sum(
        1
        for child in node.body
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
        and not child.name.startswith("_")
    )
    return metrics, public


def measure_module(tree: ast.Module, dotted: str, path: Path, source: str) -> ModuleMetrics:
    public_classes: list[str] = []
    metrics: list[CallableMetrics] = []
    public_callables = 0

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            public_classes.append(node.name)
            class_metrics, public = _measure_class(node)
            metrics.extend(class_metrics)
            public_callables += public
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            public_callables += 0 if node.name.startswith("_") else 1
            metrics.append(measure_callable(node, node.name))

    return ModuleMetrics(
        dotted=dotted,
        path=path,
        lines=source.count("\n") + 1,
        public_classes=tuple(public_classes),
        public_callables=public_callables,
        callables=tuple(metrics),
    )
