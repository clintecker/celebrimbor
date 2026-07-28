"""Tier 0: the commodity ladder. Lint, format, types.

This is the adoption wedge — it must pass on a fresh repo, needs no ledger and
no theory of testing, and it is the only part of celebrimbor an adopter sees on
day one.

All three checks are three lines each, because an :class:`Invocation` carries
its own argv, parser and purpose. That leaves :func:`_run` as the sole place
the no-silent-skip scar is implemented: one policy for a missing tool, in one
function, rather than the same branch copied three times and drifting apart on
the fourth.
"""

from __future__ import annotations

from ..commodity import ladder
from ..commodity.tools import ToolMissingError
from ..commodity.tools import run as run_tool
from ..context import Context
from ..registry import check
from ..result import CheckResult, Stage

_LINT = "celebrimbor.lint"
_FORMAT = "celebrimbor.format"
_TYPES = "celebrimbor.types"

_FAST_TIMEOUT_S = 120


def _missing(ctx: Context, check_id: str, invocation: ladder.Invocation) -> CheckResult:
    """What a missing tool means. The whole no-silent-skip policy, in one place.

    * A trusted environment *promised* the ladder is present. It isn't, so the
      claim is unestablished — ``REFUSED``, red. A warning in a log nobody
      reads is not an acceptable substitute for a gate.
    * Without that promise, skip with the reason on the record, so a
      contributor who has not installed mypy is not blocked from committing by
      a gate CI will run properly anyway.

    The asymmetry is the point: the place where the answer matters is the place
    that fails closed.
    """
    if ctx.config.trusted_environment:
        return CheckResult.refused(
            check_id,
            f"{invocation.tool} is not installed",
            reason=(
                f"this environment is marked trusted, which promises the ladder is "
                f"present, but {invocation.tool} was not found. {invocation.purpose} is "
                f"therefore unestablished — and an unestablished claim is red, not green."
            ),
            remedy=(
                f"install {invocation.tool} (`pip install celebrimbor[tier0]`), "
                "or unset CI / CELEBRIMBOR_TRUSTED"
            ),
        )
    return CheckResult.skipped(
        check_id,
        f"{invocation.tool} is not installed and this is not a trusted environment; "
        f"{invocation.purpose} was not checked here (CI will hard-fail on this)",
    )


def _run(
    ctx: Context,
    check_id: str,
    invocation: ladder.Invocation,
    *,
    clean: str,
    summary: str,
    remedy: str | None = None,
) -> CheckResult:
    """Run one commodity tool and turn its output into a verdict."""
    try:
        result = run_tool(invocation.tool, invocation.args, cwd=ctx.root, timeout_s=_FAST_TIMEOUT_S)
    except ToolMissingError:
        return _missing(ctx, check_id, invocation)

    if result.timed_out:
        return CheckResult.refused(
            check_id,
            f"{invocation.tool} timed out after {_FAST_TIMEOUT_S}s",
            reason=f"{invocation.tool} did not finish, so {invocation.purpose} is unestablished",
        )

    parsed = invocation.parse(result)
    if not parsed.ok:
        return CheckResult.refused(
            check_id,
            f"{invocation.tool} output could not be read",
            reason=parsed.unreadable or "unknown parse failure",
            remedy=f"run `{result.command()}` by hand to see what it is saying",
        )
    if parsed.findings:
        return CheckResult.failed(
            check_id, summary.format(n=len(parsed.findings)), parsed.findings, remedy=remedy
        )
    return CheckResult.passed(check_id, clean)


@check(
    id=_LINT,
    title="the linter finds nothing",
    stage=Stage.FAST,
    falsified_by="tests/negative/test_commodity_gate.py::test_lint_violation_is_red",
)
def check_lint(ctx: Context) -> CheckResult:
    """ruff, with the strict ruleset `celebrimbor init` writes."""
    return _run(
        ctx,
        _LINT,
        ladder.ruff_check(ctx.config.source),
        clean="ruff reports no violations",
        summary="{n} lint violation(s)",
        remedy="many are auto-fixable: `ruff check --fix .`",
    )


@check(
    id=_FORMAT,
    title="every file is formatted",
    stage=Stage.FAST,
    falsified_by="tests/negative/test_commodity_gate.py::test_unformatted_file_is_red",
)
def check_format(ctx: Context) -> CheckResult:
    """Formatting is a gate rather than an autofix on purpose.

    A gate that silently rewrites the tree changes what the adopter is about to
    commit without telling them. Reporting, and letting the pre-commit hook do
    the rewriting, keeps the two actions distinguishable.
    """
    return _run(
        ctx,
        _FORMAT,
        ladder.ruff_format(ctx.config.source),
        clean="all files are formatted",
        summary="{n} file(s) need formatting",
        remedy="run `ruff format .`",
    )


@check(
    id=_TYPES,
    title="the type checker finds nothing",
    stage=Stage.FAST,
    falsified_by="tests/negative/test_commodity_gate.py::test_type_error_is_red",
)
def check_types(ctx: Context) -> CheckResult:
    """mypy in strict mode, on the configured source prefix."""
    return _run(
        ctx,
        _TYPES,
        ladder.mypy(ctx.config.source),
        clean="mypy reports no errors",
        summary="{n} type error(s)",
    )
