"""Core result vocabulary.

Every engine in celebrimbor funnels through these types, which is deliberate:
the fail-closed invariant is enforced *here*, once, at construction time,
rather than re-implemented (and eventually mis-implemented) in each engine.

Three rules live in this module and nowhere else:

1.  **There is no boolean.** ``ok`` is derived from the verdict, never
    assigned. A check cannot report success; it can only report a verdict and
    let this module decide what that means.

2.  **Not-proved is red.** ``REFUSED`` exists so that "the harness could not
    establish this" has somewhere to go that is *not* ``PASS``. Any engine
    that hits missing data, an unparseable file, or an exception yields
    ``REFUSED``, and ``REFUSED`` is red.

3.  **A skip must say why.** ``SKIPPED`` without a reason raises at
    construction. This is the type-level form of the "no silent skip" scar:
    you cannot write the quiet pass, because the constructor refuses it.
"""

from __future__ import annotations

import enum
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path


class Stage(enum.IntEnum):
    """*When* a run happens, ordered by cost — the pre-commit / PR / release axis.

    Not to be confused with a check's :class:`Family` (``commodity`` vs
    ``obligation`` — what kind of check it is). Family is *what kind*; stage is
    *how deep a run goes*. A single check has both: e.g. the ``obligation``
    ``invariants`` gate runs at the ``DEFAULT`` stage.

    A check declares the *cheapest* stage at which it is willing to run; a gate
    invocation runs every check whose stage is at or below the requested one.
    The ordering is the whole point of the ``IntEnum``: ``FAST <= DEFAULT``
    is the membership test.
    """

    FAST = 1
    """Pre-commit stage. Budget: ~10s. Lint, types, format, known-bad, surface."""

    DEFAULT = 2
    """PR stage. Budget: ~2min. Adds coverage ratchet, invariants, impact gate."""

    FULL = 3
    """Merge/release stage. Adds mutation and container/integration steps."""

    @classmethod
    def parse(cls, value: str | Stage) -> Stage:
        if isinstance(value, Stage):
            return value
        try:
            return cls[value.strip().upper()]
        except KeyError:
            valid = ", ".join(t.name.lower() for t in cls)
            raise ValueError(f"unknown stage {value!r}; expected one of {valid}") from None

    @property
    def label(self) -> str:
        return self.name.lower()


class Verdict(enum.Enum):
    """What a check concluded.

    The four states are not interchangeable and the split between ``FAIL`` and
    ``REFUSED`` is load-bearing. ``FAIL`` means the harness proved a violation:
    it has a finding to show you. ``REFUSED`` means the harness could not reach
    a conclusion — a config file was missing, a tool was absent, an AST would
    not parse. Both are red, but they demand different fixes, and collapsing
    them is how "we couldn't check" silently becomes "there's nothing wrong."
    """

    PASS = "pass"
    """The claim was checked and held."""

    FAIL = "fail"
    """The claim was checked and was violated. Findings are attached."""

    REFUSED = "refused"
    """The claim could not be checked. Red, by construction."""

    SKIPPED = "skipped"
    """The check was not applicable or not opted into. Requires a reason."""

    @property
    def is_red(self) -> bool:
        return self in _RED

    @property
    def glyph(self) -> str:
        return _GLYPHS[self]


_RED = frozenset({Verdict.FAIL, Verdict.REFUSED})
_GLYPHS = {
    Verdict.PASS: "✓",
    Verdict.FAIL: "✗",
    Verdict.REFUSED: "⊘",
    Verdict.SKIPPED: "-",
}


def _malformed(result: CheckResult) -> list[str]:
    """Why this result is not a well-formed claim, if it is not.

    A list rather than a branch chain, and a free function rather than a
    method, so the rules read as a table of things a result may not be. They
    are not defensive programming: a malformed result is a bug in a *gate*,
    and a bug in a gate must not be able to produce green.
    """
    reason = (result.reason or "").strip()
    rules = (
        (not result.check_id, "CheckResult requires a check_id"),
        (
            not result.summary.strip(),
            "CheckResult requires a non-empty summary",
        ),
        (
            result.verdict is Verdict.SKIPPED and not reason,
            "a SKIPPED result must carry a reason. Silent skips are the failure mode "
            "this harness exists to prevent.",
        ),
        (
            result.verdict is Verdict.FAIL and not result.findings,
            "a FAIL result must carry at least one finding. If the gate cannot point "
            "at the violation, it should REFUSE instead.",
        ),
        (
            result.verdict is Verdict.REFUSED and not reason,
            "a REFUSED result must explain what it could not establish.",
        ),
    )
    return [f"{result.check_id or '<no id>'}: {text}" for broken, text in rules if broken]


