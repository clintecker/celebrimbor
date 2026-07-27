# Tier 0 — the ladder

Tier 0 is the commodity ladder plus the structure gates: the checks that need no
ledger, run in seconds, and are green on a fresh repo. This is the adoption
wedge, and it is the only part of celebrimbor most projects touch on day one.

## Lint, format, types

Celebrimbor shells out to `ruff` and `mypy` — it never imports them — so the
versions that run are the ones *you* pinned. `celebrimbor init` writes a strict
default ruleset (the same one celebrimbor holds itself to).

- `celebrimbor.lint` — `ruff check`, parsed from its JSON output.
- `celebrimbor.format` — `ruff format --check`. Formatting is a *gate*, not an
  autofix: a gate that silently rewrote your tree would change what you are about
  to commit without telling you. The pre-commit hook does the rewriting.
- `celebrimbor.types` — `mypy` in strict mode.

If a tool's output cannot be parsed — a non-zero exit with unrecognized text,
usually a config error — the gate **refuses** rather than reporting clean. A tool
that told you nothing you could read has not told you all is well.

## Structure

These are measured directly from the AST, not delegated to a linter, so the
numbers are pinned to *your* codebase rather than to a tool's next release. Every
limit is a ceiling, not a target.

`celebrimbor.structure.complexity` enforces per-callable budgets:

| Metric | Default |
|---|---|
| cyclomatic complexity | 10 |
| nesting depth | 4 |
| statements | 50 |
| positional parameters | 5 (excluding `self`/`cls`) |
| keyword-only parameters | 8 |
| return statements | 8 |
| function lines | 80 |
| file lines | 500 |

Positional and keyword-only parameters are counted separately on purpose: a long
positional list is mis-orderable at the call site, while `f(a=1, ..., g=7)`
documents itself. Return count is generous because guard-clause style — many
early returns — is how you *avoid* deep nesting, and nesting has the stronger
justification.

`celebrimbor.structure.cohesion` enforces **one domain per module**, but it does
*not* count classes. It builds the module's intra-reference graph (definitions
that mention each other, plus definitions that share imported vocabulary) and
counts connected components. Five classes that are about each other are one
domain; one class and an unrelated function family are two. This distinction is
load-bearing: a naive class count flags a cohesive value-vocabulary module and
misses a genuinely mixed one.

## Known-bad and markers

Two more Tier 0 gates keep your *test* discipline honest — see
[Fixtures & markers](fixtures.md):

- `celebrimbor.known_bad` — every file in `tests/known-bad/` must be rejected by
  the checker it names, with the diagnostic it names.
- `celebrimbor.markers` — a test with no assertion is red; an `xfail`/`skip` must
  cite a reason.
