"""The known-bad provenance auditor.

``tests/known-bad/`` is a directory of files that are *deliberately wrong*, and
each one is a falsifier for a checker: proof that the checker actually rejects
the thing it is supposed to reject. A linter that has never been observed to
reject anything is a linter nobody should trust to reject the case that matters.

The audit is strict in three ways, and each closes a different way the promise
could rot:

* **Orphans caught both directions.** A file with no ``expected.yaml`` entry is
  an orphan (nobody knows what it proves); an entry naming a file that does not
  exist is a stale claim (it proves nothing while looking like it does). Both
  are red.
* **The *right* checker.** "Something complained" is compatible with the exact
  rule you care about having been silently disabled. So the entry names which
  checker must reject the file, and that checker is the one that must fire.
* **The *expected* diagnostic.** Not just rejection, but rejection with the
  named diagnostic code — because a file can be wrong in several ways at once,
  and only one of them is the point.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..commodity.tools import ToolMissingError
from ..commodity.tools import run as run_tool
from ..context import Context
from ..registry import check
from ..result import CheckResult, Finding, Tier
from ..yamlio import YamlError, expect_mapping, load_mapping

_ID = "celebrimbor.known_bad"
_RESERVED = {"README.md", "expected.yaml", "__init__.py"}
_TIMEOUT_S = 60


@dataclass(frozen=True, slots=True)
class Expectation:
    """What a known-bad file is supposed to prove."""

    filename: str
    checker: str
    diagnostic: str
    why: str = ""


def _load_expectations(path: Path) -> dict[str, Expectation]:
    data = load_mapping(path, what="known-bad expected.yaml")
    result: dict[str, Expectation] = {}
    for filename, body in data.items():
        entry = expect_mapping(body, where=f"{path}: {filename}")
        missing = {"checker", "diagnostic"} - set(entry)
        if missing:
            raise YamlError(
                f"{path}: {filename} is missing {', '.join(sorted(missing))}. Every known-bad "
                "file must name the checker that rejects it and the diagnostic it produces."
            )
        result[str(filename)] = Expectation(
            filename=str(filename),
            checker=str(entry["checker"]).strip(),
            diagnostic=str(entry["diagnostic"]).strip(),
            why=str(entry.get("why", "")).strip(),
        )
    return result


def _fixture_files(known_bad_dir: Path) -> set[str]:
    return {
        p.name
        for p in known_bad_dir.iterdir()
        if p.is_file() and p.name not in _RESERVED and not p.name.startswith(".")
    }


def _diagnostics_from(checker: str, file: Path, root: Path) -> set[str] | str:
    """The diagnostic codes ``checker`` produces on ``file``.

    Returns a string starting ``missing:`` when the checker is absent, so the
    caller can apply the no-silent-skip policy. Runs the checker *isolated* from
    project config: a known-bad file lives under a per-file-ignore, and the
    whole point is to see the rule fire regardless.
    """
    if checker == "ruff":
        args = ["check", "--isolated", "--select", "ALL", "--output-format", "json", str(file)]
    elif checker == "mypy":
        args = ["--no-error-summary", "--show-error-codes", "--no-color-output", str(file)]
    else:
        return f"unknown checker {checker!r}; known-bad supports ruff and mypy"

    try:
        result = run_tool(checker, args, cwd=root, timeout_s=_TIMEOUT_S)
    except ToolMissingError:
        return f"missing:{checker}"

    if checker == "ruff":
        return _ruff_codes(result.stdout)
    return _mypy_codes(result.combined)


def _ruff_codes(stdout: str) -> set[str]:
    import json

    try:
        payload = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return set()
    return {
        str(item.get("code")) for item in payload if isinstance(item, dict) and item.get("code")
    }


def _mypy_codes(output: str) -> set[str]:
    import re

    return set(re.findall(r"\[([\w-]+)\]", output))


@check(
    id=_ID,
    title="every known-bad file is rejected by its checker with its diagnostic",
    tier=Tier.FAST,
    falsified_by="tests/negative/test_known_bad_gate.py::test_known_bad_file_not_actually_rejected_is_red",
)
def check_known_bad(ctx: Context) -> CheckResult:
    """Audit tests/known-bad/ for provenance in both directions."""
    directory = ctx.config.known_bad_dir
    expected_path = directory / "expected.yaml"
    if not directory.is_dir() or not expected_path.exists():
        return CheckResult.skipped(
            _ID,
            "no tests/known-bad/expected.yaml; `celebrimbor init` scaffolds one. Known-bad "
            "files are how a checker proves it still rejects what it should.",
        )

    try:
        expectations = _load_expectations(expected_path)
    except YamlError as exc:
        return CheckResult.refused(
            _ID, "known-bad expected.yaml could not be read", reason=str(exc)
        )

    files = _fixture_files(directory)
    findings = _orphan_findings(files, expectations)
    findings.extend(_provenance_findings(files, expectations, directory, ctx.root))

    checked = len(files & set(expectations))
    if findings:
        return CheckResult.failed(_ID, f"{len(findings)} known-bad provenance defect(s)", findings)
    if not checked:
        return CheckResult.passed(_ID, "known-bad directory is empty (nothing declared yet)")
    return CheckResult.passed(_ID, f"{checked} known-bad file(s) rejected as declared")


def _orphan_findings(files: set[str], expectations: dict[str, Expectation]) -> list[Finding]:
    findings: list[Finding] = []
    for filename in sorted(files - set(expectations)):
        findings.append(
            Finding(
                message=f"known-bad file {filename!r} has no entry in expected.yaml",
                code="known-bad-orphan-file",
                hint="add an entry naming the checker and diagnostic it proves, or delete the file",
            )
        )
    for filename in sorted(set(expectations) - files):
        findings.append(
            Finding(
                message=f"expected.yaml names {filename!r}, which does not exist",
                code="known-bad-stale-entry",
                hint="a claim about a file that is gone proves nothing; delete the entry",
            )
        )
    return findings


def _provenance_findings(
    files: set[str], expectations: dict[str, Expectation], directory: Path, root: Path
) -> list[Finding]:
    findings: list[Finding] = []
    for filename in sorted(files & set(expectations)):
        exp = expectations[filename]
        diagnostics = _diagnostics_from(exp.checker, directory / filename, root)
        if isinstance(diagnostics, str):
            findings.append(
                Finding(
                    message=f"cannot verify {filename!r}: {diagnostics.removeprefix('missing:')}",
                    code="known-bad-unverifiable",
                    hint=f"install {exp.checker}, or correct the checker name in expected.yaml",
                )
            )
        elif exp.diagnostic not in diagnostics:
            saw = ", ".join(sorted(diagnostics)) or "nothing"
            findings.append(
                Finding(
                    message=(
                        f"{filename!r} should be rejected by {exp.checker} with {exp.diagnostic}, "
                        f"but {exp.checker} produced: {saw}"
                    ),
                    path=Path(filename),
                    code="known-bad-not-rejected",
                    hint="the rule this file proves is not firing — it may have been disabled",
                )
            )
    return findings
