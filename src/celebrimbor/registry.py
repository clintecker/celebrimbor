"""The ordered check registry, and the falsifier obligation every check owes.

This module holds the framework's single most opinionated rule: **you cannot
register a check without naming the thing that turns it red.** A gate that has
never been observed to fail is a blind gate, and a blind gate is worse than no
gate — it manufactures confidence.

The obligation is discharged one of two ways:

* ``falsified_by="tests/negative/..."`` — a path, node id, or fixture name that
  is on the record as reddening this check. The ``registry.falsifiers`` gate
  verifies these resolve.
* ``falsified_by=Unproven("...", review_by="2026-09-01")`` — an explicit,
  dated admission that no falsifier exists yet. It is visible in every gate
  run, and it *expires*: past the review date the gate goes red. Debt with a
  deadline, never debt in silence.

There is no third option, and in particular there is no default. The keyword
is required.

Note that this module exposes no mutable global to callers. ``@check`` is the
only documented seam (per the build contract), so the registry itself is
reached through :func:`default_registry`, which app code has no reason to
touch.
"""

from __future__ import annotations

import datetime as _dt
import itertools
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from .result import CheckResult, Stage
from .waiver import DatedWaiver, parse_review_date

if TYPE_CHECKING:
    from .context import Context


class CheckFn(Protocol):
    """A check is a pure-ish function from context to verdict.

    It should not raise; if it does, the runner converts the exception to
    ``REFUSED`` rather than letting it escape. Raising is therefore *safe* but
    lossy — a check that anticipates its own failure mode should return a
    ``refused`` result with a useful reason instead.
    """

    def __call__(self, ctx: Context) -> CheckResult: ...


class Unproven(DatedWaiver):
    """A dated admission that a check has no falsifier yet.

    Same shape as every other exception in this harness: named, reasoned,
    dated, and visible. The review date is what keeps the allowlist shrinking
    — an ``Unproven`` past its date reddens ``celebrimbor.falsifiers``.

    Written at the call site as ``Unproven("reason", review_by="2026-09-01")``;
    the subject defaults to the check's own id, which the decorator fills in.
    """

    def __init__(
        self,
        reason: str,
        review_by: str | _dt.date,
        *,
        subject: str = "<check>",
    ) -> None:
        super().__init__(subject=subject, reason=reason, review_by=parse_review_date(review_by))

    def __str__(self) -> str:
        return f"unproven (review by {self.review_by.isoformat()}): {self.reason}"


Falsifier = str | tuple[str, ...] | Unproven


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """A registered check and its metadata."""

    id: str
    title: str
    fn: CheckFn
    stage: Stage
    falsified_by: Falsifier
    order: int
    tags: frozenset[str] = field(default_factory=frozenset)
    tier1: bool = False
    """Tier 1 checks are opt-in: absent unless the adopter authored the ledger
    they read. Tier 0 checks are always registered."""

    @property
    def falsifier_paths(self) -> tuple[str, ...]:
        if isinstance(self.falsified_by, Unproven):
            return ()
        if isinstance(self.falsified_by, str):
            return (self.falsified_by,)
        return self.falsified_by

    @property
    def unproven(self) -> Unproven | None:
        return self.falsified_by if isinstance(self.falsified_by, Unproven) else None


class DuplicateCheckError(ValueError):
    """Two checks claimed the same id. Ids address results; they must be unique."""


