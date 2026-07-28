# Configuration reference

Configuration is for the **exceptions only** — convention supplies the rest.
Every setting has a default that works on a conventionally-laid-out project, and
the config is optional. If you need config to get started, the conventions are
wrong, and that is a bug to report, not a knob to turn.

Settings live under `[tool.celebrimbor]` in `pyproject.toml`, or in a dedicated
`celebrimbor.toml` (which takes precedence). Resolution is explicit, and a
malformed file never falls back to defaults:

```mermaid
flowchart TD
    A["look for config —<br/>celebrimbor.toml, else [tool.celebrimbor] in pyproject"] --> B{found?}
    B -->|no| CONV([convention defaults])
    B -->|yes| C{parses?}
    C -->|yes| USE([use it])
    C -->|no| REF([refused — never falls back to defaults])
```

## Layout

```toml
[tool.celebrimbor]
source = "src"                 # source prefix (inferred if omitted)
tests = "tests"
known_bad = "tests/known-bad"
```

If a config file exists but is malformed, celebrimbor **refuses** — it never
falls back to defaults, because you asked for something specific and silently
doing something else is the estimating behavior the harness forbids.

## Environment

```toml
[tool.celebrimbor]
trusted_environment = true     # a missing tool is red, not a skip
pinned_environment = true      # ratchets may baseline here
```

Both default to a CI signal (`CI=1`, or the usual CI env vars, or
`CELEBRIMBOR_TRUSTED=1`). You rarely set these by hand — CI sets them for you.

## Your own checks and checkers

```toml
[tool.celebrimbor]
# App @check modules the CLI imports so `celebrimbor gate` runs your gates too.
check_modules = ["myapp.quality_checks"]

# A domain linter that proves its own tests/known-bad/ fixtures (beyond ruff/mypy).
# Either a subprocess `command` (with {file}) or an in-process `callable`
# ("module:function" returning the diagnostics); `match` is "exact" or "substring".
[tool.celebrimbor.known_bad_checkers.style_audit]
callable = "myapp.editorial:diagnostics_for"     # or: command = "... {file}"
match = "substring"                              # for phrase-emitting linters
```

`check_modules` is [Writing custom checks](../guides/custom-checks.md);
`known_bad_checkers` is [Fixtures & markers](../gate/fixtures.md). A named module
that will not import, or a checker command that will not run, is a hard
fail-closed error — never a silently smaller gate.

## Ledger paths

Point celebrimbor at existing ledgers instead of moving them under
`.celebrimbor/`. This is the hook that lets a project with an established
`quality/` directory adopt without reorganizing.

```toml
[tool.celebrimbor.paths]
surfaces = "quality/surfaces.yaml"
invariants = "quality/invariants.yaml"
producers = "quality/producers.yaml"
coverage_baseline = "quality/coverage-baseline.yaml"
mutation_baseline = "quality/mutation-baseline.yaml"
structure_baseline = "quality/structure-baseline.yaml"
```

An unknown key here is an error, not ignored — a typo'd override would leave
celebrimbor reading the default location while you believed it was pointed
elsewhere.

## Structure budgets

```toml
[tool.celebrimbor.limits]
complexity = 10
nesting = 4
max_statements = 50
max_params = 5              # positional, excluding self/cls
max_keyword_params = 8
max_returns = 8
max_function_lines = 80
max_file_lines = 500
max_domains_per_file = 1
max_public_callables = 20
```

Every value is a ceiling. An unknown limit key is an error — a silently-dropped
typo reads as a configured budget that is quietly not enforced.

## Other

```toml
[tool.celebrimbor]
min_coverage_floor = 60.0      # the low-floor meta-ratchet threshold
formatter = "ruff-format"
mutation_tool = "mutmut"
import_check = true            # opt in to the runtime import-health gate (it imports your code)
exclude = ["*/generated/*"]    # globs excluded from the surface inventory
disabled_checks = ["celebrimbor.mutation"]   # exceptions, on the record

# Your own @check modules. The CLI imports each so `celebrimbor gate` runs your
# domain checks too — not only the builtins. A module that will not import is a
# hard, fail-closed error, never a silently smaller gate.
check_modules = ["myapp.quality_checks"]

# Which roles the change-impact gate governs. Empty = the default
# (parser, normalizer, verifier, producer, adapter, orchestrator). Set it to
# match an existing harness's notion of a policy role. An unknown role name is
# an error, not ignored — a typo would silently shrink what is governed.
policy_roles = ["verifier", "parser", "producer", "adapter", "orchestrator"]
```

Disabling a check is visible in every run — an exception, not a hiding place.

## State directory

By default celebrimbor keeps ratified ledgers and baselines under `.celebrimbor/`
in your repo. These are **committed** — they are the record of your team's
ratified judgments and your ratcheted history, not a cache. The only thing that
belongs in `.gitignore` is `.celebrimbor/cache/`.
