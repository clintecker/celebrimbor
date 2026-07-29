"""Celebrimbor — invariant-driven design as a framework.

A claim a system cannot contradict is a claim it will eventually get wrong.
Celebrimbor's job is to make every unit of an application carry its own
falsifier, and to make the gate fail closed: refuse when it cannot prove,
never estimate.

Public surface, in its entirety::

    celebrimbor.gate(stage="fast")     # run the gate programmatically
    @celebrimbor.check(...)           # register an app-specific check
    celebrimbor.Unproven(...)         # a dated admission of missing falsifier
    celebrimbor.CheckResult, Finding, Verdict, Stage, Family  # what a check returns

That is the whole documented seam. There is deliberately no exposed registry
object: a raw registry invites app code to mutate ordering or bypass
registration, and the completeness guarantee is only as good as the claim that
``@check`` is the one door.

Imports here are kept cheap — no click, no rich, no yaml at module import —
because the fast stage has a ~10s budget and interpreter startup is the one
cost no check can amortize.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .registry import Family, Unproven, check
from .result import CheckResult, Finding, GateReport, Stage, Verdict

if TYPE_CHECKING:
    from pathlib import Path

    from .context import Context

__version__ = "0.11.0"

if TYPE_CHECKING:
    from .ratchets.mutation import Survivor

__all__ = [
    "CheckResult",
    "Family",
    "Finding",
    "GateReport",
    "Stage",
    "Survivor",
    "Unproven",
    "Verdict",
    "__version__",
    "check",
    "gate",
]


def __getattr__(name: str) -> object:
    # `Survivor` is exposed lazily: apps supplying a mutation survivor set
    # (`mutation_survivors` config) import it, but its module pulls in yaml, and
    # this package is kept yaml-free at import so the fast stage stays cheap.
    if name == "Survivor":
        from .ratchets.mutation import Survivor

        return Survivor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def gate(
    stage: str | Stage = Stage.FAST,
    *,
    root: Path | str | None = None,
    diff_base: str | None = None,
) -> GateReport:
    """Run the gate and return its report. The programmatic form of the CLI.

    Does not raise on failure and does not exit; inspect ``report.ok`` or
    ``report.exit_code``. Callers that want the exception ergonomics can raise
    on ``not report.ok`` themselves — making that the default would hide the
    per-check detail that is the actual product.
    """
    from .checks import load_check_modules
    from .context import Context as _Context
    from .runner import load_builtin_checks, run

    load_builtin_checks()
    ctx = _Context.for_root(root, stage=stage, diff_base=diff_base)
    load_check_modules(ctx.config.check_modules)  # raises CheckModuleError, like a bad config
    return run(ctx)


def _context_for(root: Path | str | None = None, stage: str | Stage = Stage.FAST) -> Context:
    """Internal helper for the test seam; not part of the public API."""
    from .context import Context as _Context

    return _Context.for_root(root, stage=stage)
