"""The terminal check: did every registered check actually run?

This must be the last module in ``CHECK_MODULES``, because it compares the
accumulated report against the registry and therefore has to run after
everything it is checking.

It closes the loop the build contract asks for — "a meta-test proving no check
escapes the runner" — but as a *gate* rather than only a test, so the property
holds in an adopter's repo and not just in celebrimbor's CI. A check that
silently stopped running is the purest form of the failure mode this project
exists to prevent: the report still looks green, and the thing it was
green about was never examined.

Note what it cannot catch: itself. If the terminal check does not run, nothing
reports that the terminal check did not run. That regress stops at
celebrimbor's own test suite, which asserts this check is present in every
stage's expected set — the one place a static assertion is enough.
"""

from __future__ import annotations

from ..context import Context
from ..registry import check, default_registry
from ..result import CheckResult, Finding, Stage
from ..runner import escaped, strays

_ID = "celebrimbor.completeness"


@check(
    id=_ID,
    title="no registered check escaped the runner",
    stage=Stage.FAST,
    terminal=True,
    falsified_by="tests/negative/test_runner_completeness.py::test_dropped_check_is_red",
)
def check_runner_completeness(ctx: Context) -> CheckResult:
    """Compare what ran against what the registry says should have run."""
    report = ctx.partial
    if report is None:
        return CheckResult.refused(
            _ID,
            "no report is in flight",
            reason=(
                "this check compares the running report against the registry, and there "
                "is no report — it was invoked outside the runner, so it can conclude nothing"
            ),
        )

    registry = default_registry()
    findings: list[Finding] = []

    # This check is itself still in flight, so it is legitimately absent from
    # the report at this moment. Everything else must be present.
    missing = escaped(report, registry) - {_ID}
    findings.extend(
        Finding(
            message=f"check {check_id!r} is registered for stage {report.stage.label} but did not run",
            code="runner-escaped",
            hint="a check that stops running is a gate that silently disappeared",
        )
        for check_id in sorted(missing)
    )

    findings.extend(
        Finding(
            message=(f"the report contains a result for {check_id!r}, which is not registered"),
            code="runner-stray",
            hint=(
                "results are being manufactured outside the registry, so nothing proves "
                "*those* are complete"
            ),
        )
        for check_id in sorted(strays(report, registry))
    )

    if findings:
        return CheckResult.failed(
            _ID,
            f"the runner and the registry disagree on {len(findings)} check(s)",
            findings,
        )

    ran = len(report) + 1
    return CheckResult.passed(
        _ID, f"{ran}/{ran} registered check(s) ran at stage {report.stage.label}"
    )
