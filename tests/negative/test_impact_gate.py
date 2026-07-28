"""Negative fixtures for the change-impact gate.

The changed-file set is injected by seeding the context's memo — the same slot
``changed_files()`` reads from — rather than by driving a real git repo. That
keeps each fixture deterministic and lets it state exactly which change it is
testing. The one path that *must* see real git behaviour, the unknowable-diff
refusal, gets it for free: a plain tmp directory is not a repo, so the diff
genuinely cannot be resolved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from celebrimbor.result import Stage, Verdict
from celebrimbor.runner import run_spec
from tests.conftest import Project, _pin_all

pytestmark = pytest.mark.negative

_ID = "celebrimbor.impact"


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


def _run_with_diff(project: Project, changed: tuple[str, ...]) -> object:
    """Run the impact gate with an injected changed-file set."""
    ctx = project.context(stage=Stage.DEFAULT)
    ctx.memo("git.changed_files", lambda: tuple(Path(p) for p in changed))
    return run_spec(project.spec(_ID), ctx)


def _policy_project(project: Project) -> Project:
    """A project with a verifier (a policy role) and no invariants yet."""
    project.module(
        "app.checking",
        '''
        """Verifying."""

        from __future__ import annotations


        def verify_row(row: dict[str, str]) -> bool:
            """False when empty."""
            if not row:
                return False
            return all(k and v for k, v in row.items())
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.checking:
            role: verifier
            status: ratified
        """
    )
    _pin_all(project)
    return project


def test_policy_change_without_invariant_is_red(project: Project) -> None:
    """Changing a policy-role module with no invariant naming it is the gap."""
    _policy_project(project)
    result = _run_with_diff(project, ("src/app/checking.py",))
    assert result.verdict is Verdict.FAIL
    assert "impact-ungoverned" in codes(result)
    assert any("app.checking" in f.message for f in result.findings)


def test_policy_change_with_governing_invariant_passes(project: Project) -> None:
    """An invariant naming the module as an enforcer governs the change."""
    _policy_project(project)
    project.write(
        ".celebrimbor/invariants.yaml",
        """
        version: 1
        invariants:
          row-is-nonempty:
            statement: a verified row has non-empty keys and values
            enforced_by: app.checking:verify_row
        """,
    )
    result = _run_with_diff(project, ("src/app/checking.py",))
    assert result.verdict is Verdict.PASS


def test_non_policy_change_is_ignored(project: Project) -> None:
    """A `pure` module carries no policy, so changing it needs no invariant."""
    project.module(
        "app.mathy",
        '"""Pure."""\n\n\ndef add(a: int, b: int) -> int:\n    """Sum."""\n    return a + b\n',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.mathy:
            role: pure
            status: ratified
        """
    )
    _pin_all(project)
    result = _run_with_diff(project, ("src/app/mathy.py",))
    assert result.verdict is Verdict.PASS


def test_change_outside_source_prefix_is_ignored(project: Project) -> None:
    """A changed README is not a policy change."""
    _policy_project(project)
    result = _run_with_diff(project, ("README.md", "docs/guide.md"))
    assert result.verdict is Verdict.PASS
    assert "no source modules changed" in result.summary


def test_unknowable_diff_refuses_rather_than_passing(project: Project) -> None:
    """Fail closed: a diff we cannot compute is not an empty diff.

    A plain tmp directory is not a git repo, so `changed_files()` returns None,
    and the gate must refuse rather than report that nothing changed.
    """
    _policy_project(project)
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.REFUSED
    assert "could not be determined" in result.summary


def test_override_introduced_policy_change_is_caught(project: Project) -> None:
    """An adapter introduced by one override still makes the module policy-bearing."""
    project.module(
        "app.mixed",
        '''
        """Mostly pure, one boundary call."""

        from __future__ import annotations

        import urllib.request


        def slugify(text: str) -> str:
            """Pure."""
            return text.strip().lower()


        def fetch_tags(url: str) -> bytes:
            """The one adapter here."""
            return urllib.request.urlopen(url).read()
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
              fetch_tags: adapter
        """
    )
    _pin_all(project)
    result = _run_with_diff(project, ("src/app/mixed.py",))
    assert result.verdict is Verdict.FAIL
    assert any("app.mixed" in f.message and "adapter" in f.message for f in result.findings)


def test_orchestrator_is_a_policy_role_by_default(project: Project) -> None:
    """A changed orchestrator with no governing invariant is a gap by default.

    Rewiring dependency edges is a silent behaviour change, so the impact gate
    governs orchestrators out of the box.
    """
    project.module(
        "app.flow",
        '''
        """Coordinating."""

        from __future__ import annotations


        def run_pipeline(load: object, transform: object, save: object) -> None:
            """Wire the steps together."""
            save(transform(load()))
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.flow:
            role: orchestrator
            status: ratified
        """
    )
    _pin_all(project)
    result = _run_with_diff(project, ("src/app/flow.py",))
    assert result.verdict is Verdict.FAIL
    assert any("orchestrator" in f.message for f in result.findings)


def test_policy_roles_config_narrows_the_governed_set(project: Project) -> None:
    """An adopter can match an existing harness's policy-role set via config."""
    project.write(
        "pyproject.toml",
        """
        [project]
        name = "acme"
        version = "0.0.0"

        [tool.celebrimbor]
        source = "src"
        policy_roles = ["verifier", "parser", "producer", "adapter"]
        """,
    )
    project.module(
        "app.flow",
        '''
        """Coordinating."""

        from __future__ import annotations


        def run_pipeline(load: object, save: object) -> None:
            """Wire steps."""
            save(load())
        ''',
    )
    project.surfaces(
        """
        version: 1
        modules:
          app.flow:
            role: orchestrator
            status: ratified
        """
    )
    _pin_all(project)
    # orchestrator dropped from the policy set -> its change is not governed -> green
    result = _run_with_diff(project, ("src/app/flow.py",))
    assert result.verdict is Verdict.PASS


def test_unknown_policy_role_is_a_config_error(project: Project) -> None:
    """A typo'd policy role would silently shrink governance, so it's rejected."""
    from celebrimbor.config import Config, ConfigError

    project.write(
        "pyproject.toml",
        """
        [project]
        name = "acme"
        version = "0.0.0"

        [tool.celebrimbor]
        policy_roles = ["verifer"]
        """,
    )
    with pytest.raises(ConfigError, match="unknown role"):
        Config.load(project.root)
