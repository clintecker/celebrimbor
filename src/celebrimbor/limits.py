"""Structural budgets.

These live in their own leaf module — importing nothing from the package —
rather than beside the code that measures them. That is not tidiness: it is
the fix for a real cycle. ``Limits`` is configuration, so ``config`` needs it
at runtime; but it describes structure, so it originally sat in
``structure.complexity``, which made ``config`` import ``structure``, which
imports ``surface``, which imports ``config``.

The general rule this module is an instance of: **data that several layers
share belongs below all of them, not inside whichever one defined it first.**
The layering gate exists to catch the version of this mistake that does not
announce itself with an ImportError.

Every value here is a *ceiling*, not a target. Nothing rewards being far under.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Limits:
    """Per-callable and per-module structural ceilings."""

    complexity: int = 10
    """McCabe complexity: one, plus one per decision point. Ten is the
    conventional line where a function stops fitting in one reader's head —
    and, more to the point, where the number of paths a test would have to
    cover exceeds what anyone actually covers."""

    nesting: int = 4
    """Deepest block nesting. Measured separately from complexity because they
    fail differently: twelve sequential ifs scores badly on complexity but
    reads fine, while four levels of nesting does not."""

    max_statements: int = 50

    max_params: int = 5
    """*Positional* parameters, excluding ``self``/``cls``. A long positional
    list is unreadable and mis-orderable at the call site, and is usually an
    unnamed concept waiting to become a dataclass.

    Keyword-only parameters are counted separately, under
    :attr:`max_keyword_params`. They are a different smell — or rather, mostly
    not a smell: ``f(a=1, b=2, ..., g=7)`` cannot be mis-ordered and documents
    itself at every call site. Counting the two against one ceiling measures
    the wrong thing, and would penalise exactly the API shape that fixes the
    problem the limit exists for."""

    max_keyword_params: int = 8
    """Keyword-only parameters. Generous, because these are self-documenting;
    a ceiling at all only because past it a callable is usually configuring
    rather than doing."""

    max_returns: int = 8
    """Return statements.

    Deliberately generous, and it is worth recording why, because this limit
    is in genuine tension with :attr:`nesting`. The tidy argument against many
    exits — that a postcondition gets hard to state — is real but weak; the
    argument for them is that guard clauses are the primary way to *avoid*
    deep nesting, which is the failure a reader actually hits. Two rules
    cannot both win, so the one with the stronger justification does, and this
    one gives way."""

    max_function_lines: int = 80
    max_file_lines: int = 500

    max_domains_per_file: int = 1
    """Independent domains per module, measured as connected components of the
    intra-module reference graph — not a class count. Five classes that are
    about each other are one domain; one class and one unrelated function
    family are two. See `structure.cohesion` for why counting classes is the
    wrong metric."""

    max_public_callables: int = 20
    """Past this a module has usually become a grab bag rather than a domain."""
