# Stages and families

`celebrimbor gate` is one command. Two **independent** things decide what it
runs. Keep them apart:

| Axis | Question | Values | Where it lives |
|---|---|---|---|
| **Stage** | *How deep should this run go?* | `fast` → `default` → `full` | the `--fast` / `--full` flags |
| **Family** | *What kind of check is this?* | `commodity` / `obligation` | a property of each check |

The two axes are different in nature, which is the whole reason they get
different words. **Stage is ordinal** — a scale, `fast` ⊂ `default` ⊂ `full`, and
a fourth, deeper stage is conceivable. **Family is categorical** — a check either
needs an authored ledger (`obligation`) or it doesn't (`commodity`); there is no
third answer and no "in between," so there are exactly two families, forever.
(This is why they aren't numbered: `commodity`/`obligation` are kinds, and
numbers `0`/`1`/`2`… would falsely suggest a sequence that could grow.)

A single check has one of each. The `obligation` `invariants` gate is in the
obligation family, and runs at the `default` stage. Family is about the check;
stage is about the run.

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

## The family axis — what kind of check

- **`commodity` — the commodity ladder.** Lint, types, format, structure,
  known-bad, marker grammar. Off-the-shelf rigor wired with opinionated
  defaults. Needs no ledger and passes on a fresh repo — the adoption wedge.
- **`obligation` — the obligation engine.** Surface roles, capabilities,
  producers, invariants, impact, ratchets, imports. Opt-in and authored: each
  obligation gate *skips with a reason* until you create the ledger it reads, so
  it never reddens on day one.

## Every check, on both axes

| Check | Stage | Family | What it enforces |
|---|---|---|---|
| `lint` / `format` / `types` | fast | commodity | ruff + mypy, strict, shelled out |
| `structure.complexity` | fast | commodity | complexity, nesting, length, param budgets |
| `structure.cohesion` | fast | commodity | one domain per module (connected components) |
| `structure.capabilities` | fast | obligation | dependencies injected, budgeted by role |
| `surface.completeness` | fast | obligation | every public callable is in a ratified map |
| `surface.naming` | fast | obligation | a callable named for a stronger role than assigned |
| `surface.evidence` | fast | obligation | a declared role the code contradicts |
| `surface.pin` | fast | obligation | a ratified role still describes the code |
| `known_bad` | fast | commodity | every known-bad file is rejected as declared |
| `markers` | fast | commodity | a marked test asserts; xfail/skip cite a reason |
| `falsifiers` / `registry` / `completeness` | fast | commodity | the gates on the gates |
| `producers` | default | obligation | no blind verifiers |
| `invariants` | default | obligation | every enforcer resolves; criticals keep a proof |
| `impact` | default | obligation | a changed policy-role module is named by an invariant |
| `imports` | default | obligation | modules import clean, no import-time effects |
| `coverage` | default | obligation | per-module coverage only rises |
| `mutation` | full | obligation | no new mutant survives (survivor identity) |

## Reading the output

```
celebrimbor gate — fast stage

  ✓ celebrimbor.lint            ruff reports no violations
  ✗ celebrimbor.structure.complexity   1 breach
      · myapp.report:build — cyclomatic complexity is 14 (limit 10)
        → extract the branches
  ⊘ celebrimbor.coverage        coverage could not be measured
      no .coverage data file; run your tests under coverage first
  – celebrimbor.invariants      skipped: no invariant ledger (obligation gates are opt-in)

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
