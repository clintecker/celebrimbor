"""Negative fixtures for the structure ratchet.

The comparator is pure, so most of these test it directly. The gate-level
fixtures prove the whole flow: strict with no baseline, grandfather on
``--update``, and fail only new-or-worsened afterward — the adoption path for a
codebase with existing structure debt.
"""

from __future__ import annotations

import pytest

from celebrimbor.config import Config
from celebrimbor.context import Context
from celebrimbor.ratchets.baseline import BaselineEnvironmentError
from celebrimbor.ratchets.structure import Breach, StructureBaseline, ratchet, rebaseline
from celebrimbor.result import Tier, Verdict
from celebrimbor.runner import run_spec
from tests.conftest import Project

pytestmark = pytest.mark.negative

_COMPLEXITY = "celebrimbor.structure.complexity"


def _b(key: str, value: int) -> Breach:
    return Breach(key=key, value=value, message=key)


# ---------------------------------------------------------------------------
# comparator (pure)
# ---------------------------------------------------------------------------


def test_no_baseline_is_strict() -> None:
    """Greenfield stays strict: with no baseline every breach survives."""
    current = [_b("complexity/a:f:cyclomatic-complexity", 14)]
    assert ratchet(current, None).survived == tuple(current)


def test_grandfathered_breach_passes() -> None:
    base = StructureBaseline(breaches={"complexity/a:f:cyclomatic-complexity": 14})
    current = [_b("complexity/a:f:cyclomatic-complexity", 14)]
    verdict = ratchet(current, base)
    assert verdict.clean
    assert verdict.grandfathered == 1


def test_new_breach_fails_despite_baseline() -> None:
    """The point of the ratchet: only new breaches fail."""
    base = StructureBaseline(breaches={"complexity/a:f:cyclomatic-complexity": 14})
    current = [
        _b("complexity/a:f:cyclomatic-complexity", 14),  # grandfathered
        _b("complexity/b:g:nesting-depth", 6),  # new
    ]
    verdict = ratchet(current, base)
    assert [b.key for b in verdict.survived] == ["complexity/b:g:nesting-depth"]
    assert verdict.grandfathered == 1


def test_worsened_breach_fails() -> None:
    """A ratchet only tightens: a grandfathered breach that got worse fails."""
    base = StructureBaseline(breaches={"complexity/a:f:cyclomatic-complexity": 14})
    current = [_b("complexity/a:f:cyclomatic-complexity", 17)]
    assert [b.value for b in ratchet(current, base).survived] == [17]


def test_improved_but_still_breaching_passes() -> None:
    """Improvement is never punished, even if still over the limit."""
    base = StructureBaseline(breaches={"complexity/a:f:cyclomatic-complexity": 17})
    current = [_b("complexity/a:f:cyclomatic-complexity", 12)]
    assert ratchet(current, base).clean


def test_resolved_breaches_are_reported() -> None:
    base = StructureBaseline(breaches={"complexity/a:f:cyclomatic-complexity": 14})
    assert ratchet([], base).resolved == ("complexity/a:f:cyclomatic-complexity",)


def test_rebaseline_refuses_on_dev_box() -> None:
    with pytest.raises(BaselineEnvironmentError, match="dev box|pinned"):
        rebaseline([_b("complexity/a:f:x", 14)], reason="x", environment="dev", pinned=False)


def test_rebaseline_requires_a_reason() -> None:
    with pytest.raises(BaselineEnvironmentError, match="reason"):
        rebaseline([_b("complexity/a:f:x", 14)], reason=None, environment="ci", pinned=True)


# ---------------------------------------------------------------------------
# gate level — the adoption path
# ---------------------------------------------------------------------------


def _tangled(project: Project, module: str, name: str) -> None:
    body = "\n".join(f'    if v == {n}:\n        return "{n}"' for n in range(14))
    project.write(
        f"src/{module.replace('.', '/')}.py",
        f'"""M."""\n\n\ndef {name}(v: int) -> str:\n    """C."""\n{body}\n    return "x"\n',
    )


def _gate(project: Project, **ctx_kwargs) -> object:  # noqa: ANN003
    cfg = Config.load(project.root).with_overrides(pinned_environment=True)
    ctx = Context(config=cfg, tier=Tier.DEFAULT, **ctx_kwargs)
    return run_spec(project.spec(_COMPLEXITY), ctx)


def test_adoption_path_grandfathers_then_fails_only_new(project: Project) -> None:
    """The full press-style adoption: strict, grandfather, then new-only."""
    _tangled(project, "app.legacy", "old_mess")

    # 1. Strict with no baseline — the debt fails.
    assert _gate(project).verdict is Verdict.FAIL

    # 2. Grandfather it, in CI, with a reason.
    updated = _gate(project, update_baselines=True, update_reason="grandfather existing debt")
    assert updated.verdict is Verdict.PASS
    assert (project.root / ".celebrimbor/baselines/structure.yaml").exists()

    # 3. Now the debt is grandfathered — green.
    assert _gate(project).verdict is Verdict.PASS

    # 4. New debt still fails, and names only the new callable.
    _tangled(project, "app.fresh", "new_mess")
    result = _gate(project)
    assert result.verdict is Verdict.FAIL
    assert all("app.fresh" in f.message for f in result.findings), (
        "grandfathered debt must not reappear; only the new breach fails"
    )


def test_update_on_dev_box_refuses(project: Project) -> None:
    """A dev box cannot bake in a baseline that differs from CI's."""
    _tangled(project, "app.legacy", "old_mess")
    cfg = Config.load(project.root).with_overrides(pinned_environment=False)
    ctx = Context(config=cfg, tier=Tier.DEFAULT, update_baselines=True, update_reason="x")
    result = run_spec(project.spec(_COMPLEXITY), ctx)
    assert result.verdict is Verdict.REFUSED
    assert "dev box" in (result.reason or "") or "pinned" in (result.reason or "")
