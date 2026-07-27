# Fixtures & markers

Two Tier 0 gates keep your *test* discipline honest — because a test suite is
only trustworthy if the tests can actually fail.

## Known-bad provenance

`tests/known-bad/` is a directory of files that are *deliberately wrong*, each
one a falsifier for a checker: proof that the checker still rejects what it is
supposed to. A linter that has never been observed to reject anything is a linter
nobody should trust.

`celebrimbor.known_bad` audits it strictly, in three ways:

- **Orphans, both directions.** A file with no `expected.yaml` entry is an orphan
  (nobody knows what it proves); an entry naming a file that does not exist is a
  stale claim. Both are red.
- **The *right* checker.** "Something complained" is compatible with the exact
  rule you care about having been silently disabled. The entry names which
  checker must reject the file.
- **The *expected* diagnostic.** Not just rejection, but rejection with the named
  code — a file can be wrong several ways at once, and only one is the point.

```yaml
# tests/known-bad/expected.yaml
unused_import.py:
  checker: ruff
  diagnostic: F401
  why: proves the unused-import rule is actually enabled
```

The gate runs the named checker (isolated from project config, so a per-file
ignore does not hide the rule) and confirms the diagnostic fires.

## Marker grammar

`celebrimbor.markers` enforces that a test's markers mean something checkable —
this is where quiet dishonesty accumulates:

- **A test must assert.** A test with no `assert`, no `pytest.raises`, no
  `self.assert*` cannot fail, so it proves nothing. Rejected.
- **An `xfail` must cite a reason.** `@pytest.mark.xfail` with no `reason=` is
  undocumented debt nobody will revisit.
- **A `skip` must name its condition.** `@pytest.mark.skipif` needs a reason; a
  bare `skip` needs one too.

Celebrimbor's own test suite obeys this grammar. The check is AST-based, so it
does not need to run your tests to catch a vacuous one.

## Utilities

Two supporting utilities ship in the package for your own tests to import (they
are not gates):

- **`celebrimbor.scenarios.pairwise`** — deterministic all-pairs scenario
  generation. Most interaction bugs are triggered by two values; pairwise covers
  every value-pair across all parameters in a fraction of the cases. It is
  deterministic (no RNG) so a failing scenario is reproducible and a committed
  baseline is meaningful, and `uncovered_pairs()` lets you *prove* completeness.
- **`celebrimbor.differ`** — a toolchain-stable snapshot differ with a
  reason-gated update and a `self_proof()` that mutates a baseline in memory to
  confirm the differ actually detects a change. A differ never shown to detect a
  change is a blind differ.
