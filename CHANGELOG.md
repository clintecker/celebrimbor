# Changelog

All notable changes to celebrimbor are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.11.0 — 2026-07-28

### Added

- **An app can supply its own mutation survivor set (issue #12).** The mutation
  ratchet's *logic* — baseline, compare on survivor identity, reason-gated update
  — was already what an app with its own deterministic mutation wants; only the
  acquisition was hardwired to `mutmut`. Now `[tool.celebrimbor]
  mutation_survivors = "myapp.mutation:survivors"` names an importable callable
  returning `frozenset[celebrimbor.Survivor]`, and celebrimbor runs its
  survivor-identity ratchet over that instead of running the tool. A source that
  will not import, or returns something other than `Survivor`s, is refused (red),
  never a quiet pass.
- `celebrimbor.Survivor` is now public (exposed lazily so importing the package
  stays yaml-free), for apps building the survivor set.

## 0.10.1 — 2026-07-28

### Added

- `scripts/release.sh` — cuts a release without `gh release create` detaching
  HEAD from `main` (gh checks out a newly-created tag). The script creates and
  pushes the tag itself, then calls gh with `--verify-tag` so gh finds the tag
  already present and touches nothing local. Guards on a clean, pushed `main`
  with a matching version and a changelog entry; the notes come from that entry.
  This release was cut with it. See CONTRIBUTING.md.

## 0.10.0 — 2026-07-28

Two generic invariant-ledger enhancements, so an app can unify its ledger onto
celebrimbor's without dropping anything (issue #11).

### Added

- **An invariant can keep several negative proofs.** `negative_proof` now accepts
  a string *or a list* — an invariant can be independently falsified more than
  one way. Each named proof must resolve (a named-but-deleted proof is drift,
  exactly like a renamed enforcer), so this is stricter than "at least one," not
  looser.
- **A `limitations` vocabulary + `markers_cite_limitations`.** An invariant may
  declare `limitations:` — the cases the promise knowingly does not cover, as
  ids. With `[tool.celebrimbor] markers_cite_limitations = true` (off by
  default), an `xfail`/`skip` `reason=` must *cite* one of those declared
  limitations, so a catalogued known-gap can't be confused with a shrug. It
  fails closed: on with no ledger or no limitations declared, the markers gate
  refuses rather than reddening every reason.

### Changed

- `ledgers.invariants.Invariant`: `negative_proof: str | None` → `negative_proofs:
  tuple[str, ...]`, and the `proof_path` property → `proof_paths`. The YAML key
  is unchanged (`negative_proof`, string or list); only the Python model changed.

## 0.9.0 — 2026-07-28

Two more shapes of real-world known-bad checker fit now, so an app with domain
linters can retire its provenance auditor entirely (issue #10).

### Added

- **Substring match mode.** `[tool.celebrimbor.known_bad_checkers.<name>] match`
  is `exact` (default) or `substring`. Substring lets a fixture pass when its
  declared diagnostic appears *inside* an emitted line — for linters that emit
  human phrases with a variable part (`sentence break uses an em dash`) rather
  than stable codes. The three provenance guarantees are unchanged; only how a
  line is compared.
- **In-process Python checker seam.** A checker can be a `callable =
  "module:function"` instead of a `command`. celebrimbor imports it and calls
  `func(path) -> Iterable[str]` in-process — for checkers with no clean per-file
  subprocess entry (book-context-bound editorial linters). Composes with
  `match`. Every failure (bad ref, import error, a checker that raises) is a
  fail-closed *unverifiable*, never a quiet pass.

### Changed (breaking)

- `config.CheckerCommand` → `config.CheckerSpec`: it can now hold a `callable`,
  not just a `command`, so the name is made honest. Config written for 0.8.0
  (`command` + `pattern`) is unaffected; only the Python type name changed.

## 0.8.0 — 2026-07-28

### Added

- **App-declared known-bad checkers (issue #9).** The known-bad provenance gate
  only knew `ruff` and `mypy`, so an app whose fixtures are rejected by its own
  domain linter couldn't use it and had to keep a parallel auditor. Now a
  checker can be declared in config, and its fixtures get the same three
  guarantees (orphans both directions, the *right* checker fires, the *expected*
  diagnostic appears):

  ```toml
  [tool.celebrimbor.known_bad_checkers.style_audit]
  command = "python -m myapp.style_audit {file}"   # {file} = the fixture path
  pattern = "^([A-Z-]+)"                            # optional: first group = the code
  ```

  `ruff`/`mypy` remain built-in shorthands. A checker that will not run is
  *unverifiable* — red, never a quiet pass. New `config.CheckerCommand`.

## 0.7.1 — 2026-07-28

### Fixed

- **The import-health probe no longer false-positives on every ssl-importing
  module (issue #8).** The probe replaced the `socket.socket` *class* with a
  function; the stdlib's own `class SSLSocket(socket):` in `ssl.py` — reached
  transitively by `urllib` → `http.client` → `ssl`, i.e. by nearly every module
  — then failed at class-creation with `TypeError: function() argument 'code'
  must be code, not str`, before the guard even ran. With `import_check = true`
  this reddened *every* module of a real app. The guard is now a **subclass**
  that flags and blocks on construction, so the class stays subclassable while a
  real import-time socket is still recorded and prevented. The same
  class-replaced-with-a-function hazard applied to `subprocess.Popen` (also a
  class, not a function) and is fixed the same way. Ships with two regression
  fixtures: an ssl-importing module now passes, and an import-time socket is
  still blocked.

## 0.7.0 — 2026-07-28

`check_modules` — the CLI can now run an app's own `@check` registrations, so
`celebrimbor gate` is the whole gate, not just the builtins (issue #7).

### Added

- **`[tool.celebrimbor] check_modules = ["myapp.quality_checks"]`.** The CLI
  imports each listed module (after the builtins, before the run) so an
  adopter's domain checks run through `celebrimbor gate` itself, rather than
  requiring a hand-rolled programmatic entry point. A module that will not
  import is a **hard, fail-closed error** — a declared check that silently never
  runs is the exact failure mode this harness exists to prevent (same as #1).
  New `celebrimbor.checks.load_check_modules` / `CheckModuleError`.

### Fixed

- **The terminal completeness check now sorts last unconditionally.** It had
  relied on being registered last; a check registered *after* it (which is what
  loading an app module does) would run after it and be misreported as
  "escaped". `CheckSpec` gained a `terminal` flag and the registry sorts on it,
  so the completeness gate covers app checks correctly.

## 0.6.0 — 2026-07-28

Retire the numbered "Tier 0 / Tier 1." The two check families are now named,
not numbered, so nothing implies a "Tier 2" that will never exist.

A check's family is a **categorical pair, not a scale** — a check either needs
an authored ledger or it doesn't — so numbering it (0, 1, …) falsely suggested
a sequence. Contrast the run **stage** (fast/default/full), which *is* ordinal
and keeps its scale.

### Changed (breaking)

- `Tier 0` → **`commodity`** (the commodity ladder) and `Tier 1` →
  **`obligation`** (the obligation engine), everywhere:
  - the `tier1: bool` check attribute becomes `family: Family` where
    `Family` is `COMMODITY` | `OBLIGATION` (new, exported as `celebrimbor.Family`)
  - `@celebrimbor.check(tier1=True)` → `@celebrimbor.check(family=Family.OBLIGATION)`
  - the `[tier0]` install extra is renamed `[commodity]`
  - `celebrimbor explain` marks obligation gates `[obligation]` (was `[tier1]`)

  The `--fast` / `--full` flags and the `Stage` axis are unchanged.

### Documentation

- The gate overview page is renamed **Stages and families** and now spells out
  why the two axes get different words: stage is a scale, family is a pair.
- The Tier 0 page becomes **The commodity ladder**. All "Tier 0/1" prose across
  the site, README, and docstrings is retired in favour of commodity/obligation.

## 0.5.0 — 2026-07-27

Nomenclature: "tier" meant two different things. Now it means one.

The word described both *what kind* of check something is (Tier 0 commodity
ladder vs Tier 1 obligation engine) **and** *how deep a run goes*
(fast/default/full) — and both used numbers, so "tier 1" was ambiguous. The
run-depth axis is now **stage**; **tier** refers only to the gate family.

### Changed (breaking)

- The execution axis is renamed `Tier` → `Stage` throughout the public API:
  - `celebrimbor.Tier` → `celebrimbor.Stage` (values `FAST`/`DEFAULT`/`FULL`
    unchanged)
  - `celebrimbor.gate(tier=...)` → `celebrimbor.gate(stage=...)`
  - `@celebrimbor.check(tier=...)` → `@celebrimbor.check(stage=...)`
  - `ctx.tier` → `ctx.stage`, `report.tier` → `report.stage`,
    `Registry.for_tier` → `Registry.for_stage`

  The `--fast` / `--full` CLI flags, the `tier1: bool` check attribute, and the
  `[tier0]` install extra are unchanged — those correctly refer to the tier
  (gate-family) axis, which keeps the name.

### Documentation

- The gate overview page is rewritten as **Stages and tiers**, opening with an
  explicit two-axis table so the distinction is stated once, up front.
- Tier 0 is now called "the commodity ladder" consistently (it had drifted
  between "the wedge" and "the ladder").

## 0.4.0 — 2026-07-27

celebrimbor now gates itself. The full Tier 1 obligation engine runs against
celebrimbor's own source and ships green: 242 callables classified, ratified,
and pinned; 14 producers proved through real verifiers; 8 critical invariants
each with a negative proof; every module import-clean. See
[celebrimbor on celebrimbor](https://clintecker.github.io/celebrimbor/concepts/self-hosting/).

Turning it on found real defects in the tool, which are the fixes below.

### Fixed

- **All-digit shape pins no longer break the surface map.** A `blake2s` pin that
  lands in the digits `0`–`9` only was written to YAML unquoted, read back as an
  integer, and refused by the loader — taking the whole of Tier 1 down with a
  fail-closed refusal. Pins are now quoted on write and the legacy unquoted form
  is coerced on read. Ships with its own round-trip falsifier. Found by pointing
  celebrimbor at itself.

### Changed

- **The runner injects its clock.** `run_spec`/`run` took the elapsed time from
  the ambient `time.perf_counter`; they now accept a `clock` parameter defaulted
  to the real clock, so the timing they record is a seam a test can pin. This is
  celebrimbor's own capability gate applied to celebrimbor.
- **`load_all` / `load_builtin_checks` return the module names they loaded.**
  Registration-by-import had no observable result; the loaders now return the
  tuple of names they ensured are imported, so the load can be inspected and
  proved rather than trusted.

### Added

- celebrimbor ships its own `.celebrimbor/` ledgers as a worked, real-world
  example: a 49-row ratified surface map, a 15-entry producer ledger (14 proved,
  1 on a dated `pending` list), and an 8-invariant ledger. The import-health gate
  is enabled on itself (`import_check = true`).
- New documentation page, **celebrimbor on celebrimbor**, documenting the
  self-hosting result honestly — including the one `pending` producer and the
  CI-only ratchets.

## 0.3.1 — 2026-07-27

Evidence-check accuracy — three blind spots that forced honest roles to be
exempted during real adoption (issue #6).

### Fixed

- **I/O through a variable receiver is now traced.** `path.read_bytes()`,
  `entry.is_file()`, `d.glob(...)` — inside a comprehension or loop, on a local
  or injected receiver — were missed because the capability patterns keyed on the
  literal `Path`. The scanner now also keys on distinctive method leaves.
- **Seam-delegation counts as adapting.** A wrapper whose one syscall lives one
  module deeper — a call into an adapter-classified module, an I/O-verb method
  (`transport.get`, `client.post_json`, `runner.run`), or a private same-module
  helper that itself does I/O — no longer reads as "adapts nothing".
- **Stateful in-memory fakes may be adapters.** A test-double that mutates its
  own state and touches no ambient capability *is* the injected backend, so it
  satisfies `adapter` rather than fitting no role.

The escape these guard stays closed: a genuinely inert function (pure value
computation) declared `adapter` is still contradicted. Against a real 86-module
codebase these cut adapter false-positives from 18 to 6 — the remainder genuine
misclassifications the sharper check now surfaces.

### Changed

- The ratification pin scheme is bumped (it now includes state-mutation and I/O
  character), so existing ratified rows re-open once and must be re-ratified with
  `celebrimbor ratify`. This affects only projects with a committed surface map.

## 0.3.0 — 2026-07-27

### Added

- **Import-health gate** (`celebrimbor.imports`, opt-in via `import_check = true`).
  The one gate that imports the application — every other check is AST-only. It
  imports each module in an **isolated subprocess** (never the gate's own
  process, so the "classify without importing" guarantee is never compromised)
  and reports (a) any module that does not import, and (b) any import-time side
  effect — a file write, socket, or process spawn during import. The probe guards
  those effects, so it detects *and prevents* them: a module that would write a
  file on import does not actually write one during the check. Off by default,
  because it runs your code.

## 0.2.1 — 2026-07-27

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

## 0.2.0 — 2026-07-27

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

## 0.1.0 — 2026-07-27

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
