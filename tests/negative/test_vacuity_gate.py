"""Negative fixtures for the vacuity gate.

Each fixture proves the gate turns red in the exact situation it claims to
catch — a tautological assertion — and that it stays green on real assertions,
refuses on unparseable source, and does not let a known-bad fixture's syntax
error take the run down.

Every test here asserts something real, so this file is also a small proof that
celebrimbor's own suite obeys the very grammar this gate enforces.
"""

from __future__ import annotations

import pytest

from celebrimbor.result import Verdict
from tests.conftest import Project

pytestmark = pytest.mark.negative

_ID = "celebrimbor.vacuity"


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


def test_tautological_assert_is_red(project: Project) -> None:
    """`assert True` holds for every input, so it can never turn red — vacuous."""
    project.module(
        "app.demo",
        '''
        """Demo."""

        from __future__ import annotations


        def prove() -> None:
            assert True
        ''',
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "assert-tautology" in codes(result)


def test_self_comparison_is_red(project: Project) -> None:
    """`x is x` is true regardless of the value, so it asserts nothing."""
    project.module(
        "app.demo",
        '''
        """Demo."""

        from __future__ import annotations


        def prove(x: int) -> None:
            assert x is x
        ''',
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "assert-tautology" in codes(result)


def test_or_true_is_red(project: Project) -> None:
    """`e or True` always short-circuits to a truthy constant."""
    project.write(
        "tests/test_short_circuit.py",
        """
        def test_thing() -> None:
            e = compute()
            assert e or True
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "assert-tautology" in codes(result)


def test_real_assertions_pass(project: Project) -> None:
    """The proving path: assertions whose truth depends on a value are fine."""
    project.module(
        "app.demo",
        '''
        """Demo."""

        from __future__ import annotations


        def prove(x: int, y: int, items: list[int]) -> None:
            assert x == y
            assert x is not None
            assert len(items) >= 0
        ''',
    )
    assert project.run(_ID).verdict is Verdict.PASS


def test_unparseable_source_refuses(project: Project) -> None:
    """AST-only: a file that will not parse is refused, never silently passed."""
    project.write("src/app/broken.py", "def oops(:\n    pass\n")
    result = project.run(_ID)
    assert result.verdict is Verdict.REFUSED


def test_unparseable_test_file_refuses(project: Project) -> None:
    """The test-tree parse branch fails closed too: a broken, non-known-bad test
    file is refused, never silently passed. Locks the inline ``ast.parse`` branch
    the source-tree fixture does not reach."""
    project.write("tests/test_broken.py", "def oops(:\n    pass\n")
    result = project.run(_ID)
    assert result.verdict is Verdict.REFUSED


def test_known_bad_syntax_error_does_not_break_the_run(project: Project) -> None:
    """A deliberately-broken known-bad fixture is excluded, so the run survives it."""
    project.write("tests/known-bad/broken.py", "def oops(:\n    pass\n")
    project.module(
        "app.demo",
        '''
        """Demo."""

        from __future__ import annotations


        def prove(x: int, y: int) -> None:
            assert x == y
        ''',
    )
    assert project.run(_ID).verdict is Verdict.PASS
