# celebrimbor

**Invariant-driven design as a framework.**

A claim a system cannot contradict is a claim it will eventually get wrong.
AI-generated code optimizes for plausibility, which means it lives in exactly
that vacuum. Celebrimbor's job is to make every unit of an application **carry
its own falsifier**, and to make the gate **fail closed** — refuse when it
cannot prove, never estimate.

```bash
pip install celebrimbor
celebrimbor init
celebrimbor gate --fast
```

## Two tiers

**Tier 0** — the commodity ladder (lint, types, format, complexity budgets,
known-bad) wired with opinionated defaults. Green on a fresh repo in under ten
minutes, no theory of testing required.

**Tier 1** — the obligation engine (surface-role completeness, the capability
budget, the no-blind-verifier ledger, the invariant ledger, the impact gate,
mutation). Opt-in and authored, so it never reddens day one.

## The idea

Every callable has a **role**, and a role names the kind of proof it owes.

| Role | Owes |
|---|---|
| `pure` | a property or unit test over its contract |
| `parser` | a unit test with malformed input that must be refused |
| `normalizer` | a property test (idempotence and folding) |
| `verifier` | a negative fixture that must turn it red |
| `producer` | proof through the verifier that inspects its artifact |
| `orchestrator` | an interaction test over its dependency edges |
| `adapter` | a contract test against fake and real backends |
| `presenter` | an integration or end-to-end run |

Roles are **inferred, then ratified** — never silently accepted. Inference
pre-fills the rows it is confident about and abstains on the rest; abstention
is red until a human confirms. Inference may never propose the low-obligation
escape roles, because a wrong guess there silently voids the gates that key on
role.

The role also sets a **capability budget**: which external dependencies a
callable may reach for instead of being handed. A `pure` function calling
`datetime.now()` is a contradiction of a declared obligation. An `adapter`
doing so is the whole reason adapters exist.

## The gate, tier by tier

Nineteen checks, each one carrying its own falsifier — a negative fixture on the
record that has been observed to turn it red. A gate that has never been seen to
fail is a blind gate, so celebrimbor refuses to register a check without one.

**Tier 0 — `gate --fast`** (~10s, no ledger, passes on a fresh repo)

| Check | Enforces |
|---|---|
| `lint` / `format` / `types` | ruff + mypy, strict, shelled out (your pinned versions) |
| `structure.complexity` | cyclomatic / nesting / length budgets, measured from the AST |
| `structure.cohesion` | one domain per module — connected components, not a class count |
| `known_bad` | every `tests/known-bad/` file is rejected by the *named* checker with the *expected* diagnostic |
| `markers` | a test with no assertion is red; `xfail`/`skip` must cite a reason |
| `falsifiers` / `registry` / `completeness` | the gates on the gates |

**Tier 1 — opt-in** (authored, never reddens day one)

| Check | Enforces |
|---|---|
| `surface.completeness` | every public callable is accounted for in a **ratified** surface map |
| `surface.naming` | a callable named for a stronger role than it's assigned (drift) |
| `surface.evidence` | a declared role the code *contradicts* (a `verifier` that can never turn red) |
| `surface.pin` | a ratified role still describes the code it ratified (shape drift) |
| `structure.capabilities` | dependencies injected, not reached for — budgeted by role |
| `producers` | no blind verifiers: every producer is proved through a verifier proven to bite |
| `invariants` | every named enforcer resolves; every critical promise keeps a negative proof |
| `impact` | a changed policy-role module is named by some invariant |

**PR tier — `gate`** adds the coverage ratchet. **Merge tier — `gate --full`** adds the mutation ratchet (survivor *identity*, not count).

Every gate **fails closed**: when it cannot prove something it refuses (red), never estimates. A missing tool in a trusted environment is red; a skip always carries its reason.

## Commands

```
celebrimbor init [--surfaces]     scaffold the ladder; --surfaces adds the role map
celebrimbor gate [--fast|--full]  run it
celebrimbor ratify <module>...    confirm surface rows and pin them to the code
celebrimbor explain               print the taxonomy, budget and registered checks
```

## Programmatic API

```python
import celebrimbor

report = celebrimbor.gate(tier="fast")   # run the gate; inspect report.ok
report.exit_code                         # 0 only if every check that ran proved its claim

@celebrimbor.check(                       # register an app-specific check
    id="myapp.manifest",
    title="every artifact is listed in the manifest",
    falsified_by="tests/known-bad/manifest_missing_entry.json",
)
def check_manifest(ctx): ...
```

## License

MIT
