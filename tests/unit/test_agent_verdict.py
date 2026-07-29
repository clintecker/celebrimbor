"""The agent verdict: ``celebrimbor gate --format=agent``.

These tests construct :class:`GateReport` objects directly rather than pointing
a real gate at a project, because the serialiser's whole job is the shape of the
output — the mapping from verdicts to work items — and that is exactly what a
directly-built report exercises without a project on disk.

The load-bearing properties, each with a test below:

* a green report emits zero work items (an agent loop's terminate condition);
* ``FAIL`` and ``REFUSED`` stay structurally distinct — the former carries
  ``found``, the latter additionally ``refused_because``;
* ``SKIPPED`` is never a work item, only an entry in ``skipped``;
* ids are deterministic across runs;
* the only float anywhere in the object is ``duration_s`` (the no-score guard).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from celebrimbor.agent import render_agent
from celebrimbor.result import CheckResult, Finding, GateReport, Stage


def _render(*results: CheckResult, duration_s: float = 1.5) -> dict[str, Any]:
    report = GateReport(stage=Stage.DEFAULT, duration_s=duration_s)
    for result in results:
        report.add(result)
    payload = render_agent(report)
    parsed: dict[str, Any] = json.loads(payload)
    return parsed


def test_green_report_has_no_work_items() -> None:
    verdict = _render(CheckResult.passed("celebrimbor.lint", "no violations"))
    assert verdict["ok"] is True
    assert verdict["exit_code"] == 0
    assert verdict["work_items"] == []
    assert verdict["totals"] == {"proved": 1, "failed": 0, "refused": 0, "skipped": 0}


def test_fail_yields_a_work_item_with_found_and_no_refused_because() -> None:
    result = CheckResult.failed(
        "celebrimbor.surface.evidence",
        "a role is contradicted",
        Finding(
            message="build is declared verifier but can never turn red",
            path=Path("src/myapp/report.py"),
            line=42,
            code="role-contradicted",
            hint="give it a rejecting path",
        ),
    )
    verdict = _render(result)
    assert verdict["ok"] is False
    assert verdict["exit_code"] == 1
    (item,) = verdict["work_items"]
    assert item["verdict"] == "fail"
    assert item["kind"] == "role-contradicted"
    assert item["blocking"] is True
    assert item["found"] == "build is declared verifier but can never turn red"
    assert item["action"] == "give it a rejecting path"
    assert item["location"] == {"path": "src/myapp/report.py", "line": 42}
    assert "refused_because" not in item


def test_refused_yields_a_work_item_with_refused_because() -> None:
    result = CheckResult.refused(
        "celebrimbor.invariants",
        "an invariant lacks a real negative proof",
        "the named negative proof could not be resolved to a real test",
        remedy="write the negative proof, or drop `critical: true`",
    )
    verdict = _render(result)
    (item,) = verdict["work_items"]
    assert item["verdict"] == "refused"
    assert item["kind"] == "unestablished"
    assert item["blocking"] is True
    assert item["found"] == "the named negative proof could not be resolved to a real test"
    assert (
        item["refused_because"] == "the named negative proof could not be resolved to a real test"
    )
    assert item["action"] == "write the negative proof, or drop `critical: true`"


def test_refused_with_a_finding_keeps_found_and_refused_because_distinct() -> None:
    """A REFUSED may still carry a finding; then ``found`` (the finding's
    message) and ``refused_because`` (the result's reason) are different facts."""
    result = CheckResult(
        check_id="celebrimbor.invariants",
        verdict=CheckResult.refused("x", "s", "r").verdict,  # Verdict.REFUSED
        summary="an invariant lacks a real negative proof",
        findings=(
            Finding(
                message="invariant 'order-has-customer' has no resolvable negative_proof",
                path=Path(".celebrimbor/invariants.yaml"),
                code="invariant-proof-absent",
            ),
        ),
        reason="the named negative proof could not be resolved to a real test",
    )
    verdict = _render(result)
    (item,) = verdict["work_items"]
    assert item["found"] == "invariant 'order-has-customer' has no resolvable negative_proof"
    assert (
        item["refused_because"] == "the named negative proof could not be resolved to a real test"
    )
    assert item["found"] != item["refused_because"]
    assert item["kind"] == "invariant-proof-absent"


def test_skipped_is_absent_from_work_items_and_present_in_skipped() -> None:
    result = CheckResult.skipped(
        "celebrimbor.coverage", "no coverage baseline yet, and not the pinned environment"
    )
    verdict = _render(
        CheckResult.passed("celebrimbor.lint", "no violations"),
        result,
    )
    assert verdict["work_items"] == []
    assert verdict["skipped"] == [
        {
            "check_id": "celebrimbor.coverage",
            "reason": "no coverage baseline yet, and not the pinned environment",
        }
    ]
    # A skip does not redden the gate, but it is not a proof either.
    assert verdict["ok"] is True
    assert verdict["totals"]["skipped"] == 1


def test_ids_are_deterministic_across_runs() -> None:
    result = CheckResult.failed(
        "celebrimbor.surface.evidence",
        "a role is contradicted",
        Finding(message="never turns red", path=Path("src/a.py"), line=7, code="role-contradicted"),
    )
    first = _render(result)
    second = _render(result)
    assert first["work_items"][0]["id"] == second["work_items"][0]["id"]
    # And the id is anchored on the check_id.
    assert first["work_items"][0]["id"].startswith("celebrimbor.surface.evidence#")


def test_two_findings_on_one_result_become_two_work_items() -> None:
    result = CheckResult.failed(
        "celebrimbor.structure.complexity",
        "two modules over budget",
        [
            Finding(message="a.py too complex", path=Path("src/a.py"), code="structure-module"),
            Finding(message="b.py too complex", path=Path("src/b.py"), code="structure-module"),
        ],
    )
    verdict = _render(result)
    assert len(verdict["work_items"]) == 2
    ids = {item["id"] for item in verdict["work_items"]}
    assert len(ids) == 2  # distinct facts get distinct ids


def test_every_red_result_across_a_multi_red_report_becomes_a_work_item() -> None:
    """The central fail-closed property, asserted directly across a report with
    multiple red results of different kinds and ids: every red check_id is
    represented, red iff the queue is non-empty, and the queue never holds fewer
    items than there are red results."""
    verdict = _render(
        CheckResult.failed(
            "celebrimbor.surface.evidence",
            "a role is contradicted",
            Finding(
                message="never turns red", path=Path("src/a.py"), line=7, code="role-contradicted"
            ),
        ),
        CheckResult.refused(
            "celebrimbor.invariants",
            "an invariant lacks a real negative proof",
            "the named negative proof could not be resolved to a real test",
        ),
        CheckResult.failed(
            "celebrimbor.structure.complexity",
            "a module is over budget",
            Finding(message="a.py too complex", path=Path("src/a.py"), code="structure-module"),
        ),
    )
    red_check_ids = {
        "celebrimbor.surface.evidence",
        "celebrimbor.invariants",
        "celebrimbor.structure.complexity",
    }
    item_check_ids = {item["check_id"] for item in verdict["work_items"]}
    assert red_check_ids <= item_check_ids  # every red check_id is represented
    assert (verdict["exit_code"] == 1) == bool(verdict["work_items"])  # red iff non-empty queue
    assert len(verdict["work_items"]) >= verdict["totals"]["failed"] + verdict["totals"]["refused"]


def test_empty_report_is_red_and_leaves_exactly_one_work_item() -> None:
    """An empty report is RED (``GateReport.ok`` deems it so), so it must never
    hand an agent an empty queue — the terminate condition — as though it passed.
    The report-level redness becomes exactly one synthetic REFUSED item."""
    verdict = _render()  # zero results
    assert verdict["ok"] is False
    assert verdict["exit_code"] == 1
    (item,) = verdict["work_items"]
    assert item["verdict"] == "refused"  # REFUSED, not FAIL: nothing was proved
    assert item["check_id"] == "celebrimbor.gate"
    assert item["blocking"] is True
    assert "refused_because" in item
    # Red iff non-empty queue holds for the empty report too.
    assert (verdict["exit_code"] == 1) == bool(verdict["work_items"])


def _floats_outside(node: Any, key: str | None, path: str) -> list[str]:
    """Every location holding a float, other than the key ``duration_s``."""
    hits: list[str] = []
    if isinstance(node, bool):
        return hits  # bool is an int subclass but never a float; not a score
    if isinstance(node, float):
        if key != "duration_s":
            hits.append(path)
        return hits
    if isinstance(node, dict):
        for k, v in node.items():
            hits.extend(_floats_outside(v, k, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits.extend(_floats_outside(v, key, f"{path}[{i}]"))
    return hits


def test_no_float_anywhere_except_duration_s() -> None:
    """The no-score guard: a severity or quality float would let an agent
    optimise a number instead of clearing the fact. There must be none."""
    verdict = _render(
        CheckResult.failed(
            "celebrimbor.surface.evidence",
            "contradicted",
            Finding(message="m", path=Path("src/a.py"), line=1, code="role-contradicted"),
        ),
        CheckResult.refused("celebrimbor.invariants", "s", "r"),
        CheckResult.skipped("celebrimbor.coverage", "no baseline"),
        duration_s=2.14,
    )
    assert _floats_outside(verdict, None, "$") == []


def test_output_is_valid_json() -> None:
    report = GateReport(stage=Stage.FAST, duration_s=0.3)
    report.add(CheckResult.passed("celebrimbor.lint", "ok"))
    # Round-trips without raising, and names its schema.
    parsed = json.loads(render_agent(report))
    assert parsed["schema"] == "celebrimbor/agent-verdict/1"
    assert parsed["stage"] == "fast"
