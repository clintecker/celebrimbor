"""The no-blind-verifier producer ledger.

The rule, stated once: **you cannot inherit a verifier that inspects nothing.**
A ``producer`` makes an artifact, and the only thing that makes an artifact
trustworthy is a verifier that would go red if the artifact were wrong. So
every producer must name, on the record:

* the ``verifier`` that inspects its artifact, and
* a ``negative_fixture`` — a test that feeds that verifier a bad artifact and
  proves it turns red.

The second half is the part that is usually missing and always the point. A
verifier nobody has watched reject anything is a verifier that might reject
nothing, and a producer proved by such a verifier is proved by nothing. The
negative fixture is the verifier's own falsifier, the same idea the check
registry applies to itself, pushed down to the application's artifacts.

A producer that does not yet have this can sit in ``pending`` — but visibly,
with a reason and a review date, on an allowlist that expires. Debt with a
deadline, never debt in silence.

Shape of ``.celebrimbor/producers.yaml``::

    version: 1
    producers:
      myapp.render:                          # a producer (module or module:callable)
        verifier: myapp.verify:verify_summary
        negative_fixture: tests/negative/test_render.py::test_empty_summary_caught
    pending:
      myapp.export:
        reason: verifier not written yet
        review_by: 2026-09-01

**Override granularity is load-bearing.** The producers the gate demands
entries for come from :meth:`SurfaceMap.effective_roles`, which is module
default *plus* per-callable overrides — so a ``producer`` introduced by a
single override on an otherwise ``pure`` module is caught, not just a module
whose default is ``producer``. That was a scar; missing it means the cheapest
way to ship an unchecked artifact is a one-line override.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..waiver import Pending, WaiverError
from ..yamlio import YamlError, expect_mapping, load_mapping

LEDGER_VERSION = 1


class ProducerLedgerError(YamlError):
    """The producer ledger is unusable. Red — a broken ledger checks nothing."""


@dataclass(frozen=True, slots=True)
class ProducerRecord:
    """One producer's on-the-record proof-through-verifier."""

    subject: str
    """The producer, as ``module`` or ``module:callable``."""

    verifier: str
    """The verifier that inspects this producer's artifact, as ``module:callable``."""

    negative_fixture: str
    """A test that feeds the verifier a bad artifact and proves it turns red."""

    @property
    def fixture_path(self) -> str:
        return self.negative_fixture.split("::", 1)[0].strip()

    @property
    def fixture_node(self) -> str | None:
        _, sep, node = self.negative_fixture.partition("::")
        return node.strip() if sep else None


@dataclass(frozen=True, slots=True)
class ProducerLedger:
    """A parsed producer ledger."""

    path: Path
    records: dict[str, ProducerRecord] = field(default_factory=dict)
    pending: dict[str, Pending] = field(default_factory=dict)
    version: int = LEDGER_VERSION

    def subjects(self) -> set[str]:
        return set(self.records) | set(self.pending)

    def covers(self, subject: str) -> bool:
        return subject in self.records or subject in self.pending

    def expired_pending(self) -> list[Pending]:
        return [p for p in self.pending.values() if p.expired()]


def load_producers(path: Path) -> ProducerLedger:
    """Parse a producer ledger. Raises on any defect rather than defaulting."""
    data = load_mapping(path, what="producer ledger")

    version = data.get("version", LEDGER_VERSION)
    if not isinstance(version, int) or version > LEDGER_VERSION:
        raise ProducerLedgerError(
            f"{path}: producer ledger version {version!r} is not supported (max {LEDGER_VERSION})"
        )

    records = _parse_records(path, data.get("producers") or {})
    pending = _parse_pending(path, data.get("pending") or {})

    overlap = set(records) & set(pending)
    if overlap:
        raise ProducerLedgerError(
            f"{path}: {', '.join(sorted(overlap))} appear(s) in both `producers` and "
            "`pending`. A producer is either proved or admitted-pending, not both."
        )

    return ProducerLedger(path=path, records=records, pending=pending, version=int(version))


def _parse_records(path: Path, raw: object) -> dict[str, ProducerRecord]:
    mapping = expect_mapping(raw, where=f"{path}: producers")
    records: dict[str, ProducerRecord] = {}
    for subject, body in mapping.items():
        entry = expect_mapping(body, where=f"{path}: producers.{subject}")
        missing = {"verifier", "negative_fixture"} - set(entry)
        if missing:
            raise ProducerLedgerError(
                f"{path}: producers.{subject} is missing {', '.join(sorted(missing))}. "
                "A producer owes both the verifier that inspects it and a negative "
                "fixture proving that verifier bites."
            )
        records[str(subject)] = ProducerRecord(
            subject=str(subject),
            verifier=str(entry["verifier"]).strip(),
            negative_fixture=str(entry["negative_fixture"]).strip(),
        )
    return records


def _parse_pending(path: Path, raw: object) -> dict[str, Pending]:
    mapping = expect_mapping(raw, where=f"{path}: pending")
    pending: dict[str, Pending] = {}
    for subject, body in mapping.items():
        try:
            pending[str(subject)] = Pending.from_dict(body, subject=str(subject))
        except WaiverError as exc:
            raise ProducerLedgerError(f"{path}: pending.{subject}: {exc}") from exc
    return pending
