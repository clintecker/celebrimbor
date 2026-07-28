"""The object every check receives.

``Context`` is deliberately thin: a project root, resolved config, the stage
being run, and a memo table. The memo table is what makes the ~10s fast stage
possible — the surface inventory is an AST walk over the whole source tree and
several gates need it, so it is computed once per run and shared.

The memo is keyed by string and stores whatever the producer put there. That
is loose typing on purpose: engines own their own cache keys, and the
alternative (a field per cached artifact) would make ``Context`` import every
engine and turn the module graph into a knot.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from .config import Config
from .result import Stage

if TYPE_CHECKING:
    from .result import GateReport

T = TypeVar("T")

_DIFF_TIMEOUT_S = 20


@dataclass(slots=True)
class Context:
    """Everything a check is allowed to know about the run."""

    config: Config
    stage: Stage = Stage.FAST
    diff_base: str | None = None
    """Git ref the impact gate diffs against. ``None`` means "work out the
    merge base with the default branch," which is what a PR wants."""

    partial: GateReport | None = None
    """The report accumulated so far. Only the terminal completeness check
    reads this; ordinary checks must not, because a check that branches on
    other checks' results is a check whose falsifier no longer isolates it."""

    update_baselines: bool = False
    update_reason: str | None = None

    _memo: dict[str, object] = field(default_factory=dict, repr=False)

    @property
    def root(self) -> Path:
        return self.config.root

    # -- shared computation -------------------------------------------------

    def memo(self, key: str, produce: Callable[[], T]) -> T:
        """Compute ``produce()`` once per run and reuse it.

        Exceptions are not cached: a transient failure should not poison the
        rest of the run into a false conclusion.
        """
        if key in self._memo:
            cached: object = self._memo[key]
            return cached  # type: ignore[return-value]
        value = produce()
        self._memo[key] = value
        return value

    # -- git ----------------------------------------------------------------

    def changed_files(self) -> tuple[Path, ...] | None:
        """Repo-relative paths changed against the diff base.

        Returns ``None`` — not an empty tuple — when the diff cannot be
        determined (not a repo, git absent, unknown base). The distinction
        matters: an empty tuple means "nothing changed, and we know it," which
        lets the impact gate pass; ``None`` means "we could not tell," which
        the impact gate must treat as ``REFUSED``. Collapsing the two would
        make a broken git invocation read as a clean diff.
        """
        return self.memo("git.changed_files", self._compute_changed_files)

    def _compute_changed_files(self) -> tuple[Path, ...] | None:
        base = self.diff_base or self._merge_base()
        if base is None:
            return None
        out = self._git("diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD")
        if out is None:
            # Fall back to a plain two-dot diff; `...` fails when the base is
            # not an ancestor, which happens on a freshly rebased branch.
            out = self._git("diff", "--name-only", "--diff-filter=ACMR", base)
        if out is None:
            return None
        return tuple(Path(line) for line in out.splitlines() if line.strip())

    def _merge_base(self) -> str | None:
        head = self._git("rev-parse", "--abbrev-ref", "HEAD")
        for candidate in ("origin/main", "origin/master", "main", "master"):
            if head is not None and head.strip() == candidate.rsplit("/", 1)[-1]:
                continue
            base = self._git("merge-base", candidate, "HEAD")
            if base:
                return base.strip()
        return None

    def _git(self, *args: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.root), *args],
                capture_output=True,
                text=True,
                timeout=_DIFF_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout

    def is_git_repo(self) -> bool:
        return self._git("rev-parse", "--git-dir") is not None

    # -- convenience --------------------------------------------------------

    @classmethod
    def for_root(
        cls,
        root: Path | str | None = None,
        *,
        stage: str | Stage = Stage.FAST,
        **kwargs: object,
    ) -> Context:
        return cls(config=Config.load(root), stage=Stage.parse(stage), **kwargs)  # type: ignore[arg-type]
