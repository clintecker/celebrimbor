"""Negative fixtures for the no-blind-verifier producer gate."""

from __future__ import annotations

import pytest

from celebrimbor.result import Stage, Verdict
from tests.conftest import Project, _pin_all

pytestmark = pytest.mark.negative

_ID = "celebrimbor.producers"


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


def _producer_project(project: Project) -> Project:
    """A project with one producer and the verifier that inspects its artifact."""
    project.module(
        "app.render",
        '''
        """Rendering the summary artifact."""

        from __future__ import annotations

        from pathlib import Path


        def build_summary(rows: list[str], target: Path) -> Path:
            """Write a summary file and return where it went."""
            target.write_text("\\n".join(rows), encoding="utf-8")
            return target
        ''',
    )
    project.module(
        "app.checking",
        '''
        """Inspecting the summary artifact."""

        from __future__ import annotations

        from pathlib import Path


        def verify_summary(target: Path, expected: int) -> bool:
            """False when the summary does not have the expected number of lines."""
            if not target.exists():
                return False
            lines = [x for x in target.read_text(encoding="utf-8").splitlines() if x]
            return len(lines) == expected
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.render:
            role: producer
            status: ratified
          app.checking:
            role: verifier
            status: ratified
        """
    )
    _pin_all(project)
    return project


def test_producer_without_ledger_entry_is_red(project: Project) -> None:
    """A producer with no ledger entry is a verifier that inspects nothing."""
    _producer_project(project)
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.FAIL
    assert "producer-uncovered" in codes(result)
    assert any("app.render" in f.message for f in result.findings)


def test_full_ledger_entry_passes(project: Project) -> None:
    """The proving path: verifier resolves, is a verifier, and its fixture exists."""
    _producer_project(project)
    project.write(
        "tests/negative/test_render.py", "def test_empty_summary_caught() -> None:\n    ...\n"
    )
    project.write(
        ".celebrimbor/producers.yaml",
        """
        version: 1
        producers:
          app.render:
            verifier: app.checking:verify_summary
            negative_fixture: tests/negative/test_render.py::test_empty_summary_caught
        """,
    )
    assert project.run(_ID, stage=Stage.DEFAULT).verdict is Verdict.PASS


def test_verifier_that_is_not_a_verifier_is_red(project: Project) -> None:
    """The named verifier must actually be classified `verifier`.

    Pointing a producer at a `pure` helper and calling it the verifier is how a
    blind verifier gets laundered into looking proved.
    """
    _producer_project(project)
    project.write("tests/negative/test_render.py", "def test_x() -> None:\n    ...\n")
    project.write(
        ".celebrimbor/producers.yaml",
        """
        version: 1
        producers:
          app.render:
            verifier: app.render:build_summary
            negative_fixture: tests/negative/test_render.py::test_x
        """,
    )
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.FAIL
    assert "producer-verifier-miscast" in codes(result)


def test_missing_negative_fixture_is_red(project: Project) -> None:
    """The negative fixture is the verifier's own falsifier; it must exist."""
    _producer_project(project)
    project.write(
        ".celebrimbor/producers.yaml",
        """
        version: 1
        producers:
          app.render:
            verifier: app.checking:verify_summary
            negative_fixture: tests/negative/does_not_exist.py::test_ghost
        """,
    )
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.FAIL
    assert "producer-fixture-absent" in codes(result)


def test_override_producer_is_caught(project: Project) -> None:
    """A producer introduced by a per-callable override, not a module default.

    This is the override-granularity scar: the cheapest way to ship an
    unchecked artifact is a one-line override on an innocent module, and the
    gate has to see through it.
    """
    project.module(
        "app.mixed",
        '''
        """Mostly pure, with one artifact-builder."""

        from __future__ import annotations

        from pathlib import Path


        def slugify(text: str) -> str:
            """Pure."""
            return text.strip().lower().replace(" ", "-")


        def build_report(rows: list[str], target: Path) -> Path:
            """The one producer here."""
            target.write_text("\\n".join(rows), encoding="utf-8")
            return target
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.mixed:
            role: pure
            status: ratified
            overrides:
              build_report: producer
        """
    )
    _pin_all(project)

    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.FAIL
    assert any("app.mixed:build_report" in f.message for f in result.findings), (
        "an override-introduced producer must be demanded a ledger entry"
    )


def test_expired_pending_is_red(project: Project) -> None:
    """The pending allowlist shrinks: a past review date reddens it."""
    _producer_project(project)
    project.write(
        ".celebrimbor/producers.yaml",
        """
        version: 1
        pending:
          app.render:
            reason: verifier fixture not written yet
            review_by: 2020-01-01
        """,
    )
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.FAIL
    assert "producer-pending-expired" in codes(result)


def test_unexpired_pending_is_allowed_but_visible(project: Project) -> None:
    """Not-yet-due pending debt passes, but the summary still names it."""
    _producer_project(project)
    project.write(
        ".celebrimbor/producers.yaml",
        """
        version: 1
        pending:
          app.render:
            reason: verifier fixture coming in the next PR
            review_by: 2099-01-01
        """,
    )
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.PASS
    assert "pending" in result.summary


def test_no_producers_is_a_clean_pass(project: Project) -> None:
    """A project with no producers has nothing to prove and no ledger to write."""
    project.module(
        "app.pure", '"""Pure."""\n\n\ndef add(a: int, b: int) -> int:\n    return a + b\n'
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.pure:
            role: pure
            status: ratified
        """
    )
    _pin_all(project)
    assert project.run(_ID, stage=Stage.DEFAULT).verdict is Verdict.PASS
