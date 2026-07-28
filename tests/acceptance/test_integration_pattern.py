"""Acceptance: the pattern by which an existing app adopts celebrimbor.

A real adopter imports celebrimbor, keeps its own domain data (its surface map,
its invariants, its fixtures), and its quality gate stays green through the
swap. This module proves celebrimbor can *support* that by exercising every
seam the adoption depends on:

* an app registers its own domain checks through the one documented seam;
* those checks adapt the app's existing "raise on failure" style without loss;
* the app keeps its ledgers where they already live, via path overrides;
* app checks and builtins run together under the same completeness guarantee;
* app checks read celebrimbor's ledger loaders on the app's own files.

If all of that holds, adoption is a mechanical migration, which is exactly what
"celebrimbor can support this app" has to mean. The fictional ``acme`` app below
stands in for any real adopter.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import celebrimbor
from celebrimbor.config import Config
from celebrimbor.context import Context
from celebrimbor.ledgers.invariants import load_invariants
from celebrimbor.registry import Registry
from celebrimbor.result import CheckResult, Stage, Verdict
from celebrimbor.runner import escaped, expected_ids, run, strays
from tests.conftest import Project


def raising_check_adapter(check_id: str, title: str, fn, registry: Registry):
    """Adapt an app's zero-arg 'raise on failure' check to celebrimbor's seam.

    This is the shim an adopter writes once: an existing ``def check_foo() -> None``
    that raises ``AssertionError`` becomes a celebrimbor check. Everything the
    app already has keeps working; only the wrapper is new.
    """

    @celebrimbor.check(
        id=check_id,
        title=title,
        stage=Stage.FAST,
        falsified_by="tests/acceptance/test_integration_pattern.py",
        registry=registry,
    )
    def _wrapped(ctx: Context) -> CheckResult:  # noqa: ARG001
        try:
            fn()
        except AssertionError as exc:
            return CheckResult.failed(
                check_id,
                f"{title}: failed",
                celebrimbor.Finding(message=str(exc) or "assertion failed"),
            )
        return CheckResult.passed(check_id, f"{title}: held")

    return _wrapped


def test_app_can_register_and_run_domain_checks() -> None:
    """An app's own checks run through the ordered registry and its runner."""
    registry = Registry()

    def check_orders_have_customers() -> None:
        # An app's existing raising check. Passes here.
        assert True, "every order has a customer"

    def check_prices_never_negative() -> None:
        raise AssertionError("SKU-9 has price -3")

    raising_check_adapter(
        "acme.orders", "orders reference a customer", check_orders_have_customers, registry
    )
    raising_check_adapter(
        "acme.prices", "prices are non-negative", check_prices_never_negative, registry
    )

    root = Path(tempfile.mkdtemp())
    (root / "src").mkdir()
    ctx = Context(config=Config.load(root), stage=Stage.FAST)
    report = run(ctx, registry=registry)

    assert report.by_id("acme.orders").verdict is Verdict.PASS
    assert report.by_id("acme.prices").verdict is Verdict.FAIL
    # The completeness guarantee covers app checks exactly as it covers builtins.
    assert not escaped(report, registry)
    assert not strays(report, registry)
    assert report.ids() == expected_ids(registry, Stage.FAST)


def test_app_keeps_its_ledger_where_it_already_lives(project: Project) -> None:
    """Path overrides: an app keeps invariants in quality/, celebrimbor reads it there."""
    project.write(
        "pyproject.toml",
        """
        [project]
        name = "acme"
        version = "0.0.0"

        [tool.celebrimbor]
        source = "src"

        [tool.celebrimbor.paths]
        invariants = "quality/invariants.yaml"
        """,
    )
    project.module(
        "app.orders", '"""Orders."""\n\n\ndef validate(o: dict) -> dict:\n    return o\n'
    )
    # The app's existing ledger, in its existing location, with its own extra fields.
    project.write(
        "quality/invariants.yaml",
        """
        version: 1
        invariants:
          INV-1:
            id: INV-1
            statement: every order references a customer
            enforced_by: app.orders:validate
            risk: high
            criticality: normal
            owner: team-orders
        """,
    )
    config = Config.load(project.root)
    assert config.invariants_path == project.root / "quality/invariants.yaml"

    # celebrimbor's own loader reads the app's file, tolerating its extra fields.
    ledger = load_invariants(config.invariants_path)
    assert "INV-1" in ledger.invariants
    assert ledger.invariants["INV-1"].statement == "every order references a customer"

    # And the invariant gate, run against it, is green.
    result = project.run("celebrimbor.invariants", stage=Stage.DEFAULT)
    assert result.verdict is Verdict.PASS


def test_public_api_surface_is_sufficient_for_an_integrator() -> None:
    """Everything an adoption needs is reachable from the public package."""
    # The documented seam.
    assert callable(celebrimbor.check)
    assert callable(celebrimbor.gate)
    for name in ("CheckResult", "Finding", "Verdict", "Stage", "Unproven", "GateReport"):
        assert hasattr(celebrimbor, name), f"celebrimbor.{name} must be public"

    # The deeper primitives an app's own checks build on — reachable as
    # documented sub-APIs, not the top-level seam, but importable.
    from celebrimbor.ledgers import load_invariants, load_producers  # noqa: F401
    from celebrimbor.ratchets import coverage_regressions, new_survivors  # noqa: F401
    from celebrimbor.scenarios import pairwise  # noqa: F401
    from celebrimbor.surface import inventory, load_map  # noqa: F401

    assert True  # the imports above are the assertion


@pytest.mark.parametrize("stage", ["fast", "default", "full"])
def test_gate_is_callable_programmatically_at_every_tier(stage: str, tmp_path) -> None:
    """An adopter drives the gate from its own harness, not only the CLI."""
    (tmp_path / "src").mkdir()
    report = celebrimbor.gate(stage=stage, root=tmp_path)
    # An empty project has no source, so builtins may refuse — but the call
    # itself must return a report with a real exit code, never raise.
    assert report.exit_code in (0, 1)
    assert report.stage is celebrimbor.Stage.parse(stage)
