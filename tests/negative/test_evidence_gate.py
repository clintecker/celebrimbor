"""Negative fixtures for the role-evidence and ratification-pin gates.

These two answer different questions and the tests are organised to keep that
visible: evidence catches a role that was *always* wrong, the pin catches a
role that *stopped being right*. A fixture that conflated them would let either
gate rot while the other kept the suite green.
"""

from __future__ import annotations

import pytest

from celebrimbor.result import Verdict
from tests.conftest import Project, _pin_all

pytestmark = pytest.mark.negative

_EVIDENCE = "celebrimbor.surface.evidence"
_PIN = "celebrimbor.surface.pin"


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


def test_verifier_that_cannot_fail_is_red(toy: Project) -> None:
    """The blind verifier, detected statically.

    A verifier whose every return path is a truthy literal, with no raise, has
    no failing path at all. It cannot turn red, so it inspects nothing — and
    that is precisely the failure this whole project is organised around.
    """
    assert toy.run(_EVIDENCE).verdict is Verdict.PASS

    toy.module(
        "app.checking",
        '''
        """Verifying, allegedly."""

        from __future__ import annotations


        def verify_row(row: dict[str, str]) -> bool:
            """Always happy."""
            del row
            return True
        ''',
    )
    _pin_all(toy)

    result = toy.run(_EVIDENCE)
    assert result.verdict is Verdict.FAIL
    assert "role-contradicted" in codes(result)
    assert any("can never turn red" in f.message for f in result.findings)


def test_parser_that_cannot_refuse_is_red(toy: Project) -> None:
    """A parser with no failing path at all cannot reject malformed input.

    The council's rule: `parser` and `verifier` owe the same thing — a reachable
    failing path. This parser always returns a non-empty dict and never raises,
    so it has no failing path and genuinely cannot refuse. Still red.
    """
    toy.module(
        "app.parsing",
        '''
        """Parsing, permissively."""

        from __future__ import annotations


        def parse_row(raw: str) -> dict[str, str]:
            """Never says no."""
            return {"raw": raw}
        ''',
    )
    _pin_all(toy)

    result = toy.run(_EVIDENCE)
    assert result.verdict is Verdict.FAIL
    assert any("refuse malformed input" in f.message for f in result.findings)


def test_parser_that_refuses_by_value_passes(toy: Project) -> None:
    """The council's core decision: refusal-by-value is refusal.

    A parser that refuses malformed input by *returning* an error-encoding value
    — the fail-closed-by-value style celebrimbor uses in its own ladder — has a
    reachable failing path and must NOT be flagged. Before this fix, `not
    f.raises` false-flagged every total, error-returning parser; the rule now
    keys on `all_returns_truthy` (the verifier's own predicate), which this
    parser does not trip because it returns a variable, not a truthy literal.
    """
    toy.module(
        "app.parsing",
        '''
        """Parsing, fail-closed by value."""

        from __future__ import annotations

        from dataclasses import dataclass


        @dataclass
        class Parsed:
            """Either a value or a refusal, in the value channel."""

            value: dict[str, str] | None = None
            unreadable: str | None = None


        def parse_row(raw: str) -> Parsed:
            """Refuse malformed input by returning, not raising."""
            if "=" not in raw:
                return Parsed(unreadable=f"no '=' in {raw!r}")
            key, _, value = raw.partition("=")
            return Parsed(value={key: value})
        ''',
    )
    _pin_all(toy)

    result = toy.run(_EVIDENCE)
    assert result.verdict is Verdict.PASS, (
        "a parser that refuses by returning an error value has a failing path and is "
        "not blind; flagging it was the category error the council removed"
    )


def test_adapter_that_adapts_nothing_is_red(project: Project) -> None:
    """Closes the escape where `adapter` is declared to widen the capability budget.

    `adapter` is the one role with an unrestricted budget, so declaring it
    without a boundary to adapt silently disables the injection gate. That has
    to cost something, or it is the obvious way to make the gate quiet.
    """
    project.module(
        "app.fake",
        '''
        """Not actually a boundary."""

        from __future__ import annotations


        def send_message(text: str) -> str:
            """Pure string work wearing an adapter's clothes."""
            return text.strip().upper()
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.fake:
            role: adapter
            status: ratified
        """
    )
    _pin_all(project)

    result = project.run(_EVIDENCE)
    assert result.verdict is Verdict.FAIL
    assert any("not adapting anything" in f.message for f in result.findings)


def test_shape_drift_unratifies_row(toy: Project) -> None:
    """Ratification binds to the code it ratified.

    This is the answer to "someone edits it into something more complex and
    never reclassifies it": the role, the name and the capability set are all
    unchanged, so every other gate stays green. Only the pin notices.
    """
    assert toy.run(_PIN).verdict is Verdict.PASS

    toy.module(
        "app.parsing",
        '''
        """Parsing, now considerably more involved."""

        from __future__ import annotations


        class MalformedError(ValueError):
            """Bad input."""


        def parse_row(raw: str) -> dict[str, str]:
            """Parse `k=v`, with a pile of new special cases."""
            if not raw:
                raise MalformedError("empty")
            if raw.startswith("#"):
                raw = raw[1:]
            if raw.endswith(";"):
                raw = raw[:-1]
            if len(raw) > 200:
                raw = raw[:200]
            for candidate in ("==", "=", ":"):
                if candidate in raw:
                    break
            if "=" not in raw:
                raise MalformedError(raw)
            key, _, value = raw.partition("=")
            return {key.strip(): value.strip()}
        ''',
    )

    result = toy.run(_PIN)
    assert result.verdict is Verdict.FAIL
    assert "pin-drift" in codes(result)

    # The point of the separation: nothing else noticed.
    assert toy.run(_EVIDENCE).verdict is Verdict.PASS
    assert toy.run("celebrimbor.surface.naming").verdict is Verdict.PASS


def test_cosmetic_edits_do_not_break_the_pin(toy: Project) -> None:
    """The pin covers character, not content.

    Without this the pin would redden on every commit, and a gate that reddens
    on every commit is a gate that gets turned off within a week. Renaming a
    local and rewording a docstring must be free.
    """
    toy.module(
        "app.parsing",
        '''
        """Parsing. (Docstring reworded, local renamed, nothing else.)"""

        from __future__ import annotations


        class MalformedError(ValueError):
            """Input we refuse."""


        def parse_row(text: str) -> dict[str, str]:
            """Parse `k=v` and refuse anything else at all."""
            if "=" not in text:
                raise MalformedError(text)
            name, _, contents = text.partition("=")
            return {name: contents}
        ''',
    )
    assert toy.run(_PIN).verdict is Verdict.PASS


def test_ratified_but_unpinned_row_is_red(toy: Project) -> None:
    """A hand-ratified row with no pin has no drift protection, so it is red."""
    toy.surfaces(
        """
        version: 1
        modules:
          app.parsing:
            role: parser
            status: ratified
          app.checking:
            role: verifier
            status: ratified
        """
    )
    result = toy.run(_PIN)
    assert result.verdict is Verdict.FAIL
    assert "pin-missing" in codes(result)
    assert any("celebrimbor ratify" in (f.hint or "") for f in result.findings)
