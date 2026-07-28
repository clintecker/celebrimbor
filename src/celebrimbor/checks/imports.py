"""The import-health gate: the package imports cleanly, with no import-time effects.

This is the one gate that imports the application. Everything else in celebrimbor
is AST-only — deliberately, so the completeness guarantee can never fall behind
code that fails to import. This check *chooses* to import, and it does so on the
far side of a subprocess boundary (:mod:`celebrimbor._import_probe`) that the AST
inventory never crosses. The two live in separate processes so the guarantee and
the convenience never contaminate each other.

It is **opt-in** — ``import_check = true`` in config — because importing runs the
adopter's code. Off by default, it skips with a reason. On, it reports two
things the AST cannot see:

* a module that does not import (an import-time ``NameError``, a missing optional
  dependency, a circular import that only bites at import time);
* a module that performs a side effect *while importing* (writes a file, opens a
  socket, spawns a process) — the property that lets a stdlib-only tool import a
  submodule cheaply.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..context import Context
from ..registry import Family, check
from ..result import CheckResult, Finding, Stage
from ..surface.inventory import ModuleInfo
from ._shared import get_inventory

_ID = "celebrimbor.imports"
_TIMEOUT_S = 120


def _import_name(module: ModuleInfo, source_dir: Path) -> str | None:
    """The name ``importlib`` would use for this module.

    Bridges celebrimbor's source-relative dotted names to real import paths. If
    the source prefix points *at* a package (``src/press`` with an ``__init__``),
    its parent goes on the path and modules import as ``press.<dotted>``; if it
    is a src-root (``src/`` with no ``__init__``), the source goes on the path and
    modules import as their dotted name directly.
    """
    if not module.dotted:
        return None
    if (source_dir / "__init__.py").exists():
        pkg = source_dir.name
        return pkg if module.dotted == pkg else f"{pkg}.{module.dotted}"
    return module.dotted


def _path_entry(source_dir: Path) -> Path:
    return source_dir.parent if (source_dir / "__init__.py").exists() else source_dir


@check(
    id=_ID,
    title="every module imports cleanly, with no import-time side effects",
    stage=Stage.DEFAULT,
    family=Family.OBLIGATION,
    falsified_by="tests/negative/test_import_gate.py::test_module_that_raises_on_import_is_red",
)
def check_imports(ctx: Context) -> CheckResult:
    """Import every module in an isolated subprocess and report faults."""
    if not ctx.config.import_check:
        return CheckResult.skipped(
            _ID,
            "the import-health check is opt-in (it imports your code, unlike every other "
            "gate). Set `import_check = true` in [tool.celebrimbor] to enable it.",
        )

    inv = get_inventory(ctx)
    source_dir = ctx.config.source_dir
    names = [n for m in inv.modules if (n := _import_name(m, source_dir)) is not None]
    if not names:
        return CheckResult.refused(
            _ID,
            "no importable modules were found",
            reason=f"nothing to import under {ctx.config.source!r}",
        )

    probe = _run_probe(ctx, _path_entry(source_dir), names)
    if isinstance(probe, CheckResult):
        return probe

    findings = _findings(probe)
    if findings:
        return CheckResult.failed(_ID, f"{len(findings)} import-health defect(s)", findings)
    return CheckResult.passed(_ID, f"{len(names)} module(s) import cleanly, no import-time effects")


def _run_probe(ctx: Context, path_entry: Path, names: list[str]) -> dict[str, object] | CheckResult:
    """Run the probe subprocess and parse its JSON, or a refusal."""
    import subprocess

    argv = [sys.executable, "-m", "celebrimbor._import_probe", str(path_entry), *names]
    try:
        proc = subprocess.run(
            argv, cwd=str(ctx.root), capture_output=True, text=True, timeout=_TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired:
        return CheckResult.refused(
            _ID,
            f"importing the package timed out after {_TIMEOUT_S}s",
            reason="a module blocks on import; the harness cannot conclude, so it refuses",
        )
    except OSError as exc:
        return CheckResult.refused(_ID, "the import probe could not run", reason=str(exc))

    try:
        parsed: dict[str, object] = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return CheckResult.refused(
            _ID,
            "the import probe produced no readable result",
            reason=(
                "the subprocess importing your package crashed before reporting. "
                f"stderr:\n{proc.stderr.strip()[:600] or '(empty)'}"
            ),
        )
    return parsed


def _findings(probe: dict[str, object]) -> list[Finding]:
    findings: list[Finding] = []
    errors: dict[str, str] = probe.get("errors") or {}  # type: ignore[assignment]
    for module, message in sorted(errors.items()):
        findings.append(
            Finding(
                message=f"{module} does not import: {message}",
                code="import-error",
                hint="fix the import-time fault; a module that will not import cannot be used",
            )
        )
    effects: dict[str, list[str]] = probe.get("effects") or {}  # type: ignore[assignment]
    for module, kinds in sorted(effects.items()):
        findings.append(
            Finding(
                message=f"{module} performs a side effect while importing: {', '.join(kinds)}",
                code="import-side-effect",
                hint="move the effect out of import time into a function called explicitly",
            )
        )
    return findings
