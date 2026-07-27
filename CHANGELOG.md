# Changelog

All notable changes to celebrimbor are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] — 2026-07-27

### Added

- **Configurable `policy_roles`** (`[tool.celebrimbor] policy_roles = [...]`) — the
  role set the change-impact gate governs. Lets an adopter match an existing
  harness's notion of a policy role. An unknown role name is a config error, not
  silently ignored.

### Changed

- **`orchestrator` is a policy role by default.** A silent change to how a module
  wires its dependency edges is a silent change to what the system does, so the
  impact gate now governs orchestrators out of the box. The default policy set is
  now `parser, normalizer, verifier, producer, adapter, orchestrator`.

## [0.2.0] — 2026-07-27

Adoption hardening — the changes that let an established codebase with existing
debt adopt celebrimbor without hitting a wall of exemptions.

### Added

- **Structure ratchet** (`celebrimbor.ratchets.structure`). The complexity,
  cohesion, and capability gates now grandfather the breaches that exist at
  adoption — a deliberate, reason-gated act taken in CI (`gate
  --update-baselines --reason ...`) — and thereafter fail only *new or worsened*
  breaches, keyed by a line-independent identity. A greenfield repo with no
  baseline stays strict (every breach fails), so this does not weaken the gate
  for new projects. Committed baseline + pure comparator + 10 negative fixtures.
- Configurable structure baseline path (`[tool.celebrimbor.paths].structure_baseline`).

### Changed

- **`surface.completeness` fails loud on a config mismatch.** A surface map whose
  rows match zero inventory callables (the wrong-`source` signature) now
  **refuses** with the real cause, instead of reporting "0/N accounted" and a
  wall of uncovered findings.
- **Naming inference drops the ambiguous `check_` verifier prefix.** `check_digit`
  (a checksum noun) and `check_value` (a getter) now abstain rather than
  misinfer as `verifier`; `verify_*` and `*_verifier` still classify real
  verifiers.
- **A package-dir source's root `__init__` is named by its package** (e.g.
  `press`) rather than the empty string, which surfaced as a confusing
  `module ''` in the completeness gate.

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

[0.2.1]: https://github.com/clintecker/celebrimbor/releases/tag/v0.2.1
[0.2.0]: https://github.com/clintecker/celebrimbor/releases/tag/v0.2.0
[0.1.0]: https://github.com/clintecker/celebrimbor/releases/tag/v0.1.0
