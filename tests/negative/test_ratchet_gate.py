"""Negative fixtures for the coverage and mutation ratchets.

The comparators are pure, so most of these are tested at that level — the point
of a ratchet is the comparison, and a comparison is exactly what unit-tests
without machinery. The gate-level fixtures inject the current measurement
through the same memo the acquisition reads, so a coverage run or a mutation
run is never actually needed to prove the ratchet bites.
"""

from __future__ import annotations

import pytest

from celebrimbor.ratchets.baseline import BaselineEnvironmentError
from celebrimbor.ratchets.coverage import (
    CoverageBaseline,
    coverage_regressions,
    rebaseline as cov_rebaseline,
)
from celebrimbor.ratchets.mutation import (
    MutationBaseline,
    Survivor,
    new_survivors,
    rebaseline as mut_rebaseline,
    resolved_survivors,
)
from celebrimbor.result import Tier, Verdict
from celebrimbor.runner import run_spec
from tests.conftest import Project

pytestmark = pytest.mark.negative


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# coverage comparator (pure)
# ---------------------------------------------------------------------------


def test_coverage_drop_below_floor_is_a_regression() -> None:
    baseline = CoverageBaseline(floors={"app.core": 90.0})
    regressions = coverage_regressions({"app.core": 82.0}, baseline, minimum=60.0)
    assert [r.kind for r in regressions] == ["drop"]


def test_coverage_rise_is_not_a_regression() -> None:
    baseline = CoverageBaseline(floors={"app.core": 90.0})
    assert coverage_regressions({"app.core": 97.0}, baseline, minimum=60.0) == []


def test_low_floor_without_reason_is_red() -> None:
    """The meta-ratchet: auto-baselining a weak floor is not green."""
    baseline = CoverageBaseline(floors={"app.legacy": 12.0})
    regressions = coverage_regressions({"app.legacy": 12.0}, baseline, minimum=60.0)
    assert [r.kind for r in regressions] == ["low-floor"]


def test_low_floor_with_reason_is_allowed() -> None:
    baseline = CoverageBaseline(
        floors={"app.legacy": 12.0}, reasons={"app.legacy": "vendored, ratcheting up"}
    )
    assert coverage_regressions({"app.legacy": 12.0}, baseline, minimum=60.0) == []


def test_new_module_below_policy_is_red() -> None:
    """New code must clear the global minimum or carry a recorded reason."""
    baseline = CoverageBaseline(floors={"app.core": 90.0})
    regressions = coverage_regressions({"app.core": 91.0, "app.new": 40.0}, baseline, minimum=60.0)
    assert [r.kind for r in regressions] == ["new-below-policy"]
    assert regressions[0].module == "app.new"


def test_rebaseline_refuses_on_dev_box() -> None:
    """The scar: never take a baseline outside the pinned environment."""
    with pytest.raises(BaselineEnvironmentError, match="dev box|pinned"):
        cov_rebaseline(
            {"app.core": 90.0},
            CoverageBaseline(),
            minimum=60.0,
            reason="anything",
            environment="dev",
            tool="coverage",
            pinned=False,
        )


def test_rebaseline_will_not_lower_a_floor_without_a_reason() -> None:
    """No silent lowering: dropping a floor demands a written reason."""
    previous = CoverageBaseline(floors={"app.core": 90.0})
    with pytest.raises(BaselineEnvironmentError, match="reason"):
        cov_rebaseline(
            {"app.core": 70.0},
            previous,
            minimum=60.0,
            reason=None,
            environment="ci",
            tool="coverage",
            pinned=True,
        )


def test_rebaseline_raises_floors_freely() -> None:
    previous = CoverageBaseline(floors={"app.core": 90.0})
    updated = cov_rebaseline(
        {"app.core": 96.0},
        previous,
        minimum=60.0,
        reason=None,
        environment="ci",
        tool="coverage",
        pinned=True,
    )
    assert updated.floors["app.core"] == 96.0


# ---------------------------------------------------------------------------
# mutation comparator (pure) — survivor IDENTITY, not count
# ---------------------------------------------------------------------------


def _s(file: str, line: int, op: str) -> Survivor:
    return Survivor(file=file, line=line, operator=op)


def test_new_survivor_with_same_count_is_a_regression() -> None:
    """The whole point: a changed set with an identical count is still a hole.

    Baseline has two survivors; the current run has two survivors; the counts
    match exactly — and yet one member is new. A count comparison passes this;
    identity comparison catches it.
    """
    baseline = MutationBaseline(
        survivors=frozenset({_s("a.py", 10, "and->or"), _s("a.py", 20, "+->-")})
    )
    current = frozenset({_s("a.py", 10, "and->or"), _s("b.py", 5, "True->False")})
    assert len(current) == len(baseline.survivors)  # same count
    appeared = new_survivors(current, baseline)
    assert [s.identity for s in appeared] == ["b.py:5:True->False"]


