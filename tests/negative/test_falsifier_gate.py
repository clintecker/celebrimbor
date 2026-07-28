"""Negative fixtures for the gates on the gates.

These are the ones that matter most, and the ones easiest to get wrong. If
``celebrimbor.falsifiers`` stops working, every other falsifier promise in the
codebase becomes unenforced simultaneously, and nothing else would notice.
"""

from __future__ import annotations

import datetime as dt

import pytest

from celebrimbor.registry import DuplicateCheckError, Registry, Unproven, check
from celebrimbor.result import CheckResult, Stage, Verdict
from celebrimbor.waiver import WaiverError
from tests.conftest import Project

pytestmark = pytest.mark.negative

_FALSIFIERS = "celebrimbor.falsifiers"


def _noop(_ctx: object) -> CheckResult:
    return CheckResult.passed("x", "fine")


def test_unproven_past_review_date_is_red(project: Project) -> None:
    """Debt with a deadline. Past the deadline, the gate says so.

    An allowlist that cannot expire is an allowlist that only grows, and the
    build contract asks for a visible, *shrinking* one.
    """
    registry = Registry()
    check(
        id="app.legacy",
        title="a check nobody has written a falsifier for",
        stage=Stage.FAST,
        falsified_by=Unproven("no negative fixture yet", review_by="2020-01-01"),
        registry=registry,
    )(_noop)

    spec = registry.get("app.legacy")
    assert spec is not None
    assert spec.unproven is not None
    assert spec.unproven.expired(), "a 2020 review date is comfortably in the past"

    # And the gate that reads it agrees.
    from celebrimbor.checks.meta import check_falsifiers
    from celebrimbor.registry import default_registry

    default_registry().register(spec)
    try:
        result = check_falsifiers(project.context())
        assert result.verdict is Verdict.FAIL
        assert any("falsifier-expired" == f.code for f in result.findings)
    finally:
        default_registry()._specs.pop("app.legacy", None)  # noqa: SLF001


def test_unproven_within_review_date_is_allowed_but_visible(project: Project) -> None:
    """Not yet expired is not the same as not counted."""
    future = (dt.date.today() + dt.timedelta(days=90)).isoformat()
    registry = Registry()
    check(
        id="app.pending",
        title="a check with dated debt",
        stage=Stage.FAST,
        falsified_by=Unproven("fixture coming", review_by=future),
        registry=registry,
    )(_noop)

    from celebrimbor.checks.meta import check_falsifiers
    from celebrimbor.registry import default_registry

    default_registry().register(registry.get("app.pending"))  # type: ignore[arg-type]
    try:
        result = check_falsifiers(project.context())
        assert result.verdict is Verdict.PASS
        assert "dated allowlist" in result.summary, "pending debt must stay visible"
    finally:
        default_registry()._specs.pop("app.pending", None)  # noqa: SLF001


def test_app_check_with_missing_falsifier_is_red(project: Project) -> None:
    """A path that does not resolve is a broken promise, not a formality."""
    from celebrimbor.checks.meta import check_falsifiers
    from celebrimbor.registry import default_registry

    check(
        id="app.claims",
        title="a check pointing at a file that does not exist",
        stage=Stage.FAST,
        falsified_by="tests/negative/test_nothing_here.py::test_absent",
    )(_noop)
    try:
        result = check_falsifiers(project.context())
        assert result.verdict is Verdict.FAIL
        assert any(f.code == "falsifier-missing" for f in result.findings)
    finally:
        default_registry()._specs.pop("app.claims", None)  # noqa: SLF001


def test_duplicate_check_id_is_rejected() -> None:
    """Ids address results, so a collision would silence one of the two.

    The second registration would otherwise replace or shadow the first, and
    the report would still show an entry under that name — a gate disappearing
    while looking present.
    """
    registry = Registry()
    check(id="app.dup", title="first", stage=Stage.FAST, falsified_by="a", registry=registry)(_noop)
    with pytest.raises(DuplicateCheckError, match="already registered"):
        check(id="app.dup", title="second", stage=Stage.FAST, falsified_by="b", registry=registry)(
            _noop
        )


def test_check_without_falsifier_cannot_be_written() -> None:
    """`falsified_by` has no default. That is the whole point of the decorator."""
    with pytest.raises(TypeError, match="falsified_by"):
        check(id="app.x", title="t", stage=Stage.FAST)(_noop)  # type: ignore[call-arg]


def test_empty_falsifier_is_rejected() -> None:
    """A blank string is not a falsifier; it is the absence of one, disguised."""
    with pytest.raises(ValueError, match="must name a real falsifier"):
        check(id="app.y", title="t", stage=Stage.FAST, falsified_by="   ")(_noop)
    with pytest.raises(ValueError, match="cannot be an empty tuple"):
        check(id="app.z", title="t", stage=Stage.FAST, falsified_by=())(_noop)


def test_unproven_requires_a_reason_and_a_date() -> None:
    """An undated or unexplained waiver waives nothing."""
    with pytest.raises(WaiverError, match="requires a reason"):
        Unproven("", review_by="2030-01-01")
    with pytest.raises(WaiverError, match="ISO date"):
        Unproven("because", review_by="soon")


def test_empty_registry_refuses_rather_than_passes(project: Project) -> None:
    """No checks registered means the check modules failed to import.

    Reporting "all falsifiers accounted for" over an empty registry would be
    the purest possible false green: vacuously true, and completely wrong.
    """
    from celebrimbor.checks.meta import check_falsifiers
    from celebrimbor.registry import default_registry

    registry = default_registry()
    saved = dict(registry._specs)  # noqa: SLF001
    registry._specs.clear()  # noqa: SLF001
    try:
        result = check_falsifiers(project.context())
        assert result.verdict is Verdict.REFUSED
        assert "not that all is well" in (result.reason or "")
    finally:
        registry._specs.update(saved)  # noqa: SLF001
