"""Celebrimbor's own registered checks.

Registration happens by import side effect, which is a genuine hazard: a check
in a module nobody imports is a check that silently never runs, and that is a
gate quietly disappearing — the exact failure mode this project exists to
prevent, occurring inside the tool meant to prevent it.

Two things contain that hazard. First, :data:`CHECK_MODULES` is an explicit,
ordered list rather than a package walk, so the load order (and therefore the
gate's output order) is deliberate. Second, celebrimbor's own test suite walks
this package on disk and asserts every module defining a ``@check`` appears in
that list — so forgetting to add one is caught by a test, not by nobody.

Order matters twice over: cheap checks first, so a fast tier surfaces its
failures early; and ``terminal`` last, because the completeness check compares
the accumulated report against the registry and must therefore run after
everything it is checking.
"""

from __future__ import annotations

CHECK_MODULES: tuple[str, ...] = (
    "meta",
    "structure",
    "surface",
    "knownbad",
    "markers",
    "evidence",
    "producers",
    "invariants",
    "impact",
    "imports",
    "ratchets",
    "commodity",
    "terminal",
)

_loaded = False


def load_all() -> None:
    """Import every check module exactly once. Idempotent."""
    global _loaded
    if _loaded:
        return
    import importlib

    for name in CHECK_MODULES:
        importlib.import_module(f"{__name__}.{name}")
    _loaded = True


def _reset_for_tests() -> None:
    """Allow a test to force a re-import cycle. Not part of the public API."""
    global _loaded
    _loaded = False
