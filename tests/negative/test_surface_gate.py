"""Negative fixtures for the surface gates.

Each test here is named by a ``falsified_by=`` somewhere in the source. That is
not a coincidence and it is not documentation: ``celebrimbor.falsifiers``
resolves those strings, and the meta-test in ``tests/meta`` asserts each one
names a test that exists. Renaming a test here breaks the gate that points at
it, which is the intended coupling.

Every test asserts two things — that the gate went red, *and* which finding
code it went red with. "Something complained" is compatible with the rule you
care about having been silently disabled, so a fixture that only checks
redness is barely better than none.
"""

from __future__ import annotations

import pytest

from celebrimbor.result import Verdict
from tests.conftest import Project

pytestmark = pytest.mark.negative

_COMPLETENESS = "celebrimbor.surface.completeness"
_NAMING = "celebrimbor.surface.naming"


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


def test_uncovered_callable_is_red(toy: Project) -> None:
    """A public callable the map does not account for is a completeness hole."""
    assert toy.run(_COMPLETENESS).verdict is Verdict.PASS

    toy.module(
        "app.orphan",
        '''
        """Nobody put this in the map."""

        from __future__ import annotations


        def build_thing(target: str) -> str:
            """Make something."""
            return target.upper()
        ''',
    )

    result = toy.run(_COMPLETENESS)
    assert result.verdict is Verdict.FAIL
    assert "surface-uncovered" in codes(result)
    assert any("app.orphan" in f.message for f in result.findings)


def test_unratified_row_is_red(toy: Project) -> None:
    """Inference pre-fills; it never manufactures green."""
    toy.surfaces(
        """
        version: 1
        modules:
          app.parsing:
            role: parser
            status: inferred
          app.checking:
            role: verifier
            status: ratified
        """
    )
    result = toy.run(_COMPLETENESS)
    assert result.verdict is Verdict.FAIL
    assert "surface-unratified" in codes(result)


def test_stale_row_is_red(toy: Project) -> None:
    """A row for a module that no longer exists is drift, not tidiness."""
    (toy.root / "src/app/parsing.py").unlink()
    result = toy.run(_COMPLETENESS)
    assert result.verdict is Verdict.FAIL
    assert "surface-stale" in codes(result)


def test_unparseable_module_refuses_rather_than_fails(toy: Project) -> None:
    """AST-only means a broken module cannot drop out of the count.

    Note the verdict: ``REFUSED``, not ``FAIL``. We do not know what is in that
    module, and reporting it as merely "missing a row" would understate it.
    """
    toy.write("src/app/broken.py", "def oops(  :\n")
    result = toy.run(_COMPLETENESS)
    assert result.verdict is Verdict.REFUSED
    assert "could not be parsed" in result.summary


def test_malformed_map_refuses_and_never_defaults(toy: Project) -> None:
    """An unreadable ledger is red — it must never fall back to a default role."""
    toy.surfaces("version: 1\nmodules:\n  app.parsing:\n    role: not-a-real-role\n")
    result = toy.run(_COMPLETENESS)
    assert result.verdict is Verdict.REFUSED
    assert "not-a-real-role" in (result.reason or "")


def test_absent_map_skips_rather_than_passes(project: Project) -> None:
    """Tier 1 is opt-in: absent is a skip, and a skip is not a pass."""
    project.module("app.thing", "def do_it() -> int:\n    return 1\n")
    result = project.run(_COMPLETENESS)
    assert result.verdict is Verdict.SKIPPED
    assert not result.proved, "a skipped check has established nothing"
    assert result.reason and "opt-in" in result.reason


def test_naming_conflict_is_red(toy: Project) -> None:
    """A name promising more proof than the role demands is drift.

    This is what stops a ratified row from silently extending to code nobody
    ratified: the module stays `parser`, but the new callable reads `adapter`.
    """
    assert toy.run(_NAMING).verdict is Verdict.PASS

    toy.module(
        "app.parsing",
        '''
        """Parsing, now with a surprise."""

        from __future__ import annotations


        class MalformedError(ValueError):
            """Bad input."""


        def parse_row(raw: str) -> dict[str, str]:
            """Parse `k=v`, refusing anything else."""
            if "=" not in raw:
                raise MalformedError(raw)
            key, _, value = raw.partition("=")
            return {key: value}


        def fetch_remote_rows(client: object) -> list[str]:
            """Reach out to somewhere else entirely."""
            del client
            return []
        ''',
    )

    result = toy.run(_NAMING)
    assert result.verdict is Verdict.FAIL
    assert "naming-conflict" in codes(result)
    assert any("fetch_remote_rows" in f.message for f in result.findings)


def test_naming_conflict_only_fires_in_the_dangerous_direction(toy: Project) -> None:
    """A name suggesting *less* proof than the role is harmless: the role wins.

    Without this, the gate would fire on every module whose default is stricter
    than its individual members — which is most modules, under safest-wins.
    """
    toy.module(
        "app.checking",
        '''
        """Verifying, plus a plain helper."""

        from __future__ import annotations


        def verify_row(row: dict[str, str]) -> bool:
            """False when the row is empty."""
            if not row:
                return False
            return all(k and v for k, v in row.items())


        def normalize_key(key: str) -> str:
            """A weaker-sounding name inside a verifier module."""
            return key.strip().lower()
        ''',
    )
    assert toy.run(_NAMING).verdict is Verdict.PASS


def test_explicit_override_silences_the_conflict(toy: Project) -> None:
    """The one-line correction flow has to actually work.

    If overriding were not respected here, the gate would be unsatisfiable for
    any legitimately-named exception, and an unsatisfiable gate gets disabled.
    """
    toy.module(
        "app.parsing",
        '''
        """Parsing, with a deliberately-named exception."""

        from __future__ import annotations


        class MalformedError(ValueError):
            """Bad input."""


        def parse_row(raw: str) -> dict[str, str]:
            """Parse `k=v`, refusing anything else."""
            if "=" not in raw:
                raise MalformedError(raw)
            key, _, value = raw.partition("=")
            return {key: value}


        def fetch_remote_rows(client: object) -> list[str]:
            """Named like an adapter, and genuinely is one."""
            del client
            return []
        ''',
    )
    toy.surfaces(
        """
        version: 1
        modules:
          app.parsing:
            role: parser
            status: ratified
            overrides:
              fetch_remote_rows: adapter
          app.checking:
            role: verifier
            status: ratified
        """
    )
    assert toy.run(_NAMING).verdict is Verdict.PASS
