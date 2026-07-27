"""Tests for the scenario generator and the baseline differ.

Both are utilities apps import rather than gates, so these are ordinary unit
tests — but they still carry falsifiers: the scenario generator is checked
against ``uncovered_pairs`` (its own completeness falsifier) and the differ
against ``self_proof`` (its own bite falsifier).
"""

from __future__ import annotations

import pytest

from celebrimbor.differ import DifferUpdateError, Normalizer, diff, self_proof, update
from celebrimbor.scenarios import cartesian, pairwise, uncovered_pairs

# ---------------------------------------------------------------------------
# scenario generator
# ---------------------------------------------------------------------------

_PARAMS = {
    "browser": ["chrome", "firefox", "safari"],
    "os": ["linux", "mac", "win"],
    "auth": ["oauth", "password"],
}


def test_pairwise_covers_every_value_pair() -> None:
    """The generator's own falsifier: no pair may be left uncovered."""
    scenarios = pairwise(_PARAMS)
    assert uncovered_pairs(scenarios, _PARAMS) == set()


def test_pairwise_is_smaller_than_exhaustive() -> None:
    """The whole point: far fewer cases than the full cartesian product."""
    scenarios = pairwise(_PARAMS)
    assert len(scenarios) < len(cartesian(_PARAMS))


def test_pairwise_is_deterministic() -> None:
    """Same input, same output — a randomised generator would break baselines."""
    assert pairwise(_PARAMS) == pairwise(_PARAMS)


def test_single_parameter_degenerates_to_its_values() -> None:
    assert pairwise({"x": [1, 2, 3]}) == [{"x": 1}, {"x": 2}, {"x": 3}]


def test_empty_params_yields_no_scenarios() -> None:
    assert pairwise({}) == []


# ---------------------------------------------------------------------------
# baseline differ
# ---------------------------------------------------------------------------


def test_identical_output_matches() -> None:
    assert diff("a\nb\nc", "a\nb\nc").matched


def test_changed_line_is_reported() -> None:
    result = diff("a\nb\nc", "a\nX\nc")
    assert not result.matched
    assert result.differences[0].line == 2


def test_trailing_whitespace_is_normalized_away() -> None:
    """Toolchain stability: a reformat by one trailing space is not a diff."""
    assert diff("a  \nb\t", "a\nb").matched


def test_volatile_tokens_are_masked() -> None:
    """A caller-named volatile token (a timestamp) must not cause a diff."""
    norm = Normalizer(volatile=(r"\d{4}-\d{2}-\d{2}",))
    assert diff("run at 2024-01-01", "run at 2025-12-31", norm).matched


def test_update_refuses_without_a_reason() -> None:
    with pytest.raises(DifferUpdateError, match="reason"):
        update("new output", reason=None)


def test_update_with_reason_returns_normalized_output() -> None:
    assert update("a  \n\n\n\nb  ", reason="intentional new format") == "a\n\nb"


def test_self_proof_confirms_the_differ_bites() -> None:
    """The differ's own falsifier: it must detect an in-memory mutation."""
    assert self_proof("some committed baseline\nwith two lines")


def test_self_proof_on_empty_baseline() -> None:
    assert self_proof("")
