"""An in-process known-bad checker, used by the callable-seam tests (issue #10).

Stands in for an app's book-context-bound editorial linter: it takes a fixture
path and returns human-phrase diagnostics with a variable part (the position)
and a stable signature phrase.
"""

from __future__ import annotations

from pathlib import Path


def diagnostics_for(file: Path) -> list[str]:
    text = Path(file).read_text(encoding="utf-8")
    out: list[str] = []
    if "badword" in text:
        out.append(f"{file.name}:1: message contains a badword here")
    return out
