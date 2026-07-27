"""The coverage ratchet: a per-module floor that may only rise.

The comparison is a pure function of two dicts — current coverage and the
committed floors — so the interesting logic is testable without running a
single test or a coverage tool. Acquiring the current numbers (shelling out to
``coverage``) is the gate's job; deciding what they *mean* is here.

The low-floor meta-ratchet lives here too: a floor recorded below the
configured threshold is a regression against the *policy*, not against the last
run, and it is red until a human writes down why. Auto-baselining a module at
12% and calling it green is exactly the false-green the ratchet exists to
prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..surface.inventory import dotted_name
from ..yamlio import dump, expect_mapping, load_mapping
from .baseline import RatchetError, require_pinned, require_reason

BASELINE_VERSION = 1


@dataclass(frozen=True, slots=True)
class CoverageBaseline:
    """Committed per-module coverage floors."""

    floors: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    environment: str = "unknown"
    tool: str = "unknown"
    version: int = BASELINE_VERSION

    def floor_for(self, module: str, default: float) -> float:
        return self.floors.get(module, default)


@dataclass(frozen=True, slots=True)
class Regression:
    """One module that fell below what it owes."""

    module: str
    current: float
    floor: float
    kind: str
    """``"drop"`` (fell below its committed floor) or ``"low-floor"`` (floor is
    below policy and unexplained) or ``"new-below-policy"`` (a new module under
    the global floor with no reason)."""

    @property
    def message(self) -> str:
        if self.kind == "drop":
            return (
                f"{self.module} coverage is {self.current:.1f}%, below its floor of "
                f"{self.floor:.1f}% — coverage may only rise"
            )
        if self.kind == "low-floor":
            return (
                f"{self.module} has a coverage floor of {self.floor:.1f}%, below the "
                f"configured minimum, with no recorded reason"
            )
        return (
            f"{self.module} is new at {self.current:.1f}% coverage, below the configured "
            f"minimum of {self.floor:.1f}%, with no recorded reason"
        )


def parse_coverage_json(data: Any, source_prefix: str) -> dict[str, float]:
    """Turn coverage.py's JSON report into ``{dotted_module: percent}``.

    Keyed by dotted module name so it lines up with every other ledger. Files
    outside the source prefix are dropped — test files and tooling are not what
    a source-coverage floor is about.
    """
    if not isinstance(data, dict) or "files" not in data:
        raise RatchetError("coverage JSON has no `files` section; is this a coverage.py report?")
    prefix = Path(source_prefix)
    result: dict[str, float] = {}
    for filename, info in data["files"].items():
        rel = Path(filename)
        try:
            rel.relative_to(prefix)
        except ValueError:
            continue
        summary = info.get("summary", {}) if isinstance(info, dict) else {}
        percent = summary.get("percent_covered")
        if percent is None:
            continue
        dotted = dotted_name(rel, source_prefix)
        if dotted:
            result[dotted] = float(percent)
    return result


def coverage_regressions(
    current: dict[str, float],
    baseline: CoverageBaseline,
    *,
    minimum: float,
) -> list[Regression]:
    """Every way the current coverage violates the ratchet. Pure.

    Three violations, deliberately distinct so the remedy is unambiguous:

    * a module fell below its committed floor (the ratchet proper);
    * a committed floor sits below policy with no reason (the meta-ratchet);
    * a new module is below policy with no reason (new code must clear the bar).
    """
    regressions: list[Regression] = []

    for module, floor in baseline.floors.items():
        if floor < minimum and module not in baseline.reasons:
            regressions.append(Regression(module, floor, minimum, "low-floor"))

    for module, value in current.items():
        if module in baseline.floors:
            floor = baseline.floors[module]
            if value + 1e-9 < floor:
                regressions.append(Regression(module, value, floor, "drop"))
        elif value + 1e-9 < minimum and module not in baseline.reasons:
            regressions.append(Regression(module, value, minimum, "new-below-policy"))

    return regressions


def rebaseline(
    current: dict[str, float],
    previous: CoverageBaseline,
    *,
    minimum: float,
    reason: str | None,
    environment: str,
    tool: str,
    pinned: bool,
) -> CoverageBaseline:
    """Compute an updated baseline: floors rise to current, never silently fall.

    A floor that would *drop* (current below the committed floor) is only
    allowed with a reason, and the reason is recorded against that module so
    the next run's meta-ratchet does not re-flag it. Raising a floor needs no
    reason — improvement is always allowed.
    """
    require_pinned(pinned, action="take a coverage baseline")

    new_floors: dict[str, float] = {}
    new_reasons = dict(previous.reasons)
    lowered: list[str] = []

    for module, value in current.items():
        prior = previous.floors.get(module)
        if prior is not None and value + 1e-9 < prior:
            lowered.append(module)
        new_floors[module] = value if prior is None else max(prior, value)
        # A floor set below policy, or one being lowered, records the reason so
        # the next run's meta-ratchet does not re-flag an acknowledged case.
        if reason and (value < minimum or module in lowered):
            new_reasons[module] = reason

    if lowered and not reason:
        require_reason(reason, action=f"lower the coverage floor for {', '.join(sorted(lowered))}")

    return CoverageBaseline(
        floors=new_floors,
        reasons=new_reasons,
        environment=environment,
        tool=tool,
    )


def load_coverage_baseline(path: Path) -> CoverageBaseline:
    data = load_mapping(path, what="coverage baseline")
    floors_raw = expect_mapping(data.get("floors") or {}, where=f"{path}: floors")
    reasons_raw = expect_mapping(data.get("reasons") or {}, where=f"{path}: reasons")
    try:
        floors = {str(k): float(v) for k, v in floors_raw.items()}
    except (TypeError, ValueError) as exc:
        raise RatchetError(f"{path}: floors must be module -> number: {exc}") from exc
    return CoverageBaseline(
        floors=floors,
        reasons={str(k): str(v) for k, v in reasons_raw.items()},
        environment=str(data.get("environment", "unknown")),
        tool=str(data.get("tool", "unknown")),
        version=int(data.get("version", BASELINE_VERSION)),
    )


def write_coverage_baseline(path: Path, baseline: CoverageBaseline) -> None:
    payload: dict[str, Any] = {
        "version": baseline.version,
        "environment": baseline.environment,
        "tool": baseline.tool,
        "floors": {k: round(v, 2) for k, v in sorted(baseline.floors.items())},
    }
    if baseline.reasons:
        payload["reasons"] = dict(sorted(baseline.reasons.items()))
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# celebrimbor coverage ratchet — floors may only rise. Taken in CI.\n"
    path.write_text(header + dump(payload), encoding="utf-8")
