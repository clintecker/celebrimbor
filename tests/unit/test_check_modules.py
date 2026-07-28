"""App check-module loading, and the terminal-last ordering it depends on.

`[tool.celebrimbor] check_modules` lets the CLI import an app's own `@check`
modules so its domain checks run through `celebrimbor gate` itself, not only
through a hand-rolled programmatic entry point (issue #7). Two properties make
it safe: a module that will not import is a hard, fail-closed error; and the
terminal completeness check still runs last, so a check registered *after* it
(which is exactly what loading an app module does) is still covered.
"""

from __future__ import annotations

import pytest

from celebrimbor.checks import CheckModuleError, load_check_modules
from celebrimbor.registry import Registry, check
from celebrimbor.result import CheckResult


def test_load_check_modules_imports_and_returns_names() -> None:
    """The happy path: importable modules load and their names come back."""
    assert load_check_modules(["json", "csv"]) == ("json", "csv")


def test_load_check_modules_empty_is_a_noop() -> None:
    assert load_check_modules([]) == ()


def test_missing_module_is_a_hard_error_not_a_skip() -> None:
    """Fail closed: a declared check that cannot load must not vanish quietly."""
    with pytest.raises(CheckModuleError) as exc:
        load_check_modules(["celebrimbor._no_such_module_"])
    assert "check_modules" in str(exc.value)
    assert "_no_such_module_" in str(exc.value)


def test_import_time_error_propagates_as_check_module_error() -> None:
    """A module that raises *while importing* is a hard error too, with cause."""
    with pytest.raises(CheckModuleError) as exc:
        load_check_modules(["this.module.is.not.real.at.all"])
    assert isinstance(exc.value.__cause__, Exception)


def test_terminal_check_sorts_last_even_when_registered_first() -> None:
    """A normal check registered *after* the terminal one still runs before it.

    This is the ordering an app check hits: the CLI loads the terminal builtin,
    then imports the app module, whose `@check` gets a higher order number. If
    the terminal check did not sort last, it would run before the app check and
    report it as "escaped".
    """
    reg = Registry()

    @check(
        id="app.terminal", title="terminal", terminal=True, falsified_by="tests/x.py", registry=reg
    )
    def _terminal(_ctx: object) -> CheckResult:
        return CheckResult.passed("app.terminal", "ok")

    @check(
        id="app.late",
        title="registered after the terminal one",
        falsified_by="tests/x.py",
        registry=reg,
    )
    def _late(_ctx: object) -> CheckResult:
        return CheckResult.passed("app.late", "ok")

    order = [spec.id for spec in reg]
    assert order[-1] == "app.terminal", f"terminal must sort last, got {order}"
    assert order.index("app.late") < order.index("app.terminal")
