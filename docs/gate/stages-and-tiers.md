# Stages and tiers

`celebrimbor gate` is one command. Two **independent** things decide what it
runs, and they are easy to confuse because both were once called "tier." They
are not the same axis:

| Axis | Question | Values | Where it lives |
|---|---|---|---|
| **Stage** | *How deep should this run go?* | `fast` → `default` → `full` | the `--fast` / `--full` flags |
| **Tier** | *What kind of check is this?* | `0` (commodity ladder) / `1` (obligation engine) | a property of each check |

A single check has **both**. The Tier 1 `invariants` gate is tier 1 (it is part
of the obligation engine) and runs at the `default` stage (it is too slow for
pre-commit). Tier is about the check; stage is about the run.

!!! note "check vs. gate"
    A **check** is one registered unit (`@check`, one line of gate output). Each
    check is a **gate** — it can stop the run — so the two words name the same
    thing; "the gate" (singular) is the whole run of them together.

## The stage axis — how deep a run goes

Each stage runs every check assigned to it *or a cheaper one*, so they nest:
`full` ⊇ `default` ⊇ `fast`.

```bash
celebrimbor gate --fast    # fast stage    — pre-commit    — target < ~10s
celebrimbor gate           # default stage — pull request  — target < ~2min
celebrimbor gate --full    # full stage    — merge/release — as slow as it must be
```

## The tier axis — what kind of check

- **Tier 0 — the commodity ladder.** Lint, types, format, structure, known-bad,
  marker grammar. Off-the-shelf rigor wired with opinionated defaults. Needs no
  ledger and passes on a fresh repo — it is the adoption wedge.
- **Tier 1 — the obligation engine.** Surface roles, capabilities, producers,
  invariants, impact, ratchets, imports. Opt-in and authored: each Tier 1 check
  *skips with a reason* until you create the ledger it reads, so it never
  reddens on day one.

## Every check, on both axes

| Check | Stage | Tier | What it enforces |
|---|---|:--:|---|
| `lint` / `format` / `types` | fast | 0 | ruff + mypy, strict, shelled out |
| `structure.complexity` | fast | 0 | complexity, nesting, length, param budgets |
| `structure.cohesion` | fast | 0 | one domain per module (connected components) |
| `structure.capabilities` | fast | 1 | dependencies injected, budgeted by role |
| `surface.completeness` | fast | 1 | every public callable is in a ratified map |
| `surface.naming` | fast | 1 | a callable named for a stronger role than assigned |
| `surface.evidence` | fast | 1 | a declared role the code contradicts |
| `surface.pin` | fast | 1 | a ratified role still describes the code |
| `known_bad` | fast | 0 | every known-bad file is rejected as declared |
| `markers` | fast | 0 | a marked test asserts; xfail/skip cite a reason |
| `falsifiers` / `registry` / `completeness` | fast | 0 | the gates on the gates |
| `producers` | default | 1 | no blind verifiers |
| `invariants` | default | 1 | every enforcer resolves; criticals keep a proof |
| `impact` | default | 1 | a changed policy-role module is named by an invariant |
| `imports` | default | 1 | modules import clean, no import-time effects |
| `coverage` | default | 1 | per-module coverage only rises |
| `mutation` | full | 1 | no new mutant survives (survivor identity) |

## Reading the output

```
celebrimbor gate — fast stage

  ✓ celebrimbor.lint            ruff reports no violations
  ✗ celebrimbor.structure.complexity   1 breach
      · myapp.report:build — cyclomatic complexity is 14 (limit 10)
        → extract the branches
  ⊘ celebrimbor.coverage        coverage could not be measured
      no .coverage data file; run your tests under coverage first
  – celebrimbor.invariants      skipped: no invariant ledger (Tier 1 is opt-in)

  RED   9 proved   1 failed   1 refused   1 skipped   0.31s
```

- `✓` proved, `✗` failed (with a finding), `⊘` refused (could not check — also
  red), `–` skipped (with its reason).
- `--plain` drops color for logs and CI annotations; `-v` widens findings and
  shows hints and skips.
- Exit code is `0` only if every check that ran proved its claim.

## Programmatic

```python
report = celebrimbor.gate(stage="default")
report.ok           # bool — false if anything is red, or if nothing ran
report.exit_code    # 0 or 1
report.red          # the red results
report.by_id("celebrimbor.types")
```
