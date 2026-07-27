"""Structural gates: complexity budgets and the dependency-injection gate.

Both gates ratchet. On a greenfield repo with no structure baseline they are
strict — every breach fails. On an established codebase they grandfather the
debt that exists at adoption (a deliberate, reason-gated act taken in CI) and
thereafter fail only new or worsened breaches. See
:mod:`celebrimbor.ratchets.structure` for why structure grandfathers explicitly
rather than auto-baselining the way coverage does.

The two gates share one baseline file, keyed by namespace (``complexity/…`` and
``capability/…``) so each manages only its own entries. Because the runner
executes checks sequentially, the read-modify-write on ``--update-baselines`` is
safe.
"""

from __future__ import annotations

from ..context import Context
from ..ratchets.baseline import BaselineEnvironmentError, require_pinned, require_reason
from ..ratchets.structure import (
    Breach,
    StructureBaseline,
    load_structure_baseline,
    ratchet,
    write_structure_baseline,
)
from ..registry import check
from ..result import CheckResult, Finding, Tier
from ..structure.capabilities import scan_callable, violations
from ..structure.cohesion import analyze
from ..structure.complexity import measure_module
from ..yamlio import YamlError
from ._shared import get_inventory, iter_ratified, require_surface_map

_COMPLEXITY = "celebrimbor.structure.complexity"
_CAPABILITIES = "celebrimbor.structure.capabilities"


def _slug(metric: str) -> str:
    return metric.replace(" ", "-")


# ---------------------------------------------------------------------------
# shared ratchet flow
# ---------------------------------------------------------------------------


def _load_baseline(ctx: Context, gate_id: str) -> StructureBaseline | CheckResult | None:
    path = ctx.config.structure_baseline_path
    if not path.exists():
        return None
    try:
        return load_structure_baseline(path)
    except YamlError as exc:
        return CheckResult.refused(
            gate_id, "the structure baseline could not be read", reason=str(exc)
        )


def _namespaced(baseline: StructureBaseline | None, namespace: str) -> StructureBaseline | None:
    """The baseline restricted to one gate's keys, so `resolved` is accurate."""
    if baseline is None:
        return None
    prefix = f"{namespace}/"
    return StructureBaseline(
        breaches={k: v for k, v in baseline.breaches.items() if k.startswith(prefix)},
        environment=baseline.environment,
    )


def _update(ctx: Context, gate_id: str, breaches: list[Breach], namespace: str) -> CheckResult:
    """Merge this gate's breaches into the shared baseline, keeping the others."""
    try:
        require_pinned(ctx.config.pinned_environment, action="take a structure baseline")
        reason = require_reason(
            ctx.update_reason, action=f"grandfather {len(breaches)} structure breach(es)"
        )
    except BaselineEnvironmentError as exc:
        return CheckResult.refused(gate_id, "structure baseline was not updated", reason=str(exc))

    path = ctx.config.structure_baseline_path
    existing: dict[str, int] = {}
    if path.exists():
        loaded = _load_baseline(ctx, gate_id)
        if isinstance(loaded, CheckResult):
            return loaded
        if loaded is not None:
            existing = dict(loaded.breaches)

    prefix = f"{namespace}/"
    merged = {k: v for k, v in existing.items() if not k.startswith(prefix)}
    merged.update({b.key: b.value for b in breaches})
    write_structure_baseline(path, StructureBaseline(breaches=merged, environment="ci"), reason)
    return CheckResult.passed(gate_id, f"structure baseline updated: {len(breaches)} grandfathered")


def _report(
    ctx: Context,
    gate_id: str,
    breaches: list[Breach],
    namespace: str,
    *,
    clean_summary: str,
) -> CheckResult:
    baseline = _load_baseline(ctx, gate_id)
    if isinstance(baseline, CheckResult):
        return baseline
    if ctx.update_baselines:
        return _update(ctx, gate_id, breaches, namespace)

    verdict = ratchet(breaches, _namespaced(baseline, namespace))
    if verdict.survived:
        tail = f" ({verdict.grandfathered} grandfathered)" if verdict.grandfathered else ""
        return CheckResult.failed(
            gate_id,
            f"{len(verdict.survived)} new or worsened structural breach(es){tail}",
            [Finding(message=b.message, code=b.code) for b in verdict.survived],
            remedy=(
                None
                if baseline is None
                else "to grandfather existing debt at adoption: "
                "`celebrimbor gate --update-baselines --reason ...` in CI"
            ),
        )
    detail = clean_summary
    if verdict.grandfathered:
        detail += f"; {verdict.grandfathered} grandfathered breach(es) held"
    return CheckResult.passed(gate_id, detail)


# ---------------------------------------------------------------------------
# complexity + cohesion
# ---------------------------------------------------------------------------


