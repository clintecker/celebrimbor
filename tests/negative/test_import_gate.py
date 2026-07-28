"""Negative fixtures for the opt-in import-health gate.

These run the real probe subprocess against real fixture modules — the whole
point is that importing genuinely happens (in isolation), so a mocked import
would defeat the check. The gate is opt-in, so every fixture enables it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from celebrimbor.config import Config
from celebrimbor.context import Context
from celebrimbor.result import Stage, Verdict
from celebrimbor.runner import run_spec
from tests.conftest import Project

pytestmark = pytest.mark.negative

_ID = "celebrimbor.imports"


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


def _project(project: Project, *, opt_in: bool = True) -> Project:
    flag = "\nimport_check = true" if opt_in else ""
    project.write(
        "pyproject.toml",
        f'[project]\nname = "app"\nversion = "0"\n\n[tool.celebrimbor]\nsource = "src"{flag}\n',
    )
    project.write("src/app/__init__.py", '"""app."""\n')
    project.write("src/app/good.py", '"""Clean."""\n\n\ndef go() -> int:\n    return 1\n')
    return project


def _run(project: Project) -> object:
    return run_spec(project.spec(_ID), Context(config=Config.load(project.root), stage=Stage.DEFAULT))


def test_module_that_raises_on_import_is_red(project: Project) -> None:
    """An import-time fault the AST cannot see — only importing reveals it."""
    _project(project)
    project.write("src/app/boom.py", '"""Boom."""\nraise RuntimeError("explodes at import")\n')
    result = _run(project)
    assert result.verdict is Verdict.FAIL
    assert "import-error" in codes(result)
    assert any("app.boom" in f.message for f in result.findings)


def test_import_time_file_write_is_red(project: Project) -> None:
    """A file written at import time is an import-time side effect."""
    _project(project)
    project.write(
        "src/app/writes.py",
        '"""Writes on import."""\nopen("side_effect.txt", "w").write("x")\n',  # noqa: SIM115
    )
    result = _run(project)
    assert result.verdict is Verdict.FAIL
    assert "import-side-effect" in codes(result)
    assert any("filesystem-write" in f.message for f in result.findings)


def test_import_time_side_effect_is_not_actually_performed(project: Project) -> None:
    """The probe records the effect but the guard prevents it — the file is not written."""
    _project(project)
    project.write(
        "src/app/writes.py",
        '"""Writes on import."""\nopen("must_not_exist.txt", "w").write("x")\n',  # noqa: SIM115
    )
    _run(project)
    assert not (project.root / "must_not_exist.txt").exists(), (
        "the guard must prevent the real write, not just record it"
    )


def test_import_time_subprocess_is_red(project: Project) -> None:
    """Spawning a process at import time is a side effect (and it is blocked)."""
    _project(project)
    project.write(
        "src/app/spawns.py",
        '"""Spawns on import."""\nimport subprocess\nsubprocess.run(["true"])\n',
    )
    result = _run(project)
    assert result.verdict is Verdict.FAIL
    assert any("process" in f.message for f in result.findings)


def test_clean_package_passes(project: Project) -> None:
    """A package that imports cleanly with no import-time effects is green."""
    _project(project)
    project.write(
        "src/app/tidy.py",
        '"""Tidy."""\n\nimport json\n\n\ndef load(raw: str) -> dict:\n    return json.loads(raw)\n',
    )
    assert _run(project).verdict is Verdict.PASS


def test_opt_out_skips_with_a_reason(project: Project) -> None:
    """Off by default: the one gate that imports code must be chosen."""
    _project(project, opt_in=False)
    project.write("src/app/boom.py", '"""Boom."""\nraise RuntimeError("would explode")\n')
    result = _run(project)
    assert result.verdict is Verdict.SKIPPED
    assert not result.proved
    assert "opt-in" in (result.reason or "")


def test_probe_module_names_bridge_a_package_dir_source(project: Project) -> None:
    """A package-dir source (src/pkg) imports as pkg.<module>, not the bare name."""
    from celebrimbor.checks.imports import _import_name
    from celebrimbor.surface.inventory import ModuleInfo

    src = project.root / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    root_init = ModuleInfo(dotted="pkg", path=Path("src/pkg/__init__.py"))
    build = ModuleInfo(dotted="build", path=Path("src/pkg/build.py"))
    assert _import_name(root_init, src) == "pkg"
    assert _import_name(build, src) == "pkg.build"