class Registry:
    """An insertion-ordered, id-unique collection of checks.

    Order matters and is preserved: cheap checks registered first surface their
    failures first, which is most of what makes a ~10s stage feel fast.
    """

    def __init__(self) -> None:
        self._specs: dict[str, CheckSpec] = {}
        self._counter = itertools.count()

    def register(self, spec: CheckSpec) -> CheckSpec:
        existing = self._specs.get(spec.id)
        if existing is not None:
            raise DuplicateCheckError(
                f"check id {spec.id!r} is already registered by "
                f"{existing.fn.__module__}.{getattr(existing.fn, '__qualname__', '?')}"
            )
        self._specs[spec.id] = spec
        return spec

    def next_order(self) -> int:
        return next(self._counter)

    def __len__(self) -> int:
        return len(self._specs)

    def __iter__(self) -> Iterator[CheckSpec]:
        return iter(sorted(self._specs.values(), key=lambda s: s.order))

    def __contains__(self, check_id: object) -> bool:
        return check_id in self._specs

    def get(self, check_id: str) -> CheckSpec | None:
        return self._specs.get(check_id)

    def all(self) -> tuple[CheckSpec, ...]:
        return tuple(self)

    def for_stage(self, stage: Stage) -> tuple[CheckSpec, ...]:
        """Every check that runs at ``stage`` — i.e. every check at or below it.

        This is the sole definition of "what a gate run should contain," and
        the meta-check ``registry.completeness`` compares a report against it.
        If a check could escape the runner, it would have to escape this
        function first.
        """
        return tuple(s for s in self if s.stage <= stage)

    def ids(self) -> set[str]:
        return set(self._specs)

    def clear(self) -> None:
        """Reset. Exists for celebrimbor's own tests; not part of the public API."""
        self._specs.clear()
        self._counter = itertools.count()


_DEFAULT = Registry()


def default_registry() -> Registry:
    """The process-wide registry that ``@check`` writes into."""
    return _DEFAULT


def _validate(check_id: str, title: str, falsified_by: Falsifier) -> None:
    """Reject a malformed registration at import time, not at gate time.

    Raising here means a bad `@check` breaks the process that defines it,
    rather than producing a check that silently misbehaves later.
    """
    if not check_id or not check_id.strip():
        raise ValueError("check() requires a non-empty id")
    if not title or not title.strip():
        raise ValueError(
            f"check {check_id!r} requires a title; it is what the adopter reads on failure"
        )
    if isinstance(falsified_by, str) and not falsified_by.strip():
        raise ValueError(
            f"check {check_id!r}: falsified_by must name a real falsifier, or be an "
            "Unproven(reason, review_by=...) if none exists yet"
        )
    if isinstance(falsified_by, tuple) and not falsified_by:
        raise ValueError(f"check {check_id!r}: falsified_by cannot be an empty tuple")


def check(
    *,
    id: str,  # noqa: A002 - `id` reads correctly at the call site; the shadowing is local
    title: str,
    falsified_by: Falsifier,
    stage: str | Stage = Stage.FAST,
    tags: Iterable[str] = (),
    tier1: bool = False,
    registry: Registry | None = None,
) -> Callable[[CheckFn], CheckFn]:
    """Register a check into the ordered registry the runner proves complete.

    This is the only documented seam for app-specific checks.

    ``falsified_by`` is required and has no default, which is the point: the
    framework will not let you add a gate without saying how you know the gate
    works. Pass a path/node-id that reddens it, or an :class:`Unproven` with a
    review date.

    The decorated function is returned unchanged, so it stays directly
    callable and directly unit-testable.

    Example::

        @celebrimbor.check(
            id="myapp.manifest",
            title="every artifact is listed in the manifest",
            stage="fast",
            falsified_by="tests/known-bad/manifest_missing_entry.json",
        )
        def check_manifest(ctx):
            ...
    """
    _validate(id, title, falsified_by)
    resolved_stage = Stage.parse(stage)
    target = registry if registry is not None else _DEFAULT

    # An Unproven authored at the call site cannot know its own check id, so
    # bind it here. Without this the pending list would be a wall of
    # "<check>" rows and the shrinking-allowlist property would be unreadable.
    resolved_falsifier = falsified_by
    if isinstance(falsified_by, Unproven) and falsified_by.subject == "<check>":
        resolved_falsifier = Unproven(
            falsified_by.reason, falsified_by.review_by, subject=id.strip()
        )

    def decorate(fn: CheckFn) -> CheckFn:
        target.register(
            CheckSpec(
                id=id.strip(),
                title=title.strip(),
                fn=fn,
                stage=resolved_stage,
                falsified_by=resolved_falsifier,
                order=target.next_order(),
                tags=frozenset(tags),
                tier1=tier1,
            )
        )
        return fn

    return decorate
