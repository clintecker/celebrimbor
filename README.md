<div align="center">

# celebrimbor

**Invariant-driven design as a framework.**

An omakase quality harness that makes every unit of your application carry its
own falsifier — and makes the gate fail closed: refuse when it cannot prove,
never estimate.

[![gate](https://github.com/clintecker/celebrimbor/actions/workflows/gate.yml/badge.svg)](https://github.com/clintecker/celebrimbor/actions/workflows/gate.yml)
[![docs](https://github.com/clintecker/celebrimbor/actions/workflows/docs.yml/badge.svg)](https://clintecker.github.io/celebrimbor/)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[Documentation](https://clintecker.github.io/celebrimbor/) ·
[Getting started](https://clintecker.github.io/celebrimbor/getting-started/) ·
[Concepts](https://clintecker.github.io/celebrimbor/concepts/thesis/)

</div>

---

## Why — especially for AI-generated code

A claim a system cannot contradict is a claim it will eventually get wrong. Most
quality tooling checks that code *runs*; it rarely checks that code is what it
*says* it is. That gap — the space between plausible and correct — is where bugs
live, and it is exactly where AI-generated code lives, because a language model
optimizes for plausibility. That is what a hallucination *is*: output that looks
right and carries no proof.

An AI can hand you a `verify_*` function that always returns `True`, a parser
that never rejects bad input, a "pure" helper that secretly reaches for the
clock, or a test that asserts nothing — and every one of those passes your
linter, your type checker, and the tests the AI wrote alongside them. Nothing in
the commodity ladder forces the code to be *falsifiable*.

Celebrimbor closes that vacuum with one idea, applied relentlessly: **every unit
carries its own falsifier, and the gate fails closed.** A gate that has never
been observed to fail is a blind gate, so it refuses to register a check without
a negative fixture proving it can turn red. A role you declare is a claim the
code can contradict, not an attestation taken on faith. When the harness cannot
prove something, it refuses — red — rather than guessing green.

The effect on AI-written code is concrete: the gate is an adversary a model
cannot talk its way past. It cannot ship a blind verifier — the evidence gate
detects "can never turn red" from the syntax tree. It cannot ship a pure
function that touches the world — the capability gate sees the un-injected
reach. It cannot ship a check with no falsifier — the decorator won't accept
one. It cannot quietly change what a module *does* — ratification is pinned to
the code's shape, so a rewrite re-opens the question. You keep AI velocity, but
with a falsifier always in reach — which is the difference between code that
looks trustworthy and code you can actually trust.

## Beyond linting, types, TDD, and pre-commits

Those tools are necessary and celebrimbor runs them for you on the commodity ladder. But note
what each can and cannot see:

- **Linters** check style. **Type checkers** check shapes. **TDD** checks the
  cases you thought to write. **Pre-commit** runs those on every commit.
- None of them ask: *is this the role it claims to be?* Does this verifier
  actually verify, or just return `True`? Is this dependency injected so a test
  *could* contradict it? Does every artifact-producer have a verifier that is
  proven to reject a bad artifact? Did a "pure" function quietly gain a side
  effect? Has this module's behavior drifted away from the judgment a human
  once signed off on?

Celebrimbor is the layer *above* the commodity ladder that makes those claims
falsifiable. It does not replace your tests, types, or linters — it makes them
mean something, by refusing to let a unit assert a property it cannot be forced
to prove.

## Why celebrimbor, and not a pile of tools

The individual ideas here are not new. Mutation testing, property-based testing,
dependency injection, the object-capability model, coverage ratchets, invariant
ledgers, provenance-checked fixtures, design-by-contract — each has a tool, a
paper, or a community. What is new is the **coupling**. In celebrimbor they are
not eight tools bolted together; they are one obligation engine keyed on a
single spine: the **role**.

One ratified-then-pinned role map decides everything downstream. The role says
what proof a callable owes, which capabilities it may reach for, whether a change
to it needs a governing invariant, and — for producers — that it names a verifier
proven to bite. Because every gate reads the same source of truth, they reinforce
each other instead of contradicting: the capability gate can only be trusted
because the evidence gate proves the role is honest, and the impact gate is only
meaningful because the surface map is provably complete. A pile of separate tools
cannot give you that; each sees only its own slice.

And the reason a discipline this thorough is *adoptable* is **convention over
configuration**. Roles are inferred, not authored. Known-bad is a directory, not
a config block. Ratchets auto-baseline in CI. You do not wire twenty tools —
you run `celebrimbor init` and ratify a pre-filled map one line at a time. The
config file exists for exceptions only. That is also what makes it resistant to
AI hallucination: the conventions are enforced *structurally*, in the gate, not
left to a prompt or a reviewer's diligence. The burden of proof sits on the code,
by construction — and that is a thing no linter, no test suite, and no amount of
careful reviewing can give you on its own.

## Install

```bash
pip install celebrimbor              # core
pip install "celebrimbor[commodity]"     # + ruff, mypy, pytest, coverage
```

## Quickstart

```bash
celebrimbor init        # scaffold opinionated ruff/mypy/pytest config + a pre-commit hook
celebrimbor gate --fast # lint, types, format, complexity, cohesion, known-bad, markers
```

The commodity ladder is designed to go green on a fresh repo in under ten minutes, no theory
of testing required. It is the adoption wedge.

## The idea

Every callable has a **role**, and a role names the *kind of proof it owes*.

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
pre-fills the rows it is confident about and abstains on the rest; abstention is
red until a human confirms. And a role is not just a label: the **evidence
gate** checks the code is consistent with what the role claims — a `verifier`
whose every path returns truthy *can never turn red*, so it is refused. Ratifying
a role **pins** it to the code's shape, so a later rewrite that changes character
re-opens the question.

The role also sets a **capability budget** — which external dependencies a
callable may reach for instead of being handed. A `pure` function calling
`datetime.now()` is a contradiction of a declared obligation; an `adapter` doing
so is the whole reason adapters exist. An un-injected dependency is a claim the
test cannot contradict.

## The gate: two families, three stages

Twenty gates. Every one carries a falsifier. Two independent axes decide what
runs — don't conflate them:

**Family — *what kind* of check** (a fixed pair, not a scale):

- **`commodity` — the commodity ladder** (no ledger, passes on a fresh repo):
  lint, types, format, complexity/nesting/length budgets, cohesion (one domain
  per module), known-bad provenance, marker grammar.
- **`obligation` — the obligation engine** (opt-in, authored, never reddens day
  one): surface-role completeness, naming drift, role evidence, ratification
  pins, capability injection, no-blind-verifier producers, invariant ledger,
  change-impact, import-health.

**Stage — *how deep* a run goes** (an ordinal scale). Each nests the cheaper one:

- **`gate --fast`** (~10s, pre-commit): commodity plus the cheap obligation gates.
- **`gate`** (~2min, PR): adds the coverage ratchet, invariants, change-impact.
- **`gate --full`** (release): adds the mutation ratchet (survivor *identity*,
  not count).

A check has one of each: the `obligation` `invariants` gate runs at the PR
stage. Every gate **fails closed**: when it cannot prove something it refuses
(red), never estimates. A missing tool in a trusted environment is red; a skip
always carries its reason.

## Custom checks

The one documented seam for app-specific checks:

```python
import celebrimbor

@celebrimbor.check(
    id="myapp.manifest",
    title="every artifact is listed in the manifest",
    falsified_by="tests/known-bad/manifest_missing_entry.json",
)
def check_manifest(ctx):
    ...
```

`falsified_by` is required and has no default — the framework will not let you
add a gate without saying how you know the gate works. Point the CLI at your
module and your checks run through `celebrimbor gate` itself, in the same ordered
registry as the builtins, under the same no-check-escapes guarantee:

```toml
[tool.celebrimbor]
check_modules = ["myapp.quality_checks"]        # your @check gates, run by the CLI

[tool.celebrimbor.known_bad_checkers.style_audit]
callable = "myapp.editorial:diagnostics_for"    # your own known-bad linter
match = "substring"
```

That is the point of the seams added across 0.7–0.10: your domain checks, your
fixture-provenance linter, and your invariants (which may keep several proofs and
declare `limitations:` a suppressed test must cite) all run through **one** gate,
so an existing quality harness folds into celebrimbor instead of living beside
it. Anything that will not import or run is a hard, fail-closed error — never a
silently smaller gate.

```python
report = celebrimbor.gate(stage="fast")   # drive it programmatically
report.exit_code                          # 0 only if every check proved its claim
```

## Documentation

Full documentation — concepts, every gate, adoption guide, CLI and config
reference — lives at **[clintecker.github.io/celebrimbor](https://clintecker.github.io/celebrimbor/)**.

## Contributing

Celebrimbor holds itself to its own gate. See [CONTRIBUTING.md](CONTRIBUTING.md)
— including the one rule that has no exceptions: every check you add must name
the negative fixture that proves it can turn red.

## License

[MIT](LICENSE) © 2026 Clint Ecker
