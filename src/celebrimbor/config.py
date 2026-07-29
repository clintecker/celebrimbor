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
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
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
        ``pyproject.toml``. Neither existing is normal and fine.
        """
        base = Path(root or Path.cwd()).resolve()
        data = _read_config_data(base)
        cfg = cls(root=base)
        if not data:
            return replace(cfg, source=_infer_source_layout(base))
        return _apply(cfg, data, base)

    def with_overrides(self, **kwargs: Any) -> Config:
        return replace(self, **kwargs)


def _read_config_data(root: Path) -> dict[str, Any]:
    dedicated = root / CONFIG_FILENAME
    if dedicated.is_file():
        # A dedicated file may either be flat or nest everything under
        # [celebrimbor]. Both read the same way to an adopter, so both work.
        data = _load_toml(dedicated)
        nested = data.get("celebrimbor")
        return nested if isinstance(nested, dict) else data
    pyproject = root / PYPROJECT
    if pyproject.is_file():
        tool = _load_toml(pyproject).get("tool", {})
        if isinstance(tool, dict) and isinstance(tool.get("celebrimbor"), dict):
            return dict(tool["celebrimbor"])
    return {}


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: not valid TOML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{path}: could not be read: {exc}") from exc


def _infer_source_layout(root: Path) -> str:
    """Guess the source prefix when no config says.

    Prefers a ``src/`` layout, then a single top-level package directory. If
    neither is obvious we return ``"src"`` and let the surface inventory
    report an empty tree — which the audit reads as ``REFUSED``, not as a
    clean bill of health.
    """
    if (root / "src").is_dir():
        return "src"
    candidates = [
        p
        for p in root.iterdir()
        if p.is_dir()
        and (p / "__init__.py").is_file()
        and not p.name.startswith((".", "_"))
        and p.name not in {"tests", "test", "docs"}
    ]
    if len(candidates) == 1:
        return candidates[0].name
    return "src"


def _as_str(value: Any, key: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string, got {type(value).__name__}")
    return value


def _as_bool(value: Any, key: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false, got {type(value).__name__}")
    return value


def _as_floor(value: Any, key: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ConfigError(f"{key} must be a number, got {type(value).__name__}")
    if not 0.0 <= float(value) <= 100.0:
        raise ConfigError(f"{key} must be between 0 and 100, got {value}")
    return float(value)


def _as_str_tuple(value: Any, key: str) -> tuple[str, ...]:
    return tuple(_expect_str_list(value, key))


def _as_str_set(value: Any, key: str) -> frozenset[str]:
    return frozenset(_expect_str_list(value, key))


# One parser per configurable key. A table rather than a branch chain, so
# adding a setting is adding a row — and so the "unknown key" check below has
# a single source of truth about what is known.
_PARSERS: dict[str, Callable[[Any, str], Any]] = {
    "source": _as_str,
    "tests": _as_str,
    "known_bad": _as_str,
    "formatter": _as_str,
    "mutation_tool": _as_str,
    "mutation_survivors": _as_str,
    "trusted_environment": _as_bool,
    "pinned_environment": _as_bool,
    "import_check": _as_bool,
    "markers_cite_limitations": _as_bool,
    "min_coverage_floor": _as_floor,
    "exclude": _as_str_tuple,
    "check_modules": _as_str_tuple,
    "known_bad_checkers": lambda value, _key: _parse_known_bad_checkers(value),
    "disabled_checks": _as_str_set,
    "policy_roles": lambda value, key: _parse_policy_roles(value, key),
    "limits": lambda value, _key: _parse_limits(value),
    "paths": lambda value, _key: _parse_paths(value),
}


def _parse_policy_roles(value: Any, key: str) -> tuple[str, ...]:
    """Validate ``policy_roles`` against the real role names, fail loud on a typo.

    A misspelled role here would silently shrink what the impact gate governs —
    the adopter would believe a role is watched when it is not — so an unknown
    name is an error, not ignored.
    """
    from .roles import Role

    names = _expect_str_list(value, key)
    valid = {r.value for r in Role}
    unknown = [n for n in names if n not in valid]
    if unknown:
        raise ConfigError(
            f"{key}: unknown role(s) {', '.join(sorted(unknown))}. "
            f"Valid roles: {', '.join(sorted(valid))}"
        )
    return tuple(names)


_KNOWN_PATHS = frozenset(
    {
        "surfaces",
        "invariants",
        "producers",
        "coverage_baseline",
        "mutation_baseline",
        "structure_baseline",
    }
)


def _parse_paths(raw: Any) -> dict[str, str]:
    """Read ``[tool.celebrimbor.paths]`` — per-ledger path overrides.

    Unknown keys are an error, not ignored: a typo'd override (``invariant``
    for ``invariants``) would silently leave celebrimbor reading the default
    location while the adopter believed it was pointed elsewhere — a gate
    quietly checking the wrong file.
    """
    if not isinstance(raw, dict):
        raise ConfigError(f"paths must be a table, got {type(raw).__name__}")
    unknown = set(raw) - _KNOWN_PATHS
    if unknown:
        raise ConfigError(
            f"unknown path override(s): {', '.join(sorted(unknown))}. "
            f"Known: {', '.join(sorted(_KNOWN_PATHS))}"
        )
    return {key: _as_str(value, f"paths.{key}") for key, value in raw.items()}


def _parse_known_bad_checkers(raw: Any) -> dict[str, CheckerSpec]:
    """Read ``[tool.celebrimbor.known_bad_checkers.<name>]`` (issues #9, #10).

    Each entry needs exactly one of ``command`` (subprocess, with a ``{file}``
    placeholder) or ``callable`` (``module:function``, in-process), and may set a
    ``pattern`` (regex, first group = the code) and a ``match`` (``exact`` or
    ``substring``). A checker with neither, or both, is an error rather than a
    silently-inert one — the whole point is a checker that actually runs.
    """
    if not isinstance(raw, dict):
        raise ConfigError(f"known_bad_checkers must be a table, got {type(raw).__name__}")
    return {str(name): _checker_from(str(name), body) for name, body in raw.items()}


def _opt_str(value: Any, where: str) -> str | None:
    return _as_str(value, where) if value else None


def _checker_from(name: str, body: Any) -> CheckerSpec:
    if not isinstance(body, dict):
        raise ConfigError(f"known_bad_checkers.{name} must be a table, got {type(body).__name__}")
    command, call = body.get("command"), body.get("callable")
    if bool(command) == bool(call):
        raise ConfigError(
            f"known_bad_checkers.{name} needs exactly one of `command` (a {{file}} "
            "subprocess) or `callable` (a module:function run in-process)"
        )
    if command and "{file}" not in str(command):
        raise ConfigError(
            f"known_bad_checkers.{name}.command must contain the {{file}} placeholder, so "
            "the gate knows where to pass the fixture path"
        )
    match = str(body.get("match", "exact")).strip()
    if match not in {"exact", "substring"}:
        raise ConfigError(
            f"known_bad_checkers.{name}.match must be 'exact' or 'substring', got {match!r}"
        )
    return CheckerSpec(
        command=_opt_str(command, f"known_bad_checkers.{name}.command"),
        callable_ref=_opt_str(call, f"known_bad_checkers.{name}.callable"),
        code_pattern=_opt_str(body.get("pattern"), f"known_bad_checkers.{name}.pattern"),
        match=match,
    )


def _apply(cfg: Config, data: dict[str, Any], root: Path) -> Config:
    unknown = set(data) - set(_PARSERS)
    if unknown:
        raise ConfigError(
            f"unknown celebrimbor config key(s): {', '.join(sorted(unknown))}. "
            f"Known keys: {', '.join(sorted(_PARSERS))}"
        )
    updates = {key: _PARSERS[key](value, key) for key, value in data.items()}
    updates.setdefault("source", _infer_source_layout(root))
    return replace(cfg, **updates)


def _parse_limits(raw: Any) -> Limits:
    """Read ``[tool.celebrimbor.limits]``.

    Unknown keys are an error rather than ignored. A typo'd limit that is
    silently dropped reads as a configured budget that is quietly not being
    enforced — the adopter believes they set a ceiling and no ceiling exists.
    """
    if not isinstance(raw, dict):
        raise ConfigError(f"limits must be a table, got {type(raw).__name__}")
    known = {f.name for f in fields(Limits)}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(
            f"unknown limit(s): {', '.join(sorted(unknown))}. "
            f"Known limits: {', '.join(sorted(known))}"
        )
    values: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise ConfigError(f"limits.{key} must be an integer, got {type(value).__name__}")
        if value < 1:
            raise ConfigError(f"limits.{key} must be at least 1, got {value}")
        values[key] = value
    return Limits(**values)


def _expect_str_list(value: Any, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key} must be a list of strings")
    return list(value)
