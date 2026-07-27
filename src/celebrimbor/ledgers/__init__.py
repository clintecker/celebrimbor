"""Declarative ledgers: the producer ledger and the invariant ledger.

Both share a shape and a discipline. Each is a YAML file a human authors, each
is validated for *referential integrity* against the code rather than merely
parsed, and each fails on drift between what it claims and what exists. A
ledger that can fall out of step with the code without anyone noticing is a
ledger that documents a system nobody has anymore.
"""

from __future__ import annotations

from .invariants import Invariant, InvariantLedger, load_invariants
from .producers import ProducerLedger, ProducerRecord, load_producers

__all__ = [
    "Invariant",
    "InvariantLedger",
    "ProducerLedger",
    "ProducerRecord",
    "load_invariants",
    "load_producers",
]
