"""The completeness audit: does the map account for every public callable?

This is the gate the whole obligation engine rests on. Every Tier 1 gate keys
on role, and a role only means something if the map is *complete* — if a
public callable can exist that the map does not mention, then "this module is
a producer, so it owes X" says nothing about the callables that slipped past.

The audit therefore compares two independently-derived sets: the AST inventory
(ground truth, from source bytes) and the surface map (the human's claims). It
reports drift in both directions. A map row for a module that no longer exists
is as much a defect as a module with no row — the first means the ledger is
describing code that is gone, and a ledger nobody notices has rotted is a
ledger nobody trusts.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..waiver import Exemption
from .inventory import CallableInfo, Inventory, ModuleInfo
from .map import SurfaceMap, SurfaceRow


@dataclass(frozen=True, slots=True)
class SurfaceAudit:
    """Everything wrong with a surface map, in one pass."""

    unparseable: tuple[ModuleInfo, ...] = ()
    """Modules the AST could not read. Refusal, not failure — we do not know
    what is in them, and reporting them as merely 'missing a row' would
    understate that."""

    uncovered: tuple[CallableInfo, ...] = ()
    """Public callables no map row accounts for. The completeness hole."""

    unratified: tuple[SurfaceRow, ...] = ()
    """Rows still marked `inferred`. Red until a human confirms."""

    expired_exemptions: tuple[Exemption, ...] = ()
    """Waivers past their review date. The shrinking-allowlist property."""

    stale_rows: tuple[str, ...] = ()
    """Rows for modules the inventory no longer contains. Drift."""

    total_callables: int = 0
    total_modules: int = 0

    @property
    def clean(self) -> bool:
        return not (
            self.unparseable
            or self.uncovered
            or self.unratified
            or self.expired_exemptions
            or self.stale_rows
        )

    @property
    def must_refuse(self) -> bool:
        """Unparseable source means the audit cannot conclude, only refuse."""
        return bool(self.unparseable)

    def covered(self) -> int:
        return self.total_callables - len(self.uncovered)


def audit(inv: Inventory, smap: SurfaceMap) -> SurfaceAudit:
    """Compare the AST inventory against the surface map."""
    uncovered = [
        info
        for info in inv.callables()
        if smap.resolve(info.module, info.qualname).blocks_gate
        and smap.resolve(info.module, info.qualname).via == "absent"
    ]

    known_modules = inv.module_names()
    stale = tuple(sorted(m for m in smap.modules() if m not in known_modules))

    return SurfaceAudit(
        unparseable=inv.unparseable,
        uncovered=tuple(uncovered),
        unratified=tuple(sorted(smap.unratified(), key=lambda r: r.module)),
        expired_exemptions=tuple(smap.expired_exemptions()),
        stale_rows=stale,
        total_callables=sum(1 for _ in inv.callables()),
        total_modules=len(inv.modules),
    )


def missing_row_snippet(inv: Inventory, module: str) -> str:
    """The exact YAML to paste for an uncovered module.

    Gate output that says "add a row" and gate output that says "add *this*
    row" are different products. The second is the difference between a
    one-line confirm and an authoring task, which is the promise the
    convention makes.
    """
    info = inv.by_module(module)
    count = len(info.callables) if info else 0
    names = ", ".join(c.qualname for c in (info.callables if info else ())[:4])
    trailer = ", …" if info and len(info.callables) > 4 else ""
    return (
        f"  {module}:                    # {count} public callable(s): {names}{trailer}\n"
        f"    role: <choose one>\n"
        f"    status: ratified"
    )
