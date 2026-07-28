"""The invariant ledger: promises the system makes, and their enforcers.

An invariant is a claim the application makes about itself — "every order has a
customer", "prices are never negative", "a published post has a slug". The
ledger records each one *with the callable that enforces it* and, for the
critical ones, *the negative proof that the enforcer actually bites*.

The ledger is validated for referential integrity, not merely parsed: every
named enforcer must resolve to a real callable, and every invariant marked
``critical`` must keep a real negative proof. It renders to human docs, and it
fails on drift — an enforcer that has been renamed or deleted turns the gate
red, because a promise whose enforcer is gone is a promise nobody is keeping.

This is the same discipline as the producer ledger, one level more general: a
producer ledger is an invariant ledger specialised to "the artifact is
correct". Here the promise can be anything the application cares to name.

Shape of ``.celebrimbor/invariants.yaml``::

    version: 1
    invariants:
      order-has-customer:
        statement: every order references an existing customer
        enforced_by: myapp.orders:validate_order
        critical: true
        negative_proof: tests/negative/test_orders.py::test_orphan_order_rejected
      slug-is-unique:
        statement: no two posts share a slug
        enforced_by: myapp.posts:check_slug_unique
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..yamlio import YamlError, expect_mapping, load_mapping

LEDGER_VERSION = 1


class InvariantLedgerError(YamlError):
    """The invariant ledger is unusable. Red — a broken ledger checks nothing."""


@dataclass(frozen=True, slots=True)
class Invariant:
    """One promise the system makes about itself."""

    name: str
    statement: str
    enforced_by: str
    """The callable that enforces this invariant, as ``module:callable``."""

    critical: bool = False
    """Critical invariants must keep a real negative proof. The failure of a
    critical invariant is the kind of thing that corrupts data or leaks it, so
    "we believe it holds" is not enough — something must have watched it fail."""

    negative_proofs: tuple[str, ...] = ()
    """Tests proving the enforcer rejects a violation — one or more. An invariant
    can be independently falsified several ways, and each is a real proof the gate
    resolves. At least one is required when ``critical``; each named one must
    exist, because a named-but-deleted proof is drift."""

    limitations: tuple[str, ...] = ()
    """The cases this promise knowingly does *not* cover, as ids/slugs. Declared,
    reviewable debt — and, with ``markers_cite_limitations``, the vocabulary an
    ``xfail``/``skip`` must cite so a "known gap" cannot be confused with a shrug."""

    @property
    def enforcer_module(self) -> str:
        return self.enforced_by.split(":", 1)[0]

    @property
    def enforcer_callable(self) -> str | None:
        _, sep, qualname = self.enforced_by.partition(":")
        return qualname if sep else None

    @property
    def proof_paths(self) -> tuple[str, ...]:
        """The file part of each negative proof, for the on-disk existence check."""
        return tuple(p.split("::", 1)[0].strip() for p in self.negative_proofs)


@dataclass(frozen=True, slots=True)
class InvariantLedger:
    """A parsed invariant ledger."""

    path: Path
    invariants: dict[str, Invariant] = field(default_factory=dict)
    version: int = LEDGER_VERSION

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.invariants.values())

    def critical(self) -> list[Invariant]:
        return [inv for inv in self.invariants.values() if inv.critical]

    def enforcer_modules(self) -> set[str]:
        return {inv.enforcer_module for inv in self.invariants.values()}

    def limitation_ids(self) -> set[str]:
        """Every declared limitation, across all invariants — the citable catalog."""
        return {lim for inv in self.invariants.values() for lim in inv.limitations}


def load_invariants(path: Path) -> InvariantLedger:
    """Parse an invariant ledger. Raises on any defect rather than defaulting."""
    data = load_mapping(path, what="invariant ledger")

    version = data.get("version", LEDGER_VERSION)
    if not isinstance(version, int) or version > LEDGER_VERSION:
        raise InvariantLedgerError(
            f"{path}: invariant ledger version {version!r} is not supported (max {LEDGER_VERSION})"
        )

    raw = data.get("invariants")
    if raw is None:
        raise InvariantLedgerError(f"{path}: invariant ledger has no `invariants:` section")

    invariants: dict[str, Invariant] = {}
    for name, body in expect_mapping(raw, where=f"{path}: invariants").items():
        invariants[str(name)] = _parse_invariant(path, str(name), body)

    return InvariantLedger(path=path, invariants=invariants, version=int(version))


def _as_str_tuple(path: Path, where: str, value: object) -> tuple[str, ...]:
    """A string, a list of strings, or nothing, normalized to a tuple."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise InvariantLedgerError(f"{path}: {where} must be a string or a list of strings")


def _parse_invariant(path: Path, name: str, body: object) -> Invariant:
    entry = expect_mapping(body, where=f"{path}: invariants.{name}")
    missing = {"statement", "enforced_by"} - set(entry)
    if missing:
        raise InvariantLedgerError(
            f"{path}: invariants.{name} is missing {', '.join(sorted(missing))}. "
            "An invariant owes a statement and the callable that enforces it."
        )

    critical = bool(entry.get("critical", False))
    negative_proofs = _as_str_tuple(
        path, f"invariants.{name}.negative_proof", entry.get("negative_proof")
    )
    if critical and not negative_proofs:
        raise InvariantLedgerError(
            f"{path}: invariants.{name} is `critical` but names no `negative_proof`. "
            "A critical promise must keep a real proof that its enforcer bites — "
            "otherwise 'critical' is a label, not a guarantee."
        )

    return Invariant(
        name=name,
        statement=str(entry["statement"]).strip(),
        enforced_by=str(entry["enforced_by"]).strip(),
        critical=critical,
        negative_proofs=negative_proofs,
        limitations=_as_str_tuple(path, f"invariants.{name}.limitations", entry.get("limitations")),
    )


def render_docs(ledger: InvariantLedger) -> str:
    """The ledger as human-readable markdown.

    "It renders human docs" is a build-contract requirement, and it earns its
    place: an invariant ledger nobody reads is a config file, but an invariant
    ledger that renders the system's promises is documentation that cannot lie,
    because the gate has already checked every line of it against the code.
    """
    lines = ["# System invariants", ""]
    for inv in sorted(ledger.invariants.values(), key=lambda i: i.name):
        mark = " **(critical)**" if inv.critical else ""
        lines.append(f"## {inv.name}{mark}")
        lines.append("")
        lines.append(inv.statement)
        lines.append("")
        lines.append(f"- enforced by `{inv.enforced_by}`")
        for proof in inv.negative_proofs:
            lines.append(f"- proven by `{proof}`")
        for limitation in inv.limitations:
            lines.append(f"- does not cover: {limitation}")
        lines.append("")
    return "\n".join(lines)
