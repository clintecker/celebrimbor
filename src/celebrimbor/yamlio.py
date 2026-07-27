"""A thin, documented port over PyYAML. Roughly forty lines, on purpose.

Every ledger in celebrimbor is YAML that a human ratifies by hand, so reading
one has a specific failure posture: a ledger that will not parse, or that
parses to the wrong shape, must produce a *refusal*, never a default. The
stdlib gives us nothing here, and a house wrapper that quietly returns ``{}``
on error is precisely the estimating behaviour this project exists to remove.

So this module does two things and no more: ``safe_load`` with errors turned
into a typed exception carrying the file and line, and a dump with stable key
order for diffable output. There is no schema layer, no magic tag handling, no
implicit type coercion beyond what ``safe_load`` already does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class YamlError(ValueError):
    """A YAML file could not be read or was not the expected shape."""


def load_mapping(path: Path, *, what: str = "ledger") -> dict[str, Any]:
    """Read a YAML file that must be a mapping.

    An empty file is an error, not an empty mapping: an adopter who
    accidentally truncated their invariant ledger should see a refusal, not a
    gate that suddenly has nothing to check and therefore passes.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise YamlError(f"{path}: {what} could not be read: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark is not None else ""
        raise YamlError(f"{path}: {what} is not valid YAML{where}: {exc}") from exc
    if data is None:
        raise YamlError(
            f"{path}: {what} is empty. An empty ledger checks nothing, which is not "
            "the same as having nothing to check — delete the file to opt out instead."
        )
    if not isinstance(data, dict):
        raise YamlError(f"{path}: {what} must be a mapping, got {type(data).__name__}")
    return data


def dump(data: Any) -> str:
    """Serialize with stable ordering and block style, for reviewable diffs."""
    return yaml.safe_dump(
        data,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )


def write(path: Path, data: Any, *, header: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dump(data)
    text = f"{header.rstrip()}\n{body}" if header else body
    path.write_text(text, encoding="utf-8")


def expect_mapping(value: Any, *, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise YamlError(f"{where}: expected a mapping, got {type(value).__name__}")
    return value


def expect_list(value: Any, *, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise YamlError(f"{where}: expected a list, got {type(value).__name__}")
    return value
