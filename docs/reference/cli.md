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
  surface map (Tier 1).
- Never overwrites a config section you already have; re-running only appends
  what is missing. `--force` overwrites sections celebrimbor owns.

## `celebrimbor gate`

Run the gate.

```bash
celebrimbor gate [--fast | --full] [OPTIONS]
```

| Option | Effect |
|---|---|
| `--fast` | pre-commit tier (~10s) |
| (default) | PR tier (~2min) — adds coverage ratchet, invariants, impact |
| `--full` | merge/release tier — adds mutation |
| `--root DIR` | project root (default: cwd) |
| `--diff-base REF` | git ref the impact gate diffs against |
| `-v`, `--verbose` | show hints, skips, and full findings |
| `--plain` | no color — for logs and CI annotations |
| `--update-baselines` | re-baseline ratchets (requires `--reason`, pinned env) |
| `--reason TEXT` | why a baseline is being moved — recorded |

Exit code is `0` only if every check that ran proved its claim.

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
drift from what is enforced.

```bash
celebrimbor explain
```
