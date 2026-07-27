"""Structural gates: complexity budgets and the dependency-injection gate."""

from __future__ import annotations

from ..context import Context
from ..registry import check
from ..result import CheckResult, Finding, Tier
from ..structure.capabilities import scan_callable, violations
from ..structure.cohesion import analyze
from ..structure.complexity import measure_module
from ._shared import get_inventory, iter_ratified, require_surface_map

_COMPLEXITY = "celebrimbor.structure.complexity"
_CAPABILITIES = "celebrimbor.structure.capabilities"


@check(
    id=_COMPLEXITY,
    title="no callable or module exceeds its structural budget",
    tier=Tier.FAST,
    falsified_by="tests/negative/test_structure_gate.py::test_complex_function_is_red",
)
def check_complexity(ctx: Context) -> CheckResult:
    """Complexity, nesting, length, parameter and return counts.

    Tier 0 and always on: this needs no ledger and no role map, only source.
    Measured from the AST rather than delegated to ruff so the numbers stay
    pinned to this codebase — a ratchet whose denominator shifts when a linter
    upgrades reddens CI for reasons nobody changed.
    """
    inv = get_inventory(ctx)
    limits = ctx.config.limits
    findings: list[Finding] = []
    measured = 0

    for module in inv.modules:
        if module.tree is None:
            continue
        metrics = measure_module(module.tree, module.dotted, module.path, module.source)
        measured += 1

        findings.extend(
            Finding(
                message=f"{module.dotted}: {name} is {actual} (limit {limit})",
                path=module.path,
                code="structure-module",
                hint=_module_hint(name),
            )
            for name, actual, limit in metrics.breaches(limits)
        )

        cohesion = analyze(module.tree, module.dotted, module.path)
        if cohesion.count > limits.max_domains_per_file:
            findings.append(
                Finding(
                    message=(
                        f"{module.dotted}: {cohesion.count} independent domains in one "
                        f"module (limit {limits.max_domains_per_file}) — {cohesion.describe()}"
                    ),
                    path=module.path,
                    code="structure-cohesion",
                    hint=(
                        "these clusters never reference each other, so they are separate "
                        "reasons for this file to change. Split them into modules named "
                        "for what they are."
                    ),
                )
            )

        for callable_metrics in metrics.callables:
            findings.extend(
                Finding(
                    message=(
                        f"{module.dotted}:{callable_metrics.qualname} — "
                        f"{name} is {actual} (limit {limit})"
                    ),
                    path=module.path,
                    line=callable_metrics.lineno,
                    code="structure-callable",
                    hint=_callable_hint(name),
                )
                for name, actual, limit in callable_metrics.breaches(limits)
            )

    if not measured:
        return CheckResult.refused(
            _COMPLEXITY,
            "no source modules were found",
            reason=(
                f"nothing to measure under {ctx.config.source!r}. An empty source tree "
                "proves nothing, so this refuses rather than reporting a clean pass."
            ),
            remedy="set `source` in celebrimbor.toml if the layout is unconventional",
        )

    if findings:
        return CheckResult.failed(
            _COMPLEXITY,
            f"{len(findings)} structural budget breach(es) across {measured} module(s)",
            findings,
        )
    return CheckResult.passed(_COMPLEXITY, f"{measured} module(s) within structural budget")


def _module_hint(metric: str) -> str:
    return {
        "file lines": "split the module; long files hide unrelated domains inside one import",
        "public callables": "the module has grown into a grab bag; split by domain",
    }.get(metric, "reduce it")


def _callable_hint(metric: str) -> str:
    return {
        "cyclomatic complexity": (
            "extract the branches. Complexity is the count of paths a test would have "
            "to cover; past ~10 nobody covers them all and the uncovered ones are where "
            "plausible-but-wrong lives."
        ),
        "nesting depth": "invert conditions and return early, or extract the inner block",
        "statements": "the callable is doing several jobs; name them and split",
        "parameters": (
            "group related parameters into a dataclass — a long parameter list is usually "
            "an unnamed concept"
        ),
        "return statements": "many exits make the postcondition hard to state, let alone prove",
        "lines": "split it; a callable that does not fit on a screen cannot be reviewed",
    }.get(metric, "reduce it")


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
    calling ``datetime.now()`` has behaviour at midnight that no test can
    reach, because there is no seam to reach it through.

    This is Tier 1 because the *budget* comes from the role. Without a ratified
    map there is no principled answer to "is this reach allowed here" — and
    guessing one would either flag every adapter (noise nobody keeps) or flag
    nothing (a gate that never fires). With roles, the same line is a violation
    in a `pure` callable and correct in an `adapter`.
    """
    smap = require_surface_map(ctx, _CAPABILITIES)
    if isinstance(smap, CheckResult):
        return smap

    findings: list[Finding] = []
    scanned = 0
    for entry in iter_ratified(ctx, smap):
        scanned += 1
        findings.extend(
            Finding(
                message=breach.message,
                path=entry.info.path,
                line=breach.use.lineno,
                code="capability-ambient",
                hint=breach.remedy,
            )
            for breach in violations(scan_callable(entry.node, entry.info), entry.role)
        )

    if findings:
        return CheckResult.failed(
            _CAPABILITIES,
            f"{len(findings)} ambient dependency use(s) outside the role's capability budget",
            findings,
            remedy="inject the capability, or reclassify the callable as an `adapter`",
        )
    return CheckResult.passed(
        _CAPABILITIES,
        f"{scanned} ratified callable(s) stay within their role's capability budget",
    )
