"""Role evidence: making a declared role a claim the code can contradict.

Without this module the role map is an *attestation*. A human types
``role: pure``, marks it ratified, and every downstream gate keys off that
word. Two escapes follow immediately, and both are real:

* Declare ``adapter`` everywhere. Its capability budget is unrestricted, so the
  dependency-injection gate goes quiet — the role that exists to *concentrate*
  boundary code becomes the way to opt out of the boundary rule.
* Declare ``pure`` on something whose effects arrive through an injected
  parameter. ``def process(record, db): db.execute(...)`` reads as clean to the
  capability gate, because ``db`` is a seam. It is not pure.

So each role gets **necessary conditions** the syntax tree can check. Not
sufficient ones — nothing here proves a parser parses correctly. But a
declaration that the code visibly contradicts is a declaration the harness can
refuse, and that is the difference between a claim and an assertion.

The sharpest of them is ``verifier``: a callable whose every return path is
truthy *can never turn red*. That is the blind verifier this whole project is
organised around, and it turns out to be statically detectable. ``parser``
shares that exact contradiction — a reachable failing path is the thing both
roles owe, and refusing malformed input by *returning* a value that encodes
refusal is the same claim as refusing it by raising, so both are checked with
the same ``all_returns_truthy`` predicate. Checking ``parser`` for a literal
``raise`` instead would false-flag every total, fail-closed-by-value parser.

A word on what these conditions are *not*. They are **necessary contradiction
detectors**, not proofs. Reachability is undecidable from the AST: passing the
``verifier``/``parser`` check means only "not provably blind", never "proven to
refuse". The positive proof lives where it always has in this harness — in the
negative fixture the role owes, a malformed input observed to travel the
failing path. The static check is the cheap floor; the fixture is the gate.
(That the static layer alone cannot prove reachability is not a weakening: the
check was never sound for that, for either role, and a dead ``raise`` was always
as gameable as a dead error-return. Honesty about which layer proves what is the
point.)

Conditions are stated conservatively and fire only on clear contradiction,
because a noisy gate is a disabled gate. Where a condition genuinely does not
apply, the escape is the same as everywhere else in this harness: an exemption,
by name, with a reason and a review date.
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..roles import Role
from ._method_names import IO_METHODS, MUTATING_METHODS, VALUE_METHODS
from .capabilities import Capability, root_of, scan_callable

if TYPE_CHECKING:
    from ..surface.inventory import CallableInfo


@dataclass(frozen=True, slots=True)
class RoleFacts:
    """Structural facts about a callable, relevant to what role it can be."""

    raises: bool
    returns_value: bool
    all_returns_truthy: bool
    """Every ``return`` yields a literal that is truthy, and nothing raises.
    Such a callable has no failing path at all."""

    mutates_params: bool
    mutates_self: bool
    """Writes to ``self``/``cls`` attributes or items. A stateful in-memory
    test-double (a fake backend) mutates its own state and touches no ambient
    capability — it is neither ``pure`` nor a real-capability ``adapter``, but it
    *is* the injected backend, so this fact lets it satisfy the ``adapter`` role."""

    delegates_to_adapter: bool
    """Calls a name that resolves to an adapter-classified module. A seam-wrapper
    that delegates its one I/O op to a capability module (``adapters.post(...)``)
    is doing adapter work even though the syscall lives one module deeper."""

    performs_io_call: bool
    """Calls an I/O-verb method (``.run``, ``.get``, ``.execute``, ...) on any
    receiver. Catches backend interaction the capability patterns miss — a call
    into an unclassified seam, or an injected transport — and satisfies the
    ``adapter`` role without the escape it would open for other roles."""

    ambient: frozenset[Capability]
    injected_calls: int
    collaborators: frozenset[str]
    effectful: bool
    complexity_band: int
    """Complexity bucketed coarsely, so a pin survives small edits but not a
    change of character. See :func:`signature`."""


def _band(value: int) -> int:
    """Bucket a complexity score. Coarse on purpose.

    A pin that breaks whenever complexity moves by one would redden on every
    commit and be disabled within a week. These buckets change when a callable
    changes *character*, not when it changes size.
    """
    for index, ceiling in enumerate((3, 6, 10, 16, 25)):
        if value <= ceiling:
            return index
    return 5


def _param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    a = node.args
    names = {arg.arg for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs)}
    if a.vararg:
        names.add(a.vararg.arg)
    if a.kwarg:
        names.add(a.kwarg.arg)
    return frozenset(names | {"self", "cls"})


# Shared with the capability gate on purpose: if the two disagreed about what
# "the object this call is on" means, a call could read as injected to one gate
# and ambient to the other.
_root_name = root_of


def _truthy_literal(node: ast.expr | None) -> bool:
    """Is this return value a literal that is unconditionally truthy?

    Only literals count. ``return result`` tells us nothing, so it is not
    treated as truthy — the gate must not accuse a verifier that might well
    return False at runtime.
    """
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if isinstance(node, ast.List | ast.Set | ast.Tuple):
        # Unconditionally truthy iff at least one element is a *guaranteed* (non-
        # ``*splat``) member: that one element makes the container non-empty for
        # every input. ``[*a]`` (all splat) can be empty and is not truthy, but
        # ``[1, *a]`` always has its ``1``, so it is.
        return any(not isinstance(e, ast.Starred) for e in node.elts)
    if isinstance(node, ast.Dict):
        # A ``None`` key marks ``**a`` unpacking: ``{**a}`` can be empty. A single
        # literal key (``{"k": v, **a}``) guarantees one entry, so it is truthy.
        return any(k is not None for k in node.keys)
    return False


def _raises(node: ast.AST) -> bool:
    return any(isinstance(c, ast.Raise) for c in ast.walk(node))


def _return_values(node: ast.AST) -> list[ast.expr | None]:
    return [c.value for c in ast.walk(node) if isinstance(c, ast.Return)]


def _stores_to(c: ast.AST, roots: frozenset[str]) -> bool:
    """A `self.x = ...` / `self.x[i] = ...` / `self.x += ...` rooted at `roots`."""
    target = c.target if isinstance(c, ast.AugAssign) else c
    return (
        isinstance(target, ast.Attribute | ast.Subscript)
        and (isinstance(target.ctx, ast.Store) or isinstance(c, ast.AugAssign))
        and _root_name(target) in roots
    )


def _mutating_call(c: ast.AST, roots: frozenset[str]) -> bool:
    """A `self.x.append(...)`-style in-place mutation rooted at `roots`."""
    return (
        isinstance(c, ast.Call)
        and isinstance(c.func, ast.Attribute)
        and c.func.attr in MUTATING_METHODS
        and _root_name(c.func) in roots
    )


def _mutates(node: ast.AST, roots: frozenset[str]) -> bool:
    """Does the body mutate state through one of ``roots`` — by store or in place?"""
    return any(_stores_to(c, roots) or _mutating_call(c, roots) for c in ast.walk(node))


def _method_name(func: ast.expr) -> str | None:
    return func.attr if isinstance(func, ast.Attribute) else None


def _call_shape(node: ast.AST, params: frozenset[str]) -> tuple[int, frozenset[str]]:
    """``(calls that look like using an injected resource, distinct collaborators)``.

    "Looks like a resource" excludes :data:`_VALUE_METHODS` — see there for why
    counting every call on a parameter makes the adapter condition vacuous.
    """
    injected = 0
    collaborators: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        root = _root_name(child.func)
        if root is None:
            continue
        if root in params and _method_name(child.func) not in VALUE_METHODS:
            injected += 1
        collaborators.add(root)
    return injected, frozenset(collaborators)


def _delegates(node: ast.AST, adapter_symbols: frozenset[str]) -> bool:
    """Does the body call a name that resolves to an adapter-classified module?"""
    if not adapter_symbols:
        return False
    return any(
        isinstance(c, ast.Call) and _root_name(c.func) in adapter_symbols for c in ast.walk(node)
    )


def _is_io_method(name: str) -> bool:
    """`post`, or a compound like `post_json` / `run_capture` / `get_bytes`.

    Prefix matching on the leading verb catches the common `<verb>_<noun>`
    naming (``client.post_json(...)``) without matching an unrelated name that
    merely starts with the letters (``getter`` has no ``_``, so it never splits
    to ``get``)."""
    return name in IO_METHODS or (name.split("_", 1)[0] in IO_METHODS and "_" in name)


def performs_io(node: ast.AST) -> bool:
    """Does the body call an I/O-verb method (`.run`, `.post_json`, `.execute`)?"""
    return any(
        isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and _is_io_method(c.func.attr)
        for c in ast.walk(node)
    )


def gather(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    info: CallableInfo,
    complexity: int,
    adapter_symbols: frozenset[str] = frozenset(),
) -> RoleFacts:
    """Extract role-relevant structural facts from one callable.

    ``adapter_symbols`` are the names, bound in this callable's module, that refer
    to adapter-classified modules — supplied by the evidence gate, which has the
    surface map. Empty when the caller has no map (e.g. the pin, which only needs
    shape), and the delegation fact is then simply absent.

    Several separate passes over the same body rather than one branching walk. A
    function body is small enough that the extra traversals are free, and the
    single-walk version scored 15 on the complexity gate this module helps
    enforce — which was a fair verdict, not a technicality.
    """
    params = _param_names(node)
    returns = _return_values(node)
    raises = _raises(node)
    injected_calls, collaborators = _call_shape(node, params)

    return RoleFacts(
        raises=raises,
        returns_value=any(r is not None for r in returns),
        all_returns_truthy=(
            bool(returns) and not raises and all(_truthy_literal(r) for r in returns)
        ),
        mutates_params=_mutates(node, params),
        mutates_self=_mutates(node, frozenset({"self", "cls"})),
        delegates_to_adapter=_delegates(node, adapter_symbols),
        performs_io_call=performs_io(node),
        ambient=frozenset(use.capability for use in scan_callable(node, info)),
        injected_calls=injected_calls,
        collaborators=collaborators,
        effectful=info.observably_effectful,
        complexity_band=_band(complexity),
    )


@dataclass(frozen=True, slots=True)
class Contradiction:
    """A declared role the code visibly contradicts."""

    role: Role
    because: str
    remedy: str


@dataclass(frozen=True, slots=True)
class Condition:
    """One necessary condition for a role, and what it means to fail it.

    ``violated`` returns True when the facts *contradict* the role — the
    inverted polarity is deliberate, so the table below reads as a list of
    ways to be wrong rather than a list of things to be true.
    """

    role: Role
    violated: Callable[[RoleFacts], bool]
    because: Callable[[RoleFacts], str]
    remedy: str


def _fixed(text: str) -> Callable[[RoleFacts], str]:
    """Most reasons do not depend on the facts; this keeps the table uniform."""
    return lambda _facts: text


# Necessary conditions, as data. Written as a table rather than a branch chain
# for the usual reason — the chain scored 17 on the complexity gate this very
# module helps enforce — but also because a table is the honest shape: these
# are independent claims about independent roles, not a decision procedure.
# Adding a role's condition should never mean editing control flow.
_CONDITIONS: tuple[Condition, ...] = (
    Condition(
        Role.VERIFIER,
        lambda f: f.all_returns_truthy,
        _fixed(
            "every return path is a truthy literal and nothing raises, so this verifier "
            "has no failing path — it can never turn red"
        ),
        "a verifier that cannot fail inspects nothing; give it a path that rejects, "
        "and a negative fixture that exercises it",
    ),
    # A parser and a verifier owe the same underlying thing: a *reachable
    # failing path*. Refusal-by-raise and refusal-by-value (returning
    # ``ParsedOutput(unreadable=...)``, ``None``, a ``Result``) are one claim in
    # two channels — the effect channel and the value channel — and the value
    # channel is the more disciplined encoding, not a weaker one. So the
    # contradiction is the same as the verifier's: a callable whose every return
    # is a truthy literal with no raise has no failing path at all and can never
    # refuse anything. Checking ``not f.raises`` instead would false-flag every
    # total, fail-closed-by-value parser — which is most real parsers, and
    # celebrimbor's own.
    #
    # This is a *necessary* contradiction detector, not proof of refusal.
    # Reachability is undecidable from the AST, so a green here means only "not
    # provably blind", exactly as it does for the verifier. The real proof that
    # a parser refuses is the negative fixture the role owes — a malformed input
    # observed to travel the refusal path. The static check is the cheap floor;
    # the fixture is the gate.
    Condition(
        Role.PARSER,
        lambda f: f.all_returns_truthy,
        _fixed(
            "every return path is a truthy literal and nothing raises, so this parser "
            "has no failing path — it can never refuse malformed input"
        ),
        "a parser owes a unit test with malformed input that must be refused. Give it a "
        "path that rejects — raise, or return a value that encodes refusal — and the "
        "negative fixture that exercises it.",
    ),
    # An adapter is a boundary. It genuinely adapts when it reaches a capability,
    # calls something it was handed, delegates to an adapter-classified module (a
    # seam-wrapper whose one syscall lives one module deeper), or holds its own
    # mutable state (a stateful in-memory fake IS the injected backend). Only a
    # callable that does *none* of these — inert, pure computation dressed as an
    # adapter to obtain the unrestricted capability budget — is contradicted.
    Condition(
        Role.ADAPTER,
        lambda f: (
            not (
                f.ambient
                or f.injected_calls
                or f.delegates_to_adapter
                or f.performs_io_call
                or f.mutates_self
            )
        ),
        _fixed(
            "it touches no capability, calls nothing it was handed, delegates to no "
            "adapter module, and holds no state — so it is not adapting anything"
        ),
        "`adapter` carries an unrestricted capability budget, so declaring it without "
        "a boundary to adapt silently disables the injection gate. Classify it as what "
        "it actually is.",
    ),
    Condition(
        Role.PURE,
        lambda f: f.mutates_params,
        _fixed("it writes to one of its parameters, so calling it changes the caller's state"),
        "return a new value instead, or classify it as `normalizer`",
    ),
    Condition(
        Role.PURE,
        lambda f: bool(f.ambient),
        lambda f: f"it reaches for {', '.join(sorted(c.value for c in f.ambient))} directly",
        "inject the capability, or classify it honestly",
    ),
    Condition(
        Role.PRODUCER,
        lambda f: not (f.effectful or f.returns_value),
        _fixed(
            "it has no observable effect and returns nothing, so it produces no artifact "
            "for a verifier to inspect"
        ),
        "if it genuinely produces nothing, it is not a producer",
    ),
    Condition(
        Role.ORCHESTRATOR,
        lambda f: len(f.collaborators) < 2,
        lambda f: (
            f"it calls {len(f.collaborators)} distinct collaborator(s), so there are no "
            "dependency edges to write an interaction test over"
        ),
        "an orchestrator coordinates; with one collaborator there is nothing to coordinate",
    ),
)


def contradictions(role: Role, facts: RoleFacts) -> list[Contradiction]:
    """Necessary conditions for ``role`` that ``facts`` violates.

    Each condition answers "what would this role have to look like, at
    minimum?" A callable failing one is not merely unusual — it cannot be
    doing the job the role names.
    """
    return [
        Contradiction(role, condition.because(facts), condition.remedy)
        for condition in _CONDITIONS
        if condition.role is role and condition.violated(facts)
    ]


def signature(facts: RoleFacts) -> str:
    """A short hash of the role-relevant *shape* of a callable.

    Ratification pins this. When it changes, the row reverts to un-ratified and
    goes red until a human re-confirms — which is the answer to "someone edits
    it into something more complex and never reclassifies it."

    What is deliberately *not* in the hash matters as much as what is: no
    identifiers, no literals, no line numbers, no body text. Renaming a local,
    fixing a typo, reformatting, or adding a docstring must not re-redden a
    ratified row, or the pin becomes noise and gets turned off. What is in the
    hash is character: which capabilities it reaches for, whether it can fail,
    whether it returns anything, whether it mutates its inputs, roughly how
    many collaborators it has, and its complexity band.
    """
    parts = (
        "2",  # scheme version; bump to invalidate every pin deliberately
        "".join(sorted(c.value[0] for c in facts.ambient)) or "-",
        "R" if facts.raises else "-",
        "V" if facts.returns_value else "-",
        "T" if facts.all_returns_truthy else "-",
        "M" if facts.mutates_params else "-",
        "S" if facts.mutates_self else "-",
        "I" if facts.performs_io_call else "-",
        "E" if facts.effectful else "-",
        str(_band(len(facts.collaborators))),
        str(facts.complexity_band),
    )
    return hashlib.blake2s(":".join(parts).encode(), digest_size=5).hexdigest()


def module_signature(signatures: dict[str, str]) -> str:
    """Combine per-callable signatures into one pin for a module row.

    Order-independent by construction, so reordering functions in a file does
    not break the pin — moving code around is not a change of character.
    """
    joined = ";".join(f"{name}={sig}" for name, sig in sorted(signatures.items()))
    return hashlib.blake2s(joined.encode(), digest_size=6).hexdigest()
