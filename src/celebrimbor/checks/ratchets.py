"""The ratchet gates: coverage floor (PR tier) and mutation survivors (merge tier).

Both follow the same shape — acquire the current measurement, then compare it
against a committed baseline with a pure comparator — and both delegate the
scars (pinned-environment gating, reason-gated updates, the low-floor
meta-ratchet) to the ratchet modules so the gate itself stays about acquisition
and reporting.

Auto-baseline closes the "existing repo goes red on day two" gap: on the first
run in the pinned environment, with no baseline yet, the gate records the
current numbers and passes. Every run after ratchets against them.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..commodity.tools import ToolMissingError, version_of
from ..commodity.tools import run as run_tool
from ..context import Context
from ..ratchets import coverage as cov
from ..ratchets import mutation as mut
from ..ratchets.baseline import BaselineEnvironmentError
from ..registry import check
from ..result import CheckResult, Finding, Tier
from ..yamlio import YamlError

_COVERAGE = "celebrimbor.coverage"
_MUTATION = "celebrimbor.mutation"


def _environment_label(ctx: Context) -> str:
    return "ci" if ctx.config.pinned_environment else "dev"


# ---------------------------------------------------------------------------
# coverage ratchet
# ---------------------------------------------------------------------------


def _acquire_coverage(ctx: Context) -> dict[str, float] | str:
    """Current per-module coverage, or a string explaining why we could not.

    Reads an existing ``.coverage`` data file via ``coverage json``. The PR
    tier expects the test run to have already produced it; the gate measures,
    it does not run the suite itself.
    """

    def produce() -> dict[str, float] | str:
        if not (ctx.root / ".coverage").exists():
            return "no .coverage data file; run your tests under coverage first"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "coverage.json"
            try:
                result = run_tool("coverage", ["json", "-o", str(out)], cwd=ctx.root, timeout_s=60)
            except ToolMissingError:
                return "missing:coverage"
            if not out.exists():
                return f"coverage json failed: {result.combined[:300] or '(no output)'}"
            data = json.loads(out.read_text(encoding="utf-8"))
        return cov.parse_coverage_json(data, ctx.config.source)

    return ctx.memo("ratchet.coverage", produce)


@check(
    id=_COVERAGE,
    title="per-module coverage only rises",
    tier=Tier.DEFAULT,
    tier1=True,
    falsified_by="tests/negative/test_ratchet_gate.py::test_coverage_drop_is_red",
)
def check_coverage(ctx: Context) -> CheckResult:
    """The coverage ratchet, with auto-baseline and the low-floor meta-ratchet."""
    current = _acquire_coverage(ctx)
    if isinstance(current, str):
        if current == "missing:coverage":
            if ctx.config.trusted_environment:
                return CheckResult.refused(
                    _COVERAGE,
                    "coverage is not installed",
                    reason="trusted environment promised the ladder, but `coverage` is absent",
                )
            return CheckResult.skipped(_COVERAGE, "coverage is not installed (dev box)")
        return CheckResult.refused(_COVERAGE, "coverage could not be measured", reason=current)

    path = ctx.config.coverage_baseline_path
    minimum = ctx.config.min_coverage_floor

    if not path.exists():
        return _baseline_coverage(ctx, current, path)

    try:
        baseline = cov.load_coverage_baseline(path)
    except YamlError as exc:
        return CheckResult.refused(
            _COVERAGE, "the coverage baseline could not be read", reason=str(exc)
        )

    if ctx.update_baselines:
        return _update_coverage(ctx, current, baseline, path)

    regressions = cov.coverage_regressions(current, baseline, minimum=minimum)
    if regressions:
        return CheckResult.failed(
            _COVERAGE,
            f"{len(regressions)} coverage ratchet violation(s)",
            [
                Finding(message=r.message, code=f"coverage-{r.kind}", hint=_coverage_hint(r.kind))
                for r in regressions
            ],
        )
    return CheckResult.passed(
        _COVERAGE, f"{len(baseline.floors)} module floor(s) held; coverage did not fall"
    )


def _coverage_hint(kind: str) -> str:
    return {
        "drop": "add tests to restore coverage, or --update-baselines --reason in CI to record why",
        "low-floor": "raise coverage above the configured minimum, or record a reason via --update",
        "new-below-policy": "new code must clear the configured minimum, or record a reason",
    }.get(kind, "")


def _baseline_coverage(ctx: Context, current: dict[str, float], path: Path) -> CheckResult:
    if not ctx.config.pinned_environment:
        return CheckResult.skipped(
            _COVERAGE,
            "no coverage baseline yet, and this is not the pinned environment. The baseline "
            "is taken in CI so it does not read higher than CI will.",
        )
    baseline = cov.CoverageBaseline(
        floors=dict(current),
        environment=_environment_label(ctx),
        tool=version_of("coverage") or "coverage",
    )
    cov.write_coverage_baseline(path, baseline)
    return CheckResult.passed(
        _COVERAGE, f"coverage baseline recorded for {len(current)} module(s) (first run in CI)"
    )


def _update_coverage(
    ctx: Context, current: dict[str, float], baseline: cov.CoverageBaseline, path: Path
) -> CheckResult:
    try:
        updated = cov.rebaseline(
            current,
            baseline,
            minimum=ctx.config.min_coverage_floor,
            reason=ctx.update_reason,
            environment=_environment_label(ctx),
            tool=version_of("coverage") or "coverage",
            pinned=ctx.config.pinned_environment,
        )
    except BaselineEnvironmentError as exc:
        return CheckResult.refused(_COVERAGE, "coverage baseline was not updated", reason=str(exc))
    cov.write_coverage_baseline(path, updated)
    return CheckResult.passed(_COVERAGE, f"coverage baseline updated: {ctx.update_reason}")


# ---------------------------------------------------------------------------
# mutation ratchet
# ---------------------------------------------------------------------------


def _acquire_survivors(ctx: Context) -> frozenset[mut.Survivor] | str:
    """Current surviving mutants, or a string explaining why we could not.

    Injectable via the ``ratchet.survivors`` memo for tests; in production the
    gate reads the mutation tool's results. Mutation is genuinely slow, which
    is why this whole gate is merge-tier only.
    """
    memoized = ctx._memo.get("ratchet.survivors")
    if memoized is not None:
        return memoized  # type: ignore[return-value]
    return "mutation acquisition requires the configured mutation tool; not yet wired for auto-run"


@check(
    id=_MUTATION,
    title="no new mutant survives (survivor identity, not count)",
    tier=Tier.FULL,
    tier1=True,
    falsified_by="tests/negative/test_ratchet_gate.py::test_new_survivor_with_same_count_is_red",
)
def check_mutation(ctx: Context) -> CheckResult:
    """The mutation ratchet. A *new* survivor is red even if the count is flat."""
    current = _acquire_survivors(ctx)
    if isinstance(current, str):
        return CheckResult.skipped(_MUTATION, current)

    path = ctx.config.mutation_baseline_path
    if not path.exists():
        return _baseline_mutation(ctx, current, path)

    try:
        baseline = mut.load_mutation_baseline(path)
    except YamlError as exc:
        return CheckResult.refused(
            _MUTATION, "the mutation baseline could not be read", reason=str(exc)
        )

    if ctx.update_baselines:
        return _update_mutation(ctx, current, baseline, path)

    appeared = mut.new_survivors(current, baseline)
    if appeared:
        resolved = mut.resolved_survivors(current, baseline)
        note = (
            f" ({len(resolved)} old survivor(s) now killed, but that does not offset a new hole)"
            if resolved
            else ""
        )
        return CheckResult.failed(
            _MUTATION,
            f"{len(appeared)} new surviving mutant(s){note}",
            [
                Finding(
                    message=f"new survivor {s.identity} — a mutation here goes uncaught",
                    path=Path(s.file),
                    line=s.line,
                    code="mutation-new-survivor",
                    hint="add a test that kills this mutant, or --update-baselines --reason in CI",
                )
                for s in appeared
            ],
        )
    return CheckResult.passed(
        _MUTATION,
        f"no new survivors; {len(baseline.survivors)} known survivor(s) unchanged or killed",
    )


def _baseline_mutation(ctx: Context, current: frozenset[mut.Survivor], path: Path) -> CheckResult:
    if not ctx.config.pinned_environment:
        return CheckResult.skipped(
            _MUTATION, "no mutation baseline yet, and this is not the pinned environment"
        )
    baseline = mut.MutationBaseline(
        survivors=current,
        environment=_environment_label(ctx),
        tool=version_of(ctx.config.mutation_tool) or ctx.config.mutation_tool,
    )
    mut.write_mutation_baseline(path, baseline)
    return CheckResult.passed(
        _MUTATION, f"mutation baseline recorded: {len(current)} survivor(s) (first run in CI)"
    )


def _update_mutation(
    ctx: Context, current: frozenset[mut.Survivor], baseline: mut.MutationBaseline, path: Path
) -> CheckResult:
    try:
        updated = mut.rebaseline(
            current,
            baseline,
            reason=ctx.update_reason,
            environment=_environment_label(ctx),
            tool=version_of(ctx.config.mutation_tool) or ctx.config.mutation_tool,
            pinned=ctx.config.pinned_environment,
        )
    except BaselineEnvironmentError as exc:
        return CheckResult.refused(_MUTATION, "mutation baseline was not updated", reason=str(exc))
    mut.write_mutation_baseline(path, updated)
    return CheckResult.passed(_MUTATION, f"mutation baseline updated: {ctx.update_reason}")
