"""Negative proof for the invariant ``cli-exit-reflects-verdict``.

The CLI's one load-bearing promise as an adapter is that it propagates the gate's
verdict into the process exit status: ``celebrimbor gate`` exits non-zero when the
report is red, and zero only when every check that ran proved its claim. A CLI
that printed a red report but exited 0 would report success over a failing gate —
the precise silent pass the whole harness exists to prevent.

These tests bite the enforcer directly: they replace the gate *run* with a report
of a known verdict and assert the command's exit status follows it. If ``cli:gate``
were changed to swallow the exit code (``sys.exit(0)``, or no exit at all), the
red case below turns red.
"""

from __future__ import annotations

from pathlib import Path

import celebrimbor.runner as runner_mod
from celebrimbor import cli
from celebrimbor.result import CheckResult, Finding, GateReport, Stage

from click.testing import CliRunner


def _report(result: CheckResult) -> GateReport:
    report = GateReport(stage=Stage.FAST)
    report.add(result)
    return report


def _invoke_gate_returning(monkeypatch, tmp_path: Path, report: GateReport):
    """Invoke ``celebrimbor gate`` with the run stubbed to yield ``report``.

    ``gate`` re-imports ``run`` from the runner module on each call, so patching
    the attribute on the module is what the command actually resolves.
    """
    monkeypatch.setattr(runner_mod, "run", lambda ctx: report)
    return CliRunner().invoke(cli.main, ["gate", "--root", str(tmp_path)])


def test_red_gate_exits_nonzero(monkeypatch, tmp_path: Path) -> None:
    """A red report must drive a non-zero exit — the enforcer's whole job."""
    red = _report(CheckResult.failed("demo.check", "a demo failure", [Finding(message="boom")]))
    result = _invoke_gate_returning(monkeypatch, tmp_path, red)
    assert result.exit_code != 0, "gate reported success over a red report"


def test_green_gate_exits_zero(monkeypatch, tmp_path: Path) -> None:
    """The other half: a proved report must exit 0, or the exit code means nothing."""
    green = _report(CheckResult.passed("demo.check", "proved"))
    result = _invoke_gate_returning(monkeypatch, tmp_path, green)
    assert result.exit_code == 0, f"gate failed a green report (exit {result.exit_code})"
