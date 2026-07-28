# The thesis

Celebrimbor is **invariant-driven design as a framework**: it removes the
epistemic vacuum where plausible-but-wrong code lives.

The one-paragraph version: a claim a system cannot contradict is a claim it will
eventually get wrong. AI-generated code — which optimizes for plausibility —
lives in exactly that vacuum. Celebrimbor's job is to make every unit of an
application **carry its own falsifier** and to make the gate **fail closed**:
refuse when it cannot prove, never estimate.

Three principles fall out of that, and every design decision in the codebase
serves them.

## Self-falsifying claims

A unit that asserts a property must be forced to prove it. This is not a slogan
— it is a required argument. The `@check` decorator has no default for
`falsified_by`; you cannot register a gate without naming how it can fail:

```python
@celebrimbor.check(
    id="myapp.manifest",
    title="every artifact is listed",
    falsified_by="tests/known-bad/manifest_missing.json",  # ← not optional
)
def check_manifest(ctx): ...
```

The same shape recurs:

- A `producer` must name a `verifier`, and that verifier must name a negative
  fixture that turns it red. You cannot inherit a verifier that inspects nothing.
- A declared role is checked against the code (the [evidence gate](../gate/surface.md#evidence)),
  so a `verifier` that can never fail is refused.

The pattern is fractal: the same discipline the harness applies to your code, it
applies to its own gates, and to [the gates on those gates](../gate/meta.md).

## Fail closed

When the harness cannot establish something, it goes red — it never estimates,
defaults, or passes. A missing config file, an unparseable module, a tool that
is absent in a trusted environment, a git diff it cannot compute: all of these
**refuse**, distinct from both *pass* and *fail*. "We could not check" must never
silently become "there is nothing wrong."

This is enforced in the type system, once, so no engine can forget it: results
are constructed through a vocabulary where a skipped check must carry a reason, a
failure must carry a finding, and an empty gate is red because it proved nothing.
See [Fail closed](fail-closed.md).

## Invariants over checks

Prefer making an illegal state *unrepresentable* over checking for it after the
fact. The clearest example: there is no "unclassified" role. An earlier design
had one, and it was deleted — because a role that means "I don't know" could be
ratified, and every gate keying on role would then read a real, ratified,
meaningless value. `Role.parse` now *raises* on anything outside the eight; the
illegal value cannot be constructed, let alone ratified. Inference abstains by
producing *nothing*; an unclassifiable module simply gets no row, and the
completeness audit reddens the gap.

## The compass

When a design decision is unclear, three questions resolve it — and a "no" to any
is a "no" to the feature:

```mermaid
flowchart TD
    F["a proposed feature"] --> Q1{makes a claim<br/>more falsifiable?}
    Q1 -->|no| REJ([reject])
    Q1 -->|yes| Q2{fails closed<br/>when unsure?}
    Q2 -->|no| REJ
    Q2 -->|yes| Q3{moves a check<br/>toward an invariant?}
    Q3 -->|no| REJ
    Q3 -->|yes| KEEP([keep])
```

If a proposed feature would let a unit assert something it cannot be forced to
prove, it is the wrong feature — no matter how convenient.
