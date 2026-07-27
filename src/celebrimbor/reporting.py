"""Rendering a gate report for a human.

Two principles, both consequences of the fail-closed doctrine rather than of
taste:

**Skips are as visible as failures.** A skipped check is rendered with its
reason, every run, in the summary line. The whole point of forcing a reason at
construction is defeated if the reason is then hidden — a skip nobody sees is
the silent pass with extra steps.

**Refusals read differently from failures.** ``✗`` means we proved something
is wrong and can point at it; ``⊘`` means we could not tell. They need
different fixes, and a report that renders them identically trains the reader
to treat "we could not check" as "there is a bug," which is how people learn
to ignore the second one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .result import CheckResult, GateReport, Verdict

if TYPE_CHECKING:
    from rich.console import Console

_STYLES = {
    Verdict.PASS: "green",
    Verdict.FAIL: "red",
    Verdict.REFUSED: "yellow",
    Verdict.SKIPPED: "dim",
}

_MAX_FINDINGS = 12


def render(report: GateReport, *, verbose: bool = False) -> None:
    """Print a report to the terminal. Imports rich lazily."""
    from rich.console import Console

    console = Console(stderr=False, highlight=False)
    console.print()
    console.print(f"[bold]celebrimbor gate[/] [dim]— tier {report.tier.label}[/]")
    console.print()

    for result in report:
        _render_result(console, result, verbose=verbose)

    console.print()
    console.print(_summary_line(report))
    console.print()


def _render_result(console: Console, result: CheckResult, *, verbose: bool) -> None:
    style = _STYLES[result.verdict]
    timing = f"[dim]{result.duration_s * 1000:.0f}ms[/]" if result.duration_s else ""
    console.print(
        f"  [{style}]{result.verdict.glyph}[/] {result.check_id}  [dim]{result.summary}[/] {timing}"
    )

    # A skip has already said everything it has to say in its summary line.
    if result.verdict is Verdict.SKIPPED and not verbose:
        return

    _render_reason(console, result)
    _render_findings(console, result, verbose=verbose)
    if result.remedy:
        console.print(f"      [cyan]→ {_escape(result.remedy)}[/]")


def _render_reason(console: Console, result: CheckResult) -> None:
    """Why the harness could not conclude. Only refusals carry one visibly."""
    if not result.reason or result.verdict is Verdict.SKIPPED:
        return
    for line in result.reason.splitlines():
        console.print(f"      [yellow]{_escape(line)}[/]")


def _render_findings(console: Console, result: CheckResult, *, verbose: bool) -> None:
    shown = result.findings[:_MAX_FINDINGS]
    for finding in shown:
        location = f"[dim]{finding.location()}[/] " if finding.path else ""
        console.print(f"      [red]·[/] {location}{_escape(finding.message)}")
        if finding.hint and verbose:
            for line in finding.hint.splitlines():
                console.print(f"        [dim]{_escape(line)}[/]")

    hidden = len(result.findings) - len(shown)
    if hidden > 0:
        console.print(f"      [dim]… and {hidden} more (run with -v to widen output)[/]")


def _escape(text: str) -> str:
    """Neutralize rich markup in content we did not author.

    Findings quote source identifiers, and a callable named ``[bold]`` would
    otherwise reformat the report or swallow the message.
    """
    return text.replace("[", "\\[")


def _summary_line(report: GateReport) -> str:
    passed = sum(1 for r in report if r.verdict is Verdict.PASS)
    failed = sum(1 for r in report if r.verdict is Verdict.FAIL)
    refused = sum(1 for r in report if r.verdict is Verdict.REFUSED)
    skipped = len(report.skipped)

    parts = [f"[green]{passed} proved[/]"]
    if failed:
        parts.append(f"[red]{failed} failed[/]")
    if refused:
        parts.append(f"[yellow]{refused} refused[/]")
    if skipped:
        parts.append(f"[dim]{skipped} skipped[/]")

    verdict = "[bold green]PASS[/]" if report.ok else "[bold red]RED[/]"
    if not report.results:
        verdict = "[bold red]RED[/] (no checks ran — an empty gate proves nothing)"
    return f"  {verdict}  " + "  ".join(parts) + f"  [dim]{report.duration_s:.2f}s[/]"


def render_plain(report: GateReport) -> str:
    """A no-colour rendering, for logs, CI annotations and tests."""
    lines = [f"celebrimbor gate — tier {report.tier.label}"]
    for result in report:
        lines.append(f"{result.verdict.glyph} {result.check_id}: {result.summary}")
        if result.reason and result.verdict is not Verdict.SKIPPED:
            lines.extend(f"    {line}" for line in result.reason.splitlines())
        lines.extend(f"    · {finding}" for finding in result.findings[:_MAX_FINDINGS])
    lines.append("PASS" if report.ok else "RED")
    return "\n".join(lines)