def test_killing_a_survivor_is_progress_not_a_regression() -> None:
    baseline = MutationBaseline(
        survivors=frozenset({_s("a.py", 10, "and->or"), _s("a.py", 20, "+->-")})
    )
    current = frozenset({_s("a.py", 10, "and->or")})
    assert new_survivors(current, baseline) == []
    assert [s.identity for s in resolved_survivors(current, baseline)] == ["a.py:20:+->-"]


def test_mutation_rebaseline_requires_reason_for_new_survivors() -> None:
    """Accepting a new survivor is admitting a weaker suite; it needs a reason."""
    previous = MutationBaseline(survivors=frozenset({_s("a.py", 10, "and->or")}))
    current = frozenset({_s("a.py", 10, "and->or"), _s("c.py", 1, "x->None")})
    with pytest.raises(BaselineEnvironmentError, match="reason"):
        mut_rebaseline(current, previous, reason=None, environment="ci", tool="mutmut", pinned=True)


def test_mutation_rebaseline_refuses_on_dev_box() -> None:
    with pytest.raises(BaselineEnvironmentError, match="dev box|pinned"):
        mut_rebaseline(
            frozenset(),
            MutationBaseline(),
            reason="x",
            environment="dev",
            tool="mutmut",
            pinned=False,
        )


# ---------------------------------------------------------------------------
# gate level — injected measurement
# ---------------------------------------------------------------------------


def _ci_project(project: Project) -> Project:
    """A project that looks like the pinned environment."""
    project.write(
        "pyproject.toml",
        """
        [project]
        name = "fixture"
        version = "0.0.0"

        [tool.celebrimbor]
        source = "src"
        trusted_environment = true
        pinned_environment = true
        """,
    )
    project.surfaces("version: 1\nmodules: {}\n")
    return project


def test_coverage_drop_is_red(project: Project) -> None:
    """Gate level: an injected coverage drop against a committed baseline."""
    _ci_project(project)
    project.write(
        ".celebrimbor/baselines/coverage.yaml",
        "version: 1\nenvironment: ci\nfloors:\n  app.core: 90.0\n",
    )
    ctx = project.context(tier=Tier.DEFAULT)
    ctx.memo("ratchet.coverage", lambda: {"app.core": 80.0})
    result = run_spec(project.spec("celebrimbor.coverage"), ctx)
    assert result.verdict is Verdict.FAIL
    assert "coverage-drop" in codes(result)


def test_first_run_in_ci_auto_baselines(project: Project) -> None:
    """Auto-baseline closes the day-two-red gap: first CI run records and passes."""
    _ci_project(project)
    ctx = project.context(tier=Tier.DEFAULT)
    ctx.memo("ratchet.coverage", lambda: {"app.core": 88.0})
    result = run_spec(project.spec("celebrimbor.coverage"), ctx)
    assert result.verdict is Verdict.PASS
    assert "baseline recorded" in result.summary
    assert (project.root / ".celebrimbor/baselines/coverage.yaml").exists()


def test_no_baseline_on_dev_box_skips(project: Project) -> None:
    """A dev box does not baseline; it skips, so it cannot inflate above CI."""
    project.write(
        "pyproject.toml",
        """
        [project]
        name = "fixture"
        version = "0.0.0"

        [tool.celebrimbor]
        source = "src"
        pinned_environment = false
        """,
    )
    project.surfaces("version: 1\nmodules: {}\n")
    ctx = project.context(tier=Tier.DEFAULT)
    ctx.memo("ratchet.coverage", lambda: {"app.core": 88.0})
    result = run_spec(project.spec("celebrimbor.coverage"), ctx)
    assert result.verdict is Verdict.SKIPPED
    assert not result.proved


def test_new_survivor_with_same_count_is_red(project: Project) -> None:
    """Gate level: the survivor-identity regression, injected."""
    _ci_project(project)
    project.write(
        ".celebrimbor/baselines/mutation.yaml",
        "version: 1\nenvironment: ci\nsurvivors:\n  - src/app/a.py:10:and->or\n  - src/app/a.py:20:+->-\n",
    )
    ctx = project.context(tier=Tier.FULL)
    ctx.memo(
        "ratchet.survivors",
        lambda: frozenset(
            {
                Survivor("src/app/a.py", 10, "and->or"),
                Survivor("src/app/b.py", 5, "True->False"),
            }
        ),
    )
    result = run_spec(project.spec("celebrimbor.mutation"), ctx)
    assert result.verdict is Verdict.FAIL
    assert "mutation-new-survivor" in codes(result)
    assert any("b.py:5" in f.message for f in result.findings)
