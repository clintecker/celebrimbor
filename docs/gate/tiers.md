# The gate, tier by tier

`celebrimbor gate` is the one command. It runs three tiers of increasing cost;
each tier runs every check registered at or below it.

```bash
celebrimbor gate --fast    # pre-commit tier   — target < ~10s
celebrimbor gate           # PR tier           — target < ~2min
celebrimbor gate --full    # merge/release tier — as slow as it must be
```

## What runs at each tier

| Check | Tier | Tier 1? | What it enforces |
|---|---|---|---|
| `lint` / `format` / `types` | fast | | ruff + mypy, strict, shelled out |
| `structure.complexity` | fast | | complexity, nesting, length, param budgets |
| `structure.cohesion` | fast | | one domain per module (connected components) |
| `structure.capabilities` | fast | ✅ | dependencies injected, budgeted by role |
| `surface.completeness` | fast | ✅ | every public callable is in a ratified map |
| `surface.naming` | fast | ✅ | a callable named for a stronger role than assigned |
| `surface.evidence` | fast | ✅ | a declared role the code contradicts |
| `surface.pin` | fast | ✅ | a ratified role still describes the code |
| `known_bad` | fast | | every known-bad file is rejected as declared |
| `markers` | fast | | a marked test asserts; xfail/skip cite a reason |
| `falsifiers` / `registry` / `completeness` | fast | | the gates on the gates |
| `producers` | default | ✅ | no blind verifiers |
| `invariants` | default | ✅ | every enforcer resolves; criticals keep a proof |
| `impact` | default | ✅ | a changed policy-role module is named by an invariant |
| `coverage` | default | ✅ | per-module coverage only rises |
| `mutation` | full | ✅ | no new mutant survives (survivor identity) |

**Tier 0** (everything not marked Tier 1) needs no ledger and passes on a fresh
repo. It is the adoption wedge. **Tier 1** is opt-in and authored — each Tier 1
check skips (with a reason) until you create the ledger it reads, so it never
reddens on day one.

## Reading the output

```
celebrimbor gate — tier fast

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
report = celebrimbor.gate(tier="default")
report.ok           # bool — false if anything is red, or if nothing ran
report.exit_code    # 0 or 1
report.red          # the red results
report.by_id("celebrimbor.types")
```
