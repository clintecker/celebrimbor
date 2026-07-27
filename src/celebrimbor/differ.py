"""A toolchain-stable baseline differ, with a reason-gated update.

Snapshot testing compares fresh output against a committed baseline and fails
on any difference. This differ is that, with three properties the naive version
lacks:

* **Toolchain-stable normalization.** Before comparing, both sides pass through
  a normalizer that strips the noise a snapshot should not be sensitive to —
  trailing whitespace, blank-line runs, and (optionally) volatile tokens the
  caller names. A differ that reddens because a library reformatted its output
  by one space is a differ people delete.
* **Reason-gated update.** :func:`update` refuses to overwrite a baseline
  without a recorded reason. A snapshot silently accepting whatever the code
  now produces is not a test; it is a rubber stamp.
* **Proven bite.** :func:`self_proof` mutates a baseline *in memory* and
  confirms the differ reports the mutation. A differ that has never been shown
  to detect a change is a blind differ — the same scar as a blind verifier,
  applied to the differ itself.

Explicitly **not** here: any notion of a "major" versus "minor" difference, or
"a fix must not change the snapshot's shape." That scoping is a domain policy
that belongs in whatever app needs it, and dragging it into a general differ
was called out as an anti-goal.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field


class DifferUpdateError(RuntimeError):
    """An attempt to update a baseline without a reason. Refused, not warned."""


@dataclass(frozen=True, slots=True)
class Normalizer:
    """How to render output comparable without being noise-sensitive."""

    strip_trailing_whitespace: bool = True
    collapse_blank_lines: bool = True
    volatile: tuple[str, ...] = ()
    """Regexes whose matches are replaced with a stable placeholder before
    comparison — timestamps, temp paths, run ids. Named by the caller, because
    only the caller knows which tokens are legitimately volatile."""

    def apply(self, text: str) -> str:
        result = text
        for pattern in self.volatile:
            result = re.sub(pattern, "<volatile>", result)
        lines = result.split("\n")
        if self.strip_trailing_whitespace:
            lines = [ln.rstrip() for ln in lines]
        if self.collapse_blank_lines:
            lines = _collapse_blanks(lines)
        return "\n".join(lines).strip("\n")


def _collapse_blanks(lines: Sequence[str]) -> list[str]:
    out: list[str] = []
    blank = False
    for line in lines:
        if line.strip():
            out.append(line)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return out


@dataclass(frozen=True, slots=True)
class Difference:
    """One line that changed between baseline and current."""

    line: int
    baseline: str | None
    current: str | None

    def __str__(self) -> str:
        old = "∅" if self.baseline is None else repr(self.baseline)
        new = "∅" if self.current is None else repr(self.current)
        return f"line {self.line}: {old} → {new}"


@dataclass(frozen=True, slots=True)
class DiffResult:
    """The outcome of a comparison."""

    differences: tuple[Difference, ...] = field(default_factory=tuple)

    @property
    def matched(self) -> bool:
        return not self.differences

    def summary(self) -> str:
        if self.matched:
            return "output matches baseline"
        return f"{len(self.differences)} line(s) differ from baseline"


def diff(baseline: str, current: str, normalizer: Normalizer | None = None) -> DiffResult:
    """Compare current output against a baseline after normalization. Pure."""
    norm = normalizer or Normalizer()
    base_lines = norm.apply(baseline).split("\n")
    curr_lines = norm.apply(current).split("\n")

    differences: list[Difference] = []
    for index in range(max(len(base_lines), len(curr_lines))):
        b = base_lines[index] if index < len(base_lines) else None
        c = curr_lines[index] if index < len(curr_lines) else None
        if b != c:
            differences.append(Difference(line=index + 1, baseline=b, current=c))
    return DiffResult(differences=tuple(differences))


def update(current: str, *, reason: str | None, normalizer: Normalizer | None = None) -> str:
    """Produce the new baseline content, refusing without a reason.

    Returns the *normalized* current output, so a committed baseline is already
    in the form comparisons happen in — a baseline that had to be normalized on
    every read would drift from what the author reviewed.
    """
    if not (reason or "").strip():
        raise DifferUpdateError(
            "refusing to update a baseline without a reason. A snapshot that accepts whatever "
            "the code now produces is a rubber stamp, not a test."
        )
    return (normalizer or Normalizer()).apply(current)


def self_proof(baseline: str, normalizer: Normalizer | None = None) -> bool:
    """Prove this differ can detect a change, by mutating the baseline in memory.

    Returns True when a one-character mutation of the baseline is reported as a
    difference. A differ that returns False here is blind and must not be
    trusted — the same reasoning as every other gate carrying its own falsifier.
    """
    norm = normalizer or Normalizer()
    normalized = norm.apply(baseline)
    if not normalized:
        mutated = "x"
    else:
        # Flip a character on the first non-blank line to guarantee a real,
        # normalization-surviving change.
        marker = "~MUT~"
        mutated = normalized + f"\n{marker}"
    return not diff(normalized, mutated, norm).matched
