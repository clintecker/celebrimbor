"""Gates that stop a declared role from being merely asserted.

Two failure modes, two gates.

``celebrimbor.surface.evidence`` answers *can this callable be what it says it
is?* — the code has to be consistent with the role's necessary conditions. It
closes the escapes where a role is declared to obtain something (an
``adapter``'s open capability budget) rather than to describe something.

``celebrimbor.surface.pin`` answers *is this ratification still about this
code?* — ratification is a point-in-time judgment, and code moves. A row whose
pinned shape no longer matches reverts to un-ratified.

Both are obligation gates, because both need the map. Neither substitutes for the other:
evidence catches a role that was always wrong, the pin catches a role that
stopped being right.
"""

from __future__ import annotations

import ast

from ..context import Context
from ..registry import Family, check
from ..result import CheckResult, Finding, Stage
from ..roles import Role
from ..structure.complexity import cyclomatic
from ..structure.evidence import (
    contradictions,
    gather,
    module_signature,
    performs_io,
    signature,
)
from ..surface.inventory import Inventory, ModuleInfo, callable_nodes
from ..surface.map import RATIFIED, SurfaceMap, SurfaceRow
from ._shared import get_inventory, iter_ratified, require_surface_map

_EVIDENCE = "celebrimbor.surface.evidence"
_PIN = "celebrimbor.surface.pin"


def _adapter_modules(smap: SurfaceMap) -> set[str]:
    """Dotted names of modules whose effective role is `adapter`."""
    return {m for m in smap.modules() if Role.ADAPTER in smap.effective_roles(m)}


def _matches_adapter(target: str, adapter_modules: set[str]) -> bool:
    """Does an imported module reference resolve to an adapter module?

    Suffix-tolerant so an absolute ``from press.adapters import x`` matches the
    surface-map's source-relative ``adapters``, and vice versa. The surface map
    strips the source prefix; import statements usually do not.
    """
    return any(
        target == a or target.endswith(f".{a}") or a.endswith(f".{target}") for a in adapter_modules
    )


def _plain_import_symbols(node: ast.Import, adapter_modules: set[str]) -> set[str]:
    """`import adapters` / `import adapters as a` → the bound root name."""
    return {
        alias.asname or alias.name.split(".", 1)[0]
        for alias in node.names
        if _matches_adapter(alias.name, adapter_modules)
    }


def _from_import_symbols(node: ast.ImportFrom, adapter_modules: set[str]) -> set[str]:
    """`from adapters import post` → the bound name; `from . import adapters` too."""
    source = node.module or ""
    return {
        alias.asname or alias.name
        for alias in node.names
        # The source is the adapter module, or the alias itself is (bare `from .`).
        if _matches_adapter(source, adapter_modules)
        or _matches_adapter(alias.name, adapter_modules)
    }


def _io_helper_names(module: ModuleInfo) -> set[str]:
    """Same-module functions that themselves perform I/O.

    A callable that delegates to a private helper which does the syscall
    (``lookup(t) -> _fetch(t, ...)`` where ``_fetch`` calls ``t.get(...)``) is
    adapting through that helper. One level, same module, no recursion — enough
    for the common "extract the request into a private function" pattern without
    turning the evidence gate into a whole-program analysis.
    """
    if module.tree is None:
        return set()
    return {
        node.name
        for node in module.tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and performs_io(node)
    }


def _adapter_symbols(module: ModuleInfo, adapter_modules: set[str]) -> frozenset[str]:
    """Names, bound in this module, a call to which counts as adapting.

    Two sources: imports of an adapter-classified module (a seam-wrapper
    delegating one module deeper), and same-module helpers that themselves do
    I/O (a wrapper delegating to a private request function).
    """
    symbols: set[str] = _io_helper_names(module)
    if module.tree is not None and adapter_modules:
        for node in module.tree.body:
            if isinstance(node, ast.Import):
                symbols |= _plain_import_symbols(node, adapter_modules)
            elif isinstance(node, ast.ImportFrom):
                symbols |= _from_import_symbols(node, adapter_modules)
    return frozenset(symbols)


def compute_pin(module: ModuleInfo) -> str | None:
    """The current shape-pin for a module, or None if it cannot be computed."""
    if module.tree is None:
        return None
    nodes = callable_nodes(module.tree)
    signatures = {
        info.qualname: signature(gather(node, info, cyclomatic(node)))
        for info in module.callables
        if (node := nodes.get(info.qualname)) is not None
    }
    return module_signature(signatures) if signatures else None