@dataclass(frozen=True, slots=True)
class Finding:
    """One concrete, locatable thing that is wrong.

    A ``FAIL`` with no findings is suspicious enough that
    :class:`CheckResult` rejects it: if a gate says something is broken it must
    be able to point at it.
    """

    message: str
    path: Path | None = None
    line: int | None = None
    code: str | None = None
    hint: str | None = None

    def location(self) -> str:
        if self.path is None:
            return "<project>"
        if self.line is None:
            return str(self.path)
        return f"{self.path}:{self.line}"

    def __str__(self) -> str:
        prefix = f"{self.location()}: " if self.path else ""
        suffix = f" [{self.code}]" if self.code else ""
        return f"{prefix}{self.message}{suffix}"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The outcome of a single check.

    Construct via the classmethods rather than directly; they encode which
    fields each verdict requires. The ``__post_init__`` validation is not
    defensive programming, it is the fail-closed invariant: a malformed result
    is a bug in a *gate*, and a bug in a gate must not be able to produce
    green.
    """

    check_id: str
    verdict: Verdict
    summary: str
    findings: tuple[Finding, ...] = ()
    reason: str | None = None
    duration_s: float = 0.0
    remedy: str | None = None

    def __post_init__(self) -> None:
        for complaint in _malformed(self):
            raise ValueError(complaint)

    # -- derived state ------------------------------------------------------

    @property
    def ok(self) -> bool:
        """True when this result does not redden the gate.

        Note that ``SKIPPED`` is ok but not ``PASS``. A skipped check has
        proved nothing; it has merely declined to run, on the record.
        """
        return not self.verdict.is_red

    @property
    def is_red(self) -> bool:
        return self.verdict.is_red

    @property
    def proved(self) -> bool:
        """True only when the check actually established its claim."""
        return self.verdict is Verdict.PASS

    # -- constructors -------------------------------------------------------

    @classmethod
    def passed(cls, check_id: str, summary: str, *, duration_s: float = 0.0) -> CheckResult:
        return cls(check_id, Verdict.PASS, summary, duration_s=duration_s)

    @classmethod
    def failed(
        cls,
        check_id: str,
        summary: str,
        findings: Sequence[Finding] | Finding,
        *,
        remedy: str | None = None,
        duration_s: float = 0.0,
    ) -> CheckResult:
        items = (findings,) if isinstance(findings, Finding) else tuple(findings)
        return cls(
            check_id,
            Verdict.FAIL,
            summary,
            findings=items,
            remedy=remedy,
            duration_s=duration_s,
        )

    @classmethod
    def refused(
        cls,
        check_id: str,
        summary: str,
        reason: str,
        *,
        remedy: str | None = None,
        duration_s: float = 0.0,
    ) -> CheckResult:
        """The harness could not prove the claim. This is red.

        Use this — never ``passed`` and never ``skipped`` — whenever an engine
        runs into something it cannot evaluate.
        """
        return cls(
            check_id,
            Verdict.REFUSED,
            summary,
            reason=reason,
            remedy=remedy,
            duration_s=duration_s,
        )

    @classmethod
    def skipped(cls, check_id: str, reason: str, *, duration_s: float = 0.0) -> CheckResult:
        """The check does not apply here. Not red, but never invisible.

        Legitimate uses are narrow: the adopter has not opted into the obligation
        feature this check gates, or the check is inapplicable to this project
        shape. "The tool wasn't installed" is only a skip when no
        trusted-environment promise was made; otherwise it is ``refused``.
        """
        return cls(
            check_id,
            Verdict.SKIPPED,
            f"skipped: {reason}",
            reason=reason,
            duration_s=duration_s,
        )


@dataclass(slots=True)
class GateReport:
    """The outcome of a whole gate run."""

    stage: Stage
    results: list[CheckResult] = field(default_factory=list)
    duration_s: float = 0.0

    def __iter__(self) -> Iterator[CheckResult]:
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    @property
    def red(self) -> list[CheckResult]:
        return [r for r in self.results if r.is_red]

    @property
    def skipped(self) -> list[CheckResult]:
        return [r for r in self.results if r.verdict is Verdict.SKIPPED]

    @property
    def ok(self) -> bool:
        """An empty report is not ok.

        A gate that ran zero checks has proved nothing, and reporting green for
        it is exactly the plausible-but-wrong outcome this project exists to
        prevent. Emptiness is caught here rather than at the call site so no
        caller can forget.
        """
        return bool(self.results) and not self.red

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1

    def ids(self) -> set[str]:
        return {r.check_id for r in self.results}

    def by_id(self, check_id: str) -> CheckResult | None:
        for r in self.results:
            if r.check_id == check_id:
                return r
        return None
