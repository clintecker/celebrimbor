"""The dual runner: one execution path, reachable from the CLI and from pytest.

"Dual" does not mean two runners. It means one runner, :func:`run_spec`, with
two front doors — the CLI walks the registry itself, and the pytest seam
parametrizes over the same registry and calls the same function. If there were
two execution paths, a check could behave differently under each, and the
"no check escapes the runner" guarantee would only cover one of them.

Every way a check can misbehave is converted to red here:

* raises              -> ``REFUSED`` (with the traceback in the reason)
* returns ``None``    -> ``REFUSED``
* returns a wrong id  -> ``REFUSED`` (a result filed under another id would
                        appear as a missing check *and* a stray pass)
* times out           -> not our problem; checks are in-process and a hung
                        check hangs the gate visibly, which is honest

None of these paths can produce ``PASS``, which is the property that makes the
runner itself fail closed.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable, Iterable

from .context import Context
from .registry import CheckSpec, Registry, default_registry
from .result import CheckResult, GateReport, Stage

Clock = Callable[[], float]
"""A monotonic seconds source. Injected so the timing the runner records is a
dependency a test can pin, not a wall-clock reading it cannot. The default is
the real clock; the point of the seam is that tests do not have to use it."""


def run_spec(spec: CheckSpec, ctx: Context, *, clock: Clock = time.perf_counter) -> CheckResult:
    """Execute one check, converting every failure mode into a verdict.

    This function never raises for a fault inside ``spec.fn``. It is the sole
    place where check-authored code is called.
    """
    if spec.id in ctx.config.disabled_checks:
        return CheckResult.skipped(
            spec.id, "disabled in celebrimbor config (an exception, on the record)"
        )

    started = clock()
    try:
        # Typed as `object`, not CheckResult: app-authored checks are not
        # type-checked by us, so the guards below are genuinely reachable.
        result: object = spec.fn(ctx)
    except Exception:
        elapsed = clock() - started
        return CheckResult.refused(
            spec.id,
            f"{spec.title} — the check itself raised",
            reason=(
                "the check raised an exception, so its claim is unestablished:\n"
                + traceback.format_exc(limit=6).strip()
            ),
            remedy="fix the check; a gate that cannot run proves nothing",
            duration_s=elapsed,
        )
    elapsed = clock() - started

    if result is None:
        return CheckResult.refused(
            spec.id,
            f"{spec.title} — the check returned nothing",
            reason="a check must return a CheckResult; returning None establishes nothing",
            duration_s=elapsed,
        )
    if not isinstance(result, CheckResult):
        return CheckResult.refused(
            spec.id,
            f"{spec.title} — the check returned {type(result).__name__}",
            reason="a check must return a CheckResult",
            duration_s=elapsed,
        )
    if result.check_id != spec.id:
        return CheckResult.refused(
            spec.id,
            f"{spec.title} — the check filed its result under the wrong id",
            reason=(
                f"registered as {spec.id!r} but returned a result for {result.check_id!r}; "
                "a misfiled result would read as both a missing check and a stray pass"
            ),
            duration_s=elapsed,
        )

    # Preserve the measured duration; checks rarely bother to set it.
    if result.duration_s == 0.0:
        return CheckResult(
            check_id=result.check_id,
            verdict=result.verdict,
            summary=result.summary,
            findings=result.findings,
            reason=result.reason,
            duration_s=elapsed,
            remedy=result.remedy,
        )
    return result


def run(
    ctx: Context,
    *,
    registry: Registry | None = None,
    stage: Stage | None = None,
    clock: Clock = time.perf_counter,
) -> GateReport:
    """Run every check registered at or below ``stage``.

    The report is built incrementally and exposed on the context as it grows,
    so the terminal completeness check can compare what actually ran against
    what the registry says should have run.
    """
    reg = registry if registry is not None else default_registry()
    resolved = stage if stage is not None else ctx.stage
    report = GateReport(stage=resolved)
    ctx.partial = report

    started = clock()
    for spec in reg.for_stage(resolved):
        report.add(run_spec(spec, ctx, clock=clock))
    report.duration_s = clock() - started
    return report


def expected_ids(registry: Registry, stage: Stage) -> set[str]:
    """What a complete run at ``stage`` must contain.

    Sole definition, used by both the terminal completeness check and the
    meta-test in celebrimbor's own suite.
    """
    return {s.id for s in registry.for_stage(stage)}


def escaped(report: GateReport, registry: Registry) -> set[str]:
    """Ids that should have run at the report's stage but are absent from it."""
    return expected_ids(registry, report.stage) - report.ids()


def strays(report: GateReport, registry: Registry) -> set[str]:
    """Ids present in the report that the registry does not know about.

    A stray is as bad as an escapee: it means results are being manufactured
    somewhere other than the registry, and nothing proves *those* are complete.
    """
    return report.ids() - registry.ids()


def load_builtin_checks() -> tuple[str, ...]:
    """Import the modules that register celebrimbor's own checks.

    Registration-by-import-side-effect is a real hazard — a check in a module
    nobody imports is a check that silently never runs — so the import list is
    explicit and centralized here rather than scattered, and the meta-test
    walks the package to prove nothing is missing from it.

    Returns the module names it ensured are loaded, so the load has an
    inspectable result rather than a bare side effect.
    """
    from . import checks

    return checks.load_all()


def iter_specs(stage: str | Stage = Stage.FULL) -> Iterable[CheckSpec]:
    """Every registered spec at or below ``stage``. The pytest seam uses this."""
    load_builtin_checks()
    return default_registry().for_stage(Stage.parse(stage))