def _complexity_breaches(ctx: Context) -> list[Breach] | CheckResult:
    inv = get_inventory(ctx)
    limits = ctx.config.limits
    breaches: list[Breach] = []
    measured = 0

    for module in inv.modules:
        if module.tree is None:
            continue
        measured += 1
        metrics = measure_module(module.tree, module.dotted, module.path, module.source)

        for name, actual, limit in metrics.breaches(limits):
            breaches.append(
                Breach(
                    key=f"complexity/{module.dotted}::{_slug(name)}",
                    value=actual,
                    message=f"{module.dotted}: {name} is {actual} (limit {limit}) — {_module_hint(name)}",
                    code="structure-module",
                )
            )

        cohesion = analyze(module.tree, module.dotted, module.path)
        if cohesion.count > limits.max_domains_per_file:
            breaches.append(
                Breach(
                    key=f"complexity/{module.dotted}::cohesion",
                    value=cohesion.count,
                    message=(
                        f"{module.dotted}: {cohesion.count} independent domains in one module "
                        f"(limit {limits.max_domains_per_file}) — {cohesion.describe()}"
                    ),
                    code="structure-cohesion",
                )
            )

        for cm in metrics.callables:
            breaches.extend(
                Breach(
                    key=f"complexity/{module.dotted}:{cm.qualname}:{_slug(name)}",
                    value=actual,
                    message=(
                        f"{module.dotted}:{cm.qualname} — {name} is {actual} (limit {limit}) "
                        f"— {_callable_hint(name)}"
                    ),
                    code="structure-callable",
                )
                for name, actual, limit in cm.breaches(limits)
            )

    if not measured:
        return CheckResult.refused(
            _COMPLEXITY,
            "no source modules were found",
            reason=(
                f"nothing to measure under {ctx.config.source!r}. An empty source tree proves "
                "nothing, so this refuses rather than reporting a clean pass."
            ),
            remedy="set `source` in celebrimbor.toml if the layout is unconventional",
        )
    return breaches


@check(
    id=_COMPLEXITY,
    title="no callable or module exceeds its structural budget",
    tier=Tier.FAST,
    falsified_by="tests/negative/test_structure_gate.py::test_complex_function_is_red",
)
def check_complexity(ctx: Context) -> CheckResult:
    """Complexity, nesting, length, parameter, return, and cohesion budgets.

    Measured from the AST rather than delegated to ruff so the numbers stay
    pinned to this codebase — a metric whose definition shifts when a linter
    upgrades reddens CI for reasons nobody changed. Ratchets against a structure
    baseline when one exists; strict otherwise.
    """
    breaches = _complexity_breaches(ctx)
    if isinstance(breaches, CheckResult):
        return breaches
    return _report(
        ctx,
        _COMPLEXITY,
        breaches,
        "complexity",
        clean_summary="every module is within its structural budget",
    )


def _module_hint(metric: str) -> str:
    return {
        "file lines": "split the module; long files hide unrelated domains inside one import",
        "public callables": "the module has grown into a grab bag; split by domain",
    }.get(metric, "reduce it")


def _callable_hint(metric: str) -> str:
    return {
        "cyclomatic complexity": "extract the branches",
        "nesting depth": "invert conditions and return early, or extract the inner block",
        "statements": "the callable is doing several jobs; name them and split",
        "positional parameters": "group related parameters into a dataclass",
        "return statements": "many exits make the postcondition hard to state",
        "lines": "split it; a callable that does not fit on a screen cannot be reviewed",
    }.get(metric, "reduce it")


# ---------------------------------------------------------------------------
# capabilities
# ---------------------------------------------------------------------------


@check(
    id=_CAPABILITIES,
    title="external dependencies are injected, not reached for",
    tier=Tier.FAST,
    tier1=True,
    falsified_by="tests/negative/test_structure_gate.py::test_ambient_clock_in_pure_is_red",
)
def check_capabilities(ctx: Context) -> CheckResult:
    """The dependency-injection gate, budgeted by role.

    An un-injected dependency is a claim the test cannot contradict: a function
    calling ``datetime.now()`` has behaviour at midnight that no test can reach,
    because there is no seam to reach it through. Tier 1 because the *budget*
    comes from the role. Ratchets against the shared structure baseline.
    """
    smap = require_surface_map(ctx, _CAPABILITIES)
    if isinstance(smap, CheckResult):
        return smap

    breaches: list[Breach] = []
    scanned = 0
    for entry in iter_ratified(ctx, smap):
        scanned += 1
        for breach in violations(scan_callable(entry.node, entry.info), entry.role):
            breaches.append(
                Breach(
                    key=f"capability/{entry.info.key}:{breach.use.capability.value}",
                    value=1,
                    message=f"{breach.message} — {breach.remedy}",
                    code="capability-ambient",
                )
            )

    return _report(
        ctx,
        _CAPABILITIES,
        breaches,
        "capability",
        clean_summary=f"{scanned} ratified callable(s) stay within their role's capability budget",
    )
