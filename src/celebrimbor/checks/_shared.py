"""Loaders shared across check modules, memoized on the context.

The AST walk is the dominant cost of the fast tier, and five gates want the
same inventory. Every expensive artifact a check needs is produced through
this module so it is computed exactly once per run.

Each loader also fixes the *failure posture* for its artifact in one place. A
missing Tier 1 ledger is a skip (the adopter has not opted in); a present but
malformed one is a refusal (they opted in and we cannot read their intent).
Deciding that per-check would eventually get it backwards somewhere.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass

from ..context import Context
from ..result import CheckResult
from ..roles import Role
from ..surface.inventory import CallableInfo, Inventory, ModuleInfo, callable_nodes, inventory
from ..surface.map import SurfaceMap, load_map
from ..yamlio import YamlError


@dataclass(frozen=True, slots=True)
class LedgerState:
    """The outcome of trying to load an opt-in ledger.

    Exactly one of ``value`` / ``skip_reason`` / ``error`` is set. Modelling
    the three outcomes explicitly keeps a check from conflating "absent" with
    "broken" — the first is a legitimate pass-through and the second must be
    red.
    """

    value: object | None = None
    skip_reason: str | None = None
    error: str | None = None

    @property
    def present(self) -> bool:
        return self.value is not None


def get_inventory(ctx: Context) -> Inventory:
    """The AST inventory of the configured source tree."""
    return ctx.memo("surface.inventory", lambda: inventory(ctx.config))


def get_surface_map(ctx: Context) -> LedgerState:
    """The surface map, or why there isn't one."""

    def load() -> LedgerState:
        path = ctx.config.surfaces_path
        if not path.exists():
            return LedgerState(
                skip_reason=(
                    "no surface map: Tier 1 is opt-in. Run `celebrimbor init --surfaces` "
                    "to generate a pre-filled, ratify-me map."
                )
            )
        try:
            return LedgerState(value=load_map(path))
        except YamlError as exc:
            return LedgerState(error=str(exc))

    return ctx.memo("surface.map", load)


def surface_map_or_none(ctx: Context) -> SurfaceMap | None:
    state = get_surface_map(ctx)
    return state.value if isinstance(state.value, SurfaceMap) else None


@dataclass(frozen=True, slots=True)
class RatifiedCallable:
    """One callable whose role a human has actually confirmed.

    Bundled because every role-keyed gate needs the same four things together,
    and because assembling them involves a nested walk that scored badly on the
    complexity gate in each of the three checks that had grown its own copy.
    """

    module: ModuleInfo
    info: CallableInfo
    node: ast.FunctionDef | ast.AsyncFunctionDef
    role: Role


def require_surface_map(ctx: Context, check_id: str) -> SurfaceMap | CheckResult:
    """The surface map, or the verdict explaining why this check cannot run.

    Every Tier 1 gate opens with the same three-way decision — absent means
    skip, malformed means refuse, present means proceed — and each copy of it
    was a chance to get the skip/refuse polarity backwards in one place only.
    The union return makes the non-map branches impossible to forget: there is
    no map to carry on with.
    """
    state = get_surface_map(ctx)
    if state.error:
        return CheckResult.refused(
            check_id,
            "the surface map could not be read",
            reason=state.error,
            remedy="fix the map; an unreadable ledger cannot be checked, so it is red",
        )
    if state.skip_reason:
        return CheckResult.skipped(check_id, state.skip_reason)
    if not isinstance(state.value, SurfaceMap):
        return CheckResult.refused(
            check_id,
            "the surface map loaded to an unexpected shape",
            reason=f"expected a SurfaceMap, got {type(state.value).__name__}",
        )
    return state.value


def iter_ratified(ctx: Context, smap: SurfaceMap) -> Iterator[RatifiedCallable]:
    """Every callable whose role is ratified, with its AST node and role.

    Un-ratified and absent rows are skipped rather than judged. The
    completeness gate is already red for them, and a row nobody has confirmed
    has no authority to permit or forbid anything — judging against it would
    double-report the same gap under a second check's name.
    """
    for module in ctx.memo("surface.inventory", lambda: inventory(ctx.config)).modules:
        if module.tree is None:
            continue
        nodes = callable_nodes(module.tree)
        for info in module.callables:
            node = nodes.get(info.qualname)
            resolution = smap.resolve(info.module, info.qualname)
            if node is None or resolution.role is None or resolution.blocks_gate:
                continue
            yield RatifiedCallable(module=module, info=info, node=node, role=resolution.role)
