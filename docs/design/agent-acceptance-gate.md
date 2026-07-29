# Design: the agent-acceptance gate

*Status: Phase 0 in build. Phases 1–3 designed, not started.*

This is the design for celebrimbor's highest-leverage next move: turning the gate
into the acceptance check an agent's code must clear before a human looks at it.
It has three pillars, built in order of rising risk:

1. **A machine-consumable verdict** — `celebrimbor gate --format=agent`, where
   every red result becomes exactly one actionable work item and a green run
   emits zero. An agent loop consumes celebrimbor's fail-closed refusals as its
   TODO queue.
2. **A first-class vacuity gate** — promote the scattered "this can never turn
   red" detectors into one gate with one vocabulary, so a test or a role that
   *cannot fail* is named as such.
3. **Provenance-weighted proof burden** — AI-authored regions owe a strictly
   higher bar: proved through a verifier, or carrying a dated `Unproven`.

Nothing here relaxes the doctrine. It adds no score, it fails closed, and human
ratification stays the one sanctioned judgment.

---

## Phase 0 — the agent verdict

### The shape

`celebrimbor gate --format=agent` emits one JSON object derived from the same
`GateReport` the human sees. The design rule is a single sentence: **every red
verdict becomes exactly one work item; a green run emits zero work items.** An
agent loop terminates when `work_items` is empty. There is no severity float, no
ranking number an agent could optimise — items are unordered facts, and
`blocking` is a boolean.

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

The serialiser reads `GateReport` → `CheckResult` → `Finding` and adds *no*
new field to those frozen types. It maps:

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

Two properties are load-bearing:

- **`REFUSED` and `FAIL` stay structurally distinct.** A `FAIL` carries `found`;
  a `REFUSED` carries `refused_because`. The whole point of the split in
  `result.py` is that an agent must not "fix" a refusal by making the harness
  stop looking. The verdict preserves that.
- **`SKIPPED` never becomes a work item** — a skip is not a TODO — but it is
  emitted under a separate `skipped` array, so an agent cannot silently benefit
  from an obligation nobody opted into.

The serialiser is *derived from the same report the human reads*, exactly as
`celebrimbor explain` is derived from the tables it enforces. There is no
separate agent-mode evaluation that could drift from the human verdict — and a
meta-test proves it: every `Finding.code` the codebase can emit must map to a
work-item `kind`, or celebrimbor's own suite goes red.

### The CLI change

`--format={human,plain,agent}` becomes the canonical selector on `gate`, with a
default of `human`. The existing `--plain` flag is kept as a back-compatible
alias for `--format=plain` (removing it would be a breaking change for anyone's
CI). Imports stay deferred so the fast stage keeps its ~10s budget; the new
`agent.py` emitter is imported only when that format is requested.

### Why Phase 0 first

It is pure serialisation over checks that already exist. No new detection, no new
risk surface, and it ships value immediately — *any* agent loop can consume the
gate's refusals as a work list today. It is also the cheapest possible test of
the core bet: if no agent loop actually turns these items into fixes, we learn
that before building the harder phases.

---

## Phase 1 — the vacuity gate

Pull the existing vacuity detectors (`structure/evidence.py`'s
`all_returns_truthy`, `checks/markers.py`'s assertion check) into one gate keyed
on one question: *does this claim have a reachable failing path?* Expressed as a
data table in the same style as the role-evidence conditions:

| `kind` | Fires on | Because |
|---|---|---|
| `assert-tautology` | `assert True`, `assert x == x`, `... or True` | holds for every input |
| `verifier-cannot-fail` | every return path is a truthy literal, nothing raises | there is no red case |
| `mock-stubs-the-subject` | the callable under test is itself mocked in its own test | the assertion checks the mock, not the code |
| `covered-but-unasserted` | a file's lines are executed by the suite but its covering tests assert nothing | coverage proves the line runs, not that it works |

The soundness posture is the same conservatism the evidence gate already takes:
**fire only on syntactically closed contradictions.** `assert True` yes;
`assert user.is_valid()` never (it might return `False`). A noisy vacuity gate is
a disabled vacuity gate. The first two `kind`s are pure-AST and run at the FAST
stage; `covered-but-unasserted` needs coverage data, runs at DEFAULT, and
*refuses* rather than passes when that data is absent.

---

## Phase 2 — provenance-weighted proof burden

An opt-in obligation gate. Authorship comes, in priority order, from a
tamper-evident source (a git trailer or note — this repo's own `Co-Authored-By`
convention qualifies), then an explicit `.celebrimbor/provenance.yaml` ledger,
and if neither is present **the gate refuses** — "I can't tell who wrote this" is
never "assume human."

For a callable marked AI-authored in a policy role, the proof its role owes stops
being a *should* and becomes a *must*: the only escape is an explicit, dated,
expiring `Unproven("AI-authored, human review pending", review_by=...)`. The
mechanism is a boolean gate over a set of regions, not a per-file risk level, and
provenance only ever *adds* obligation to an already-strict floor — there is no
"human-authored" fast-path, because that would be the universal escape hatch.

---

## Trust-surface guardrails

This section decides whether the feature is celebrimbor or its opposite. Four
places it could rot, and the structural guard for each:

1. **The verdict becomes a score.** The instant `work_items` grows a
   `severity: 0.7` or the object grows a top-level `quality: 82`, an agent
   optimises the number. *Guard:* the schema meta-test forbids any float field
   outside `duration_s`. `blocking` is boolean; `totals` are counts of facts.
2. **"AI gets a higher bar" implies "human gets a pass."** *Guard:* provenance
   only ever adds obligation; there is no human waiver, and human-authored code
   owes exactly what its role owes today.
3. **An agent "closing" items becomes auto-ratification.** *Guard:* an agent may
   write code, fixtures, and falsifiers, and may draft a dated `Unproven`; it may
   **not** ratify a role and may **not** self-approve. `ratify` stays a human
   command, and the verdict never emits "run ratify to fix this" — it emits
   "this needs human ratification," which only a human closes.
4. **A false vacuity finding trains agents to suppress it.** *Guard:* the same
   conservatism as the evidence gate — fire only on closed contradictions; every
   false positive is a bug in celebrimbor's own suite, provable by a fixture, and
   celebrimbor holds itself strict with zero grandfathered breaches.

---

## Build sequencing

- **Phase 0 (this PR):** `agent.py` — the `WorkItem` schema and `render_agent`;
  the `--format` selector on `gate`; a meta-test asserting every `Finding.code`
  maps to a work item and forbidding any float field but `duration_s`; docs.
  Self-hosting stays green with zero grandfathered breaches.
- **Phase 1:** the vacuity gate (`structure/vacuity.py` + `checks/vacuity.py`),
  reusing `all_returns_truthy` and migrating `markers`' assertion check behind
  the shared predicate. `assert-tautology` and `verifier-cannot-fail` at FAST;
  `covered-but-unasserted` at DEFAULT, refusing when coverage is absent.
- **Phase 2:** provenance (`provenance.py` + `checks/provenance.py`), reading
  authorship through the existing git seam, failing closed on unknown authorship.
- **Phase 3:** schema hardening — version pin, round-trip meta-test over every
  verdict kind, and a `gate/agent-verdict.md` reference page.

## Kill switch

If Phase 0's verdict is not actually consumed by a real agent loop — if the items
do not become fixes — the schema is speculative API surface and Phases 1–3 are
premature. Phase 0 is deliberately cheap so this is discoverable before the
expensive detection work is built. Validate the loop against a real agent before
writing the vacuity engine.
