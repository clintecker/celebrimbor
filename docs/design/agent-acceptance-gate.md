# Design: the agent-acceptance gate

*Status: Phase 0 in build. Phases 1–3 designed, not started.*

This is the design for celebrimbor's most valuable next move: turning the gate
into the acceptance check an agent's code has to clear before a person even looks
at it. It has three pillars, built in order of rising risk:

1. **A machine-readable verdict** — `celebrimbor gate --format=agent`, where every
   red result becomes exactly one clear work item and a green run produces none.
   An agent loop picks up celebrimbor's refusals as its to-do list. (The gate
   *fails closed*: when it can't prove something is right, it stops and refuses
   rather than letting it through.)
2. **A dedicated vacuity gate** — gather today's scattered "this can never turn
   red" detectors into one check with one shared vocabulary, so a test or a role
   that *cannot fail* is named plainly as such. ("Vacuity" here means a claim so
   hollow that nothing could ever contradict it.)
3. **A higher proof bar for AI-written code** — code known to be written by an AI
   owes strictly more: it must be proved through a real checker, or carry a dated
   admission that it isn't yet (`Unproven`). We track where code came from — its
   *provenance* — to know when this applies.

Nothing here softens the core rules. It adds no score, it fails closed, and the
one human judgment call — you confirming each function's job by hand — stays the
only sanctioned judgment.

---

## Phase 0 — the agent verdict

### The shape

`celebrimbor gate --format=agent` prints one JSON object built from the same
`GateReport` a person sees. The design rule is a single sentence: **every red
result becomes exactly one work item; a green run produces none.** An agent loop
stops when `work_items` is empty. There is no severity score, no ranking number an
agent could optimise toward — the items are an unordered set of facts, and
`blocking` is a plain yes/no.

```json
{
  "schema": "celebrimbor/agent-verdict/1",
  "stage": "default",
  "ok": false,
  "exit_code": 1,
  "duration_s": 2.14,
  "totals": { "proved": 17, "failed": 2, "refused": 1, "skipped": 3 },
  "work_items": [
    {
      "id": "celebrimbor.surface.evidence#a1f3c9",
      "check_id": "celebrimbor.surface.evidence",
      "verdict": "fail",
      "kind": "role-contradicted",
      "blocking": true,
      "claim": "no callable contradicts the role it is declared to have",
      "found": "myapp.report:build is declared `verifier` but every return path is a truthy literal and nothing raises — it can never turn red",
      "location": { "path": "src/myapp/report.py", "line": 42 },
      "action": "a verifier that cannot fail inspects nothing; give it a rejecting path and a negative fixture that exercises it"
    },
    {
      "id": "celebrimbor.invariants#0c4d88",
      "check_id": "celebrimbor.invariants",
      "verdict": "refused",
      "kind": "unestablished",
      "blocking": true,
      "claim": "every critical invariant keeps a real negative proof",
      "found": "invariant 'order-has-customer' is critical but its negative_proof does not resolve to a real test",
      "location": { "path": ".celebrimbor/invariants.yaml", "line": null },
      "action": "write the negative proof that observes the enforcer rejecting a violation, or drop `critical: true`",
      "refused_because": "the named negative proof could not be resolved to a real test"
    }
  ],
  "skipped": [
    { "check_id": "celebrimbor.coverage", "reason": "no coverage baseline yet, and this is not the pinned environment" }
  ]
}
```

### Field derivation — every field comes from data that already exists

The code that builds this JSON reads `GateReport` → `CheckResult` → `Finding` and
adds *no* new field to those existing types. It simply maps what's already there:

| Work-item field | Source |
|---|---|
| `check_id`, `verdict` | `CheckResult.check_id`, `CheckResult.verdict.value` |
| `claim` | the registered `CheckSpec.title` |
| `found` | `Finding.message` (or `CheckResult.reason` for a bare `REFUSED`) |
| `action` | `Finding.hint or CheckResult.remedy` |
| `location` | `Finding.path` / `Finding.line` |
| `kind` | `Finding.code` (already a stable string: `role-contradicted`, `pin-drift`, …) |
| `blocking` | `CheckResult.is_red` |
| `refused_because` | `CheckResult.reason`, present only on `REFUSED` |
| `id` | `f"{check_id}#{blake2s(kind|path|line|found)[:6]}"` — deterministic, stable across runs |

Two things matter here:

- **A failure and a refusal stay clearly separate.** A `FAIL` carries `found` —
  the wrong thing it saw. A `REFUSED` carries `refused_because` — what it could
  not establish either way. The whole reason for that split in `result.py` is so an
  agent can't "fix" a refusal by making the tool stop looking. The verdict keeps
  the two apart.
- **A skipped check never becomes a work item** — a skip is not a to-do — but it
  is listed in a separate `skipped` array, so an agent can't quietly benefit from
  a deeper check that nobody turned on.

This JSON is *built from the same report a person reads*, in the same way
`celebrimbor explain` is built from the very tables it enforces. There is no
separate agent-mode evaluation that could drift away from what a person sees — and
a test proves it: every kind of finding the codebase can emit must map to a
work-item `kind`, or celebrimbor's own test suite goes red.

### The CLI change

