"""Shelling out to the commodity ladder, with the no-silent-skip guard.

Celebrimbor never imports ruff, mypy, pytest or a mutation tool. They are
discovered on PATH and invoked as subprocesses. That costs a little startup
time per tool and buys three things worth more: the adopter's pinned versions
are the ones that run, a tool that is absent cannot break celebrimbor's own
import, and there is no dependency-resolution fight between our pins and
theirs.

**The no-silent-skip guard.** A missing tool is the single most dangerous
outcome in this module, because the natural handling — warn and carry on — is
indistinguishable from a pass in every summary anyone actually reads. So the
handling depends on whether a promise was made:

* ``trusted_environment`` is set (CI, or ``CELEBRIMBOR_TRUSTED=1``): the
  environment promised the tool would be there. It isn't. That is a broken
  promise and it is **red** — ``REFUSED``, never skipped.
* No such promise (a dev box): warn and skip, *with the reason on the record*,
  because a contributor without mypy installed should not be blocked from
  committing by a gate that CI will run properly anyway.

The asymmetry is the point. The place where the answer matters is the place
that fails closed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_S = 300


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The outcome of one subprocess invocation."""

    tool: str
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float = 0.0
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def combined(self) -> str:
        return "\n".join(part for part in (self.stdout.strip(), self.stderr.strip()) if part)

    def command(self) -> str:
        return " ".join(self.argv)


class ToolMissingError(RuntimeError):
    """A tool could not be found. Whether that is red depends on the promise."""

    def __init__(self, tool: str, searched: tuple[str, ...]) -> None:
        self.tool = tool
        self.searched = searched
        super().__init__(f"{tool} was not found on PATH")


def _candidate_dirs() -> tuple[str, ...]:
    """Where to look for a tool, beyond PATH.

    The interpreter's own ``bin``/``Scripts`` directory comes first. In the
    overwhelmingly common case — celebrimbor installed into the same virtualenv
    as the ladder — this finds the venv's ruff even when the shell's PATH still
    points at a system one. Getting this wrong means silently linting with a
    different version than the adopter pinned.
    """
    interpreter_bin = Path(sys.executable).parent
    return (str(interpreter_bin),)


def find(tool: str) -> str | None:
    """Absolute path to ``tool``, or None."""
    for directory in _candidate_dirs():
        candidate = Path(directory) / tool
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which(tool)


def available(tool: str) -> bool:
    return find(tool) is not None


def run(
    tool: str,
    args: list[str],
    *,
    cwd: Path,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    env: dict[str, str] | None = None,
) -> ToolResult:
    """Invoke ``tool`` with ``args``. Raises :class:`ToolMissingError` if absent.

    Never uses a shell: the argv is passed through directly, so nothing in a
    filename or a config value can become a command.
    """
    import time

    executable = find(tool)
    if executable is None:
        raise ToolMissingError(tool, _candidate_dirs())

    argv = (executable, *args)
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env={**os.environ, **(env or {})},
        )
    except subprocess.TimeoutExpired as exc:
        return ToolResult(
            tool=tool,
            argv=argv,
            returncode=-1,
            stdout=_decode(exc.stdout),
            stderr=_decode(exc.stderr),
            duration_s=time.perf_counter() - started,
            timed_out=True,
        )
    return ToolResult(
        tool=tool,
        argv=argv,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_s=time.perf_counter() - started,
    )


def _decode(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def version_of(tool: str) -> str | None:
    """``tool --version``, first line. Used to stamp ratchet baselines.

    A baseline recorded under ruff 0.6 and compared under ruff 0.9 is comparing
    two different measurements, so the version goes in the baseline file and a
    mismatch is reported rather than silently absorbed.
    """
    if not available(tool):
        return None
    try:
        result = run(tool, ["--version"], cwd=Path.cwd(), timeout_s=30)
    except (ToolMissingError, OSError):
        return None
    first = result.combined.splitlines()
    return first[0].strip() if first else None
