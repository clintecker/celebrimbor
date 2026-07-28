"""The invariant-ledger gate: referential integrity and no-drift.

Every named enforcer must resolve to a real callable, and every critical
invariant must keep a real negative proof. A promise whose enforcer has been
renamed or deleted turns this red — because a promise nobody enforces is not a
promise, and a ledger that quietly describes one is worse than no ledger.
"""

from __future__ import annotations

from pathlib import Path

from ..context import Context
from ..ledgers.invariants import Invariant, load_invariants
from ..registry import Family, check
from ..result import CheckResult, Finding, Stage
from ..surface.inventory import Inventory
from ..yamlio import YamlError
from ._shared import get_inventory

_ID = "celebrimbor.invariants"


def _enforcer_finding(inv: Invariant, inventory: Inventory) -> Finding | None:
    """Does this invariant's enforcer resolve to a real callable?"""
    module = inv.enforcer_module
    qualname = inv.enforcer_callable
    if qualname is None:
        return Finding(
            message=(
                f"invariant {inv.name!r} names enforcer {inv.enforced_by!r}, which is not in "
                "`module:callable` form"
            ),
            code="invariant-enforcer-malformed",
        )
    info = inventory.by_module(module)
    if info is None or not any(c.qualname == qualname for c in info.callables):
        return Finding(
            message=(
                f"invariant {inv.name!r} is enforced_by {inv.enforced_by!r}, which does not "
                "resolve to a real callable"
            ),
            code="invariant-enforcer-absent",
            hint="the enforcer has been renamed or deleted; the promise is now unenforced",
        )
    return None


def _proof_finding(inv: Invariant, root: Path) -> Finding | None:
    """Does a critical invariant's negative proof exist on disk?"""
    if inv.proof_path is None or (root / inv.proof_path).exists():
        return None
    return Finding(
        message=(
            f"invariant {inv.name!r} names negative proof {inv.negative_proof!r}, which does "
            "not exist"
        ),
        path=Path(inv.proof_path),
        code="invariant-proof-absent",
        hint="a critical promise must keep a real proof its enforcer rejects a violation",
    )


@check(
    id=_ID,
    title="every named invariant enforcer resolves, and critical ones keep a proof",
    stage=Stage.DEFAULT,
    family=Family.OBLIGATION,
    falsified_by="tests/negative/test_invariant_gate.py::test_missing_enforcer_is_red",
)
def check_invariants(ctx: Context) -> CheckResult:
    """Validate the invariant ledger against the code it describes."""
    path = ctx.config.invariants_path
    if not path.exists():
        return CheckResult.skipped(
            _ID,
            "no invariant ledger: this is opt-in. Create .celebrimbor/invariants.yaml to "
            "record the promises your system makes and have them checked against the code.",
        )
    try:
        ledger = load_invariants(path)
    except YamlError as exc:
        return CheckResult.refused(_ID, "the invariant ledger could not be read", reason=str(exc))

    if not ledger.invariants:
        return CheckResult.refused(
            _ID,
            "the invariant ledger is empty",
            reason="an empty ledger checks nothing, which is not the same as having nothing "
            "to check; delete the file to opt out instead",
        )

    inventory = get_inventory(ctx)
    findings: list[Finding] = []
    for inv in ledger:
        candidates = (_enforcer_finding(inv, inventory), _proof_finding(inv, ctx.root))
        findings.extend(f for f in candidates if f is not None)

    if findings:
        return CheckResult.failed(_ID, f"{len(findings)} invariant-ledger defect(s)", findings)

    critical = len(ledger.critical())
    return CheckResult.passed(
        _ID,
        f"{len(ledger.invariants)} invariant(s) enforced by real callables "
        f"({critical} critical, each with a negative proof)",
    )
