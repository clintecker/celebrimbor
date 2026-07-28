# CLI reference

```
celebrimbor [COMMAND] [OPTIONS]
```

Four commands. The whole product surface is deliberately small — a CLI that grows
subcommands is one that has started asking you to learn it.

## `celebrimbor init`

Scaffold the quality ladder into a project.

```bash
celebrimbor init [--surfaces] [--root DIR] [--force]
```

- Writes opinionated `ruff`/`mypy`/`pytest`/`coverage` config into `pyproject.toml`,
  a `.pre-commit-config.yaml` whose one hook is `celebrimbor gate --fast`, and a
  `tests/known-bad/` directory.
- `--surfaces` also runs role inference and writes the pre-filled, ratify-me
  surface map (obligation).
- Never overwrites a config section you already have; re-running only appends
  what is missing. `--force` overwrites sections celebrimbor owns.

## `celebrimbor gate`

Run the gate.

```bash
celebrimbor gate [--fast | --full] [OPTIONS]
```

| Option | Effect |
|---|---|
| `--fast` | pre-commit stage (~10s) |
| (default) | PR stage (~2min) — adds coverage ratchet, invariants, impact |
| `--full` | release stage — adds mutation and container/integration steps |
| `--root DIR` | project root (default: cwd) |
| `--diff-base REF` | git ref the impact gate diffs against |
| `-v`, `--verbose` | show hints, skips, and full findings |
| `--plain` | no color — for logs and CI annotations |
| `--update-baselines` | re-baseline the coverage, mutation, **and structure** ratchets (requires `--reason`, pinned env) |
| `--reason TEXT` | why a baseline is being moved — recorded |

Exit code is `0` only if every check that ran proved its claim. A green and a red
run:

```console
$ celebrimbor gate --fast
  ✓ celebrimbor.lint            ruff reports no violations
  ✓ celebrimbor.types           mypy reports no errors
  ✓ celebrimbor.structure.complexity   every module within budget
  – celebrimbor.surface.completeness   skipped: no surface map (obligation, opt-in)
  GREEN   9 proved   0 red   4 skipped   0.28s

$ celebrimbor gate --fast
  ✗ celebrimbor.format          1 file(s) need formatting
      · src/app/core.py: file is not formatted
        → run `ruff format .`
  ⊘ celebrimbor.types           mypy is not installed
      a trusted environment promised the toolchain; a missing tool is red
  RED   7 proved   1 failed   1 refused   0.31s
```

`--version` and `-h` / `--help` are available on every command.

## `celebrimbor ratify`

Confirm surface-map rows and pin them to the current code.

```bash
celebrimbor ratify [MODULES...] [--all] [--root DIR]
```

Ratification has two halves: deciding the role is your judgment; stamping the
shape-pin is arithmetic. This does the arithmetic, so the pin is never absent.
Naming no modules and passing no `--all` is an error — "ratify everything I have
not looked at" is the one action nobody should take by accident.

## `celebrimbor explain`

Print the role taxonomy, the capability budget, and every registered check with
its falsifier — all derived from the same tables the gates read, so it cannot
drift from what is enforced. It is the fastest way to see the rules a project is
actually held to.

```console
$ celebrimbor explain
## Role obligations
  pure          a property or unit test over its contract
  parser        a unit test with malformed input that must be refused
  ...
## Registered checks
  celebrimbor.lint                      → celebrimbor's ruff config
  celebrimbor.surface.evidence  [obligation]  → tests/negative/test_evidence_gate.py::...
  ...
```
