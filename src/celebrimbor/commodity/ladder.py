"""Tool invocations and their output parsers, paired.

The pairing is the design. An earlier version kept ``ruff_check_args()`` in one
place and ``parse_ruff_json()`` in another, and the cohesion gate scored this
module at four independent domains — correctly, because nothing tied an
argument list to the parser that understood what those arguments would produce.
That is not cosmetic: ``--output-format json`` and "parse JSON" are one
decision, and separating them is how a flag change silently outlives the parser
that depended on it.

So each tool is one :class:`Invocation` carrying its argv *and* the function
that reads the result.

Parsers treat **unparseable output as a refusal**, never as "no findings". A
tool that exited non-zero and printed something we could not read has told us
something is wrong, and reporting clean because we could not understand it is
the exact estimating behaviour this harness refuses.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..result import Finding
from .tools import ToolResult


@dataclass(frozen=True, slots=True)
class ParsedOutput:
    """Findings extracted from a tool run, or the reason we could not."""

    findings: tuple[Finding, ...] = ()
    unreadable: str | None = None

    @property
    def ok(self) -> bool:
        return self.unreadable is None


def _nothing(_result: ToolResult) -> ParsedOutput:
    return ParsedOutput()


@dataclass(frozen=True, slots=True)
class Invocation:
    """How to run one tool, and how to read what it says."""

    tool: str
    args: list[str] = field(default_factory=list)
    parse: Callable[[ToolResult], ParsedOutput] = _nothing
    purpose: str = ""
    """What claim this invocation establishes. Used in the refusal message when
    the tool is missing from a trusted environment, so the adopter is told what
    went unchecked rather than merely which binary was absent."""


# ---------------------------------------------------------------------------
# ruff check
# ---------------------------------------------------------------------------


def _finding_from_ruff(item: Any) -> Finding | None:
    if not isinstance(item, dict):
        return None
    location = item.get("location")
    fix = item.get("fix")
    filename = item.get("filename")
    return Finding(
        message=str(item.get("message", "")).strip(),
        path=Path(str(filename)) if filename else None,
        line=location.get("row") if isinstance(location, dict) else None,
        code=str(item.get("code") or "") or None,
        hint=fix.get("message") if isinstance(fix, dict) else None,
    )


def parse_ruff_json(result: ToolResult) -> ParsedOutput:
    """Ruff emits a JSON array of diagnostics with ``--output-format json``."""
    text = result.stdout.strip()
    if not text:
        if result.ok:
            return ParsedOutput()
        return ParsedOutput(
            unreadable=(
                f"ruff exited {result.returncode} with no JSON on stdout. stderr:\n"
                f"{result.stderr.strip() or '(empty)'}"
            )
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return ParsedOutput(unreadable=f"ruff's JSON output could not be parsed: {exc}")
    if not isinstance(payload, list):
        return ParsedOutput(
            unreadable=f"expected a JSON array from ruff, got {type(payload).__name__}"
        )
    findings = [f for item in payload if (f := _finding_from_ruff(item)) is not None]
    return ParsedOutput(findings=tuple(findings))


def ruff_check(source: str) -> Invocation:
    return Invocation(
        tool="ruff",
        args=["check", "--output-format", "json", "--no-cache", source],
        parse=parse_ruff_json,
        purpose="linting",
    )


# ---------------------------------------------------------------------------
# ruff format
# ---------------------------------------------------------------------------

# Ruff has used two shapes for `format --check`. Older releases print
# "Would reformat: <path>"; current ones print a diagnostic block whose
# location line is "--> <path>:<line>:<col>". Both are matched rather than
# pinning a version, because a parser that silently stops recognising output
# would report a clean pass on an unformatted tree.
_WOULD_REFORMAT = re.compile(
    r"^(?:Would reformat:\s*(?P<legacy>.+)|-->\s*(?P<modern>.+?):\d+:\d+)$"
)


def parse_ruff_format(result: ToolResult) -> ParsedOutput:
    if result.ok:
        return ParsedOutput()

    findings = [
        Finding(
            message="file is not formatted",
            path=Path(named.strip()),
            code="format",
            hint="run `ruff format .`",
        )
        for line in result.combined.splitlines()
        if (match := _WOULD_REFORMAT.match(line.strip()))
        and (named := match["legacy"] or match["modern"])
    ]
    if not findings:
        return ParsedOutput(
            unreadable=(
                f"ruff format exited {result.returncode} without naming any files:\n"
                f"{result.combined[:600] or '(no output)'}"
            )
        )
    return ParsedOutput(findings=tuple(findings))


def ruff_format(source: str) -> Invocation:
    return Invocation(
        tool="ruff",
        args=["format", "--check", "--no-cache", source],
        parse=parse_ruff_format,
        purpose="format checking",
    )


# ---------------------------------------------------------------------------
# mypy
# ---------------------------------------------------------------------------

_MYPY_LINE = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+):(?:\d+:)?\s*"
    r"(?P<severity>error|note|warning):\s*"
    r"(?P<message>.*?)(?:\s+\[(?P<code>[\w-]+)\])?$"
)


def parse_mypy(result: ToolResult) -> ParsedOutput:
    """Parse mypy's ``path:line: error: message [code]`` lines.

    ``note:`` lines are dropped: they continue the error above them, and
    reporting each as its own finding triples the count for no information.
    """
    if result.ok:
        return ParsedOutput()

    findings: list[Finding] = []
    unrecognised: list[str] = []
    for raw in result.combined.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _MYPY_LINE.match(line)
        if match is None:
            unrecognised.append(line)
        elif match["severity"] != "note":
            findings.append(
                Finding(
                    message=match["message"].strip(),
                    path=Path(match["path"]),
                    line=int(match["line"]),
                    code=match["code"],
                )
            )

    # Non-zero exit, nothing recognised, but it printed something: that is a
    # crash or a config error, not a clean run.
    if not findings and unrecognised:
        return ParsedOutput(
            unreadable=(
                "mypy exited non-zero but produced no recognisable diagnostics — "
                "usually a configuration error rather than a type error:\n"
                + "\n".join(unrecognised[:8])
            )
        )
    return ParsedOutput(findings=tuple(findings))


def mypy(source: str) -> Invocation:
    return Invocation(
        tool="mypy",
        args=["--no-error-summary", "--show-error-codes", "--no-color-output", source],
        parse=parse_mypy,
        purpose="type checking",
    )
