"""Negative fixtures for the runner: nothing escapes, nothing is manufactured.

A check that silently stops running is the purest form of the failure this
project exists to prevent — the report still looks green, and the thing it was
green about was never examined.
"""

from __future__ import annotations

import pytest

from celebrimbor.context import Context
from celebrimbor.registry import Registry, check
from celebrimbor.result import CheckResult, GateReport, Stage, Verdict
from celebrimbor.runner import escaped, expected_ids, run, run_spec, strays
from tests.conftest import Project

pytestmark = pytest.mark.negative


def _passing(check_id: str):  # noqa: ANN202 - local test helper
    def fn(_ctx: Context) -> CheckResult:
        return CheckResult.passed(check_id, "fine")

    return fn


def _registry_of(*ids: str) -> Registry:
    registry = Registry()
    for check_id in ids:
        check(
            id=check_id,
            title=f"title for {check_id}",
            stage=Stage.FAST,
            falsified_by="tests/negative/test_runner_completeness.py",
            registry=registry,
        )(_passing(check_id))
    return registry


def test_dropped_check_is_red(project: Project) -> None:
    """A registered check absent from the report is an escapee."""
    registry = _registry_of("a.one", "a.two", "a.three")
    report = run(project.context(), registry=registry)
    assert not escaped(report, registry), "baseline: nothing escapes a normal run"

    # Simulate the failure: a check that was registered but never reported.
    report.results = [r for r in report.results if r.check_id != "a.two"]
    assert escaped(report, registry) == {"a.two"}


def test_stray_result_is_detected(project: Project) -> None:
    """A result from outside the registry is as bad as a missing one.

    It means verdicts are being manufactured somewhere the completeness
    guarantee does not reach, so nothing proves *those* are complete.
    """
    registry = _registry_of("a.one")
    report = run(project.context(), registry=registry)
    report.add(CheckResult.passed("a.ghost", "from nowhere"))
    assert strays(report, registry) == {"a.ghost"}


def test_raising_check_refuses_rather_than_crashing(project: Project) -> None:
    """Every fault inside a check becomes red, never an escaped exception."""
    registry = Registry()

    def explodes(_ctx: Context) -> CheckResult:
        raise RuntimeError("the check itself is broken")

    check(
        id="a.boom",
        title="a check that raises",
        stage=Stage.FAST,
        falsified_by="tests/negative/test_runner_completeness.py",
        registry=registry,
    )(explodes)

    result = run_spec(registry.get("a.boom"), project.context())  # type: ignore[arg-type]
    assert result.verdict is Verdict.REFUSED
    assert "raised an exception" in (result.reason or "")
    assert "RuntimeError" in (result.reason or "")


def test_check_returning_none_refuses(project: Project) -> None:
    """Returning nothing establishes nothing, so it cannot read as a pass."""
    registry = Registry()
    check(
        id="a.none",
        title="a check that returns nothing",
        stage=Stage.FAST,
        falsified_by="tests/negative/test_runner_completeness.py",
        registry=registry,
    )(lambda _ctx: None)  # type: ignore[arg-type,return-value]

    result = run_spec(registry.get("a.none"), project.context())  # type: ignore[arg-type]
    assert result.verdict is Verdict.REFUSED


def test_misfiled_result_refuses(project: Project) -> None:
    """A result under the wrong id reads as a missing check *and* a stray pass."""
    registry = Registry()
    check(
        id="a.real",
        title="a check that files under the wrong name",
        stage=Stage.FAST,
        falsified_by="tests/negative/test_runner_completeness.py",
        registry=registry,
    )(lambda _ctx: CheckResult.passed("a.other", "fine"))

    result = run_spec(registry.get("a.real"), project.context())  # type: ignore[arg-type]
    assert result.verdict is Verdict.REFUSED
    assert result.check_id == "a.real"
    assert "wrong id" in result.summary


def test_empty_report_is_red_not_green(project: Project) -> None:
    """A gate that ran zero checks has proved nothing.

    Reporting green for it is exactly the plausible-but-wrong outcome the
    project exists to prevent, so emptiness is caught in `GateReport.ok` where
    no caller can forget it.
    """
    report = run(project.context(), registry=Registry())
    assert len(report) == 0
    assert not report.ok
    assert report.exit_code == 1


def test_tier_filtering_is_the_only_definition_of_a_complete_run() -> None:
    """`expected_ids` is the single source of truth the meta-check compares to."""
    registry = Registry()
    for check_id, stage in (("a.fast", Stage.FAST), ("a.def", Stage.DEFAULT), ("a.full", Stage.FULL)):
        check(
            id=check_id,
            title=check_id,
            stage=stage,
            falsified_by="tests/negative/test_runner_completeness.py",
            registry=registry,
        )(_passing(check_id))

    assert expected_ids(registry, Stage.FAST) == {"a.fast"}
    assert expected_ids(registry, Stage.DEFAULT) == {"a.fast", "a.def"}
    assert expected_ids(registry, Stage.FULL) == {"a.fast", "a.def", "a.full"}


def test_disabled_check_is_skipped_visibly_not_silently(project: Project) -> None:
    """Disabling is an exception on the record, and the record is the report."""
    project.write(
        "pyproject.toml",
        """
        [project]
        name = "fixture"
        version = "0.0.0"

        [tool.celebrimbor]
        source = "src"
        disabled_checks = ["a.one"]
        """,
    )
    registry = _registry_of("a.one", "a.two")
    report = run(project.context(), registry=registry)

    disabled = report.by_id("a.one")
    assert disabled is not None
    assert disabled.verdict is Verdict.SKIPPED
    assert not disabled.proved
    assert "disabled" in (disabled.reason or "")
    # Still present in the report: disabled is not the same as absent.
    assert not escaped(report, registry)


def test_report_of_only_skips_is_not_a_pass(project: Project) -> None:
    """Skips are ok but never proved; a run of nothing but skips proved nothing."""
    report = GateReport(stage=Stage.FAST)
    report.add(CheckResult.skipped("a.one", "not opted in"))
    assert report.ok, "a skip does not redden the gate"
    assert not any(r.proved for r in report), "but nothing was established either"
