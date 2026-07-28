"""Ratifying a surface row: confirm the role, and pin it to the code.

Ratification is a command rather than a hand edit for one reason — it has two
halves, and a human can only do one of them. Flipping ``inferred`` to
``ratified`` is the judgment, and only a person can make it. Stamping the
shape-pin is bookkeeping, and a person cannot compute a blake2s digest in their
head. Leaving the pin to be typed by hand would mean it was usually absent, and
an absent pin is the drift hole it exists to close.

The file is rewritten line by line rather than parsed and re-emitted. That is
not an optimisation: ``yaml.safe_dump`` would discard every comment in the
file, including the adopter's own notes about *why* a row is what it is. Those
comments are frequently the only record of a judgment call, and a tool that
silently deletes them is a tool people stop running.

The work is split into three passes — slice the file into blocks, rewrite the
blocks we own, classify what changed — because doing all three in one loop
meant a closure mutating three variables its caller also read, which is exactly
as easy to get wrong as it sounds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_MODULE_LINE = re.compile(r"^  (?P<name>[\w.]+):\s*(?:#.*)?$")
_FIELD_LINE = re.compile(r"^    (?P<key>\w+):\s*(?P<value>[^#]*?)\s*(?P<comment>#.*)?$")

RATIFIED = "ratified"


@dataclass(slots=True)
class RatifyOutcome:
    """What ratify changed."""

    ratified: list[str] = field(default_factory=list)
    repinned: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unknown

    @property
    def touched(self) -> bool:
        return bool(self.ratified or self.repinned)

    def lines(self) -> list[str]:
        out: list[str] = []
        out.extend(f"  ratified  {m}" for m in self.ratified)
        out.extend(f"  re-pinned {m} (shape had drifted)" for m in self.repinned)
        out.extend(f"  unchanged {m}" for m in self.unchanged)
        out.extend(f"  UNKNOWN   {m} — not in the surface map" for m in self.unknown)
        return out or ["  nothing to do"]


@dataclass(frozen=True, slots=True)
class _Block:
    """One module's lines, or a run of lines belonging to no module."""

    module: str | None
    lines: list[str]


@dataclass(frozen=True, slots=True)
class _BlockState:
    """What a block said before we rewrote it."""

    was_ratified: bool
    had_pin: bool
    pin_matched: bool


def _split_blocks(lines: list[str]) -> list[_Block]:
    """Slice the file into per-module blocks, preserving everything else."""
    blocks: list[_Block] = []
    module: str | None = None
    current: list[str] = []

    for line in lines:
        match = _MODULE_LINE.match(line)
        if match:
            blocks.append(_Block(module, current))
            module, current = match["name"], [line]
        elif module is not None and (line.startswith("    ") or not line.strip()):
            current.append(line)
        else:
            blocks.append(_Block(module, current))
            module, current = None, [line]
    blocks.append(_Block(module, current))
    return [b for b in blocks if b.lines]


def _rewrite(lines: list[str], pin: str | None) -> tuple[list[str], _BlockState]:
    """Set status to ratified and stamp the pin, leaving other lines alone."""
    out: list[str] = []
    status_index: int | None = None
    was_ratified = False
    had_pin = False
    pin_matched = False

    for line in lines:
        match = _FIELD_LINE.match(line)
        if match is None:
            out.append(line)
            continue
        key, value = match["key"], match["value"].strip()
        if key == "status":
            status_index = len(out)
            was_ratified = value == RATIFIED
            out.append(f"    status: {RATIFIED}")
        elif key == "pin":
            had_pin = True
            # Compare against the unquoted digest: an existing pin is written
            # quoted (so an all-digit hash survives YAML), so strip the quotes
            # before matching, or a re-ratify would always look like a re-pin.
            pin_matched = pin is not None and value.strip('"') == pin
            out.append(f'    pin: "{pin}"' if pin else line)
        else:
            out.append(line)

    if pin and not had_pin and status_index is not None:
        out.insert(status_index + 1, f'    pin: "{pin}"')

    return out, _BlockState(was_ratified, had_pin, pin_matched)


def _record(outcome: RatifyOutcome, module: str, state: _BlockState) -> None:
    """Classify what this block's rewrite amounted to."""
    if not state.was_ratified:
        outcome.ratified.append(module)
    elif state.had_pin and state.pin_matched:
        outcome.unchanged.append(module)
    else:
        outcome.repinned.append(module)


def apply(path: Path, pins: dict[str, str], *, only: set[str] | None = None) -> RatifyOutcome:
    """Set ``status: ratified`` and stamp ``pin:`` for the named modules.

    ``pins`` maps module -> current shape digest. ``only`` restricts the
    operation; ``None`` means every module the map mentions.

    A module in ``only`` that the map does not contain is reported rather than
    silently ignored, because "I ratified it" followed by nothing happening is
    how a human comes to believe a row is confirmed when it is not.
    """
    outcome = RatifyOutcome()
    blocks = _split_blocks(path.read_text(encoding="utf-8").splitlines())
    targets = set(pins) if only is None else set(only)

    result: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        if block.module is None or block.module not in targets:
            result.extend(block.lines)
            continue
        seen.add(block.module)
        rewritten, state = _rewrite(block.lines, pins.get(block.module))
        result.extend(rewritten)
        _record(outcome, block.module, state)

    outcome.unknown = sorted(targets - seen)
    if outcome.touched:
        path.write_text("\n".join(result) + "\n", encoding="utf-8")
    return outcome
