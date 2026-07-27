"""The no-blind-verifier gate.

Every ``producer`` must name, on the record, the verifier that inspects its
artifact and a negative fixture proving that verifier turns red. This gate
enforces that, with referential integrity against the code: the named verifier
has to resolve to a real callable that the surface map classifies as a
verifier, and the negative fixture has to exist.

The producers it demands entries for come from
:meth:`SurfaceMap.effective_roles` — module default plus per-callable
overrides — so a ``producer`` introduced by a single override on a ``pure``
module is caught, not only a module whose default is ``producer``.
"""

from __future__ import annotations

from pathlib import Path

from ..context import Context
from ..ledgers.producers import ProducerLedger, ProducerRecord, load_producers
from ..registry import check
from ..result import CheckResult, Finding, Tier
from ..roles import Role
from ..surface.inventory import Inventory
from ..surface.map import SurfaceMap
from ..yamlio import YamlError
from ._shared import get_inventory, require_surface_map

_ID = "celebrimbor.producers"


def _producer_subjects(smap: SurfaceMap) -> dict[str, str]:
    """Every producer, keyed by subject, valued by a human-readable origin.

    A module-default producer keys as ``module``; an override-introduced one
    keys as ``module:callable``. The value explains which, for gate output.
    """
    subjects: dict[str, str] = {}
    for module, row in smap.rows.items():
        if row.role is Role.PRODUCER:
            subjects[module] = "module default"
        for name, (role, _status) in row.overrides.items():
            if role is Role.PRODUCER:
                subjects[f"{module}:{name}"] = "per-callable override"
    return subjects


def _resolves_to_callable(inv: Inventory, module: str, qualname: str) -> bool:
    info = inv.by_module(module)
    return info is not None and any(c.qualname == qualname for c in info.callables)


def _verifier_finding(record: ProducerRecord, smap: SurfaceMap, inv: Inventory) -> Finding | None:
    """The one thing wrong with this record's named verifier, if any."""
    module, sep, qualname = record.verifier.partition(":")
    if not sep or not qualname:
        return Finding(
            message=(
                f"producer {record.subject!r} names verifier {record.verifier!r}, which is "
                "not in `module:callable` form"
            ),
            code="producer-verifier-malformed",
        )
    if not _resolves_to_callable(inv, module, qualname):
        return Finding(
            message=(
                f"producer {record.subject!r} names verifier {record.verifier!r}, which does "
                "not resolve to a real callable"
            ),
            code="producer-verifier-absent",
            hint="the verifier that inspects an artifact must actually exist",
        )
    role = smap.resolve(module, qualname).role
    if role is not Role.VERIFIER:
        actual = role.value if role else "unclassified"
        return Finding(
            message=(
                f"producer {record.subject!r} names {record.verifier!r} as its verifier, but "
                f"that callable is classified `{actual}`, not `verifier`"
            ),
            code="producer-verifier-miscast",
            hint="a producer is only as trustworthy as a real verifier inspecting it",
        )
    return None


def _fixture_finding(record: ProducerRecord, root: Path) -> Finding | None:
    if (root / record.fixture_path).exists():
        return None
    return Finding(
        message=(
            f"producer {record.subject!r} names negative fixture {record.negative_fixture!r}, "
            "which does not exist"
        ),
        path=Path(record.fixture_path),
        code="producer-fixture-absent",
        hint="the negative fixture is the verifier's own falsifier; it must exist",
    )


def _verifier_findings(
    record: ProducerRecord, smap: SurfaceMap, inv: Inventory, root: Path
) -> list[Finding]:
    """Referential-integrity checks for one ledger record."""
    candidates = (_verifier_finding(record, smap, inv), _fixture_finding(record, root))
    return [f for f in candidates if f is not None]


@check(
    id=_ID,
    title="every producer is proved through a verifier that is proven to bite",
    tier=Tier.DEFAULT,
    tier1=True,
    falsified_by="tests/negative/test_producer_gate.py::test_producer_without_ledger_entry_is_red",
)
def check_producers(ctx: Context) -> CheckResult:
    """The no-blind-verifier gate. You cannot inherit a verifier that inspects
    nothing."""
    smap = require_surface_map(ctx, _ID)
    if isinstance(smap, CheckResult):
        return smap

    subjects = _producer_subjects(smap)
    ledger = _load_ledger(ctx)
    if isinstance(ledger, CheckResult):
        return ledger

    if not subjects and ledger is None:
        return CheckResult.passed(_ID, "no producers declared; nothing to prove")

    if ledger is None:
        return CheckResult.failed(
            _ID,
            f"{len(subjects)} producer(s) declared but no producer ledger exists",
            [
                Finding(
                    message=f"producer {subject!r} ({origin}) has no ledger entry",
                    code="producer-uncovered",
                    hint="create .celebrimbor/producers.yaml naming its verifier and negative fixture",
                )
                for subject, origin in sorted(subjects.items())
            ],
        )

    inv = get_inventory(ctx)
    findings = _audit(subjects, ledger, smap, inv, ctx.root)

    if findings:
        return CheckResult.failed(_ID, f"{len(findings)} no-blind-verifier defect(s)", findings)
    proved = len(ledger.records)
    pending = len(ledger.pending)
    detail = f"{proved} producer(s) proved through a verifier"
    if pending:
        detail += f", {pending} on a dated pending list"
    return CheckResult.passed(_ID, detail)


def _load_ledger(ctx: Context) -> ProducerLedger | CheckResult | None:
    path = ctx.config.producers_path
    if not path.exists():
        return None
    try:
        return load_producers(path)
    except YamlError as exc:
        return CheckResult.refused(_ID, "the producer ledger could not be read", reason=str(exc))


def _audit(
    subjects: dict[str, str],
    ledger: ProducerLedger,
    smap: SurfaceMap,
    inv: Inventory,
    root: Path,
) -> list[Finding]:
    findings: list[Finding] = []

    for subject, origin in sorted(subjects.items()):
        if not ledger.covers(subject):
            findings.append(
                Finding(
                    message=f"producer {subject!r} ({origin}) has no ledger entry",
                    code="producer-uncovered",
                    hint="name its verifier and a negative fixture, or add it to `pending` with a date",
                )
            )

    for record in ledger.records.values():
        findings.extend(_verifier_findings(record, smap, inv, root))

    # Stale entries: the ledger describes a producer that no longer exists.
    for subject in ledger.subjects() - set(subjects):
        findings.append(
            Finding(
                message=(
                    f"producer ledger names {subject!r}, which is no longer classified as a "
                    "producer in the surface map"
                ),
                code="producer-stale",
                hint="delete the entry; a ledger describing a role that is gone is drift",
            )
        )

    for waiver in ledger.expired_pending():
        findings.append(
            Finding(
                message=(
                    f"pending producer {waiver.subject!r} passed its review date "
                    f"({waiver.review_by.isoformat()}): {waiver.reason}"
                ),
                code="producer-pending-expired",
                hint="write the verifier and its negative fixture, or re-justify with a new date",
            )
        )
    return findings
