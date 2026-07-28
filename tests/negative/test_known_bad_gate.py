"""Negative fixtures for the known-bad provenance auditor.

These run real ruff on real deliberately-wrong files — the whole point of a
known-bad fixture is that the rule genuinely fires, and a canned checker output
would defeat it exactly the way this gate exists to prevent.
"""

from __future__ import annotations

import pytest

from celebrimbor.commodity.tools import available
from celebrimbor.result import Verdict
from tests.conftest import Project

pytestmark = pytest.mark.negative

_ID = "celebrimbor.known_bad"
needs_ruff = pytest.mark.skipif(not available("ruff"), reason="ruff is not installed")


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


@needs_ruff
def test_declared_and_actually_rejected_passes(project: Project) -> None:
    """The proving path: an unused import, declared, and ruff really flags F401."""
    project.write("tests/known-bad/unused_import.py", "import os\n")
    project.write(
        "tests/known-bad/expected.yaml",
        """
        unused_import.py:
          checker: ruff
          diagnostic: F401
          why: proves the unused-import rule is enabled
        """,
    )
    assert project.run(_ID).verdict is Verdict.PASS


@needs_ruff
def test_known_bad_file_not_actually_rejected_is_red(project: Project) -> None:
    """A file declared bad that the checker does not actually reject with the code.

    Here the file is declared to prove F401 (unused import) but is in fact
    clean of that rule — so the rule this fixture claims to prove is not firing,
    which is exactly the silent-disable this gate catches.
    """
    project.write(
        "tests/known-bad/supposedly_bad.py",
        '"""A perfectly fine file masquerading as a falsifier."""\n\n\ndef ok() -> int:\n    return 1\n',
    )
    project.write(
        "tests/known-bad/expected.yaml",
        """
        supposedly_bad.py:
          checker: ruff
          diagnostic: F401
          why: claims to prove unused-import detection, but does not
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "known-bad-not-rejected" in codes(result)


def test_orphan_file_without_entry_is_red(project: Project) -> None:
    """A known-bad file nobody declared: we do not know what it proves."""
    project.write("tests/known-bad/mystery.py", "import os\n")
    project.write("tests/known-bad/expected.yaml", "{}\n")
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "known-bad-orphan-file" in codes(result)


def test_stale_entry_for_missing_file_is_red(project: Project) -> None:
    """An entry naming a file that is gone proves nothing while looking like it does."""
    project.write(
        "tests/known-bad/expected.yaml",
        """
        deleted_fixture.py:
          checker: ruff
          diagnostic: F401
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "known-bad-stale-entry" in codes(result)


def test_wrong_diagnostic_is_red(project: Project) -> None:
    """Being caught by *some* rule is not enough; it must be the named one."""
    project.write("tests/known-bad/unused_import.py", "import os\n")
    project.write(
        "tests/known-bad/expected.yaml",
        """
        unused_import.py:
          checker: ruff
          diagnostic: E501
          why: wrong diagnostic on purpose — this is an unused import, not a long line
        """,
    )
    if not available("ruff"):
        pytest.skip("ruff is not installed")
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "known-bad-not-rejected" in codes(result)


def test_absent_directory_skips(project: Project) -> None:
    """No known-bad directory means opt-out, which is a skip, not a pass."""
    result = project.run(_ID)
    assert result.verdict is Verdict.SKIPPED
    assert not result.proved


def test_malformed_expected_refuses(project: Project) -> None:
    """An entry missing its checker cannot be audited, so the gate refuses."""
    project.write(
        "tests/known-bad/thing.py",
        "import os\n",
    )
    project.write(
        "tests/known-bad/expected.yaml",
        """
        thing.py:
          diagnostic: F401
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.REFUSED


# --- app-declared checkers (issue #9) -------------------------------------

_CHECKER = (
    'import sys\nif "badword" in open(sys.argv[1]).read():\n    print(f"BADWORD {sys.argv[1]}")\n'
)
_PYPROJECT = """
    [project]
    name = "fixture"
    version = "0.0.0"

    [tool.celebrimbor]
    source = "src"

    [tool.celebrimbor.known_bad_checkers.style_audit]
    command = "python checker.py {file}"
    pattern = "^([A-Z]+)"
    """


def test_custom_checker_that_fires_passes(project: Project) -> None:
    """A domain linter (not ruff/mypy) can prove its own known-bad fixture."""
    project.pyproject(_PYPROJECT)
    project.write("checker.py", _CHECKER)
    project.write("tests/known-bad/has_badword.txt", "this has a badword in it\n")
    project.write(
        "tests/known-bad/expected.yaml",
        """
        has_badword.txt:
          checker: style_audit
          diagnostic: BADWORD
          why: proves the badword rule still fires
        """,
    )
    assert project.run(_ID).verdict is Verdict.PASS


def test_custom_checker_that_does_not_fire_is_red(project: Project) -> None:
    """A file the declared checker does not actually reject is a red — the whole
    point survives for app checkers, not only for ruff/mypy."""
    project.pyproject(_PYPROJECT)
    project.write("checker.py", _CHECKER)
    project.write("tests/known-bad/clean.txt", "nothing wrong here\n")
    project.write(
        "tests/known-bad/expected.yaml",
        """
        clean.txt:
          checker: style_audit
          diagnostic: BADWORD
          why: claims to trip the rule, but does not
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "known-bad-not-rejected" in codes(result)


def test_undeclared_checker_is_unverifiable(project: Project) -> None:
    """A checker that is neither built-in nor declared cannot be run — fail closed."""
    project.write("tests/known-bad/thing.txt", "x\n")
    project.write(
        "tests/known-bad/expected.yaml",
        """
        thing.txt:
          checker: mystery_linter
          diagnostic: WHATEVER
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "known-bad-unverifiable" in codes(result)


# --- in-process callable + substring match (issue #10) --------------------

_CALLABLE_PYPROJECT = """
    [project]
    name = "fixture"
    version = "0.0.0"

    [tool.celebrimbor]
    source = "src"

    [tool.celebrimbor.known_bad_checkers.style_audit]
    callable = "tests.known_bad_checker_fixture:diagnostics_for"
    match = "substring"
    """


def test_in_process_callable_with_substring_match_passes(project: Project) -> None:
    """A book-bound Python linter (no per-file subprocess) proves its fixture,
    matched by a phrase substring rather than an exact code."""
    project.pyproject(_CALLABLE_PYPROJECT)
    project.write("tests/known-bad/has_badword.md", "this has a badword in it\n")
    project.write(
        "tests/known-bad/expected.yaml",
        """
        has_badword.md:
          checker: style_audit
          diagnostic: "contains a badword"   # a substring of the emitted phrase
          why: proves the badword rule still fires
        """,
    )
    assert project.run(_ID).verdict is Verdict.PASS


def test_substring_phrase_not_emitted_is_red(project: Project) -> None:
    """Substring is still strict: the declared phrase must actually appear."""
    project.pyproject(_CALLABLE_PYPROJECT)
    project.write("tests/known-bad/has_badword.md", "this has a badword in it\n")
    project.write(
        "tests/known-bad/expected.yaml",
        """
        has_badword.md:
          checker: style_audit
          diagnostic: "contains a typo"
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "known-bad-not-rejected" in codes(result)


def test_callable_that_cannot_import_is_unverifiable(project: Project) -> None:
    """A callable that will not import is a fail-closed error, not a quiet pass."""
    project.pyproject(
        """
        [project]
        name = "fixture"
        version = "0.0.0"

        [tool.celebrimbor]
        source = "src"

        [tool.celebrimbor.known_bad_checkers.style_audit]
        callable = "does.not.exist:nope"
        """
    )
    project.write("tests/known-bad/thing.md", "badword\n")
    project.write(
        "tests/known-bad/expected.yaml",
        """
        thing.md:
          checker: style_audit
          diagnostic: anything
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "known-bad-unverifiable" in codes(result)