@check(
    id=_EVIDENCE,
    title="no callable contradicts the role it is declared to have",
    stage=Stage.FAST,
    family=Family.OBLIGATION,
    falsified_by="tests/negative/test_evidence_gate.py::test_verifier_that_cannot_fail_is_red",
)
def check_role_evidence(ctx: Context) -> CheckResult:
    """Necessary conditions, checked against the syntax tree.

    Nothing here proves a role is *right*. These are the minimum structural
    facts a role implies, so that a declaration the code visibly contradicts
    can be refused — which is what makes a role a claim rather than an
    attestation.
    """
    smap = require_surface_map(ctx, _EVIDENCE)
    if isinstance(smap, CheckResult):
        return smap

    adapter_modules = _adapter_modules(smap)
    symbols_by_module: dict[str, frozenset[str]] = {}

    findings: list[Finding] = []
    examined = 0
    for entry in iter_ratified(ctx, smap):
        examined += 1
        if entry.module.dotted not in symbols_by_module:
            symbols_by_module[entry.module.dotted] = _adapter_symbols(entry.module, adapter_modules)
        facts = gather(
            entry.node,
            entry.info,
            cyclomatic(entry.node),
            adapter_symbols=symbols_by_module[entry.module.dotted],
        )
        findings.extend(
            Finding(
                message=(
                    f"{entry.info.key} is declared `{entry.role.value}` but {contradiction.because}"
                ),
                path=entry.info.path,
                line=entry.info.lineno,
                code="role-contradicted",
                hint=contradiction.remedy,
            )
            for contradiction in contradictions(entry.role, facts)
        )

    if findings:
        return CheckResult.failed(
            _EVIDENCE,
            f"{len(findings)} callable(s) contradict their declared role",
            findings,
        )
    return CheckResult.passed(
        _EVIDENCE, f"{examined} ratified callable(s) are consistent with their role"
    )


def _pin_finding(row: SurfaceRow, module: ModuleInfo, current: str) -> Finding | None:
    """What is wrong with this row's pin, if anything."""
    if row.pin is None:
        return Finding(
            message=(
                f"module {row.module!r} is ratified but unpinned, so nothing detects "
                "the code drifting away from the judgment"
            ),
            path=module.path,
            code="pin-missing",
            hint=f"run `celebrimbor ratify {row.module}` to stamp `pin: {current}`",
        )
    if row.pin != current:
        return Finding(
            message=(
                f"module {row.module!r} was ratified as `{row.role.value}` against a "
                f"different shape (pinned {row.pin}, now {current}) — its callables have "
                "changed character since a human last looked"
            ),
            path=module.path,
            code="pin-drift",
            hint=(
                f"confirm `{row.role.value}` still describes this module, then re-stamp "
                f"with `celebrimbor ratify {row.module}`"
            ),
        )
    return None


def _rows_to_pin(smap: SurfaceMap, inv: Inventory) -> list[tuple[SurfaceRow, ModuleInfo, str]]:
    """Ratified rows whose module still exists and whose pin is computable.

    Un-ratified rows and stale rows are both already reported by the
    completeness gate, so they are filtered here rather than double-reported.
    """
    out: list[tuple[SurfaceRow, ModuleInfo, str]] = []
    for row in smap.rows.values():
        if row.status != RATIFIED:
            continue
        module = inv.by_module(row.module)
        if module is None:
            continue
        current = compute_pin(module)
        if current is not None:
            out.append((row, module, current))
    return out


@check(
    id=_PIN,
    title="every ratified row is still about the code it ratified",
    stage=Stage.FAST,
    family=Family.OBLIGATION,
    falsified_by="tests/negative/test_evidence_gate.py::test_shape_drift_unratifies_row",
)
def check_ratification_pin(ctx: Context) -> CheckResult:
    """Ratification binds to a shape; drift in that shape re-opens the question.

    The pin covers character, not content: which capabilities a callable
    reaches for, whether it can fail, whether it mutates its inputs, roughly
    how many collaborators it has, its complexity band. Renaming a local or
    fixing a typo does not move it. Turning a three-line parser into something
    that opens a socket does.
    """
    smap = require_surface_map(ctx, _PIN)
    if isinstance(smap, CheckResult):
        return smap

    candidates = _rows_to_pin(smap, get_inventory(ctx))
    findings = [
        finding
        for row, module, current in candidates
        if (finding := _pin_finding(row, module, current)) is not None
    ]

    if findings:
        return CheckResult.failed(
            _PIN,
            f"{len(findings)} ratified row(s) no longer pinned to their code",
            findings,
        )
    return CheckResult.passed(
        _PIN, f"{len(candidates)} ratified row(s) still match their pinned shape"
    )
