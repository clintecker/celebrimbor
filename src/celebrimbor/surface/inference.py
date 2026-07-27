"""Role inference: a naming heuristic that shrinks the human's job.

Inference exists to make ratification a one-line confirm instead of an
authoring task. It does not exist to produce green, and the structure of this
module is built around keeping those two apart.

Three rules, and only the first is negotiable:

1.  **The name rules** (:data:`NAME_RULES`) are a heuristic and will need
    tuning against real apps' messy naming. Tune freely.

2.  **Safe direction is not negotiable.** Every proposal goes through
    :func:`_admissible`, which drops any proposal of an escape role and
    abstains on ambiguity. There is no code path from a name rule to a stored
    role that skips it. This matters more than the rules themselves: an
    over-demanding guess costs an author some test-writing, while an
    under-demanding guess silently voids the gates that key on role, and those
    are the gates the whole framework rests on.

3.  **Inferred is not ratified.** Everything produced here is written with
    ``status: inferred``, which the surface audit treats as red. Inference
    cannot manufacture a green gate because it cannot write the word
    ``ratified``.

A note on the side-effect analysis. The build contract's convention list
includes "side-effect-free signature -> pure", but the scars forbid inference
from ever proposing ``pure``. The scars win, so effect analysis here is used
only as *negative* evidence: it can withdraw a proposal (a ``build_*`` that
does nothing observable is probably not really a producer) but it can never
make one. That asymmetry is also just sound — a hit in the AST proves effects,
but a miss proves nothing, since effects hide behind any indirection the
syntax tree cannot follow.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..roles import Role, safer_of
from .inventory import CallableInfo, ModuleInfo
from .map import INFERRED, SurfaceRow


@dataclass(frozen=True, slots=True)
class NameRule:
    """One naming pattern and the role it suggests."""

    pattern: re.Pattern[str]
    role: Role
    why: str

    def matches(self, name: str) -> bool:
        return self.pattern.search(name) is not None


def _rule(regex: str, role: Role, why: str) -> NameRule:
    return NameRule(re.compile(regex, re.IGNORECASE), role, why)


# Ordered most-specific first; every matching rule contributes a proposal and
# the safe-direction fold picks among them, so ordering is for readability
# rather than precedence.
NAME_RULES: tuple[NameRule, ...] = (
    _rule(r"^(verify|validate|assert|ensure|check)_", Role.VERIFIER, "verify_* prefix"),
    _rule(r"(_verifier|_validator|_checker)$", Role.VERIFIER, "*_verifier suffix"),
    _rule(r"^(parse|load|read|decode|deserialize|from)_", Role.PARSER, "parse_* prefix"),
    _rule(r"(_parser|_loader|_reader|_decoder)$", Role.PARSER, "*_parser suffix"),
    _rule(r"^(gen|generate|build|make|render|emit|write|export)_", Role.PRODUCER, "build_* prefix"),
    _rule(r"(_builder|_generator|_writer|_renderer|_exporter)$", Role.PRODUCER, "*_builder suffix"),
    _rule(
        r"^(normali[sz]e|canonicali[sz]e|fold|clean|saniti[sz]e)_", Role.NORMALIZER, "normalize_*"
    ),
    _rule(r"(_normali[sz]er|_canonicali[sz]er)$", Role.NORMALIZER, "*_normalizer suffix"),
    _rule(
        r"^(fetch|send|post|upload|download|sync|connect|query)_", Role.ADAPTER, "I/O verb prefix"
    ),
    _rule(
        r"(_client|_adapter|_backend|_gateway|_repository|_store)$", Role.ADAPTER, "*_client suffix"
    ),
    _rule(
        r"^(run|orchestrate|coordinate|execute|dispatch|process)_",
        Role.ORCHESTRATOR,
        "run_* prefix",
    ),
    _rule(r"(_pipeline|_orchestrator|_workflow|_runner)$", Role.ORCHESTRATOR, "*_pipeline suffix"),
)


@dataclass(frozen=True, slots=True)
class Proposal:
    """What inference concluded about one callable, and why.

    ``role`` is ``None`` when inference abstained. That value exists only in
    this module's domain — it can never reach the surface map, because a
    module with nothing to propose simply gets no row.
    """

    callable_key: str
    role: Role | None
    reasons: tuple[str, ...] = ()
    withdrawn: str | None = None

    @property
    def abstained(self) -> bool:
        return self.role is None


def _admissible(role: Role | None) -> Role | None:
    """The safe-direction filter. Every proposal passes through here.

    An escape role becomes an abstention rather than passing through, which
    routes it to a human — the right outcome when the evidence points
    somewhere inference is not allowed to go.
    """
    if role is None or role.inference_forbidden:
        return None
    return role


def propose_for_callable(info: CallableInfo) -> Proposal:
    """Infer a role for one callable from its name, then apply the scars."""
    matched = [r for r in NAME_RULES if r.matches(info.name)]
    if not matched:
        return Proposal(info.key, None, ("no naming rule matched",))

    folded: Role | None = None
    for rule in matched:
        folded = safer_of(folded, _admissible(rule.role))

    reasons = tuple(r.why for r in matched)

    # Negative evidence: a name that promises an artifact, from a body with no
    # observable effect and no return value, is a naming coincidence rather
    # than a producer. Withdraw to abstention rather than proposing something
    # weaker, because "weaker" here would mean guessing.
    if folded is Role.PRODUCER and not info.observably_effectful and not info.returns_value:
        return Proposal(
            info.key,
            None,
            reasons,
            withdrawn="name suggests a producer but the body has no observable effect",
        )

    return Proposal(info.key, folded, reasons)


def propose_for_module(module: ModuleInfo) -> tuple[Role | None, tuple[Proposal, ...]]:
    """Infer a module's default role from its callables' proposals."""
    proposals = tuple(propose_for_callable(c) for c in module.callables)
    return choose_module_default([p.role for p in proposals]), proposals


def choose_module_default(proposals: Sequence[Role | None]) -> Role | None:
    """Collapse per-callable proposals into one module-default role: safest wins.

    Abstentions are dropped rather than counted. They are the absence of an
    opinion, not a vote for anything, and letting them dilute the fold would
    mean a module's default got weaker the less inference understood it —
    exactly backwards.

    The remaining roles fold through :func:`roles.safer_of`, so one producer
    among nine parsers makes the module a producer. That over-demands on the
    nine, and the mitigation is not softening this function: it is that
    over-demanding is *visible* (an author sees a test they must write) while
    under-demanding is *silent* (a gate quietly stops applying). Correcting an
    over-demand costs one line under ``overrides:``.

    This policy only holds up because the naming gate (see
    :mod:`celebrimbor.surface.naming`) drives abstentions toward zero. Folding
    ``[VERIFIER, None, None, None]`` to ``verifier`` would be over-demanding on
    three callables that never voted; folding ``[VERIFIER, PARSER, PARSER]`` to
    ``verifier`` is a real answer from a full poll.
    """
    folded: Role | None = None
    for role in proposals:
        if role is None:
            continue
        folded = safer_of(folded, _admissible(role))
    return folded


def infer_rows(modules: Iterable[ModuleInfo]) -> dict[str, SurfaceRow]:
    """Build pre-filled, un-ratified surface rows for the modules we can classify.

    A module inference cannot classify gets **no row**. That is not a silent
    drop: the surface audit compares the map against the AST inventory, so a
    module with public callables and no row is reported as a gap, with the
    exact line to add. Writing a placeholder row instead would put a
    ratifiable "I don't know" into the file, which is the state this design
    went out of its way to make unrepresentable.

    Modules that failed to parse also get no row here, and are reported
    separately as a refusal — they are the modules most likely to be hiding
    something, so they must never read as merely missing.
    """
    rows: dict[str, SurfaceRow] = {}
    for module in modules:
        if not module.dotted or not module.parsed or not module.callables:
            continue
        role, _ = propose_for_module(module)
        if role is None:
            continue
        rows[module.dotted] = SurfaceRow(module=module.dotted, role=role, status=INFERRED)
    return rows
