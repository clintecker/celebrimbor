"""Falsifier scaffolding — the pure builder and the `gate --propose` side effect.

The load-bearing property under test, beyond "does it build a sensible scaffold",
is that a scaffold is **never a proof**: it lands in a scratch directory no gate
reads, it is not ratified, and its presence never changes a verdict. Generation
moves the blank page; it does not move the gate.
"""

from __future__ import annotations

from celebrimbor.cli import _propose
from celebrimbor.falsifier import render, scaffold, slugify
from celebrimbor.ratchets.mutation import Survivor
from celebrimbor.result import Stage
from tests.conftest import Project

_SRC = "def place_order(order):\n    return order.customer and order.total\n"


# --- the pure builder -----------------------------------------------------


def test_slugify_is_stable_and_filesystem_safe() -> None:
    slug = slugify("src/app/orders.py:42:and->or")
    assert slug == "src-app-orders-py-42-and-or"
    assert "/" not in slug and ":" not in slug
    assert slugify("src/app/orders.py:42:and->or") == slug  # deterministic


def test_scaffold_extracts_the_enclosing_function() -> None:
    proposal = scaffold(Survivor("src/app/orders.py", 2, "and->or"), _SRC)
    assert proposal.identity == "src/app/orders.py:2:and->or"
    # the smallest def around the mutated line, not the whole file
    assert "def place_order(order):" in proposal.snippet
    assert "and->or" in proposal.stub
    assert "src/app/orders.py:2" in proposal.recipe


def test_scaffold_is_deterministic() -> None:
    surv = Survivor("a.py", 1, "+->-")
    assert render(scaffold(surv, "x = 1 + 2\n")) == render(scaffold(surv, "x = 1 + 2\n"))


def test_render_marks_the_scaffold_not_a_proof() -> None:
    out = render(scaffold(Survivor("a.py", 1, "+->-"), "x = 1 + 2\n"))
    assert "NOT A PROOF" in out


def test_scaffold_falls_back_to_a_window_on_unparseable_source() -> None:
    # A syntax error must not crash the scaffolder — it still locates the line.
    proposal = scaffold(Survivor("a.py", 2, "x"), "def broken(:\n    junk here\n    more\n")
    assert proposal.snippet  # a window, not an exception


# --- the `gate --propose` side effect -------------------------------------


def test_propose_writes_one_scaffold_per_survivor(project: Project) -> None:
    project.write("src/app/orders.py", _SRC)
    ctx = project.context(stage=Stage.FULL)
    ctx.memo("ratchet.survivors", lambda: frozenset({Survivor("src/app/orders.py", 2, "and->or")}))

    _propose(ctx)

    proposals = sorted((project.root / ".celebrimbor" / "proposals").glob("*.md"))
    assert len(proposals) == 1
    text = proposals[0].read_text()
    assert "NOT A PROOF" in text
    assert "def place_order(order):" in text
    # A scaffold lives outside source/ and tests/, so no gate ever scans it.
    assert proposals[0].parts[-3:-1] == (".celebrimbor", "proposals")


def test_propose_is_inert_without_a_survivor_source(project: Project) -> None:
    # celebrimbor's own case: no mutation_survivors, no injected survivors.
    ctx = project.context(stage=Stage.FULL)
    _propose(ctx)
    assert not (project.root / ".celebrimbor" / "proposals").exists()
