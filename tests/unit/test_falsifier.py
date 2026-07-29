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

# Module-level code + a class with two methods, so a snippet test can tell
# "narrowed to the enclosing method" apart from "returned the whole file".
_MODULE = (
    "import os\n"  # line 1
    "\n"  # 2
    "TOP = 1\n"  # 3
    "\n"  # 4
    "class Orders:\n"  # 5
    "    def place(self, order):\n"  # 6
    "        return order.customer and order.total\n"  # 7  <- the mutated line
    "\n"  # 8
    "    def cancel(self, order):\n"  # 9
    "        return order.cancelled\n"  # 10
)


# --- the pure builder -----------------------------------------------------


def test_slugify_is_stable_and_filesystem_safe() -> None:
    slug = slugify("src/app/orders.py:42:and->or")
    assert slug.startswith("src-app-orders-py-42-and-or-")  # readable stem + hash
    assert "/" not in slug and ":" not in slug
    assert slugify("src/app/orders.py:42:and->or") == slug  # deterministic


def test_slugify_distinguishes_operators_at_the_same_line() -> None:
    # All-punctuation operators collapse away in the readable stem; the identity
    # hash must still keep two mutants at one file:line from colliding — else the
    # second scaffold silently overwrites the first, dropping a real falsifier.
    assert slugify("src/app.py:42:+->-") != slugify("src/app.py:42:+->*")


def test_scaffold_reports_identity_stub_and_recipe() -> None:
    proposal = scaffold(Survivor("src/app/orders.py", 2, "and->or"), _SRC)
    assert proposal.identity == "src/app/orders.py:2:and->or"
    assert "and->or" in proposal.stub
    assert "src/app/orders.py:2" in proposal.recipe


def test_scaffold_narrows_to_the_smallest_enclosing_def() -> None:
    # The mutated line is inside Orders.place; the snippet must be exactly that
    # method — not the whole module, not the enclosing class, not the sibling
    # method. (A fixture that is a single top-level function cannot tell narrowing
    # apart from dumping the whole file, so this uses nested defs on purpose.)
    proposal = scaffold(Survivor("src/app/orders.py", 7, "and->or"), _MODULE)
    assert "def place(self, order):" in proposal.snippet
    assert "def cancel" not in proposal.snippet  # sibling method excluded
    assert "import os" not in proposal.snippet  # module level excluded
    assert "class Orders" not in proposal.snippet  # enclosing class excluded


def test_scaffold_is_deterministic() -> None:
    surv = Survivor("a.py", 1, "+->-")
    assert render(scaffold(surv, "x = 1 + 2\n")) == render(scaffold(surv, "x = 1 + 2\n"))


def test_render_marks_the_scaffold_not_a_proof() -> None:
    out = render(scaffold(Survivor("a.py", 1, "+->-"), "x = 1 + 2\n"))
    assert "NOT A PROOF" in out


def test_scaffold_falls_back_to_a_window_on_unparseable_source() -> None:
    # A syntax error must not crash the scaffolder — it still locates the line by
    # falling back to a window, and that window must actually contain line 2.
    proposal = scaffold(Survivor("a.py", 2, "x"), "def broken(:\n    junk here\n    more\n")
    assert "junk here" in proposal.snippet  # the window is centered on the mutated line


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


def test_propose_writes_distinct_files_for_same_line_mutants(project: Project) -> None:
    # Two mutants at one file:line must yield two scaffolds, not one overwriting
    # the other — the integration path where the slug collision actually bit.
    project.write("src/app/m.py", "def f(a, b):\n    return a + b\n")
    ctx = project.context(stage=Stage.FULL)
    ctx.memo(
        "ratchet.survivors",
        lambda: frozenset(
            {Survivor("src/app/m.py", 2, "+->-"), Survivor("src/app/m.py", 2, "+->*")}
        ),
    )
    _propose(ctx)
    proposals = sorted((project.root / ".celebrimbor" / "proposals").glob("*.md"))
    assert len(proposals) == 2


def test_propose_is_inert_without_a_survivor_source(project: Project) -> None:
    # celebrimbor's own case: no mutation_survivors, no injected survivors.
    ctx = project.context(stage=Stage.FULL)
    _propose(ctx)
    assert not (project.root / ".celebrimbor" / "proposals").exists()
