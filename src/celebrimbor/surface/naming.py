"""Making abstention a bug in the application, not a state of the harness.

Inference abstains when a name carries no role signal. Rather than accept that
as permanent, this module pushes the codebase toward being decodable — but it
has to do so without demanding a per-callable row for every unconventional
name, because "never one row per function" is a hard constraint on the surface
map's readability.

So the forcing function splits in two, by strength:

**Conflict** (:func:`conflicts`) — a callable whose name decodes to a role
*strictly safer* than the one the map assigns it. This is almost always a real
mis-assignment, and it is in the dangerous direction: the map is demanding
less proof than the name suggests is owed. Always red, no allowlist. The
escape is an explicit per-callable override, which is a human saying "I know
how it reads, and it is genuinely this."

This is also the drift detector, and it is the reason a ratified module row
does not go stale. Add ``fetch_remote()`` to a module ratified as ``pure`` and
the name decodes to ``adapter`` — rank 5 against rank 1 — so the gate reddens
on the next run rather than silently extending a ratified judgment to code
nobody ratified.

**Coverage** (:func:`undecodable`) — callables whose names decode to nothing at
all. Their role rests entirely on a module default that no per-callable signal
corroborates. Demanding an override for each would be the one-row-per-function
failure, so this is reported as a *count* and ratcheted: it may only fall.
The codebase converges on decodability over time instead of hitting a wall on
day one.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..roles import Role
from .inference import propose_for_callable
from .inventory import CallableInfo, Inventory
from .map import SurfaceMap


@dataclass(frozen=True, slots=True)
class NamingConflict:
    """A name that promises more than the map demands."""

    info: CallableInfo
    assigned: Role
    decoded: Role
    reasons: tuple[str, ...]

    @property
    def message(self) -> str:
        return (
            f"{self.info.key} is assigned `{self.assigned.value}` "
            f"(owes: {self.assigned.obligation.owes}) but its name decodes to "
            f"`{self.decoded.value}` (owes: {self.decoded.obligation.owes}). "
            f"The map demands less proof than the name suggests is owed."
        )

    @property
    def remedy(self) -> str:
        return (
            f"Either change the module role, or — if {self.info.name!r} really is "
            f"{self.assigned.value} — record that as one line under "
            f"`modules.{self.info.module}.overrides`:\n"
            f"      {self.info.qualname}: {self.assigned.value}"
        )


def conflicts(inv: Inventory, smap: SurfaceMap) -> list[NamingConflict]:
    """Callables whose names decode to a strictly safer role than assigned.

    Explicit overrides and exemptions are skipped: both are a human having
    already made this exact judgment, and re-litigating it every run would
    make the gate impossible to ever satisfy.
    """
    found: list[NamingConflict] = []
    for info in inv.callables():
        resolution = smap.resolve(info.module, info.qualname)
        if resolution.via in {"override", "exempt", "absent"}:
            continue
        assigned = resolution.role
        if assigned is None:
            continue
        proposal = propose_for_callable(info)
        decoded = proposal.role
        if decoded is None or decoded is assigned:
            continue
        if decoded.rank > assigned.rank:
            found.append(
                NamingConflict(
                    info=info,
                    assigned=assigned,
                    decoded=decoded,
                    reasons=proposal.reasons,
                )
            )
    return found


def undecodable(inv: Inventory, smap: SurfaceMap | None = None) -> list[CallableInfo]:
    """Public callables whose names carry no role signal at all.

    An explicit override or exemption counts as decoded — the signal is simply
    written down rather than encoded in the name, which is exactly as good.
    """
    found: list[CallableInfo] = []
    for info in inv.callables():
        if smap is not None:
            resolution = smap.resolve(info.module, info.qualname)
            if resolution.via in {"override", "exempt"}:
                continue
        if propose_for_callable(info).role is None:
            found.append(info)
    return found


def decodability(inv: Inventory, smap: SurfaceMap | None = None) -> tuple[int, int]:
    """``(decodable, total)`` public callables. The ratcheted measure."""
    total = sum(1 for _ in inv.callables())
    return total - len(undecodable(inv, smap)), total


def suggest_name(info: CallableInfo, role: Role) -> str:
    """A conventional name for ``info`` under ``role``, for gate output.

    Advisory only, and never applied. Renaming a public callable is a breaking
    change to somebody, so the harness proposes and a human disposes — and the
    one-line override is always the cheaper correct answer when the existing
    name is the right one.
    """
    prefixes = {
        Role.VERIFIER: "verify_",
        Role.PARSER: "parse_",
        Role.PRODUCER: "build_",
        Role.NORMALIZER: "normalize_",
        Role.ADAPTER: "fetch_",
        Role.ORCHESTRATOR: "run_",
    }
    prefix = prefixes.get(role)
    if prefix is None or info.name.startswith(prefix):
        return info.name
    return f"{prefix}{info.name}"
