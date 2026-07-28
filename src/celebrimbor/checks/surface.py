"""Surface completeness and naming-drift gates."""

from __future__ import annotations

from ..context import Context
from ..registry import check
from ..result import CheckResult, Finding, Stage
from ..surface import naming
from ..surface.audit import SurfaceAudit, audit, missing_row_snippet
from ..surface.inventory import Inventory
from ._shared import get_inventory, require_surface_map

_COMPLETENESS = "celebrimbor.surface.completeness"
_NAMING = "celebrimbor.surface.naming"


def _uncovered_findings(result: SurfaceAudit, inv: Inventory) -> list[Finding]:
    """One finding per uncovered *module*, not per callable.

    A module with forty unaccounted callables is one gap with one fix. Forty
    findings for it would bury every other kind of gap in the report, which is
    how a gate stops being read.
    """
    seen: set[str] = set()
    findings: list[Finding] = []
    for info in result.uncovered:
        if info.module in seen:
            continue
        seen.add(info.module)
        findings.append(
            Finding(
                message=f"module {info.module!r} has public callables but no surface-map row",
                path=info.path,
                line=info.lineno,
                code="surface-uncovered",
                hint="add to .celebrimbor/surfaces.yaml:\n" + missing_row_snippet(inv, info.module),
            )
        )
    return findings


def _unratified_findings(result: SurfaceAudit) -> list[Finding]:
    return [
        Finding(
            message=f"module {row.module!r} is still marked `inferred`; a human must ratify it",
            code="surface-unratified",
            hint=(
                f"confirm `role: {row.role.value}` is right, then run "
                f"`celebrimbor ratify {row.module}`"
            ),
        )
        for row in result.unratified
    ]


def _stale_findings(result: SurfaceAudit) -> list[Finding]:
    return [
        Finding(
            message=f"surface map has a row for {module!r}, which no longer exists in the source",
            code="surface-stale",
            hint="delete the row; a ledger describing code that is gone is a ledger nobody trusts",
        )
        for module in result.stale_rows
    ]


def _expired_findings(result: SurfaceAudit) -> list[Finding]:
    return [
        Finding(
            message=(
                f"exemption for {waiver.subject!r} passed its review date "
                f"({waiver.review_by.isoformat()}): {waiver.reason}"
            ),
            code="surface-exemption-expired",
            hint="re-justify with a new date, or classify the callable and delete the exemption",
        )
        for waiver in result.expired_exemptions
    ]


@check(
    id=_COMPLETENESS,
    title="every public callable is accounted for in a ratified surface map",
    stage=Stage.FAST,
    tier1=True,
    falsified_by="tests/negative/test_surface_gate.py::test_uncovered_callable_is_red",
)
def check_surface_completeness(ctx: Context) -> CheckResult:
    """The gate the whole obligation engine rests on.

    Every Tier 1 gate keys on role, so a role means nothing unless the map is
    complete. This compares the AST inventory (ground truth from source bytes)
    against the map (the human's claims) and reddens on drift in either
    direction.
    """
    smap = require_surface_map(ctx, _COMPLETENESS)
    if isinstance(smap, CheckResult):
        return smap

    inv = get_inventory(ctx)
    result = audit(inv, smap)

    # Config mismatch, not 149 real gaps. A surface map with rows that match
    # *nothing* in the inventory means the map and the source tree are talking
    # about different modules — almost always a wrong `source` prefix (e.g. the
    # map was written for `src/press` but `source` defaults to `src`). Reporting
    # "0/631 accounted" with a wall of uncovered findings buries the actual
    # cause, so fail loud with the real one.
    if smap.rows and result.covered() == 0 and result.total_callables > 0:
        return CheckResult.refused(
            _COMPLETENESS,
            f"the surface map matches none of the {result.total_callables} callables found",
            reason=(
                f"the map has {len(smap.rows)} row(s) but not one corresponds to a module "
                f"under source={ctx.config.source!r}. The map and the inventory describe "
                "different modules — check that `source` (and any `[tool.celebrimbor.paths]`) "
                "point at the tree the map was written for."
            ),
            remedy=f"set `source` in celebrimbor.toml; the map's modules look like: "
            f"{', '.join(sorted(smap.modules())[:3])}…",
        )

    # Unparseable source is a refusal, not a failure. We do not know what is in
    # those modules, and reporting them as "missing a row" would understate it.
    if result.must_refuse:
        detail = "; ".join(f"{m.path}: {m.parse_error}" for m in result.unparseable[:5])
        return CheckResult.refused(
            _COMPLETENESS,
            f"{len(result.unparseable)} module(s) could not be parsed",
            reason=(
                "the surface inventory is AST-only so a module that fails to parse "
                f"cannot silently drop out of the completeness count: {detail}"
            ),
        )

    findings = [
        *_uncovered_findings(result, inv),
        *_unratified_findings(result),
        *_stale_findings(result),
        *_expired_findings(result),
    ]

    if findings:
        return CheckResult.failed(
            _COMPLETENESS,
            f"{result.covered()}/{result.total_callables} callables accounted for; "
            f"{len(findings)} gap(s)",
            findings,
        )
    return CheckResult.passed(
        _COMPLETENESS,
        f"{result.total_callables} public callable(s) across {result.total_modules} "
        "module(s), all ratified",
    )


@check(
    id=_NAMING,
    title="no callable's name promises more proof than its role demands",
    stage=Stage.FAST,
    tier1=True,
    falsified_by="tests/negative/test_surface_gate.py::test_naming_conflict_is_red",
)
def check_naming_conflict(ctx: Context) -> CheckResult:
    """The drift detector that keeps a ratified row from going stale.

    Add ``fetch_remote()`` to a module ratified as ``pure`` and its name
    decodes to ``adapter`` — rank 5 against rank 1. Without this gate the new
    callable would silently inherit a judgment nobody made about it. The
    conflict is only reported in the dangerous direction: a name suggesting
    *less* proof than the role demands is harmless, since the role still wins.
    """
    smap = require_surface_map(ctx, _NAMING)
    if isinstance(smap, CheckResult):
        return smap

    inv = get_inventory(ctx)
    found = naming.conflicts(inv, smap)

    if found:
        return CheckResult.failed(
            _NAMING,
            f"{len(found)} callable(s) named for a role stronger than the one assigned",
            [
                Finding(
                    message=conflict.message,
                    path=conflict.info.path,
                    line=conflict.info.lineno,
                    code="naming-conflict",
                    hint=conflict.remedy,
                )
                for conflict in found
            ],
        )

    decodable, total = naming.decodability(inv, smap)
    return CheckResult.passed(
        _NAMING, f"no naming conflicts; {decodable}/{total} callable(s) decode to a role"
    )
