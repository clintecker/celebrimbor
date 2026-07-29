"""Vacuity: assertions that hold for every input, so they prove nothing.

An assertion is the smallest unit of a claim a test makes. ``assert
parse(bad).refused`` says something the code can contradict; ``assert True``
says nothing at all — it holds for every input, so it can never turn red, and a
test built on it passes vacuously. That is the same blindness the role-evidence
gate hunts (a verifier whose every return is truthy), one level down, in the
assertion itself.

This module is the pure-AST detector behind the vacuity gate's
``assert-tautology`` finding. Its posture is exactly the evidence gate's:
**fire only on syntactically closed tautologies, with zero false positives on
real assertions.** A noisy vacuity gate is a disabled vacuity gate, so when the
truth of an assertion depends on any value, this abstains. It flags only three
shapes, each provably true for every input:

* a constant truthy literal — ``assert True``, ``assert 1``, ``assert "x"``,
  ``assert (1, 2)`` — reusing the evidence gate's :func:`_truthy_literal` so
  the two gates never disagree about what "an unconditionally truthy literal"
  is;
* a value compared to *itself by identity* — ``assert x is x``, ``assert
  self.a is self.a`` — restricted to *pure* operands (names, attributes,
  constants), because a call could have side effects and ``f() is f()`` is not
  the same expression twice. Only ``is``: ``==`` is excluded because ``x == x``
  is False for ``NaN`` and under an overloaded ``__eq__``, so it is a real
  assertion, not a tautology;
* an ``or`` that always short-circuits to a truthy constant — ``assert e or
  True``, ``assert True or e`` — where one operand of an ``or`` is itself a
  truthy literal, so the whole disjunction is truthy regardless of the rest.

Everything else is left alone. ``assert x == y``, ``assert user.is_valid()``,
``assert len(items) >= 0``, ``assert x is not None`` all have a reachable false
case, so none is a tautology and none is flagged.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass

from .evidence import _truthy_literal


@dataclass(frozen=True, slots=True)
class Vacuity:
    """One ``assert`` whose condition is provably true for every input."""

    kind: str
    message: str
    line: int


def _pure_operand(node: ast.expr) -> bool:
    """A name/attribute/constant chain — nothing that could have a side effect.

    A call is excluded on purpose: ``f() == f()`` looks structurally identical
    but evaluates ``f`` twice, and ``f`` may not be pure, so it is not a
    tautology. Restricting self-comparison to pure operands is what keeps the
    detector sound.
    """
    if isinstance(node, ast.Name | ast.Constant):
        return True
    if isinstance(node, ast.Attribute):
        return _pure_operand(node.value)
    return False


def _same_operand(left: ast.expr, right: ast.expr) -> bool:
    """Structurally identical *pure* operands, so ``x == x`` / ``self.a is self.a``."""
    return _pure_operand(left) and _pure_operand(right) and ast.dump(left) == ast.dump(right)


def _constant_true(test: ast.expr) -> bool:
    """``assert True`` / ``assert 1`` / ``assert "x"`` / ``assert (1, 2)``."""
    return _truthy_literal(test)


def _self_comparison(test: ast.expr) -> bool:
    """``assert x is x`` over pure operands — identity only.

    Only ``is``. Identity is reflexive for *every* value, including ``NaN``, and
    ``is`` cannot be overloaded, so ``x is x`` is genuinely always true. ``==``
    is deliberately excluded: ``x == x`` is False for ``float('nan')`` (``assert
    x == x`` is in fact the idiomatic NaN guard) and can return False or non-bool
    under an overloaded ``__eq__`` (numpy/pandas), so it is a real, red-capable
    assertion, not a tautology — the same NaN/overload reasoning that excludes
    ``<=`` / ``>=``. ``!=`` and ``is not`` on identical operands are always
    *false* (a contradiction, not a tautology). Chained comparisons (``a is a is
    a``) are left alone; the single-operator case is the closed one.
    """
    return (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Is)
        and _same_operand(test.left, test.comparators[0])
    )


def _short_circuit_true(test: ast.expr) -> bool:
    """``assert e or True`` and friends: an ``or`` with a truthy-literal operand.

    Only ``or`` — ``e and True`` reduces to ``e`` and is not a tautology. An
    ``or`` whose value channel contains an unconditionally truthy literal is
    truthy no matter what the other operands evaluate to.
    """
    return (
        isinstance(test, ast.BoolOp)
        and isinstance(test.op, ast.Or)
        and any(_truthy_literal(value) for value in test.values)
    )


# The three closed shapes, as a table rather than a branch chain — the same
# shape (and the same reason) as the role-evidence conditions next door: these
# are independent, provably-always-true patterns, not a decision procedure, and
# adding one should never mean editing control flow.
_TAUTOLOGIES: tuple[tuple[str, Callable[[ast.expr], bool], str], ...] = (
    (
        "constant-true",
        _constant_true,
        "an unconditionally truthy literal",
    ),
    (
        "self-comparison",
        _self_comparison,
        "a value compared only to itself",
    ),
    (
        "short-circuit-true",
        _short_circuit_true,
        "an `or` that always short-circuits to a truthy constant",
    ),
)


def _tautology(test: ast.expr) -> tuple[str, str] | None:
    """The closed shape this assertion condition matches, if any."""
    for kind, matches, because in _TAUTOLOGIES:
        if matches(test):
            return kind, because
    return None


def tautologies(tree: ast.AST) -> list[Vacuity]:
    """Every ``assert`` in ``tree`` whose condition is true for every input.

    Conservative by construction: an assertion whose truth depends on a value
    is never returned. One entry per provably-always-true ``assert`` condition,
    in source order.
    """
    found: list[Vacuity] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        matched = _tautology(node.test)
        if matched is not None:
            kind, because = matched
            found.append(
                Vacuity(
                    kind=kind,
                    message=(
                        f"this assertion is {because}, so it holds for every input "
                        "and proves nothing"
                    ),
                    line=node.lineno,
                )
            )
    return found
