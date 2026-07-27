"""The mutation ratchet: survivor *identity*, not survivor count.

A mutation testing run seeds deliberate bugs and reports which ones the test
suite failed to catch — the *survivors*. The naive ratchet tracks how many
survive and demands the number not grow. That misses the failure that matters:
a survivor set that changes members while keeping the same size. Twelve
survivors last week and twelve this week, but three are new ones in code that
used to be covered — the count says all is well, and a real regression shipped.

So this ratchet tracks *which* mutants survive, by identity, and reddens on any
survivor that was not in the baseline. A survivor that disappears is progress
(the suite got stronger, or the code went away); a survivor that appears is a
hole that opened. Only the second is a regression, and the count cannot tell
the two apart.

Identity is ``file : line : operator`` — location plus what was mutated —
rather than the mutation tool's internal id, which is unstable across runs and
versions. Two runs that mutate the same operator on the same line are the same
survivor even if the tool renumbered everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..yamlio import dump, expect_list, load_mapping
from .baseline import RatchetError, require_pinned, require_reason

BASELINE_VERSION = 1


@dataclass(frozen=True, slots=True)
class Survivor:
    """One mutant the suite failed to kill, identified stably.

    Frozen and hashable on purpose: the whole ratchet is set arithmetic over
    these, and set membership is the entire mechanism.
    """

    file: str
    line: int
    operator: str
    """What was mutated — e.g. ``and->or``, ``+->-``, ``True->False``. The tool
    reports this; it is what makes two mutations at the same spot distinct."""

    @property
    def identity(self) -> str:
        return f"{self.file}:{self.line}:{self.operator}"

    def __str__(self) -> str:
        return self.identity


@dataclass(frozen=True, slots=True)
class MutationBaseline:
    """The committed set of known, accepted survivors."""

    survivors: frozenset[Survivor] = field(default_factory=frozenset)
    reasons: dict[str, str] = field(default_factory=dict)
    environment: str = "unknown"
    tool: str = "unknown"
    version: int = BASELINE_VERSION

    def identities(self) -> set[str]:
        return {s.identity for s in self.survivors}


def new_survivors(current: frozenset[Survivor], baseline: MutationBaseline) -> list[Survivor]:
    """Survivors present now but absent from the baseline. Pure.

    This is the whole ratchet: identity set difference. A changed set with the
    same count still yields new members here, which is precisely what a count
    comparison would miss.
    """
    known = baseline.identities()
    return sorted(
        (s for s in current if s.identity not in known),
        key=lambda s: (s.file, s.line, s.operator),
    )


def resolved_survivors(current: frozenset[Survivor], baseline: MutationBaseline) -> list[Survivor]:
    """Baseline survivors the suite now kills — progress worth surfacing."""
    current_ids = {s.identity for s in current}
    return sorted(
        (s for s in baseline.survivors if s.identity not in current_ids),
        key=lambda s: (s.file, s.line, s.operator),
    )


def rebaseline(
    current: frozenset[Survivor],
    previous: MutationBaseline,
    *,
    reason: str | None,
    environment: str,
    tool: str,
    pinned: bool,
) -> MutationBaseline:
    """Compute an updated survivor baseline.

    Accepting *new* survivors is admitting the suite got weaker somewhere, so
    it requires a reason. Dropping resolved survivors is always fine. This
    asymmetry is the ratchet: the update path cannot silently accept a new hole.
    """
    require_pinned(pinned, action="take a mutation baseline")

    added = new_survivors(current, previous)
    if added:
        reason = require_reason(
            reason,
            action=f"accept {len(added)} new surviving mutant(s) into the baseline",
        )

    reasons = dict(previous.reasons)
    if added and reason:
        for survivor in added:
            reasons[survivor.identity] = reason

    # Keep reasons only for survivors that still exist.
    reasons = {
        ident: why for ident, why in reasons.items() if ident in {s.identity for s in current}
    }

    return MutationBaseline(
        survivors=frozenset(current),
        reasons=reasons,
        environment=environment,
        tool=tool,
    )


def load_mutation_baseline(path: Path) -> MutationBaseline:
    data = load_mapping(path, what="mutation baseline")
    raw = expect_list(data.get("survivors") or [], where=f"{path}: survivors")
    survivors: set[Survivor] = set()
    for entry in raw:
        survivors.add(_parse_survivor(path, entry))
    reasons_raw = data.get("reasons") or {}
    return MutationBaseline(
        survivors=frozenset(survivors),
        reasons={str(k): str(v) for k, v in reasons_raw.items()},
        environment=str(data.get("environment", "unknown")),
        tool=str(data.get("tool", "unknown")),
        version=int(data.get("version", BASELINE_VERSION)),
    )


def _parse_survivor(path: Path, entry: Any) -> Survivor:
    # Accept the compact `file:line:operator` string or a mapping.
    if isinstance(entry, str):
        parts = entry.rsplit(":", 2)
        if len(parts) != 3 or not parts[1].isdigit():
            raise RatchetError(f"{path}: survivor {entry!r} is not `file:line:operator`")
        return Survivor(file=parts[0], line=int(parts[1]), operator=parts[2])
    if isinstance(entry, dict):
        missing = {"file", "line", "operator"} - set(entry)
        if missing:
            raise RatchetError(f"{path}: survivor is missing {', '.join(sorted(missing))}")
        return Survivor(
            file=str(entry["file"]), line=int(entry["line"]), operator=str(entry["operator"])
        )
    raise RatchetError(f"{path}: survivor must be a string or mapping, got {type(entry).__name__}")


def write_mutation_baseline(path: Path, baseline: MutationBaseline) -> None:
    payload: dict[str, Any] = {
        "version": baseline.version,
        "environment": baseline.environment,
        "tool": baseline.tool,
        "survivors": sorted(s.identity for s in baseline.survivors),
    }
    if baseline.reasons:
        payload["reasons"] = dict(sorted(baseline.reasons.items()))
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# celebrimbor mutation ratchet — survivor IDENTITY, not count. Taken in CI.\n"
    path.write_text(header + dump(payload), encoding="utf-8")
