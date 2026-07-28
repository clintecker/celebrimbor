"""Meta-tests: the properties that make every other guarantee binding.

The build contract asks for "a meta-test proving no check escapes the runner."
This module is that, plus the two adjacent properties without which it would
not mean much:

* every ``falsified_by`` names a test that **actually exists** — otherwise the
  falsifier obligation is a naming convention, not a gate;
* every module that registers a check is in ``CHECK_MODULES`` — otherwise a
  check can vanish by nobody importing it, and the completeness comparison
  would happily confirm that a registry missing a check ran all the checks it
  had.

The regress stops here. These are static assertions about celebrimbor's own
source, which is the one place where checking the checker does not need a
further checker.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from celebrimbor.checks import CHECK_MODULES
from celebrimbor.registry import Family, default_registry
from celebrimbor.result import Stage
from celebrimbor.runner import escaped, expected_ids, load_builtin_checks, run, strays
from tests.conftest import Project

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / "src" / "celebrimbor" / "checks"


@pytest.fixture(autouse=True)
def _loaded() -> None:
    load_builtin_checks()


def _test_functions(path: Path) -> set[str]:
    """Top-level test function names defined in a file, via AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def test_every_falsifier_names_a_test_that_exists() -> None:
    """The promise every `@check` makes, actually kept.

    ``celebrimbor.falsifiers`` deliberately does not resolve builtin checks'
    paths in an adopter's repo — a wheel ships no ``tests/`` directory, and a
    gate that always fails teaches people to disable it. This is the test that
    does the resolution, in the one repo where those files exist.
    """
    broken: list[str] = []
    for spec in default_registry():
        if spec.unproven is not None:
            continue
        for ref in spec.falsifier_paths:
            file_part, _, node = ref.partition("::")
            path = REPO_ROOT / file_part
            if not path.is_file():
                broken.append(f"{spec.id}: {file_part} does not exist")
            elif node and node not in _test_functions(path):
                broken.append(f"{spec.id}: {file_part} has no test named {node!r}")

    assert not broken, "falsifier promises that are not kept:\n  " + "\n  ".join(broken)


def test_every_check_module_is_registered_for_import() -> None:
    """A check nobody imports is a gate that silently does not exist.

    Registration happens by import side effect, so the load list is the real
    boundary. Walking the directory here means forgetting to add a module is
    caught by a test rather than by nobody.
    """
    defines_checks: set[str] = set()
    for path in sorted(CHECKS_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        decorators = (
            d
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            for d in node.decorator_list
        )
        for decorator in decorators:
            func = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name == "check":
                defines_checks.add(path.stem)
                break

    missing = defines_checks - set(CHECK_MODULES)
    assert not missing, (
        f"module(s) define @check but are absent from CHECK_MODULES: {sorted(missing)} — "
        "they would silently never run"
    )

    phantom = set(CHECK_MODULES) - {p.stem for p in CHECKS_DIR.glob("*.py")}
    assert not phantom, f"CHECK_MODULES names module(s) that do not exist: {sorted(phantom)}"


def test_terminal_check_runs_last() -> None:
    """The completeness check must run after everything it checks."""
    order = [spec.id for spec in default_registry()]
    assert order[-1] == "celebrimbor.completeness", (
        "the terminal check compares the accumulated report against the registry, "
        f"so it must be registered last; order ends with {order[-3:]}"
    )


@pytest.mark.parametrize("stage", [Stage.FAST, Stage.DEFAULT, Stage.FULL])
def test_terminal_check_is_expected_at_every_tier(stage: Stage) -> None:
    """Where the regress stops.

    If the terminal check itself does not run, nothing reports that the
    terminal check did not run. That regress has to terminate in a static
    assertion, and this is it.
    """
    assert "celebrimbor.completeness" in expected_ids(default_registry(), stage)


@pytest.mark.parametrize("stage", [Stage.FAST, Stage.DEFAULT, Stage.FULL])
def test_no_check_escapes_the_runner(project: Project, stage: Stage) -> None:
    """A real run at each stage contains exactly what the registry says it should."""
    project.module("app.thing", '"""Thing."""\n\n\ndef go() -> int:\n    """Go."""\n    return 1\n')
    registry = default_registry()
    report = run(project.context(stage=stage), registry=registry, stage=stage)

    assert not escaped(report, registry), (
        f"check(s) registered for stage {stage.label} did not run: {sorted(escaped(report, registry))}"
    )
    assert not strays(report, registry), (
        f"report contains unregistered result(s): {sorted(strays(report, registry))}"
    )
    assert report.ids() == expected_ids(registry, stage)


def test_every_check_declares_a_title_and_falsifier() -> None:
    """Structural invariants of the registry, asserted rather than assumed."""
    for spec in default_registry():
        assert spec.title.strip(), f"{spec.id} has no title"
        assert spec.falsified_by, f"{spec.id} has no falsifier"
        assert spec.id.startswith("celebrimbor."), (
            f"{spec.id} is a builtin check but is not namespaced under `celebrimbor.`"
        )


def test_obligation_checks_skip_rather_than_fail_without_their_ledger(project: Project) -> None:
    """Obligation gates are opt-in, and opt-in means absent — not passing, not red.

    This is the property that keeps `celebrimbor init` + `gate --fast` green on
    a fresh repo. If an obligation gate ever failed instead of skipping here, the
    adoption wedge would be red on day one for every project.
    """
    project.module("app.thing", '"""Thing."""\n\n\ndef go() -> int:\n    """Go."""\n    return 1\n')
    report = run(project.context(), registry=default_registry(), stage=Stage.FAST)

    for spec in default_registry().for_stage(Stage.FAST):
        if spec.family is not Family.OBLIGATION:
            continue
        result = report.by_id(spec.id)
        assert result is not None
        assert not result.is_red, f"{spec.id} is an obligation gate but reddened without a ledger"
        assert not result.proved, f"{spec.id} skipped but reported as proved"
