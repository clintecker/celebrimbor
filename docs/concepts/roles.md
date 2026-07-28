# Roles & obligations

The role is celebrimbor's spine. Every public callable has one, and a role names
the *kind of proof a callable of that role owes* — not what it does, but how it
earns trust.

## The taxonomy

| Role | Owes | Capability budget |
|---|---|---|
| `pure` | a property or unit test over its contract | nothing |
| `parser` | a unit test with malformed input that must be refused | nothing |
| `normalizer` | a property test (idempotence and folding) | nothing |
| `verifier` | a negative fixture that must turn it red | filesystem |
| `producer` | proof through the verifier that inspects its artifact | filesystem |
| `orchestrator` | an interaction test over its dependency edges | nothing |
| `adapter` | a contract test against fake and real backends | everything |
| `presenter` | an integration or end-to-end run | filesystem, process, environment |

The third column is the **capability budget** — which external dependencies a
callable of that role may reach for instead of being handed. It is enforced by
the [capabilities gate](../gate/capabilities.md) and is the reason `adapter`
carries an open budget while `pure` carries none.

Roles are assigned **by module default with per-callable overrides** — never one
row per function. A five-hundred-callable app has a map of a few dozen lines,
because a map nobody can read is a map nobody ratifies. A callable that genuinely
owes no direct proof is *exempted* by name, with a reason and a review date —
never silently. Here is a real fragment of `.celebrimbor/surfaces.yaml`:

```yaml
version: 1
modules:
  myapp.parsing:            # every callable here is a parser…
    role: parser
    status: ratified
    pin: "a1b2c3d4e5f6"     # the shape this role was ratified against
    overrides:
      dump_debug: pure      # …except this one, a plain serializer
  myapp.reporting:
    role: producer
    status: inferred        # RED until a human ratifies it
exemptions:
  myapp.parsing:_scratch:   # owes no direct proof, on the record
    reason: internal cache key; covered by the round-trip test
    review_by: 2026-10-01
```

A whole 57-module map authored this way — celebrimbor's own — is
[on GitHub](https://github.com/clintecker/celebrimbor/blob/main/.celebrimbor/surfaces.yaml).

## Inference, and its safe direction

You do not author the map from scratch. `celebrimbor init --surfaces` runs a
naming heuristic (`verify_*` → verifier, `parse_*` → parser, `build_*` →
producer, and so on) and pre-fills the rows it is confident about.

Two rules make inference trustworthy:

- **It abstains rather than guesses.** A callable whose name carries no signal
  gets *no row*. There is no "unclassified" value to ratify.
- **It only ever proposes higher-obligation roles.** Inference will never
  propose `pure` or `presenter` — the two escape roles — because a wrong guess
  *there* silently voids the very gates that key on role. Over-demanding proof
  costs an author some test-writing; under-demanding it ships an unchecked unit.
  Inference errs toward more proof, always.

Every inferred row is written `status: inferred`, which is **red until a human
ratifies it**. Inference shrinks your job to a one-line confirm; it never
manufactures green.

## A role is a claim, not a label

This is the part that makes the map trustworthy under real, messy code. Declaring
a role does not make it so — the code has to be consistent with it. The
[evidence gate](../gate/surface.md#evidence) checks necessary conditions the
role implies, from the AST:

- a `verifier` whose every return path is a truthy literal, with no raise, *can
  never turn red* — refused;
- a `parser` with no reachable failing path cannot refuse malformed input —
  refused;
- an `adapter` that touches no capability and calls nothing it was handed is not
  adapting anything — refused (this closes the "declare `adapter` to get the
  unrestricted capability budget" escape);
- a `pure` callable that mutates a parameter, or reaches for the clock, is not
  pure — refused.

These are *necessary contradiction detectors*, not proofs of correctness. They
catch a role that is provably wrong; the positive proof still lives in your tests.

!!! note "Refusal is mechanism-agnostic"
    A `parser` refuses malformed input by *raising* or by *returning* a value
    that encodes refusal (a `Result`, an error-carrying dataclass, `None`) —
    both are the same claim in different channels, and the value channel is the
    more disciplined one. The evidence gate keys on "has a reachable failing
    path", the same predicate it uses for verifiers, so idiomatic total parsers
    are not false-flagged.

## Ratification is pinned to the code

When you ratify a row, celebrimbor stamps a **pin** — a hash of the callable's
role-relevant *shape*: which capabilities it reaches for, whether it can fail,
whether it mutates its inputs, roughly how many collaborators it has, its
complexity band. It deliberately excludes names, literals, and formatting.

Ratification is a point-in-time human judgment applied to code that keeps moving.
The pin binds the judgment to the code it was made about. Rename a local or fix a
typo and nothing happens. Rewrite a three-line parser into something that opens a
socket, and the shape changes, the pin breaks, and the row **reverts to
un-ratified** — red until a human looks again. This is the answer to "someone
edited it into something more complex and never reclassified it."

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Absent
    Absent --> Inferred: init --surfaces<br/>(name has a signal)
    Absent --> Ratified: authored by hand
    Inferred --> Ratified: celebrimbor ratify<br/>(human confirms + pin stamped)
    Ratified --> Unratified: code's shape drifts<br/>(pin no longer matches)
    Unratified --> Ratified: re-ratify<br/>(human looks again)
    note right of Absent
        RED — a callable
        with no row is a hole
    end note
    note right of Inferred
        RED — a guess is
        not a judgment
    end note
    note right of Ratified
        GREEN
    end note
    note right of Unratified
        RED — the sign-off
        is about older code
    end note
```

Only the ratified state is green, and the only way in is a human confirmation —
inference and drift both leave you red.

## The obligation rank

The roles are ordered by how much isolating proof they demand — highest to
lowest:

```
producer (7)  >  verifier (6)  >  adapter (5)  >  parser (4) ≈ orchestrator (4)
              >  normalizer (3)  >  pure (1) ≈ presenter (1)
```

`pure` and `presenter` — the two escape roles — sit at the bottom, and inference
is *forbidden* from ever proposing them (a wrong guess there silently voids the
gates). The ordering exists for exactly one reason: the safe-direction rule
above. When inference is torn between two roles it proposes the higher-ranked
one; when two tie, it abstains.

## Policy roles and the impact gate

Six of the eight roles are **policy-bearing** — they *decide* or *attest*
something, so a change to them changes what the system guarantees:

| Policy roles | Not policy |
|---|---|
| `parser` · `normalizer` · `verifier` · `producer` · `orchestrator` · `adapter` | `pure` · `presenter` |

This is what the [change-impact gate](../gate/ledgers.md#the-impact-gate) keys
on. When a commit modifies a module whose role is policy-bearing, the gate asks:
*is there a recorded invariant that governs this?* If not, the change is a silent
alteration of a guarantee, made in a place with no promise watching it — and the
gate reddens. A change to a `pure` helper carries no such obligation, because a
pure function decides nothing about the system's promises. Which roles count as
policy is [configurable](../reference/configuration.md) (`policy_roles`), to
match an existing harness's notion of one.
