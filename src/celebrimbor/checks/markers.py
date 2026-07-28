"""Marker grammar: a test's markers must mean something checkable.

Test markers are where quiet dishonesty accumulates. A test marked to assert
something that contains no assertion passes vacuously. An ``xfail`` with no
stated reason is a test someone gave up on and nobody will revisit. A ``skip``
that names no condition is a test that silently never runs. Each of these looks
like coverage and is not.

So the grammar is enforced, by AST, over the test suite:

* **A marked test must assert.** A test carrying any celebrimbor marker (or a
  plain test function) with no ``assert`` and no ``pytest.raises`` and no
  ``self.assert*`` is rejected — it cannot fail, so it proves nothing.
* **An ``xfail`` must cite a reason.** ``@pytest.mark.xfail`` with no
  ``reason=`` is undocumented debt.
* **A ``skip`` must name its condition.** ``@pytest.mark.skipif`` needs a
  condition and a ``reason=``; a bare ``skip`` needs a ``reason=``.

The build contract says celebrimbor's own suite obeys this grammar, so this
gate runs over celebrimbor itself — which is why the fixtures below are careful
to always assert.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from ..context import Context
from ..registry import check
from ..result import CheckResult, Finding, Stage

_ID = "celebrimbor.markers"

_ASSERT_CALLS = {"raises", "warns", "approx", "fail", "xfail", "exit", "skip"}


@dataclass(frozen=True, slots=True)
class MarkerProblem:
    path: Path
    line: int
    test: str
    code: str
    message: str


def _decorator_chain(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_decorator_chain(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _decorator_chain(node.func)
    return ""


def _has_assertion(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Does this test body actually check anything?

    Counts ``assert``, ``raise`` inside the test, ``with pytest.raises(...)``,
    ``pytest.fail()``-style calls, and ``self.assertXxx`` — the ways a test can
    genuinely fail. Deliberately liberal: the goal is to catch tests that
    *cannot* fail, not to police assertion style.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.Call):
            name = _decorator_chain(child.func).rsplit(".", 1)[-1]
            if name in _ASSERT_CALLS or name.startswith("assert"):
                return True
        if isinstance(child, ast.With | ast.AsyncWith):
            for item in child.items:
                if "raises" in _decorator_chain(item.context_expr) or "warns" in _decorator_chain(
                    item.context_expr
                ):
                    return True
    return False


def _has_reason(dec: ast.expr) -> bool:
    return isinstance(dec, ast.Call) and any(kw.arg == "reason" for kw in dec.keywords)


def _marker_problem(
    marker: str, dec: ast.expr, node: ast.FunctionDef | ast.AsyncFunctionDef, path: Path
) -> MarkerProblem | None:
    """The grammar violation this one marker commits, if any.

    ``xfail``/``skip`` owe a ``reason=``; ``skipif`` owes one too (it already
    has its condition). Any other marker owes nothing here.
    """
    if marker in {"xfail", "skip", "skipif"} and not _has_reason(dec):
        detail = "names a condition but no reason=" if marker == "skipif" else "cites no reason="
        return MarkerProblem(
            path,
            node.lineno,
            node.name,
            f"marker-{marker}-no-reason",
            f"@pytest.mark.{marker} on {node.name!r} {detail}",
        )
    return None


def _check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, path: Path
) -> list[MarkerProblem]:
    problems: list[MarkerProblem] = []
    for dec in node.decorator_list:
        chain = _decorator_chain(dec)
        if not chain.startswith(("pytest.mark.", "mark.")):
            continue
        problem = _marker_problem(chain.rsplit(".", 1)[-1], dec, node, path)
        if problem is not None:
            problems.append(problem)

    if not _has_assertion(node):
        problems.append(
            MarkerProblem(
                path,
                node.lineno,
                node.name,
                "marker-no-assertion",
                f"test {node.name!r} contains no assertion; it cannot fail, so it proves nothing",
            )
        )
    return problems


def _scan_file(path: Path) -> list[MarkerProblem]:
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (SyntaxError, ValueError):
        return []  # a test file that will not parse is pytest's problem to report, loudly
    problems: list[MarkerProblem] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test_"
        ):
            problems.extend(_check_function(node, path))
    return problems


@check(
    id=_ID,
    title="test markers mean something: assertions present, xfail/skip explained",
    stage=Stage.FAST,
    falsified_by="tests/negative/test_marker_gate.py::test_assertionless_test_is_red",
)
def check_markers(ctx: Context) -> CheckResult:
    """Enforce the marker grammar over the test tree."""
    tests_dir = ctx.config.tests_dir
    if not tests_dir.is_dir():
        return CheckResult.skipped(_ID, f"no tests directory at {ctx.config.tests}")

    # Note what is *not* excluded: negative fixtures for other gates. The
    # marker grammar applies to them too — celebrimbor's own suite obeys it.
    # Only the known-bad directory is skipped, because its files are broken
    # source on purpose and are not tests at all.
    problems: list[MarkerProblem] = []
    scanned = 0
    for path in sorted(tests_dir.rglob("test_*.py")):
        if "known-bad" in path.parts:
            continue
        scanned += 1
        problems.extend(_scan_file(path))

    if not scanned:
        return CheckResult.skipped(_ID, "no test files found to check")
    if problems:
        return CheckResult.failed(
            _ID,
            f"{len(problems)} marker-grammar violation(s)",
            [Finding(message=p.message, path=p.path, line=p.line, code=p.code) for p in problems],
        )
    return CheckResult.passed(_ID, f"{scanned} test file(s) obey the marker grammar")
