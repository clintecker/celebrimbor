"""Configuration — for the exceptions only.

Convention supplies the rest. Every field here has a default that works on a
conventionally-laid-out Python project, and the file is optional. If an
adopter needs a ``celebrimbor.toml`` to get started, the conventions are
wrong and this module is the wrong place to fix it.

Two settings deserve a note because they are load-bearing for scars rather
than for taste:

``trusted_environment``
    The "promise." When true, a missing commodity tool is a hard failure
    rather than a skip. CI sets it (automatically, via ``CI=1``); a dev box
    does not. This is the entire mechanism behind the no-silent-skip scar.

``pinned_environment``
    Whether ratchets may take a baseline here. Defaults to the same signal.
    A dev-box baseline reads higher than CI's and hands the adopter a red CI
    on day two, so baselining off the pinned environment is simply refused.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .limits import Limits

CONFIG_FILENAME = "celebrimbor.toml"
PYPROJECT = "pyproject.toml"
STATE_DIR = ".celebrimbor"

# CI systems that identify themselves. Presence of any of these means "this is
# the pinned environment": tools are expected to exist, and baselines are
# allowed to be taken.
_CI_ENV_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "CIRCLECI")


class ConfigError(ValueError):
    """A config file exists but is unusable. Red — never fall back to defaults.

    Falling back to defaults on a malformed config is exactly the estimating
    behaviour the harness refuses: the adopter asked for something specific and
    we would silently do something else.
    """


def _detect_ci() -> bool:
    override = os.environ.get("CELEBRIMBOR_TRUSTED")
    if override is not None:
        return override.strip().lower() in {"1", "true", "yes", "on"}
    return any(os.environ.get(v, "").strip().lower() in {"1", "true"} for v in _CI_ENV_VARS)


@dataclass(frozen=True, slots=True)
class CheckerSpec:
    """How to run an app's own known-bad checker (issues #9, #10).

    Exactly one of two forms says *how* to run it:

    * ``command`` — a shell-style template with a ``{file}`` placeholder, run as
      a subprocess; ``code_pattern`` extracts diagnostic codes from its output
      (first regex group, or one per line if omitted).
    * ``callable_ref`` — ``"module:function"``, imported and called *in-process*
      as ``func(Path) -> Iterable[str]``, for a checker that has no clean
      per-file subprocess entry (book-context-bound linters, say).

    ``match`` says how the declared ``diagnostic`` is compared to what the
    checker emits: ``"exact"`` (default — an exact element of the emitted set) or
    ``"substring"`` (a substring of some emitted line, for linters that emit
    human phrases with a variable part). None of this weakens the three
    provenance guarantees; it only changes how a single line is produced and
    compared.
    """

    command: str | None = None
    callable_ref: str | None = None
    code_pattern: str | None = None
    match: str = "exact"


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved configuration for one project root."""

    root: Path

    source: str = "src"
    """Path prefix for application source. The impact gate and surface
    inventory are both parameterized on this rather than hardcoding a layout."""

    tests: str = "tests"
    known_bad: str = "tests/known-bad"

    trusted_environment: bool = field(default_factory=_detect_ci)
    pinned_environment: bool = field(default_factory=_detect_ci)

    min_coverage_floor: float = 60.0
    """The low-floor meta-ratchet threshold. A module whose auto-baselined
    floor lands below this is red until a human records a reason, so
    auto-baselining cannot freeze weak coverage as false green."""

    formatter: str = "ruff-format"
    mutation_tool: str = "mutmut"

    mutation_survivors: str = ""
    """An importable ``module:function`` returning the current surviving mutants
    as a ``frozenset[celebrimbor.Survivor]`` — an app's own deterministic mutation
    set, in place of running the ``mutation_tool``. Called in production so
    celebrimbor's survivor-identity ratchet (baseline, compare, reason-gated
    update) gates it. Empty means the mutation gate has no source and skips."""

    import_check: bool = False
    """Opt in to the runtime import-health check. Off by default because it is
    the one check that *imports* the application (everything else is AST-only),
    so a project must choose it. When true, every module is imported in an
    isolated subprocess and any import error or import-time side effect is red."""

    markers_cite_limitations: bool = False
    """Opt in to stricter marker grammar: an ``xfail``/``skip`` ``reason=`` must
    cite a limitation declared in the invariant ledger, so a *known gap* (declared,
    reviewable debt) cannot be confused with a shrug. Off by default — the base
    grammar only requires a reason to be present."""

    limits: Limits = field(default_factory=Limits)
    """Structural budgets — complexity, nesting, file length, classes per
    module. Configured as ``[tool.celebrimbor.limits]``; every key is optional
    and defaults to the value in :class:`~celebrimbor.structure.complexity.Limits`."""

    paths: dict[str, str] = field(default_factory=dict)
    """Per-file path overrides, so an app can keep its ledgers where it already
    has them instead of moving them under ``.celebrimbor/``. Configured as
    ``[tool.celebrimbor.paths]`` with any of: ``surfaces``, ``invariants``,
    ``producers``, ``coverage_baseline``, ``mutation_baseline``. This is the
    hook that lets an adopter with an existing ``quality/`` directory point
    celebrimbor at it rather than reorganise their repo — the whole point of
    convention-with-an-escape."""

    exclude: tuple[str, ...] = ()
    """Glob patterns excluded from the surface inventory."""

    check_modules: tuple[str, ...] = ()
    """Importable modules that register the app's own ``@check`` gates. The CLI
    imports each (after celebrimbor's builtins, before the run) so an adopter's
    domain checks run through ``celebrimbor gate`` itself, not only through a
    hand-rolled programmatic entry point. A module that cannot be imported is a
    hard, fail-closed error — a declared check that silently never runs is the
    exact failure mode this harness exists to prevent."""

    known_bad_checkers: dict[str, CheckerSpec] = field(default_factory=dict)
    """App-declared known-bad checkers, keyed by the name used in
    ``expected.yaml``. Lets a domain linter (not just ``ruff``/``mypy``) prove it
    still rejects its known-bad fixtures. See :class:`CheckerSpec`."""

    disabled_checks: frozenset[str] = frozenset()
    """Exceptions, on the record. Disabling a check is visible in every run."""

    policy_roles: tuple[str, ...] = ()
    """Which roles the change-impact gate treats as policy-bearing — a change to
    one of them with no governing invariant is a gap. Empty means the built-in
    default (``celebrimbor.roles.POLICY_ROLES``). Set it to match an existing
    harness's notion of a policy role, e.g.
    ``policy_roles = ["verifier", "parser", "producer", "adapter", "orchestrator"]``."""

    ambient_capabilities: tuple[str, ...] = ()
    """Capabilities that may be reached for *ambiently* by any role, because they
    are this app's tested domain medium rather than an injectable side effect — a
    file-processing tool tests its filesystem reads directly, say. Listed
    capabilities are still scanned and reported, just not a breach. Empty keeps
    the strict default (only ``adapter`` may touch any capability ambiently); an
    unknown capability name is an error, so the opt-in stays honest and on the
    record. The genuinely un-injectable ones (clock, network, …) should not go
    here — they have behaviour no test can reach."""

    # -- derived paths ------------------------------------------------------

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIR

    def _path(self, key: str, default: Path) -> Path:
        """A configured override for ``key``, or the conventional default.

        Overrides are resolved relative to the project root, so an adopter
        writes ``surfaces = "quality/surfaces.yaml"`` and celebrimbor reads
        exactly that file — no reorganising an existing layout to adopt.
        """
        override = self.paths.get(key)
        return (self.root / override) if override else default

    @property
    def surfaces_path(self) -> Path:
        return self._path("surfaces", self.state_dir / "surfaces.yaml")

    @property
    def invariants_path(self) -> Path:
        return self._path("invariants", self.state_dir / "invariants.yaml")

    @property
    def producers_path(self) -> Path:
        return self._path("producers", self.state_dir / "producers.yaml")

    @property
    def coverage_baseline_path(self) -> Path:
        return self._path("coverage_baseline", self.state_dir / "baselines" / "coverage.yaml")

    @property
    def mutation_baseline_path(self) -> Path:
        return self._path("mutation_baseline", self.state_dir / "baselines" / "mutation.yaml")

    @property
    def structure_baseline_path(self) -> Path:
        return self._path("structure_baseline", self.state_dir / "baselines" / "structure.yaml")

    @property
    def source_dir(self) -> Path:
        return self.root / self.source

    @property
    def tests_dir(self) -> Path:
        return self.root / self.tests

    @property
    def known_bad_dir(self) -> Path:
        return self.root / self.known_bad

    # -- loading ------------------------------------------------------------

    @classmethod
    def load(cls, root: Path | str | None = None) -> Config:
        """Read config for ``root``, falling back to convention.

        Precedence: ``celebrimbor.toml`` beats ``[tool.celebrimbor]`` in
        ``pyproject.toml``. Neither existing is normal and fine. The parsing
        itself lives in ``_config_load`` (imported here, not at module load, to
        keep this data module free of that machinery); this is the one seam.
        """
        from ._config_load import load_config

        return load_config(root)

    def with_overrides(self, **kwargs: Any) -> Config:
        return replace(self, **kwargs)
