"""An isolated probe that imports an app's modules and watches for side effects.

Run as a subprocess, never in the gate's own process. Two reasons: importing
arbitrary application code can crash, hang, or pollute ``sys.modules``, and none
of that must be allowed to harm the gate; and the whole point of celebrimbor's
AST inventory is that it *never imports* — so the one check that chooses to
import does it at arm's length, in its own process, on the far side of a
subprocess boundary that the inventory never crosses.

The probe installs guards *before* importing anything. During import, a module
that opens a file for writing, opens a socket, or spawns a process is doing an
import-time side effect — the property that stops a stdlib-only tool from
importing a submodule cheaply. The guards **record and prevent** those, so the
probe both detects the effect and protects the machine it runs on (a module
that writes a file on import does not actually write it here).

Output is one JSON object on stdout: ``{"errors": {mod: msg}, "effects": {mod:
[kinds]}}``. The gate reads it; this module holds no gate logic.
"""

from __future__ import annotations

import builtins
import importlib
import io
import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

# The module currently being imported, so a side effect can be attributed. Import
# is transitive, so attribution is to the top-level module whose import triggered
# the effect — good enough to point a human at where to look.
_current: dict[str, str | None] = {"name": None}
_effects: dict[str, set[str]] = {}


def _flag(kind: str) -> None:
    name = _current["name"]
    if name is not None:
        _effects.setdefault(name, set()).add(kind)


class _BlockedError(RuntimeError):
    """Raised by a guard to prevent a real side effect during import."""


def _install_guards() -> None:
    real_open = builtins.open

    def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(m in mode for m in "wax+"):
            _flag("filesystem-write")
            # Hand back an inert buffer so the write is recorded, not performed.
            return io.BytesIO() if "b" in mode else io.StringIO()
        return real_open(file, mode, *args, **kwargs)

    builtins.open = guarded_open

    import socket

    def guarded_socket(*_args: Any, **_kwargs: Any) -> Any:
        _flag("network")
        raise _BlockedError("socket opened during import")

    socket.socket = guarded_socket  # type: ignore[misc,assignment]

    def guarded_proc(kind: str) -> Callable[..., Any]:
        def guard(*_args: Any, **_kwargs: Any) -> Any:
            _flag("process")
            raise _BlockedError(f"{kind} during import")

        return guard

    subprocess.Popen = guarded_proc("subprocess")  # type: ignore[misc,assignment]
    subprocess.run = guarded_proc("subprocess")
    subprocess.call = guarded_proc("subprocess")
    subprocess.check_output = guarded_proc("subprocess")

    import os

    os.system = guarded_proc("os.system")


def main() -> int:
    path_entry = sys.argv[1]
    names = sys.argv[2:]
    sys.path.insert(0, path_entry)
    _install_guards()

    errors: dict[str, str] = {}
    for name in names:
        _current["name"] = name
        try:
            importlib.import_module(name)
        except _BlockedError as exc:
            # A blocked side effect that also aborted the import. The effect is
            # already flagged; record the import failure too, since a module that
            # cannot import without a side effect has an import-time side effect.
            errors[name] = f"blocked side effect during import: {exc}"
        except BaseException as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
        finally:
            _current["name"] = None

    print(json.dumps({"errors": errors, "effects": {k: sorted(v) for k, v in _effects.items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
