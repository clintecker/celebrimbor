"""The pure core of `celebrimbor watch` — what to watch, and when to act.

`watch` re-runs the fast gate whenever a relevant file changes, so drift
surfaces the instant it is introduced instead of two minutes into CI. This
module holds the *decisions* that inner loop makes — which files matter
(:func:`is_relevant`), whether the file set moved between two polls
(:func:`changed`), and what a single iteration does (:func:`step`) — and holds
nothing else. The ambient filesystem I/O it is a decision *about* — globbing a
tree, reading mtimes, sleeping between polls — lives in the CLI adapter, the
one role permitted to reach for a capability without being handed it.

Splitting it this way is the same discipline the harness enforces on every
other module: a function that polls the disk has a behaviour no test can reach,
because there is no seam to reach it through. So the polling is isolated behind
an injected callable and everything worth asserting about — the relevance
filter, the change detection, the one-iteration loop body — takes its world as
an argument and is unit-tested directly, without a loop that never ends.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

Snapshot = Mapping[Path, float]
"""A watched file set as ``{repo-relative path: mtime}``. Two of these, taken a
poll apart, are all :func:`changed` needs to tell whether anything moved."""

OnChange = Callable[[set[Path]], None]
"""What :func:`step` does when a relevant file changed: injected, so a test can
pass a spy and the whole loop's logic is verified without a real gate run."""

_CONFIG_FILES = frozenset({"celebrimbor.toml", "pyproject.toml"})
_LEDGER_DIR = ".celebrimbor"


def is_relevant(rel_path: Path, *, source: str, tests: str) -> bool:
    """Does a change to this repo-relative path warrant re-running the gate?

    Relevant: a ``.py`` file under the source or tests tree; either config file
    at the root; any ``.celebrimbor`` YAML — a ledger at the top *or* a baseline
    nested beneath it, because a fast check reads the structure baseline, so an
    edit there moves the fast verdict and a watch that missed it would sit on a
    stale green. The one exclusion is the cache, whose churn from the gate's own
    runs would re-trigger the loop. Everything else — a README edit, a build
    artifact, a compiled ``.pyc`` — is ignored, because re-running the gate on an
    irrelevant save is exactly how an inner-loop tool teaches you to close it.
    """
    if len(rel_path.parts) == 1 and rel_path.name in _CONFIG_FILES:
        return True
    if rel_path.parts and rel_path.parts[0] == _LEDGER_DIR:
        return rel_path.suffix == ".yaml" and "cache" not in rel_path.parts
    if rel_path.suffix == ".py":
        return _under(rel_path, source) or _under(rel_path, tests)
    return False


def _under(rel_path: Path, prefix: str) -> bool:
    """Is ``rel_path`` inside the directory named by ``prefix``?"""
    parts = Path(prefix).parts
    return rel_path.parts[: len(parts)] == parts


def changed(old: Snapshot, new: Snapshot) -> set[Path]:
    """Paths that were added, removed, or whose mtime moved between snapshots.

    Empty exactly when the two snapshots agree on every path and time — the
    property that lets a poll with no edits do nothing at all.
    """
    moved = {path for path, mtime in new.items() if old.get(path) != mtime}
    removed = {path for path in old if path not in new}
    return moved | removed


def step(
    previous: Snapshot,
    current: Snapshot,
    *,
    source: str,
    tests: str,
    on_change: OnChange,
) -> Snapshot:
    """One watch iteration: if a *relevant* file moved, invoke ``on_change``.

    Returns ``current`` so the caller can carry it forward as the next
    baseline. The re-run-and-render is injected as ``on_change`` rather than
    performed here, which is what keeps this pure: a test drives one iteration
    with a spy in place of a real gate run, and the loop's entire logic — detect
    the relevant delta, fire once, advance — is proved without ever entering the
    loop the CLI wraps it in.
    """
    delta = {p for p in changed(previous, current) if is_relevant(p, source=source, tests=tests)}
    if delta:
        on_change(delta)
    return current
