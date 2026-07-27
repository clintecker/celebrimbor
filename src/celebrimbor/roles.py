"""The role taxonomy and its proof obligations.

Eight roles. Each names *the kind of proof a callable of that role owes* — not
what it does, but how it earns trust. This is the general theory the obligation
engine runs on, and every Tier 1 gate keys on it.

There is no ninth member. "Unclassified" is deliberately *not* a role, because
a role is a claim about what proof is owed and "I don't know" is not such a
claim — it is the absence of one. Making it a ``Role`` would mean a human
could eventually ratify a row that says "unknown," and every gate keying on
role would then read a real, ratified, meaningless value.

Inference expresses abstention as ``None``, which lives only in the inference
domain and has nowhere to be written: an unclassifiable module gets no row in
the surface map, and the completeness audit reddens the gap. The illegal state
is unrepresentable rather than checked for.

Two properties are encoded here and relied on elsewhere:

**Obligation rank.** A total order on how much isolating proof a role demands.
It exists for one reason: the safe-direction rule. When inference is torn
between two roles it must propose the higher-ranked one, because over-demanding
proof costs an author some work while under-demanding it silently voids a gate.

**The escape roles.** ``PURE`` and ``PRESENTER`` are marked
``inference_forbidden``. Neither may ever be *proposed* by inference, only
ratified by a human. ``PURE`` because it is the cheapest obligation in the
taxonomy and a wrong guess there excuses a callable from everything; and
``PRESENTER`` because an end-to-end run is a blanket that touches many
callables and isolates none — assigning it by guess buries a unit inside a
proof that would stay green without it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Role(enum.Enum):
    """What kind of proof a callable owes."""

    PURE = "pure"
    PARSER = "parser"
    NORMALIZER = "normalizer"
    VERIFIER = "verifier"
    PRODUCER = "producer"
    ORCHESTRATOR = "orchestrator"
    ADAPTER = "adapter"
    PRESENTER = "presenter"

    @classmethod
    def parse(cls, value: str | Role) -> Role:
        if isinstance(value, Role):
            return value
        text = str(value).strip().lower()
        if text in {"unclassified", "unknown", "todo", "?"}:
            raise ValueError(
                f"{value!r} is not a role. A role is a claim about what proof a "
                "callable owes, and there is no way to ratify not knowing. Either "
                "name a role, or exempt the callable by name with a reason and a "
                "review date under `exemptions:`."
            )
        try:
            return cls(text)
        except ValueError:
            valid = ", ".join(r.value for r in cls)
            raise ValueError(f"unknown role {value!r}; expected one of {valid}") from None

    @property
    def obligation(self) -> Obligation:
        return OBLIGATIONS[self]

    @property
    def rank(self) -> int:
        return OBLIGATIONS[self].rank

    @property
    def inference_forbidden(self) -> bool:
        return OBLIGATIONS[self].inference_forbidden

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Obligation:
    """What a role owes, and how strongly."""

    role: Role
    owes: str
    """One line, quoted verbatim in gate output. This is what the author reads
    when a gate tells them a callable is under-proved."""

    rank: int
    """Ordering for the safe-direction rule. Higher = more isolating proof
    demanded. Only the ordering is meaningful; the absolute numbers are not."""

    inference_forbidden: bool = False
    """True for the escape roles, which inference may never propose."""

    policy: bool = False
    """Policy roles decide or attest something. The change-impact gate reddens
    when a policy-role module changes with no invariant naming it — because
    these are the roles where a silent behaviour change is a silent change to
    what the system promises."""


# The rank ordering is a judgment call, so here is the reasoning, since a later
# reader will need to argue with it:
#
#   pure / presenter (1)  — the escape roles. `pure` owes the least; `presenter`
#                           owes a lot of *runtime* but almost no isolation, so
#                           as a wrong guess it is equally excusing.
#   normalizer (3)        — a property test, but over a narrow algebraic claim.
#   parser (4)            — must be shown to *refuse*, which is a real negative.
#   orchestrator (4)      — must be shown to wire its edges correctly.
#   adapter (5)           — owes two proofs, against a fake and against a real
#                           backend, so it costs more than either above.
#   verifier (6)          — owes a negative fixture that turns it red: the gate
#                           on the gate. Guessing something weaker here means a
#                           blind verifier ships.
#   producer (7)          — the heaviest: proof *through* a verifier, plus the
#                           no-blind-verifier ledger obligation. Guessing
#                           weaker here is how an unchecked artifact ships.
OBLIGATIONS: dict[Role, Obligation] = {
    Role.PURE: Obligation(
        Role.PURE,
        "a property or unit test over its contract",
        rank=1,
        inference_forbidden=True,
    ),
    Role.PRESENTER: Obligation(
        Role.PRESENTER,
        "an integration or end-to-end run",
        rank=1,
        inference_forbidden=True,
    ),
    Role.NORMALIZER: Obligation(
        Role.NORMALIZER,
        "a property test covering idempotence and folding",
        rank=3,
        policy=True,
    ),
    Role.PARSER: Obligation(
        Role.PARSER,
        "a unit test with malformed input that must be refused",
        rank=4,
        policy=True,
    ),
    Role.ORCHESTRATOR: Obligation(
        Role.ORCHESTRATOR,
        "an interaction test over its dependency edges",
        rank=4,
    ),
    Role.ADAPTER: Obligation(
        Role.ADAPTER,
        "a contract test against fake and real backends",
        rank=5,
        policy=True,
    ),
    Role.VERIFIER: Obligation(
        Role.VERIFIER,
        "a negative fixture that must turn it red",
        rank=6,
        policy=True,
    ),
    Role.PRODUCER: Obligation(
        Role.PRODUCER,
        "proof through the verifier that inspects its artifact",
        rank=7,
        policy=True,
    ),
}

REAL_ROLES: tuple[Role, ...] = tuple(Role)

INFERABLE_ROLES: tuple[Role, ...] = tuple(
    r for r in REAL_ROLES if not OBLIGATIONS[r].inference_forbidden
)
"""The roles inference is permitted to propose. Note the absence of `pure` and
`presenter`: this tuple is the safe-direction scar, made into data."""

POLICY_ROLES: frozenset[Role] = frozenset(r for r in REAL_ROLES if OBLIGATIONS[r].policy)
"""Roles the change-impact gate treats as policy-bearing."""


def safer_of(left: Role | None, right: Role | None) -> Role | None:
    """The role demanding more isolating proof, or ``None`` to abstain.

    ``None`` is an abstention, not a bottom element: folding it with a role
    yields that role, because "no opinion" should not veto an opinion.

    The tie-break is deliberate rather than arbitrary. Equal-rank roles are
    genuinely *different* obligations, not degrees of one — a parser owes a
    refusal test and an orchestrator owes an interaction test, and satisfying
    one does nothing for the other. So "either" would be a guess, and this
    abstains instead, which surfaces the ambiguity to a human. Same fail-closed
    move as everywhere else in the harness.
    """
    if left is None:
        return right
    if right is None:
        return left
    if left is right:
        return left
    if left.rank == right.rank:
        return None
    return left if left.rank > right.rank else right
