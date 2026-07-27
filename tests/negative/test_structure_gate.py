"""Negative fixtures for the structure gates: complexity, cohesion, capabilities."""

from __future__ import annotations

import pytest

from celebrimbor.result import Verdict
from tests.conftest import Project, _pin_all

pytestmark = pytest.mark.negative

_COMPLEXITY = "celebrimbor.structure.complexity"
_CAPABILITIES = "celebrimbor.structure.capabilities"


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


def test_complex_function_is_red(project: Project) -> None:
    """A branch pile past the McCabe ceiling.

    Built by string concatenation rather than a dedented heredoc: the fixture
    has to be *valid Python*, and an f-string interpolated into an indented
    block silently was not — which the gate reported as an empty source tree
    rather than as a complex function. A negative fixture that fails for the
    wrong reason proves nothing.
    """
    body = "\n".join(f'    if value == {n}:\n        return "{n}"' for n in range(14))
    project.write(
        "src/app/tangle.py",
        '"""Too many paths."""\n\nfrom __future__ import annotations\n\n\n'
        "def classify(value: int) -> str:\n"
        '    """One return per input, apparently."""\n'
        f"{body}\n"
        '    return "other"\n',
    )
    result = project.run(_COMPLEXITY)
    assert result.verdict is Verdict.FAIL
    assert "structure-callable" in codes(result)
    assert any("cyclomatic complexity" in f.message for f in result.findings)


def test_deep_nesting_is_red(project: Project) -> None:
    """Depth is measured separately from complexity because it fails differently."""
    project.module(
        "app.deep",
        '''
        """Nested past the ceiling."""

        from __future__ import annotations


        def dig(rows: list[list[list[list[list[int]]]]]) -> int:
            """Five levels down."""
            total = 0
            for a in rows:
                for b in a:
                    for c in b:
                        for d in c:
                            for e in d:
                                total += e
            return total
        ''',
    )
    result = project.run(_COMPLEXITY)
    assert result.verdict is Verdict.FAIL
    assert any("nesting depth" in f.message for f in result.findings)


def test_two_unrelated_domains_in_one_module_is_red(project: Project) -> None:
    """Cohesion is measured as connected components, not as a class count."""
    project.module(
        "app.mixed",
        '''
        """Two things that have nothing to do with each other."""

        from __future__ import annotations

        import http.client
        import decimal


        class HttpPinger:
            """Talks to a server."""

            def ping(self, host: str) -> int:
                """Round-trip."""
                return len(host)


        class InvoiceTotal:
            """Adds up money."""

            def total(self, amounts: list[decimal.Decimal]) -> decimal.Decimal:
                """Sum."""
                return sum(amounts, decimal.Decimal(0))
        ''',
    )
    result = project.run(_COMPLEXITY)
    assert result.verdict is Verdict.FAIL
    assert "structure-cohesion" in codes(result)


def test_cohesive_module_with_many_classes_is_fine(project: Project) -> None:
    """The falsifier for the *old* rule, kept because it is what caught it.

    `max_classes_per_file = 1` fired on celebrimbor's own `result.py` — five
    classes, one domain. This test exists so nobody reintroduces a class count
    while believing they are measuring cohesion.
    """
    project.module(
        "app.vocabulary",
        '''
        """One value vocabulary, five classes."""

        from __future__ import annotations

        import enum
        from dataclasses import dataclass


        class Kind(enum.Enum):
            """Which sort."""

            A = "a"
            B = "b"


        @dataclass(frozen=True)
        class Leaf:
            """Smallest piece."""

            kind: Kind


        @dataclass(frozen=True)
        class Branch:
            """Holds leaves."""

            leaves: tuple[Leaf, ...]


        @dataclass(frozen=True)
        class Tree:
            """Holds branches."""

            branches: tuple[Branch, ...]


        def count_leaves(tree: Tree) -> int:
            """How many leaves in the tree."""
            return sum(len(b.leaves) for b in tree.branches)
        ''',
    )
    result = project.run(_COMPLEXITY)
    assert "structure-cohesion" not in codes(result), (
        "five mutually-referencing classes are one domain, not five"
    )


def test_ambient_clock_in_pure_is_red(project: Project) -> None:
    """An un-injected dependency is a claim the test cannot contradict."""
    project.module(
        "app.stamping",
        '''
        """Stamping."""

        from __future__ import annotations

        from datetime import datetime


        def label(prefix: str) -> str:
            """Reaches for the clock instead of being handed one."""
            return f"{prefix}-{datetime.now().year}"
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.stamping:
            role: pure
            status: ratified
        """
    )
    _pin_all(project)

    result = project.run(_CAPABILITIES)
    assert result.verdict is Verdict.FAIL
    assert "capability-ambient" in codes(result)
    assert any("clock" in f.message for f in result.findings)


def test_injected_clock_in_pure_is_fine(project: Project) -> None:
    """The seam is what makes the behaviour reachable, so injection satisfies it."""
    project.module(
        "app.stamping",
        '''
        """Stamping, with the clock handed in."""

        from __future__ import annotations

        from typing import Protocol


        class Clock(Protocol):
            """Something that knows the time."""

            def year(self) -> int: ...


        def label(prefix: str, clock: Clock) -> str:
            """A test can hand in a different clock."""
            return f"{prefix}-{clock.year()}"
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.stamping:
            role: pure
            status: ratified
        """
    )
    _pin_all(project)
    assert project.run(_CAPABILITIES).verdict is Verdict.PASS


def test_adapter_may_reach_for_anything(project: Project) -> None:
    """The budget is role-derived: the same line is fine at the boundary.

    Without this the gate would be a blanket ban, every project would disable
    it, and the distinction that makes it useful would be lost.
    """
    project.module(
        "app.gateway",
        '''
        """The designated boundary."""

        from __future__ import annotations

        from datetime import datetime


        def fetch_stamp() -> str:
            """Ambient clock, in the one role that is allowed one."""
            return str(datetime.now().year)
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.gateway:
            role: adapter
            status: ratified
        """
    )
    _pin_all(project)
    assert project.run(_CAPABILITIES).verdict is Verdict.PASS


def test_empty_source_tree_refuses_rather_than_passes(project: Project) -> None:
    """Nothing to measure is not the same as nothing wrong."""
    result = project.run(_COMPLEXITY)
    assert result.verdict is Verdict.REFUSED
    assert "proves nothing" in (result.reason or "")
