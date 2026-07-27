"""Debt with a deadline.

The build contract asks for the same shape in three unrelated places:

* a check with no falsifier yet (``Unproven``),
* a callable that genuinely owes no direct proof (``Exemption``),
* a producer module with no on-the-record negative fixture (``Pending``).

Each is "exempted by name, with a reason and a review date, never silently."
That is one concept, so it is one class. The important property is not the
data but the *expiry*: a waiver whose review date has passed reddens the gate
it waives. An allowlist that cannot expire is an allowlist that only grows,
and the build contract asks for a visible, shrinking one.

Waivers are also never inferred and never written by tooling. Every
constructor here demands a human-authored reason, and the empty string is not
a reason.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Self


class WaiverError(ValueError):
    """A waiver was malformed. Red — a broken waiver never waives anything."""


def parse_review_date(value: str | _dt.date) -> _dt.date:
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    try:
        return _dt.date.fromisoformat(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise WaiverError(f"review_by must be an ISO date (YYYY-MM-DD), got {value!r}") from exc


@dataclass(frozen=True, slots=True)
class DatedWaiver:
    """A named, reasoned, expiring exception."""

    subject: str
    reason: str
    review_by: _dt.date

    def __post_init__(self) -> None:
        if not str(self.subject).strip():
            raise WaiverError(f"{type(self).__name__} requires a subject to waive")
        if not str(self.reason).strip():
            raise WaiverError(
                f"{type(self).__name__} for {self.subject!r} requires a reason; "
                "an unexplained exception is the thing this harness exists to prevent"
            )
        object.__setattr__(self, "subject", str(self.subject).strip())
        object.__setattr__(self, "reason", str(self.reason).strip())
        object.__setattr__(self, "review_by", parse_review_date(self.review_by))

    def expired(self, today: _dt.date | None = None) -> bool:
        return (today or _dt.date.today()) > self.review_by

    def days_remaining(self, today: _dt.date | None = None) -> int:
        return (self.review_by - (today or _dt.date.today())).days

    def describe(self) -> str:
        state = "EXPIRED" if self.expired() else f"review by {self.review_by.isoformat()}"
        return f"{self.subject}: {self.reason} ({state})"

    def to_dict(self) -> dict[str, str]:
        return {
            "subject": self.subject,
            "reason": self.reason,
            "review_by": self.review_by.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Any, *, subject: str | None = None) -> Self:
        """Build from a ledger row.

        Accepts the ``{reason, review_by}`` mapping ledgers use, with the
        subject supplied by the surrounding key. Anything else is an error
        rather than a best-effort read: a waiver we half-understood would
        waive something we did not intend.
        """
        if not isinstance(data, dict):
            raise WaiverError(
                f"waiver for {subject or '?'} must be a mapping with 'reason' and "
                f"'review_by', got {type(data).__name__}"
            )
        resolved = subject or data.get("subject")
        if resolved is None:
            raise WaiverError("waiver requires a subject, either as a key or a 'subject' field")
        missing = {"reason", "review_by"} - set(data)
        if missing:
            raise WaiverError(
                f"waiver for {resolved!r} is missing required field(s): "
                f"{', '.join(sorted(missing))}"
            )
        return cls(subject=str(resolved), reason=data["reason"], review_by=data["review_by"])


class Exemption(DatedWaiver):
    """A callable that genuinely owes no direct proof of its own."""


class Pending(DatedWaiver):
    """A producer module still owing an on-the-record negative fixture."""


def expired_waivers(waivers: object, today: _dt.date | None = None) -> list[DatedWaiver]:
    """Every waiver in an iterable whose review date has passed."""
    if not isinstance(waivers, list | tuple | set | frozenset):
        return []
    return [w for w in waivers if isinstance(w, DatedWaiver) and w.expired(today)]
