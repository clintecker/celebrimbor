"""The vacuity gate: no assertion in the codebase is a tautology.

An assertion that holds for every input proves nothing — it can never turn red,
so a test resting on it passes vacuously. This gate reads every ``.py`` under
both the source tree and the test tree and reddens on any ``assert`` whose
condition is provably true for every input (``assert True``, ``assert x is x``,
``assert e or True``). The detection lives in :mod:`celebrimbor.structure.vacuity`
and is deliberately conservative: it fires only on syntactically closed
tautologies, never on an assertion whose truth depends on a value.

It is a ``commodity`` gate — no authored ledger, green on a clean repo — and it
runs at the ``FAST`` stage because it is pure AST.

Two exclusions keep it honest rather than noisy:

* the known-bad directory is skipped — its files are deliberately broken source
  on purpose, not assertions the suite makes, and one of them failing to parse
  must not take the whole run down with it;
* the configured ``exclude`` globs are honoured, the same set the surface
  inventory uses.

A file that will not parse (and is *not* a known-bad fixture) is a refusal, not
a pass: the gate is AST-only, so a file it cannot read is a claim it cannot
establish, and REFUSED is the fail-closed home for that.
"""

from __future__ import annotations

import ast
import fnmatch
from collections.abc import Iterator
from pathlib import Path

from ..context import Context
from ..registry import Family, check
from ..result import CheckResult, Finding, Stage
from ..structure.vacuity import tautologies
from ._shared import get_inventory

_ID = "celebrimbor.vacuity"


def _findings(tree: ast.AST, rel: Path) -> list[Finding]:
    return [
        Finding(message=v.message, path=rel, line=v.line, code="assert-tautology")
        for v in tautologies(tree)
    ]


def _excluded(rel: Path, patterns: tuple[str, ...]) -> bool:
    text = rel.as_posix()
    return "__pycache__" in rel.parts or any(fnmatch.fnmatch(text, pat) for pat in patterns)


def _test_files(ctx: Context) -> Iterator[tuple[Path, Path]]:
    """Every ``.py`` under the test tree except known-bad and excluded files.

    Yields ``(absolute, root-relative)`` pairs. Test files are not in the source
    inventory, so the gate parses them here — but with the same known-bad and
    ``exclude`` exemptions the inventory applies to source.
    """
    config = ctx.config
    tests_dir = config.tests_dir
    if not tests_dir.is_dir():
        return
    known_bad = config.known_bad_dir
    for path in sorted(tests_dir.rglob("*.py")):
        if path.is_relative_to(known_bad):
            continue
        rel = path.relative_to(config.root)
        if _excluded(rel, config.exclude):
            continue
        yield path, rel


@check(
    id=_ID,
    title="no assertion is a tautology",
    stage=Stage.FAST,
    family=Family.COMMODITY,
    falsified_by="tests/negative/test_vacuity_gate.py::test_tautological_assert_is_red",
)
def check_vacuity(ctx: Context) -> CheckResult:
    """Reject any ``assert`` that holds for every input.

    Scans source (reusing the already-parsed inventory) and tests (parsed here,
    since they are not in that inventory). One finding per tautological assert;
    an unparseable non-known-bad file refuses; a clean tree passes.
    """
    findings: list[Finding] = []
    unparseable: list[str] = []
    scanned = 0

    for module in get_inventory(ctx).modules:
        if module.tree is None:
            unparseable.append(f"{module.path}: {module.parse_error}")
            continue
        scanned += 1
        findings.extend(_findings(module.tree, module.path))

    for path, rel in _test_files(ctx):
        try:
            tree = ast.parse(path.read_bytes(), filename=str(path))
        except (SyntaxError, ValueError) as exc:
            unparseable.append(f"{rel}: {exc}")
            continue
        scanned += 1
        findings.extend(_findings(tree, rel))

    if unparseable:
        return CheckResult.refused(
            _ID,
            f"{len(unparseable)} file(s) could not be parsed",
            reason=(
                "the vacuity gate is AST-only, so a file it cannot parse is a claim it "
                "cannot establish and must not silently pass: " + "; ".join(unparseable[:5])
            ),
        )
    if findings:
        return CheckResult.failed(
            _ID,
            f"{len(findings)} tautological assertion(s) — "
            "an assertion that holds for every input proves nothing",
            findings,
            remedy="make the assertion depend on a value it could contradict, or delete it",
        )
    if not scanned:
        return CheckResult.refused(
            _ID,
            "no source or test files were found to scan",
            reason=(
                "an empty tree contains no assertions, which proves nothing rather than "
                "proving no tautology — so this refuses instead of reporting a clean pass"
            ),
            remedy="set `source`/`tests` in celebrimbor.toml if the layout is unconventional",
        )
    return CheckResult.passed(_ID, f"{scanned} file(s) contain no tautological assertion")