`--format={human,plain,agent}` becomes the main way to choose output on `gate`,
defaulting to `human`. The existing `--plain` flag stays as an alias for
`--format=plain`, so nobody's CI breaks (dropping it would). The relevant code is
loaded only when needed, so the fast stage keeps its ~10s budget — the new
`agent.py` output code is imported only when you ask for that format.

### Why Phase 0 first

It is just a reformatting of checks that already exist. No new detection, nothing
new that could go wrong, and it delivers value right away — *any* agent loop can
use the gate's refusals as a work list today. It is also the cheapest possible way
to test the core bet: if no agent loop actually turns these items into fixes, we
find that out before building the harder phases.

---

## Phase 1 — the vacuity gate

Bring today's scattered vacuity detectors (`structure/evidence.py`'s
`all_returns_truthy`, `checks/markers.py`'s assertion check) into one gate built
around a single question: *does this claim have any path that could actually
fail?* Written out as a data table, in the same style as the role-evidence
conditions:

| `kind` | Fires on | Because |
|---|---|---|
| `assert-tautology` | `assert True`, `assert x == x`, `... or True` | holds for every input |
| `verifier-cannot-fail` | every return path is a truthy literal, nothing raises | there is no red case |
| `mock-stubs-the-subject` | the callable under test is itself mocked in its own test | the assertion checks the mock, not the code |
| `covered-but-unasserted` | a file's lines are executed by the suite but its covering tests assert nothing | coverage proves the line runs, not that it works |

It stays as careful as the evidence gate already is: **only fire when the code
itself makes the contradiction certain.** `assert True`, yes; `assert
user.is_valid()`, never (that might return `False`). A vacuity gate that cries wolf
is a vacuity gate people switch off. The first two kinds read only the code's
structure and run at the fast stage; `covered-but-unasserted` needs coverage data,
runs at the default stage, and *refuses* rather than passes when that data isn't
there.

---

## Phase 2 — provenance-weighted proof burden

An opt-in check that you turn on. Who wrote a piece of code is determined, in
order: first from a source that can't be quietly forged (a git trailer or note —
this repo's own `Co-Authored-By` line counts), then from a `.celebrimbor/provenance.yaml`
file you maintain, and if neither says, **the gate refuses** — "I can't tell who
wrote this" never becomes "assume a human did."

For code marked AI-written in a governed role, the proof that role owes stops
being a *should* and becomes a *must*. The only way out is an explicit, dated,
expiring admission: `Unproven("AI-authored, human review pending", review_by=...)`.
This is a simple yes/no over a set of code regions, not a per-file risk rating.
And knowing where code came from only ever *adds* to an already-strict baseline —
there is no "a human wrote it" fast lane, because that would just become the
escape hatch everyone uses.

---

## Trust-surface guardrails

This section decides whether the feature stays true to celebrimbor or quietly
becomes its opposite. Four places it could rot, and the built-in guard for each:

1. **The verdict turns into a score.** The moment a work item grows a
   `severity: 0.7`, or the object grows a top-level `quality: 82`, an agent starts
   optimising that number. *Guard:* a test forbids any decimal field except
   `duration_s`. `blocking` is a yes/no; `totals` are plain counts.
2. **"AI owes a higher bar" quietly becomes "a human gets a pass."** *Guard:*
   knowing where code came from only ever adds obligation; there is no human
   waiver, and human-written code owes exactly what its role owes today.
3. **An agent "closing" items turns into approving its own work.** *Guard:* an
   agent may write code, fixtures, and falsifiers, and may draft a dated
   `Unproven`; it may **not** confirm a role and may **not** approve itself.
   `ratify` stays a human-only command, and the verdict never says "run ratify to
   fix this" — it says "this needs a human to confirm it," which only a human can
   do.
4. **A wrong vacuity finding trains agents to just suppress it.** *Guard:* the
   same care as the evidence gate — only fire when the code makes the
   contradiction certain; every false alarm is a bug in celebrimbor's own suite,
   provable by a kept example, and celebrimbor holds itself to this with no
   grandfathered exceptions.

---

## Build sequencing

- **Phase 0 (this PR):** `agent.py` — the `WorkItem` schema and `render_agent`;
  the `--format` selector on `gate`; a test asserting every kind of finding maps
  to a work item and forbidding any decimal field but `duration_s`; docs.
  celebrimbor stays green against its own gate, with no grandfathered exceptions.
- **Phase 1:** the vacuity gate (`structure/vacuity.py` + `checks/vacuity.py`),
  reusing `all_returns_truthy` and moving `markers`' assertion check behind the
  shared test. `assert-tautology` and `verifier-cannot-fail` at the fast stage;
  `covered-but-unasserted` at the default stage, refusing when coverage is absent.
- **Phase 2:** provenance (`provenance.py` + `checks/provenance.py`), reading
  authorship through the existing git hook-in, failing closed when authorship is
  unknown.
- **Phase 3:** locking down the schema — pin a version, add a round-trip test over
  every kind of verdict, and write a `gate/agent-verdict.md` reference page.

## Kill switch

If a real agent loop never actually uses Phase 0's verdict — if the work items
don't become fixes — then the schema is API surface we invented on a hunch, and
Phases 1–3 are premature. Phase 0 is deliberately cheap so we find this out before
building the expensive detection work. Prove the loop works against a real agent
before writing the vacuity engine.
