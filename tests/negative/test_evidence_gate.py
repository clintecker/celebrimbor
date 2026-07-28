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


def test_seam_wrapper_delegating_to_an_adapter_is_fine(project: Project) -> None:
    """#6.1: a wrapper whose one I/O op lives one module deeper is still an adapter.

    `post_json` touches no capability itself — it delegates to `adapters.post`.
    Because `adapters` is an adapter-classified module, the delegation counts as
    adapting, so the honest `adapter` role is not contradicted.
    """
    project.module(
        "app.adapters",
        '''
        """The capability seam."""

        from __future__ import annotations

        import urllib.request


        def post(url: str, data: bytes) -> bytes:
            """The one real syscall."""
            return urllib.request.urlopen(url, data).read()
        ''',
    )
    project.module(
        "app.commission",
        '''
        """A seam-wrapper."""

        from __future__ import annotations

        from app.adapters import post


        def post_json(url: str, data: bytes) -> bytes:
            """Delegate to the seam; no syscall here."""
            return post(url, data)
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.adapters:
            role: adapter
            status: ratified
          app.commission:
            role: adapter
            status: ratified
        """
    )
    _pin_all(project)
    assert project.run(_EVIDENCE).verdict is Verdict.PASS


def test_fs_read_in_a_comprehension_satisfies_adapter(project: Project) -> None:
    """#6.2: `path.read_bytes()` inside a comprehension is a real fs op."""
    project.module(
        "app.images",
        '''
        """Reads reference images."""

        from __future__ import annotations

        from pathlib import Path


        def style_references(paths: list[str]) -> list[bytes]:
            """Read each ref — a variable receiver inside a comprehension."""
            return [Path(p).read_bytes() for p in paths]
        ''',
    )
    project.surfaces(
        "version: 1\nmodules:\n  app.images:\n    role: adapter\n    status: ratified\n"
    )
    _pin_all(project)
    assert project.run(_EVIDENCE).verdict is Verdict.PASS


def test_stateful_fake_may_be_an_adapter(project: Project) -> None:
    """#6.3: a stateful in-memory fake IS the injected backend, so it may be an adapter."""
    project.module(
        "app.fakes",
        '''
        """In-memory test doubles."""

        from __future__ import annotations


        class FakeProvider:
            """A fake backend that a real adapter Protocol stands in for."""

            def __init__(self) -> None:
                self._submitted: list[str] = []

            def submit(self, job: str) -> None:
                """Mutate own state — no ambient capability, but it IS the backend."""
                self._submitted.append(job)
        ''',
    )
    project.surfaces(
        "version: 1\nmodules:\n  app.fakes:\n    role: adapter\n    status: ratified\n"
    )
    _pin_all(project)
    assert project.run(_EVIDENCE).verdict is Verdict.PASS


def test_inert_function_mislabeled_adapter_is_still_red(project: Project) -> None:
    """The escape stays closed: pure computation dressed as an adapter is refused.

    None of the three new signals fire — no capability, no injected call, no
    delegation to an adapter module, no state — so declaring `adapter` to obtain
    the open capability budget is still contradicted.
    """
    project.module(
        "app.fake_adapter",
        '''
        """Not actually a boundary."""

        from __future__ import annotations


        def shape_for(text: str) -> str:
            """Pure string work wearing an adapter's clothes."""
            return text.strip().upper()
        ''',
    )
    project.surfaces(
        "version: 1\nmodules:\n  app.fake_adapter:\n    role: adapter\n    status: ratified\n"
    )
    _pin_all(project)
    result = project.run(_EVIDENCE)
    assert result.verdict is Verdict.FAIL
    assert any("not adapting anything" in f.message for f in result.findings)


def test_io_verb_call_satisfies_adapter(project: Project) -> None:
    """#6: a call to an I/O-verb method (`transport.get`, `client.post_json`) adapts.

    Catches backend interaction the capability patterns miss — an injected
    transport, or a compound verb like `post_json` — without needing the seam
    module classified.
    """
    project.module(
        "app.lookup",
        '''
        """Looks things up over an injected transport."""

        from __future__ import annotations


        def lookup_lccn(transport: object, raw: str) -> dict:
            """Fetch via the injected transport — an I/O verb on a param."""
            return transport.get(f"/lccn/{raw}")
        ''',
    )
    project.surfaces(
        "version: 1\nmodules:\n  app.lookup:\n    role: adapter\n    status: ratified\n"
    )
    _pin_all(project)
    assert project.run(_EVIDENCE).verdict is Verdict.PASS


def test_delegation_to_a_same_module_io_helper_satisfies_adapter(project: Project) -> None:
    """#6: a wrapper delegating to a private same-module helper that does the I/O."""
    project.module(
        "app.registry",
        '''
        """Registry lookups, request extracted into a helper."""

        from __future__ import annotations


        def _fetch(transport: object, path: str) -> bytes:
            """The private helper that does the syscall."""
            return transport.get(path)


        def lookup(transport: object, ident: str) -> bytes:
            """Delegate to the I/O helper — no syscall here."""
            return _fetch(transport, f"/{ident}")
        ''',
    )
    project.surfaces(
        "version: 1\nmodules:\n  app.registry:\n    role: adapter\n    status: ratified\n"
    )
    _pin_all(project)
    assert project.run(_EVIDENCE).verdict is Verdict.PASS
