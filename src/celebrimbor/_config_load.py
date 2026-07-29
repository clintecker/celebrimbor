"""Reading and validating a celebrimbor config into a :class:`Config`.

Split from ``config.py`` — which is the data (the frozen :class:`Config`, its
derived paths, :class:`CheckerSpec`) — so neither module hides two domains in one
file. ``Config.load`` imports :func:`load_config` here; nothing else does.

Every parser refuses rather than defaults: an unknown key, a mistyped value, a
bad table shape is a :class:`~celebrimbor.config.ConfigError`, never a silent
fall-back — the adopter asked for something specific.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from .config import CONFIG_FILENAME, PYPROJECT, CheckerSpec, Config, ConfigError
from .limits import Limits


def load_config(root: Path | str | None = None) -> Config:
    """The body of :meth:`Config.load`: read, validate, and apply, or convention."""
    base = Path(root or Path.cwd()).resolve()
    data = _read_config_data(base)
    cfg = Config(root=base)
    if not data:
        return replace(cfg, source=_infer_source_layout(base))
    return _apply(cfg, data, base)


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
    "ambient_capabilities": lambda value, key: _parse_ambient_capabilities(value, key),
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


def _parse_ambient_capabilities(value: Any, key: str) -> tuple[str, ...]:
    """Validate ``ambient_capabilities`` against the real capability names.

    A typo here would silently exempt nothing while the adopter believed a
    capability was allowed ambiently, so an unknown name is an error, not
    ignored — the same loud-on-a-typo rule as ``policy_roles``.
    """
    from .structure.capabilities import Capability

    names = _expect_str_list(value, key)
    valid = {c.value for c in Capability}
    unknown = [n for n in names if n not in valid]
    if unknown:
        raise ConfigError(
            f"{key}: unknown capabilit(y/ies) {', '.join(sorted(unknown))}. "
            f"Valid capabilities: {', '.join(sorted(valid))}"
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
