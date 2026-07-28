"""Surface-map serialization round-trips, including the awkward pins.

A shape-pin is a hex digest, and roughly one digest in two hundred lands in the
digits 0-9 only. Written unquoted, YAML reads such a pin back as an *integer*,
and the loader — which demands a string — then refuses the entire map. This was
found by pointing celebrimbor at its own source: one of its 49 modules pinned to
an all-digit hash and the whole obligation engine went dark. The falsifier is here so it
stays fixed.
"""

from __future__ import annotations

from pathlib import Path

from celebrimbor.roles import Role
from celebrimbor.surface.map import SurfaceRow, load_map, render_map


def _roundtrip(row: SurfaceRow, tmp_path: Path) -> SurfaceRow:
    path = tmp_path / "surfaces.yaml"
    path.write_text(render_map({row.module: row}), encoding="utf-8")
    return load_map(path).rows[row.module]


def test_all_digit_pin_survives_the_round_trip(tmp_path: Path) -> None:
    """The bug: an all-numeric pin must come back a string, not an int."""
    row = SurfaceRow(
        module="widgets", role=Role.PARSER, status="ratified", pin="775376418253"
    )
    back = _roundtrip(row, tmp_path)
    assert back.pin == "775376418253"
    assert isinstance(back.pin, str)


def test_ordinary_hex_pin_survives_the_round_trip(tmp_path: Path) -> None:
    """The common case must keep working alongside the fix."""
    row = SurfaceRow(module="widgets", role=Role.PARSER, status="ratified", pin="a1b2c3d4e5f6")
    assert _roundtrip(row, tmp_path).pin == "a1b2c3d4e5f6"


def test_role_and_overrides_survive_the_round_trip(tmp_path: Path) -> None:
    """A quoted pin must not disturb the rest of the row."""
    row = SurfaceRow(
        module="widgets",
        role=Role.PARSER,
        status="ratified",
        pin="0123456789ab",
        overrides={"widgets:serialize": (Role.PRODUCER, "ratified")},
    )
    back = _roundtrip(row, tmp_path)
    assert back.role is Role.PARSER
    assert back.overrides["widgets:serialize"][0] is Role.PRODUCER
