# Changelog

All notable changes to celebrimbor are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-27

First release. An omakase quality harness that makes every unit carry its own
falsifier and the gate fail closed.

### Added

- **Core spine** — a three-state verdict (`pass` / `fail` / `refused` / skipped)
  with fail-closed enforced at construction; an ordered check registry where
  `@check` requires a `falsified_by`; a dual runner (CLI + pytest) that converts
  every fault to `refused` and proves no check escapes it.
- **Tier 0 ladder** — lint (ruff), types (mypy), format, and structure gates
  (complexity, nesting, length, and a cohesion gate that counts connected
  domains, not classes), wired with opinionated defaults via `celebrimbor init`.
- **Surface engine** — AST-only inventory (classify without importing),
  safe-direction role inference, ratify-then-pin surface map, a completeness
  audit, naming-drift detection, and role **evidence** (a declared role the code
  contradicts is refused).
- **Capability gate** — dependency injection enforced by role: an ambient reach
  outside a role's budget is red.
- **Ledgers** — the no-blind-verifier producer ledger, the invariant ledger
  (referential integrity + doc rendering + drift), and the change-impact gate.
- **Ratchets** — a coverage floor (per-module, auto-baselined in CI, with a
  low-floor meta-ratchet) and a mutation ratchet keyed on survivor *identity*.
- **Fixtures** — a known-bad provenance auditor, a marker-grammar gate, a
  deterministic pairwise scenario generator, and a baseline differ proven by
  in-memory mutation.
- **Public API** — `celebrimbor.gate()`, the `@celebrimbor.check` decorator, and
  configurable ledger paths for adopters with an existing layout.
- 129 tests, including a negative fixture for every gate.

[0.1.0]: https://github.com/clintecker/celebrimbor/releases/tag/v0.1.0
