"""The vacuity analyzer's false-positive floor.

The most important property of this detector is not what it flags but what it
*refuses* to flag: a vacuity gate that fires on a real assertion trains people
to suppress it, and a suppressed gate is a disabled gate. So the bulk of this
file is the non-flag proofs — `x == y`, `user.is_valid()`, `len(x) >= 0`,
`x is not None`, `f() == g()` — each of which has a reachable false case and
must be left alone.
"""

from __future__ import annotations

import ast

import pytest

from celebrimbor.structure.vacuity import tautologies


def _kinds(source: str) -> list[str]:
    return [v.kind for v in tautologies(ast.parse(source))]


@pytest.mark.parametrize(
    "source",
    [
        "assert True",
        "assert 1",
        "assert 'x'",
        "assert (1, 2)",
    ],
)
def test_constant_truthy_literal_is_flagged(source: str) -> None:
    assert _kinds(source) == ["constant-true"]


@pytest.mark.parametrize(
    "source",
    [
        "assert x is x",
        "assert self.a is self.a",
        "assert self.a.b is self.a.b",
    ],
)
def test_self_comparison_is_flagged(source: str) -> None:
    assert _kinds(source) == ["self-comparison"]


@pytest.mark.parametrize(
    "source",
    [
        "assert e or True",
        "assert True or e",
        "assert e or 1",
        "assert a or b or True",
    ],
)
def test_short_circuit_to_truthy_is_flagged(source: str) -> None:
    assert _kinds(source) == ["short-circuit-true"]


@pytest.mark.parametrize(
    "source",
    [
        "assert x == y",  # two different values
        "assert x == x",  # False for NaN and overloaded __eq__ — the idiomatic NaN guard
        "assert self.a == self.a",  # same: `==` self-compare is not a tautology
        "assert user.is_valid()",  # a call could return False
        "assert len(items) >= 0",  # not `==`/`is`, and could be a lie for a custom __len__
        "assert x is not None",  # `is not` — a real narrowing check
        "assert f() == g()",  # different calls
        "assert f() == f()",  # identical calls: excluded, a call may have side effects
        "assert x != x",  # always FALSE — a contradiction, not a tautology
        "assert ()",  # empty tuple is falsy — never true, so not a tautology
        "assert x and True",  # `and True` reduces to x
        "assert True and x",  # ditto
        "assert a == a == a",  # chained comparison — left alone
        "assert x <= x",  # <=/>= can be overloaded or meet NaN; not flagged
        "assert obj.method()",  # attribute call, not a bare attribute
        "assert [*a]",  # `*a` unpacking: empty (falsy) when `a` is empty
        "assert (*a,)",  # ditto for a tuple
        "assert {*a}",  # ditto for a set
        "assert {**a}",  # `**a` unpacking: empty (falsy) when `a` is empty
        "assert e or [*a]",  # short-circuit channel is not unconditionally truthy
    ],
)
def test_real_assertions_are_never_flagged(source: str) -> None:
    assert _kinds(source) == []


def test_reports_kind_message_and_line() -> None:
    """A finding carries a specific kind, a real message, and the assert's line."""
    tree = ast.parse("x = 1\ny = 2\nassert True\n")
    found = tautologies(tree)
    assert len(found) == 1
    assert found[0].kind == "constant-true"
    assert found[0].line == 3
    assert "proves nothing" in found[0].message


def test_multiple_tautologies_are_each_reported() -> None:
    source = "def f(x):\n    assert True\n    assert x is x\n    assert x == y\n"
    assert _kinds(source) == ["constant-true", "self-comparison"]
