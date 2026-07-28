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
from ..config import CheckerSpec
from ..context import Context
from ..registry import check
from ..result import CheckResult, Finding, Stage
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


def _diagnostics_from(
    checker: str, file: Path, root: Path, checkers: dict[str, CheckerSpec]
) -> set[str] | str:
    """What ``checker`` emits for ``file`` — a set of diagnostic strings, or an
    error string (starting ``missing:`` when the checker is absent).

    ``ruff`` and ``mypy`` are built-in shorthands; any other name is resolved
    from an app's ``[tool.celebrimbor.known_bad_checkers]`` and run either as a
    subprocess (``command``) or in-process (``callable``). Runs the checker
    *isolated* from project config where it can: a known-bad file lives under a
    per-file-ignore, and the whole point is to see the rule fire regardless.
    """
    if checker == "ruff":
        args = ["check", "--isolated", "--select", "ALL", "--output-format", "json", str(file)]
    elif checker == "mypy":
        args = ["--no-error-summary", "--show-error-codes", "--no-color-output", str(file)]
    elif checker in checkers:
        spec = checkers[checker]
        if spec.callable_ref is not None:
            return _callable_diagnostics(spec.callable_ref, file)
        return _command_diagnostics(str(spec.command), spec.code_pattern, file, root)
    else:
        known = ", ".join(sorted({"ruff", "mypy", *checkers}))
        return (
            f"unknown checker {checker!r}; known-bad runs ruff, mypy, and checkers you declare "
            f"in [tool.celebrimbor.known_bad_checkers] (available: {known})"
        )

    try:
        result = run_tool(checker, args, cwd=root, timeout_s=_TIMEOUT_S)
    except ToolMissingError:
        return f"missing:{checker}"

    if checker == "ruff":
        return _ruff_codes(result.stdout)
    return _mypy_codes(result.combined)


def _command_diagnostics(
    command: str, pattern: str | None, file: Path, root: Path
) -> set[str] | str:
    """Run an app-declared checker *command* and extract its diagnostics."""
    import shlex

    argv = shlex.split(command.replace("{file}", str(file)))
    if not argv:
        return "missing:empty command"
    tool, args = argv[0], argv[1:]
    try:
        result = run_tool(tool, args, cwd=root, timeout_s=_TIMEOUT_S)
    except ToolMissingError:
        return f"missing:{tool}"
    return _custom_codes(result.combined, pattern)


def _callable_diagnostics(ref: str, file: Path) -> set[str] | str:
    """Import a ``module:function`` and call it *in-process* on ``file``.

    For a checker with no clean per-file subprocess entry (book-context-bound
    linters). The function is handed the fixture path and returns the diagnostic
    strings it produces. Every failure mode — a malformed ref, a module or
    attribute that will not import, a checker that raises — is a fail-closed
    error string, never a silent pass.
    """
    module_name, sep, func_name = ref.partition(":")
    if not sep or not func_name:
        return f"malformed callable {ref!r}; expected 'module:function'"
    import importlib

    try:
        func = getattr(importlib.import_module(module_name), func_name)
    except (ImportError, AttributeError) as exc:
        return f"missing:{ref} ({type(exc).__name__}: {exc})"
    try:
        produced = func(file)
    except Exception as exc:  # a checker that blows up is unverifiable, not a pass
        return f"checker {ref} raised on {file.name}: {type(exc).__name__}: {exc}"
    return {str(item) for item in produced}


def _diagnostic_matches(diagnostic: str, produced: set[str], spec: CheckerSpec | None) -> bool:
    """Whether the declared diagnostic is present in what the checker emitted.

    ``exact`` (the default, and always for ruff/mypy) wants an exact element;
    ``substring`` wants the declared phrase inside some emitted line, for a
    linter whose message has a stable signature phrase and a variable part.
    """
    if spec is not None and spec.match == "substring":
        return any(diagnostic in line for line in produced)
    return diagnostic in produced


def _custom_codes(output: str, pattern: str | None) -> set[str]:
    """Diagnostic codes from a custom checker's output.

    With no pattern, each non-empty line is a code. With one, its first group
    (or the whole match) is the code, taken per match across the output — so a
    line like ``EM-DASH path:12`` yields ``EM-DASH`` for ``pattern = '^(\\S+)'``.
    """
    if not pattern:
        return {line.strip() for line in output.splitlines() if line.strip()}
    import re

    rx = re.compile(pattern, re.MULTILINE)
    return {(m.group(1) if m.groups() else m.group(0)) for m in rx.finditer(output)}


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
    stage=Stage.FAST,
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
    findings.extend(
        _provenance_findings(
            files, expectations, directory, ctx.root, ctx.config.known_bad_checkers
        )
    )

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
    files: set[str],
    expectations: dict[str, Expectation],
    directory: Path,
    root: Path,
    checkers: dict[str, CheckerSpec],
) -> list[Finding]:
    findings: list[Finding] = []
    for filename in sorted(files & set(expectations)):
        exp = expectations[filename]
        diagnostics = _diagnostics_from(exp.checker, directory / filename, root, checkers)
        if isinstance(diagnostics, str):
            findings.append(
                Finding(
                    message=f"cannot verify {filename!r}: {diagnostics.removeprefix('missing:')}",
                    code="known-bad-unverifiable",
                    hint=(
                        f"install {exp.checker}, correct the checker name, or declare it under "
                        "[tool.celebrimbor.known_bad_checkers]"
                    ),
                )
            )
        elif not _diagnostic_matches(exp.diagnostic, diagnostics, checkers.get(exp.checker)):
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
