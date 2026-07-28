"""Negative fixtures for the invariant-ledger gate."""

from __future__ import annotations

import pytest

from celebrimbor.ledgers.invariants import load_invariants, render_docs
from celebrimbor.result import Stage, Verdict
from celebrimbor.yamlio import YamlError
from tests.conftest import Project

pytestmark = pytest.mark.negative

_ID = "celebrimbor.invariants"


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


def _project_with_enforcer(project: Project) -> Project:
    project.module(
        "app.orders",
        '''
        """Order rules."""

        from __future__ import annotations


        class OrphanOrderError(ValueError):
            """An order with no customer."""


        def validate_order(order: dict[str, str]) -> dict[str, str]:
            """Refuse an order with no customer."""
            if "customer" not in order:
                raise OrphanOrderError(str(order))
            return order
        ''',
    )
    return project


def test_missing_enforcer_is_red(project: Project) -> None:
    """A promise whose enforcer does not resolve is a promise nobody keeps."""
    _project_with_enforcer(project)
    project.write(
        ".celebrimbor/invariants.yaml",
        """
        version: 1
        invariants:
          order-has-customer:
            statement: every order references an existing customer
            enforced_by: app.orders:validate_order_RENAMED
        """,
    )
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.FAIL
    assert "invariant-enforcer-absent" in codes(result)


def test_resolving_enforcer_passes(project: Project) -> None:
    """The proving path: the enforcer resolves to a real callable."""
    _project_with_enforcer(project)
    project.write(
        ".celebrimbor/invariants.yaml",
        """
        version: 1
        invariants:
          order-has-customer:
            statement: every order references an existing customer
            enforced_by: app.orders:validate_order
        """,
    )
    assert project.run(_ID, stage=Stage.DEFAULT).verdict is Verdict.PASS


def test_critical_without_negative_proof_is_rejected_at_load(project: Project) -> None:
    """A critical promise must keep a proof; 'critical' without one is a label.

    Rejected at *load*, not at check time, because a ledger that cannot state
    its own guarantee coherently should not parse into a usable object at all.
    """
    project.surfaces("version: 1\nmodules: {}\n")  # unrelated, just to have a dir
    ledger = project.write(
        ".celebrimbor/invariants.yaml",
        """
        version: 1
        invariants:
          money-never-negative:
            statement: balances are never negative
            enforced_by: app.ledger:guard
            critical: true
        """,
    )
    with pytest.raises(YamlError, match="critical.*negative_proof|negative_proof"):
        load_invariants(ledger)


def test_critical_with_missing_proof_file_is_red(project: Project) -> None:
    """A critical invariant whose proof file is gone is unproven, so red."""
    _project_with_enforcer(project)
    project.write(
        ".celebrimbor/invariants.yaml",
        """
        version: 1
        invariants:
          order-has-customer:
            statement: every order references an existing customer
            enforced_by: app.orders:validate_order
            critical: true
            negative_proof: tests/negative/gone.py::test_orphan_rejected
        """,
    )
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.FAIL
    assert "invariant-proof-absent" in codes(result)


def test_empty_ledger_refuses_rather_than_passes(project: Project) -> None:
    """An empty ledger checks nothing, which is not nothing-to-check."""
    project.write(".celebrimbor/invariants.yaml", "version: 1\ninvariants: {}\n")
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.REFUSED


def test_absent_ledger_skips(project: Project) -> None:
    """Opt-in: no ledger means skipped, not passed and not red."""
    _project_with_enforcer(project)
    result = project.run(_ID, stage=Stage.DEFAULT)
    assert result.verdict is Verdict.SKIPPED
    assert not result.proved


def test_docs_render_from_the_same_data_the_gate_checks(project: Project) -> None:
    """The rendered docs cannot lie: they come from the validated ledger."""
    _project_with_enforcer(project)
    project.write("tests/negative/test_orders.py", "def test_orphan() -> None:\n    ...\n")
    ledger_path = project.write(
        ".celebrimbor/invariants.yaml",
        """
        version: 1
        invariants:
          order-has-customer:
            statement: every order references an existing customer
            enforced_by: app.orders:validate_order
            critical: true
            negative_proof: tests/negative/test_orders.py::test_orphan
        """,
    )
    docs = render_docs(load_invariants(ledger_path))
    assert "order-has-customer" in docs
    assert "**(critical)**" in docs
    assert "app.orders:validate_order" in docs
