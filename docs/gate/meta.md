# The gates on the gates

Three of celebrimbor's twenty checks don't check *your* code at all. They check
the gate itself. They answer the oldest problem in quality tooling: **who checks
the checker?** If a gate can silently vanish, misfile its result, or ship with no
way to fail, then every green it has ever reported is suspect — the tool starts to
look trustworthy while hiding a flaw, which is the one thing celebrimbor is named
never to allow.

These three run in the everyday family, at the `fast` stage, on every project —
because the guarantee they provide is the one thing that must never be optional.

```mermaid
flowchart TD
    subgraph yours["gates over your code"]
        G1[lint · types · structure]
        G2[surface · capabilities]
        G3[producers · invariants · …]
    end
    F["celebrimbor.falsifiers<br/>every gate can be proven to fail"] --> yours
    R["celebrimbor.registry<br/>the gate set is internally consistent"] --> yours
    C["celebrimbor.completeness<br/>what should have run, ran"] --> yours
    yours --> V([a trustworthy green])
```

## `celebrimbor.falsifiers` — no blind gates

A gate nobody has ever seen turn red is a blind gate, and a blind gate
manufactures confidence. So **every `@check` must name a `falsified_by`** — a way
it could be caught being wrong, in practice a test, a fixture, or a dated
admission that one doesn't exist yet. This gate proves each of those points at
something real. The rule is enforced twice over: the `@check` decorator refuses a
check with no falsifier the moment it's registered, and this gate keeps that
promise honest over time (a `falsified_by` pointing at a test someone deleted goes
red).

The escape valve is explicit and dated: `falsified_by=Unproven("reason",
review_by="2026-09-01")` records that no falsifier exists *yet* — visible in every
run, and red once the review date passes. Debt with a deadline, never debt in
silence.

## `celebrimbor.registry` — the gate set is coherent

The registry is the single source of truth for "what checks exist." This gate
keeps it consistent: check ids are unique (two checks sharing an id would let one
silently shadow the other, since ids are how results are looked up), and every
check carries a title and a well-formed id. A duplicate id is rejected outright.

## `celebrimbor.completeness` — what should have run, ran

This is the last check to run, and it's where the regress stops. It compares the
report gathered so far against the registry: every check that should have run at
this stage is present, nothing ran that the registry doesn't know about (a *stray*
result would mean results are being manufactured outside the registry), and **the
report is not empty** — a gate that ran zero checks proved nothing, and reporting
green for that is exactly the plausible-but-wrong outcome celebrimbor exists to
prevent.

It has to run last, because it inspects everything that ran before it. But if the
last check itself never ran, nothing would report that it didn't — so that one
final link is closed by a static assertion in celebrimbor's own test suite, the
one place where checking the checker needs no further checker.

!!! note "Why this matters more than it looks"
    Checks register themselves as a side effect of being imported. A check in a
    module nobody imports is a check that silently never runs — a gate quietly
    disappearing, which is the exact failure this whole project exists to prevent,
    happening *inside the tool meant to prevent it*. These three gates, plus a
    meta-test that walks the package on disk, are what make "20 checks ran" a fact
    rather than a hope.

→ See [celebrimbor on celebrimbor](../concepts/self-hosting.md) for these gates
turned on celebrimbor's own source.
