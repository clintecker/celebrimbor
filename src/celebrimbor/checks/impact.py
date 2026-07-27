"""The change-impact gate: a policy-role change with no invariant naming it.

The other gates ask "is the code consistent with its ledgers right now?" This
one asks a question about *change*: when you modify a module that decides or
attests something — a verifier, a producer, a parser, a normalizer, an adapter
— is there a recorded promise that governs it? If not, the change is a silent
alteration of what the system guarantees, made in a place with no invariant
watching it.

It works by intersecting three things:

    git diff  →  the surface role of each changed module  →  the invariant
    that owns it  →  a gap

A changed module whose role is policy-bearing, with no invariant in the ledger
naming it as an enforcer, is the gap. It reddens.

Two design points from the build contract, both load-bearing:

* **The source prefix is parameterized**, taken from config rather than
  hardcoded, so the diff-to-module mapping works on any layout.
* **Fail closed on an unknowable diff.** If the changed-file set cannot be
  determined — not a repo, git absent, an unresolvable base — this REFUSES. It
  does not treat "I could not tell what changed" as "nothing changed", because
  that is precisely the estimate that lets a policy change slip through on the
  one run where git was unhappy.
"""

from __future__ import annotations

from pathlib import Path

from ..context import Context
from ..ledgers.invariants import InvariantLedger, load_invariants
from ..registry import check
from ..result import CheckResult, Finding, Tier
from ..roles import POLICY_ROLES, Role
from ..surface.inventory import dotted_name
from ..surface.map import SurfaceMap
from ..yamlio import YamlError
from ._shared import require_surface_map

_ID = "celebrimbor.impact"


def _changed_modules(ctx: Context) -> dict[str, Path] | None:
    """Dotted module -> changed path, for changed files under the source prefix.

    Returns ``None`` when the diff itself is unknowable, which the gate treats
    as a refusal. An empty dict means "changes, but none under source" — a real
    and passing answer, distinct from "could not tell".
    """
    changed = ctx.changed_files()
    if changed is None:
        return None
    prefix = Path(ctx.config.source)
    modules: dict[str, Path] = {}
    for path in changed:
        if path.suffix != ".py":
            continue
        try:
            path.relative_to(prefix)
        except ValueError:
            continue
        dotted = dotted_name(path, ctx.config.source)
        if dotted:
            modules[dotted] = path
    return modules


def _governed_modules(ledger: InvariantLedger | None) -> set[str]:
    return ledger.enforcer_modules() if ledger is not None else set()


def _policy_roles(ctx: Context) -> frozenset[Role]:
    """The policy-role set for this run: the config override, or the default.

    Lets an adopter match an existing harness's notion of a policy role without
    forking the taxonomy. An empty override falls back to
    :data:`celebrimbor.roles.POLICY_ROLES`.
    """
    configured = ctx.config.policy_roles
    if not configured:
        return POLICY_ROLES
    return frozenset(Role.parse(name) for name in configured)


def _policy_role_of(smap: SurfaceMap, module: str, policy: frozenset[Role]) -> Role | None:
    """The module's policy-bearing role, if it has one.

    Uses ``effective_roles`` so an override-introduced policy role counts —
    changing the one adapter callable on an otherwise pure module is still a
    policy change.
    """
    for role in smap.effective_roles(module):
        if role in policy:
            return role
    return None


@check(
    id=_ID,
    title="a changed policy-role module is named by some invariant",
    tier=Tier.DEFAULT,
    tier1=True,
    falsified_by="tests/negative/test_impact_gate.py::test_policy_change_without_invariant_is_red",
)
def check_impact(ctx: Context) -> CheckResult:
    """Redden when a policy-role module changes with no invariant naming it."""
    smap = require_surface_map(ctx, _ID)
    if isinstance(smap, CheckResult):
        return smap

    ledger = _load_ledger(ctx)
    if isinstance(ledger, CheckResult):
        return ledger

    changed = _changed_modules(ctx)
    if changed is None:
        return CheckResult.refused(
            _ID,
            "the set of changed files could not be determined",
            reason=(
                "the impact gate diffs against a base and none could be resolved (not a git "
                "repo, git absent, or an unknown base). 'I could not tell what changed' is not "
                "'nothing changed', so this refuses rather than passing."
            ),
            remedy="run inside a git repo, or pass --diff-base",
        )

    governed = _governed_modules(ledger)
    policy = _policy_roles(ctx)
    findings: list[Finding] = []
    for module, path in sorted(changed.items()):
        role = _policy_role_of(smap, module, policy)
        if role is not None and module not in governed:
            findings.append(
                Finding(
                    message=(
                        f"{module} changed and is `{role.value}` (a policy role), but no "
                        "invariant names it as an enforcer"
                    ),
                    path=path,
                    code="impact-ungoverned",
                    hint=(
                        "a change to something that decides or attests should be governed by "
                        "a recorded promise. Add an invariant naming this module, or record "
                        "why it owes none."
                    ),
                )
            )

    if findings:
        return CheckResult.failed(
            _ID,
            f"{len(findings)} policy-role change(s) with no governing invariant",
            findings,
        )

    changed_count = len(changed)
    if changed_count == 0:
        return CheckResult.passed(_ID, "no source modules changed against the diff base")
    return CheckResult.passed(
        _ID, f"{changed_count} changed module(s); every policy-role change is governed"
    )


def _load_ledger(ctx: Context) -> InvariantLedger | CheckResult | None:
    """The invariant ledger, its read-failure verdict, or None if absent.

    Absent is legitimate — the impact gate needs invariants to have anything to
    check ownership against — so a missing ledger means every policy change is
    ungoverned, which is exactly what the gate should report. It is not skipped
    away, because that would make the gate silently inert the moment someone
    deleted the invariants file.
    """
    path = ctx.config.invariants_path
    if not path.exists():
        return None
    try:
        return load_invariants(path)
    except YamlError as exc:
        return CheckResult.refused(_ID, "the invariant ledger could not be read", reason=str(exc))
