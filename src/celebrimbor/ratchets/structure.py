"""The structure ratchet: grandfather existing debt, fail only new or worse.

Adopting celebrimbor into an established codebase means meeting its structure
budgets — and an established codebase has debt. The escape the harness offers
everywhere else is an exemption per item, with a reason and a review date. For a
handful of items that is right. For a hundred and thirty-six it is the wall the
framework exists to avoid: nobody hand-writes 136 exemptions, so they turn the
gate off instead.

So structure gets a ratchet, the same shape as coverage and mutation. A
committed baseline records the breaches that exist *today*, keyed by a stable
identity that survives line-number shifts. Thereafter:

* a breach **not** in the baseline is new — it fails;
* a grandfathered breach that got **worse** (higher complexity, deeper nesting)
  fails, because a ratchet only tightens;
* a grandfathered breach at or below its baselined value passes;
* a grandfathered breach that improved below the limit drops off entirely.

Unlike coverage, structure does **not** auto-baseline on first run. Structure
limits are absolute — complexity ≤ 10 is a rule, not a relative measure — so a
greenfield repo stays strict: with no baseline, every breach fails. Grandfathering
is a deliberate, reasoned act (`gate --update-baselines --reason "..."` in CI, or
the migration scaffolds it), never something that happens silently.

The comparator is a pure function of two dicts, so the interesting logic is
testable without measuring anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..yamlio import dump, expect_mapping, load_mapping
from .baseline import RatchetError, require_pinned, require_reason

BASELINE_VERSION = 1


@dataclass(frozen=True, slots=True)
class Breach:
    """One structural budget breach, with a stable identity and its severity.

    ``key`` is location-plus-metric — e.g. ``pkg.mod:Class.method:complexity`` —
    deliberately *not* line-based, so adding a comment above a function does not
    un-grandfather it. ``value`` is the measured number (complexity 14, nesting
    5); for a presence-only breach like an ambient capability, it is 1.
    """

    key: str
    value: int
    message: str
    code: str = "structure"

    def worse_than(self, baselined: int) -> bool:
        return self.value > baselined


@dataclass(frozen=True, slots=True)
class StructureBaseline:
    """The committed set of grandfathered breaches: ``key -> value``."""

    breaches: dict[str, int] = field(default_factory=dict)
    environment: str = "unknown"
    version: int = BASELINE_VERSION

    def grandfathers(self, breach: Breach) -> bool:
        prior = self.breaches.get(breach.key)
        return prior is not None and not breach.worse_than(prior)


@dataclass(frozen=True, slots=True)
class StructureVerdict:
    """The outcome of ratcheting a set of breaches against a baseline."""

    survived: tuple[Breach, ...] = ()
    """New or worsened breaches — these fail the gate."""

    grandfathered: int = 0
    """Breaches the baseline still covers."""

    resolved: tuple[str, ...] = ()
    """Baselined keys with no current breach — debt that was paid down."""

    @property
    def clean(self) -> bool:
        return not self.survived


def ratchet(current: list[Breach], baseline: StructureBaseline | None) -> StructureVerdict:
    """Filter current breaches against the baseline. Pure.

    With no baseline, nothing is grandfathered — every breach survives, which is
    the strict, greenfield behaviour. With a baseline, only new-or-worse survive.
    """
    if baseline is None:
        return StructureVerdict(survived=tuple(current))

    survived = tuple(b for b in current if not baseline.grandfathers(b))
    grandfathered = sum(1 for b in current if baseline.grandfathers(b))
    current_keys = {b.key for b in current}
    resolved = tuple(sorted(k for k in baseline.breaches if k not in current_keys))
    return StructureVerdict(survived=survived, grandfathered=grandfathered, resolved=resolved)


def rebaseline(
    current: list[Breach],
    *,
    reason: str | None,
    environment: str,
    pinned: bool,
) -> StructureBaseline:
    """Record every current breach as grandfathered. Reason-gated, CI-only.

    Grandfathering existing debt is an admission that the code is over budget in
    known places, so it demands a written reason — the same discipline as
    lowering a coverage floor. And it may only be taken in the pinned
    environment, so a dev box cannot bake in a baseline that differs from CI's.
    """
    require_pinned(pinned, action="take a structure baseline")
    require_reason(reason, action=f"grandfather {len(current)} existing structure breach(es)")
    return StructureBaseline(
        breaches={b.key: b.value for b in current},
        environment=environment,
    )


def load_structure_baseline(path: Path) -> StructureBaseline:
    data = load_mapping(path, what="structure baseline")
    raw = expect_mapping(data.get("breaches") or {}, where=f"{path}: breaches")
    try:
        breaches = {str(k): int(v) for k, v in raw.items()}
    except (TypeError, ValueError) as exc:
        raise RatchetError(f"{path}: breaches must be key -> integer: {exc}") from exc
    return StructureBaseline(
        breaches=breaches,
        environment=str(data.get("environment", "unknown")),
        version=int(data.get("version", BASELINE_VERSION)),
    )


def write_structure_baseline(path: Path, baseline: StructureBaseline, reason: str) -> None:
    payload = {
        "version": baseline.version,
        "environment": baseline.environment,
        "reason": reason,
        "breaches": dict(sorted(baseline.breaches.items())),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# celebrimbor structure ratchet — grandfathered existing debt.\n"
        "# New or worsened breaches fail; these are the ones present at adoption.\n"
    )
    path.write_text(header + dump(payload), encoding="utf-8")
