"""The machine-consumable verdict: ``celebrimbor gate --format=agent``.

A pure serialisation of the same :class:`GateReport` the human reads, shaped so
an agent loop can consume the gate's fail-closed refusals as its TODO queue.
The one design rule is a single sentence: **every red verdict becomes exactly
one work item; a green run emits zero.** An agent loop terminates when
``work_items`` is empty.

Two doctrine constraints are enforced structurally here rather than trusted to
a reader:

**No trust surface.** There is no severity, no score, no ranking number an
agent could optimise. ``blocking`` is a boolean, ``totals`` are counts of
facts, and the only float in the whole object is ``duration_s``. A meta-test
walks the emitted object and reddens on any other float.

**``FAIL`` and ``REFUSED`` stay distinct.** A ``FAIL`` carries ``found`` — the
violation the harness can point at. A ``REFUSED`` additionally carries
``refused_because`` — what it could not establish. An agent must not be able to
"fix" a refusal by making the harness stop looking, so the two never collapse.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .registry import default_registry
from .result import CheckResult, Finding, GateReport, Verdict

SCHEMA = "celebrimbor/agent-verdict/1"

# The kind for a REFUSED result that carries no finding to name — a refusal is
# still a work item, but there is no Finding.code to pass through.
_UNESTABLISHED = "unestablished"


def render_agent(report: GateReport) -> str:
    """Serialise a gate report to the agent verdict, as a JSON string.

    Derived from the same report the human sees; adds no field to the frozen
    result types and performs no re-evaluation that could drift from the human
    verdict.
    """
    verdict: dict[str, Any] = {
        "schema": SCHEMA,
        "stage": report.stage.label,
        "ok": report.ok,
        "exit_code": report.exit_code,
        "duration_s": report.duration_s,
        "totals": _totals(report),
        "work_items": _work_items(report),
        "skipped": _skipped(report),
    }
    return json.dumps(verdict, indent=2)


def _totals(report: GateReport) -> dict[str, int]:
    return {
        "proved": sum(1 for r in report if r.verdict is Verdict.PASS),
        "failed": sum(1 for r in report if r.verdict is Verdict.FAIL),
        "refused": sum(1 for r in report if r.verdict is Verdict.REFUSED),
        "skipped": sum(1 for r in report if r.verdict is Verdict.SKIPPED),
    }


def _work_items(report: GateReport) -> list[dict[str, Any]]:
    """One work item per finding on each red result.

    A red result with no findings — only a bare ``REFUSED`` can be one, since
    ``FAIL`` requires findings by construction — still yields exactly one item,
    so no refusal ever disappears from the queue.

    The invariant is total: a red report is never an empty queue. An empty
    report has no red *results* to iterate, yet ``GateReport.ok`` deems it red
    ("an empty report is not ok"). That report-level redness becomes a synthetic
    REFUSED item, so an agent terminating on an empty queue never mistakes a gate
    that ran zero checks for a passing one.
    """
    items: list[dict[str, Any]] = []
    for result in report.red:
        findings: tuple[Finding | None, ...] = result.findings or (None,)
        items.extend(_work_item(result, finding) for finding in findings)
    if not items and not report.ok:
        items.append(_empty_gate_item())
    return items


def _empty_gate_item() -> dict[str, Any]:
    """The one work item standing in for a report that ran zero checks.

    REFUSED, not FAIL: nothing was proved, so there is no violation to point at —
    only something the gate could not establish. Keeping it a refusal preserves
    the FAIL/REFUSED split even for the report-level redness.
    """
    return {
        "id": "celebrimbor.gate#empty",
        "check_id": "celebrimbor.gate",
        "verdict": Verdict.REFUSED.value,
        "kind": "no-checks-ran",
        "blocking": True,
        "found": "the gate ran zero checks",
        "location": {"path": None, "line": None},
        "refused_because": "an empty report proves nothing; a gate that ran no checks is not ok",
    }


def _work_item(result: CheckResult, finding: Finding | None) -> dict[str, Any]:
    kind = _kind(finding)
    found = _found(result, finding)
    location = _location(finding)
    item: dict[str, Any] = {
        "id": _item_id(result.check_id, kind, location, found),
        "check_id": result.check_id,
        "verdict": result.verdict.value,
        "kind": kind,
        "blocking": result.is_red,
        "found": found,
        "location": location,
    }
    claim = _claim(result.check_id)
    if claim is not None:
        item["claim"] = claim
    action = _action(result, finding)
    if action is not None:
        item["action"] = action
    # The load-bearing split: only a REFUSED explains what it could not establish.
    if result.verdict is Verdict.REFUSED:
        item["refused_because"] = result.reason
    return item


def _kind(finding: Finding | None) -> str:
    """The finding's own stable code, verbatim — a pass-through, never a lookup.

    A lookup table from code to kind is a second source of truth that drifts;
    ``Finding.code`` is already the stable string the codebase emits.
    """
    if finding is not None and finding.code:
        return finding.code
    return _UNESTABLISHED


def _found(result: CheckResult, finding: Finding | None) -> str | None:
    if finding is not None:
        return finding.message
    return result.reason


def _location(finding: Finding | None) -> dict[str, Any]:
    if finding is None or finding.path is None:
        return {"path": None, "line": None}
    return {"path": str(finding.path), "line": finding.line}


def _action(result: CheckResult, finding: Finding | None) -> str | None:
    if finding is not None and finding.hint:
        return finding.hint
    return result.remedy


def _claim(check_id: str) -> str | None:
    """The registered check's title, if the registry knows this id.

    Omitted rather than guessed when the check is not registered (e.g. a report
    built directly in a test), so the field is never a fabrication.
    """
    spec = default_registry().get(check_id)
    return spec.title if spec is not None else None


def _item_id(check_id: str, kind: str, location: dict[str, Any], found: str | None) -> str:
    """A deterministic id, stable across runs for the same underlying fact.

    Hashes the fields that identify the fact — kind, path, line, found — so the
    same violation keeps its id between runs and an agent can track it.
    """
    parts = (kind, str(location["path"] or ""), str(location["line"] or ""), found or "")
    digest = hashlib.blake2s("|".join(parts).encode()).hexdigest()[:6]
    return f"{check_id}#{digest}"


def _skipped(report: GateReport) -> list[dict[str, Any]]:
    """Skips, on the record but never a work item — a skip is not a TODO."""
    return [{"check_id": r.check_id, "reason": r.reason} for r in report.skipped]
