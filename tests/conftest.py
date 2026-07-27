"""Test infrastructure: building throwaway projects to point gates at.

Almost every gate in celebrimbor reads a project from disk, so almost every
test needs one. :class:`Project` makes that a few lines rather than a pile of
``tmp_path`` bookkeeping, which matters more than usual here: the negative
fixtures are the *product*, not scaffolding, and a fixture that is tedious to
write is a fixture that does not get written.

The deliberate choice is that ``Project`` builds a **real directory** and runs
the **real check**, rather than mocking the filesystem or calling the engine
functions directly. A negative fixture exists to prove a gate turns red in the
situation it claims to catch. Proving that against a mock proves something
about the mock.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

from celebrimbor.config import Config
from celebrimbor.context import Context
from celebrimbor.registry import CheckSpec, default_registry
from celebrimbor.result import CheckResult, Tier
from celebrimbor.runner import load_builtin_checks, run_spec


@dataclass(slots=True)
class Project:
    """A throwaway project on disk, with the gate pointed at it."""

    root: Path

    # -- authoring ----------------------------------------------------------

    def write(self, relpath: str, content: str) -> Path:
        """Write a file, dedenting so tests can indent their heredocs."""
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
        return path

    def module(self, dotted: str, content: str) -> Path:
        """Write a source module by dotted name, under the source prefix."""
        return self.write(f"src/{dotted.replace('.', '/')}.py", content)

    def surfaces(self, content: str) -> Path:
        return self.write(".celebrimbor/surfaces.yaml", content)

    def pyproject(self, content: str = "") -> Path:
        return self.write(
            "pyproject.toml",
            content
            or """
            [project]
            name = "fixture"
            version = "0.0.0"

            [tool.celebrimbor]
            source = "src"
            """,
        )

    # -- running ------------------------------------------------------------

    def context(self, tier: Tier = Tier.FAST, **kwargs: object) -> Context:
        return Context(config=Config.load(self.root), tier=tier, **kwargs)  # type: ignore[arg-type]

    def spec(self, check_id: str) -> CheckSpec:
        load_builtin_checks()
        found = default_registry().get(check_id)
        if found is None:
            raise AssertionError(f"no check registered as {check_id!r}")
        return found

    def run(self, check_id: str, **kwargs: object) -> CheckResult:
        """Run one real check against this project, through the real runner.

        Going through :func:`run_spec` rather than calling the check function
        directly is intentional — the runner is where exceptions become
        ``REFUSED``, so a fixture that bypassed it would not be testing the
        thing that actually runs in an adopter's repo.
        """
        return run_spec(self.spec(check_id), self.context(**kwargs))


@pytest.fixture
def project(tmp_path: Path) -> Project:
    """An empty project with a minimal pyproject and a src/ layout."""
    made = Project(root=tmp_path)
    made.pyproject()
    (tmp_path / "src").mkdir(exist_ok=True)
    return made


@pytest.fixture
def toy(project: Project) -> Project:
    """A small, correct project: one module per role, all ratified.

    Tests start from green and break exactly one thing, so a red result names
    the thing that was broken rather than whatever else happened to be wrong.
    """
    project.module(
        "app.parsing",
        '''
        """Parsing."""

        from __future__ import annotations


        class MalformedError(ValueError):
            """Bad input."""


        def parse_row(raw: str) -> dict[str, str]:
            """Parse `k=v`, refusing anything else."""
            if "=" not in raw:
                raise MalformedError(raw)
            key, _, value = raw.partition("=")
            return {key: value}
        ''',
    )
    project.module(
        "app.checking",
        '''
        """Verifying."""

        from __future__ import annotations


        def verify_row(row: dict[str, str]) -> bool:
            """False when the row is empty."""
            if not row:
                return False
            return all(k and v for k, v in row.items())
        ''',
    )
    project.surfaces(
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
    _pin_all(project)
    return project


def _pin_all(project: Project) -> None:
    """Stamp current shape-pins, as `celebrimbor ratify` would."""
    from celebrimbor.checks.evidence import compute_pin
    from celebrimbor.surface.inventory import inventory
    from celebrimbor.surface.ratify import apply

    config = Config.load(project.root)
    pins = {
        module.dotted: pin
        for module in inventory(config).modules
        if module.dotted and (pin := compute_pin(module)) is not None
    }
    apply(config.surfaces_path, pins)
