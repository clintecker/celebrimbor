"""Negative fixtures for the commodity ladder, including the no-silent-skip scar.

These shell out to real ruff and real mypy. That is slower than parsing canned
output, and it is the point: the parsers exist to read what these tools
*actually* print, and a fixture fed canned output would keep passing after the
tool changed its format — which is exactly the bug that shipped once already.
"""

from __future__ import annotations

import pytest

from celebrimbor.commodity.tools import available
from celebrimbor.result import Verdict
from tests.conftest import Project

pytestmark = pytest.mark.negative

_LINT = "celebrimbor.lint"
_FORMAT = "celebrimbor.format"
_TYPES = "celebrimbor.types"

needs_ruff = pytest.mark.skipif(not available("ruff"), reason="ruff is not installed")
needs_mypy = pytest.mark.skipif(not available("mypy"), reason="mypy is not installed")

_STRICT = """
[project]
name = "fixture"
version = "0.0.0"

[tool.celebrimbor]
source = "src"

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.mypy]
python_version = "3.11"
strict = true
"""


@needs_ruff
def test_lint_violation_is_red(project: Project) -> None:
    """An unused import is exactly the kind of thing the ruleset must catch."""
    project.pyproject(_STRICT)
    project.module("app.sloppy", "import os\n\n\ndef go() -> int:\n    return 1\n")
    result = project.run(_LINT)
    assert result.verdict is Verdict.FAIL
    assert any(f.code == "F401" for f in result.findings)


@needs_ruff
def test_clean_module_lints_green(project: Project) -> None:
    """The other half of the fixture: it must also be capable of passing."""
    project.pyproject(_STRICT)
    project.module("app.tidy", '"""Tidy."""\n\n\ndef go() -> int:\n    """Go."""\n    return 1\n')
    assert project.run(_LINT).verdict is Verdict.PASS


@needs_ruff
def test_unformatted_file_is_red(project: Project) -> None:
    """Proves the format parser still understands this ruff's output shape.

    Ruff has changed the wording of `format --check` between releases, and the
    parser silently stopped recognising it — reporting a clean pass over an
    unformatted tree. This fixture is what makes that visible.
    """
    project.pyproject(_STRICT)
    project.module("app.messy", '"""Messy."""\n\n\ndef go(  a,b ) :\n    return    a+b\n')
    result = project.run(_FORMAT)
    assert result.verdict is Verdict.FAIL
    assert any(f.code == "format" for f in result.findings)
    assert any("messy" in str(f.path) for f in result.findings)


@needs_mypy
def test_type_error_is_red(project: Project) -> None:
    """A real type error, through a real mypy, parsed by our real parser."""
    project.pyproject(_STRICT)
    project.module(
        "app.wrong",
        '"""Wrong."""\n\n\ndef go() -> int:\n    """Go."""\n    return "not an int"\n',
    )
    result = project.run(_TYPES)
    assert result.verdict is Verdict.FAIL
    assert any(f.code == "return-value" for f in result.findings)


def test_missing_tool_in_trusted_environment_refuses(project: Project) -> None:
    """The no-silent-skip scar, in the direction that matters.

    A trusted environment *promised* the ladder is present. When it is not, the
    claim is unestablished — and an unestablished claim is red. A warning in a
    log nobody reads is not an acceptable substitute for a gate.
    """
    project.pyproject(
        """
        [project]
        name = "fixture"
        version = "0.0.0"

        [tool.celebrimbor]
        source = "src"
        trusted_environment = true
        formatter = "definitely-not-a-real-tool"
        """
    )
    project.module("app.thing", "def go() -> int:\n    return 1\n")

    from celebrimbor.checks.commodity import _missing
    from celebrimbor.commodity.ladder import Invocation

    result = _missing(
        project.context(),
        _LINT,
        Invocation(tool="definitely-not-a-real-tool", purpose="linting"),
    )
    assert result.verdict is Verdict.REFUSED
    assert "marked trusted" in (result.reason or "")


def test_missing_tool_without_a_promise_skips_with_a_reason(project: Project) -> None:
    """The other direction: no promise made, so a dev box is not blocked.

    But the skip carries its reason and is not a pass — `proved` is False, and
    the reason names what went unchecked.
    """
    project.pyproject(
        """
        [project]
        name = "fixture"
        version = "0.0.0"

        [tool.celebrimbor]
        source = "src"
        trusted_environment = false
        """
    )
    from celebrimbor.checks.commodity import _missing
    from celebrimbor.commodity.ladder import Invocation

    result = _missing(
        project.context(),
        _LINT,
        Invocation(tool="definitely-not-a-real-tool", purpose="linting"),
    )
    assert result.verdict is Verdict.SKIPPED
    assert not result.proved
    assert "CI will hard-fail" in (result.reason or "")


@needs_ruff
def test_unreadable_tool_output_refuses_rather_than_passing(project: Project) -> None:
    """A tool we cannot understand has not told us things are fine."""
    from celebrimbor.commodity.ladder import parse_mypy, parse_ruff_json
    from celebrimbor.commodity.tools import ToolResult

    broken = ToolResult(
        tool="ruff", argv=("ruff",), returncode=2, stdout="not json at all", stderr=""
    )
    assert not parse_ruff_json(broken).ok

    confused = ToolResult(
        tool="mypy",
        argv=("mypy",),
        returncode=2,
        stdout="mypy.ini: [mypy]: Unrecognized option",
        stderr="",
    )
    parsed = parse_mypy(confused)
    assert not parsed.ok
    assert "configuration error" in (parsed.unreadable or "")
