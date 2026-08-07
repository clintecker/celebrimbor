# Roadmap

One idea holds this whole tool together: *a claim your code can't be caught
getting wrong is a claim it will eventually get wrong.* Everything below serves
that idea. Nothing here adds a score, a grade, or a knob that would let a run pass
without proving what it claims — those would be exactly the guessing the gate
exists to refuse.

The work splits two ways. **Depth** means proving things the gate can't prove yet.
**Reach** means putting the gate in front of more code, with less friction to
adopt it. A feature earns a place on this list only if it *fails closed* (when it
can't prove something, it stops and refuses rather than waving it through), keeps
the one human judgment call — you confirming each function's job by hand — as the
only sanctioned judgment, and moves a check *toward* something the code must prove
rather than something it merely swears to.

## The through-line: the acceptance gate for AI-authored code

The way machine-generated code usually fails is that it *looks* right without any
way to be caught if it's wrong — well-shaped, passing the happy path, but with no
real *falsifier* behind it. (A falsifier is a way the code could be caught being
wrong: in practice, a test that genuinely fails when the code breaks.) The
falsifiers are missing or hollow: a checker whose every path returns something
truthy, so it can never turn red; a test whose stand-in fake replaces the very
thing it claims to test; a skipped test with a shrug for a reason.

That empty space — a claim with nothing that could ever contradict it — is exactly
what celebrimbor already refuses to accept in its own code. The next year of work
turns that into the headline feature: the gate an agent's code has to clear before
a person spends any attention on it. Four of the five tracks below feed this one
story. It is the spine of the roadmap, not a side feature.

## The five tracks

| Track | Axis | What it adds | Verdict |
|---|---|---|---|
| **Agent-acceptance gate** | Reach | A machine-consumable verdict + a first-class vacuity gate + provenance-weighted proof burden | **Building now.** The wedge. |
| **Falsifier generation** | Depth | Celebrimbor *drafts* the negative fixture; a human ratifies its intent; the machine proves its bite | **Next.** Deterministic core first, no LLM. |
| **Live surface (`watch` + LSP)** | Reach | Drift surfaces the instant it is introduced, in the editor, not three commits later in CI | **After the wedge.** Kills the week-1 adoption tax. |
| **Polyglot structural gates** | Reach | The structural gates (capabilities, complexity, cohesion) on TypeScript / Go / Rust via a tree-sitter backend | **Deferred.** Waits behind proof-gate depth. |
| **Runtime invariants** | Depth | Ledger invariants enforced as design-by-contract in the running system | **Sync gate only.** The contract library is a separate question. |

## Sequencing

The tracks aren't independent. Three of them share the same underlying machinery,
so the order we build in matters more than raw priority.

1. **The agent verdict (`--format=agent`).** Just a machine-readable printout of
   the report the gate already produces — every refusal becomes one clear work
   item, and a green run produces none. Almost no risk, it repositions the whole
   tool, and it tests the core bet before we write a line of new detection: if no
   agent loop actually uses the verdict, we find that out first. See the
   [design doc](design/agent-acceptance-gate.md).
2. **The vacuity gate.** ("Vacuity" here means a claim so hollow it can't ever be
   contradicted.) Cheap, reads only the code's structure, and a *shared
   foundation*: both the agent-acceptance gate and falsifier generation lean on
   the same engine answering one question — "does this claim have any path that
   could actually fail?" Build it once, but only after the verdict has shown the
   loop is real.
3. **`celebrimbor watch`.** Removes the ongoing cost of keeping your surface map
   up to date, *and* produces the always-warm engine that makes an agent loop over
   the verdict fast. One investment, two payoffs.
4. **Falsifier generation** — the starting scaffolds first, then a self-checking
   core guided by mutation testing (which needs live mutation runs wired in), and
   only then, behind that mechanical filter, an optional AI-model drafter.
5. **The language server** — once `watch` has proven out the incremental engine.
6. **Cross-language groundwork** — lower the risk by re-routing the current Python
   backend through a language-neutral layer, shipping nothing new, before any
   second language exists.
7. **The runtime sync gate** — the one honest, fail-closed slice of checking
   promises in the running system; it never sits in a performance-critical path.

## What is deliberately not here

- **A quality score.** A single number gets trusted, gamed, and averaged into
  meaninglessness — the guessing this tool refuses. The honest version already
  exists: a dated list of the gaps you've openly admitted (`Unproven`), where what
  matters is *how many gaps there are and how old they are*, not a grade.
- **Confirming roles automatically.** Anything that locks in a function's job, or
  accepts a proof, without a human hands away the one judgment call the whole
  design exists to protect.
- **Log-and-continue at runtime.** A promise-check that spots a contradiction and
  carries on anyway has looked at a broken claim and decided to trust it. That's
  the silent pass with extra steps.

Each track carries its own kill switch, written down in its design doc: the
condition under which building more of it would betray the core idea rather than
serve it.
