"""Deterministic pairwise scenario generation.

Exhaustive combinatorial testing is usually infeasible — five parameters with
four values each is 1024 cases — but most defects are triggered by the
interaction of just *two* values. Pairwise (all-pairs) generation covers every
pair of values across all parameters with a fraction of the cases, which is a
well-established sweet spot for interaction bugs.

Two properties matter here and both are deliberate:

* **Deterministic.** The same parameter dict always yields the same scenarios
  in the same order. Randomised generation would make a failing scenario
  irreproducible and a committed baseline meaningless. There is no RNG in this
  module.
* **Complete over pairs.** :func:`pairwise` guarantees every value-pair from
  every parameter-pair appears in at least one scenario; :func:`uncovered_pairs`
  exists so a caller can *prove* that rather than trust it.

This is a utility an application imports to build its own scenario suites, not
a gate. It carries no opinion about what the scenarios mean.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations, product
from typing import TypeVar

V = TypeVar("V")

Scenario = dict[str, object]


def _pairs_of(params: Mapping[str, Sequence[object]]) -> set[tuple[str, object, str, object]]:
    """Every (param_a, value_a, param_b, value_b) that must be covered."""
    required: set[tuple[str, object, str, object]] = set()
    for a, b in combinations(sorted(params), 2):
        for va, vb in product(params[a], params[b]):
            required.add((a, va, b, vb))
    return required


def _covered_by(scenario: Scenario, keys: Sequence[str]) -> set[tuple[str, object, str, object]]:
    covered: set[tuple[str, object, str, object]] = set()
    for a, b in combinations(keys, 2):
        covered.add((a, scenario[a], b, scenario[b]))
    return covered


def pairwise(params: Mapping[str, Sequence[object]]) -> list[Scenario]:
    """Generate a scenario set covering every value-pair. Deterministic.

    A greedy algorithm: repeatedly build the scenario that covers the most
    still-uncovered pairs, breaking every tie by sorted order so the result is
    reproducible. Greedy all-pairs is not provably minimal, but it is stable,
    understandable, and small — and :func:`uncovered_pairs` lets a caller
    confirm completeness rather than assume it.

    A parameter with a single value, or a single parameter, degenerates
    cleanly: the cartesian product is returned, since there are no pairs to
    reduce.
    """
    if not params:
        return []
    keys = sorted(params)
    if len(keys) == 1:
        return [{keys[0]: v} for v in params[keys[0]]]

    required = _pairs_of(params)
    scenarios: list[Scenario] = []

    # Deterministic candidate order: the full cartesian product, sorted. For
    # large spaces this is materialised lazily-ish, but pairwise is meant for
    # human-scale parameter sets, and the determinism is worth the simplicity.
    while required:
        best: Scenario | None = None
        best_gain: set[tuple[str, object, str, object]] = set()
        for combo in product(*(params[k] for k in keys)):
            scenario = dict(zip(keys, combo, strict=True))
            gain = _covered_by(scenario, keys) & required
            if len(gain) > len(best_gain):
                best, best_gain = scenario, gain
        if best is None:  # pragma: no cover - required non-empty guarantees a hit
            break
        scenarios.append(best)
        required -= best_gain

    return scenarios


def uncovered_pairs(
    scenarios: Sequence[Scenario], params: Mapping[str, Sequence[object]]
) -> set[tuple[str, object, str, object]]:
    """Value-pairs that ``scenarios`` fails to cover. Empty means complete.

    The falsifier for :func:`pairwise` — a caller (or a test) asserts this is
    empty rather than trusting the generator.
    """
    keys = sorted(params)
    covered: set[tuple[str, object, str, object]] = set()
    for scenario in scenarios:
        covered |= _covered_by(scenario, keys)
    return _pairs_of(params) - covered


def cartesian(params: Mapping[str, Sequence[object]]) -> list[Scenario]:
    """Every combination — the exhaustive set, for when a space is small enough."""
    keys = sorted(params)
    return [dict(zip(keys, combo, strict=True)) for combo in product(*(params[k] for k in keys))]
