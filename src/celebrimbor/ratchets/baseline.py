"""Shared baseline machinery: environment gating and reason-gated updates.

Both ratchets record *where* they were taken and refuse to be written outside
the pinned environment. That refusal lives here, once, so neither ratchet can
forget it — a dev-box baseline is the failure mode both share, and the fix is
the same for both.
"""

from __future__ import annotations

from ..yamlio import YamlError


class RatchetError(YamlError):
    """A baseline is unusable. Red — a broken baseline ratchets nothing."""


class BaselineEnvironmentError(RuntimeError):
    """An attempt to write a baseline outside the pinned environment.

    Not caught and turned into a warning: baselining on a dev box is the exact
    thing the scar forbids, so the write simply refuses. The caller — always
    ``--update`` or first-run auto-baseline — surfaces this as a red result
    telling the human to run it in CI.
    """


def require_pinned(pinned: bool, *, action: str) -> None:
    if not pinned:
        raise BaselineEnvironmentError(
            f"refusing to {action} outside the pinned environment. A baseline taken on a "
            "dev box reads higher than CI and hands you a red CI on day two. Run this in "
            "CI (or set CELEBRIMBOR_TRUSTED=1 if this really is the pinned environment)."
        )


def require_reason(reason: str | None, *, action: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise BaselineEnvironmentError(
            f"refusing to {action} without a written reason. A floor that moves without a "
            "recorded reason is a floor that will keep moving. Pass --reason."
        )
    return reason
