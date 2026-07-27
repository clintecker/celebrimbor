"""Rendering the conventions as documentation.

These renderers were originally next to the tables they describe, and the
cohesion gate split ``roles`` into two domains for it — correctly. A taxonomy
and a markdown formatter are different concerns that happen to share a
subject, and keeping them together is how a domain module slowly accretes a
presentation layer.

Everything here is derived from the same tables the gates read, so it cannot
drift from what is actually enforced. That matters more than it sounds: a
convention nobody can see is configuration with extra steps, and documentation
that describes a *different* rule than the one running is worse than none.
"""

from __future__ import annotations

from .roles import OBLIGATIONS, REAL_ROLES
from .structure.capabilities import ROLE_BUDGET, Capability


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """One table format, used by both renderers.

    Extracted because the cohesion gate scored this module at two domains:
    two table builders that shared no vocabulary read as two unrelated
    concerns, and the honest fix is that they should have shared the format.
    """
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "|" + "---|" * len(headers),
            *("| " + " | ".join(cells) + " |" for cells in rows),
        ]
    )


def role_table() -> str:
    """The role taxonomy and what each role owes."""
    return _markdown_table(
        ["Role", "Owes"],
        [[f"`{r.value}`", OBLIGATIONS[r].owes] for r in REAL_ROLES],
    )


def budget_table() -> str:
    """Which capabilities each role may reach for instead of being handed."""
    caps = list(Capability)
    return _markdown_table(
        ["Role", *(c.value for c in caps)],
        [
            [f"`{role.value}`", *("✓" if c in allowed else "" for c in caps)]
            for role, allowed in ROLE_BUDGET.items()
        ],
    )
