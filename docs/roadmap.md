# Roadmap

Celebrimbor's thesis is fixed: *a claim a system cannot contradict is a claim it
will eventually get wrong.* Everything below serves that one idea. Nothing here
adds a score, a grade, or a knob that lets a run pass without proving what it
claims — those would be the exact estimating behaviour the gate exists to refuse.

The work divides along two axes. **Depth** — prove things the gate currently
cannot. **Reach** — put the gate in front of more code, with less friction to
adopt. A feature earns a place on this list only if it fails closed, keeps human
ratification as the one sanctioned judgment, and moves a check *toward* an
invariant rather than toward an attestation.

## The through-line: the acceptance gate for AI-authored code

The dominant failure mode of machine-generated code is **plausibility without
falsifiability** — code that is well-shaped and passes the happy path, but whose
falsifiers are absent or vacuous: a verifier every return makes truthy, a test
whose mock stubs the thing under test, an `xfail` with a shrug for a reason.

That is precisely the epistemic vacuum celebrimbor already refuses for its own
roles. The next year of work turns that latent capability into the headline: the
gate an agent's code must clear before a human spends attention on it. Four of
the five tracks below feed this story; it is the spine of the roadmap, not a
separate feature.

## The five tracks

| Track | Axis | What it adds | Verdict |
|---|---|---|---|
| **Agent-acceptance gate** | Reach | A machine-consumable verdict + a first-class vacuity gate + provenance-weighted proof burden | **Building now.** The wedge. |
| **Falsifier generation** | Depth | Celebrimbor *drafts* the negative fixture; a human ratifies its intent; the machine proves its bite | **Next.** Deterministic core first, no LLM. |
| **Live surface (`watch` + LSP)** | Reach | Drift surfaces the instant it is introduced, in the editor, not three commits later in CI | **After the wedge.** Kills the week-1 adoption tax. |
| **Polyglot structural gates** | Reach | The structural gates (capabilities, complexity, cohesion) on TypeScript / Go / Rust via a tree-sitter backend | **Deferred.** Waits behind proof-gate depth. |
| **Runtime invariants** | Depth | Ledger invariants enforced as design-by-contract in the running system | **Sync gate only.** The contract library is a separate question. |

## Sequencing

The tracks are not independent. Three of them share machinery, so build order
matters more than raw priority.

1. **The agent verdict (`--format=agent`).** Pure serialisation of the report
   the gate already produces — every refusal becomes one actionable work item,
   and a green run emits zero. Near-zero risk, it is the wedge that repositions
   the whole tool, and it validates the core bet before a line of new detection
   is written: if no agent loop actually consumes the verdict, we learn that
   first. See the [design doc](design/agent-acceptance-gate.md).
2. **The vacuity gate.** Cheap, AST-only, and a *shared foundation*: both the
   agent-acceptance gate and falsifier generation consume the same
   "does this claim have a reachable failing path?" engine. Build it once — but
   only after the verdict has proven the loop is real.
3. **`celebrimbor watch`.** Kills the surface-map maintenance tax *and* yields the
   warm-inventory engine that makes an agent loop over the verdict fast. One
   investment, two payoffs.
4. **Falsifier generation** — scaffolding first, then a self-verifying
   mutation-guided core (which requires wiring live mutation execution), and only
   then, behind that mechanical filter, an optional LLM drafter.
5. **The language server** — once `watch` has proven the incremental engine.
6. **Polyglot facade extraction** — de-risk the seam by re-pointing the Python
   backend through a language-neutral facade, shipping nothing new, before any
   second grammar exists.
7. **The runtime sync gate** — the one honest, fail-closed slice of runtime
   invariants; it never enters a production hot path.

## What is deliberately not here

- **A quality score.** A single number gets trusted, gamed, and averaged into
  meaninglessness — the estimating posture the tool refuses. The honest analog
  already exists: the dated ledger of `Unproven` admissions, whose trend is *how
  many gaps there are and how old they are*, not a grade.
- **Auto-ratify.** Anything that pins a role or accepts a proof without a human
  hands away the one judgment call the whole design is built to protect.
- **Log-and-continue at runtime.** A contract that detects a contradiction and
  proceeds anyway has looked at a falsified claim and decided to trust it. That
  is the silent pass with extra steps.

Each track carries its own kill switch, documented in its design doc: the
condition under which building more of it would betray the thesis rather than
serve it.
