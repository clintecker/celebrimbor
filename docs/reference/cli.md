# CLI reference

```
celebrimbor [COMMAND] [OPTIONS]
```

Five commands. The whole tool is kept small on purpose — a CLI that keeps
sprouting subcommands is one that has started asking you to learn it.

## `celebrimbor init`

Set up the quality checks in a project.

```bash
celebrimbor init [--surfaces] [--root DIR] [--force]
```

- Writes good default config for `ruff`/`mypy`/`pytest`/`coverage` into
  `pyproject.toml`, a `.pre-commit-config.yaml` whose one hook runs
  `celebrimbor gate --fast`, and a `tests/known-bad/` directory — the folder that
  holds kept examples of code that should be rejected.
- `--surfaces` also guesses the job each function does (its *role*) and writes a
  pre-filled map for you to confirm by hand. This is one of the deeper "proving"
  checks you opt into, so it never lands on you by surprise.
- Never overwrites a config section you already have; re-running only fills in
  what is missing. `--force` overwrites the sections celebrimbor owns.

## `celebrimbor gate`

Run the gate — the single command that runs every check.

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
| `--format FMT` | `human` (default), `plain` (no color), or `agent` (a JSON work-item verdict) |
| `--plain` | back-compatible alias for `--format=plain` |
| `--propose` | scaffold a falsifier for each surviving mutant (a TODO, never a proof) |
| `--update-baselines` | re-baseline the coverage, mutation, **and structure** ratchets (requires `--reason`, pinned env) |
| `--reason TEXT` | why a baseline is being moved — recorded |

The exit code is `0` only if every check that ran actually proved its claim. Here
is a green run and a red one:

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

### `--format=agent` — the machine-consumable verdict

`--format=agent` prints one JSON object built from the same report a person sees,
shaped so an automated agent loop can pick up the gate's refusals as its work
list. (The gate *fails closed*: when it can't prove something is right, it stops
and refuses rather than waving the code through.) The rule is one sentence:
**every red result becomes exactly one work item; a green run produces none.** An
agent loop stops when `work_items` is empty.

```console
$ celebrimbor gate --fast --format=agent
{
  "schema": "celebrimbor/agent-verdict/1",
  "stage": "fast",
  "ok": false,
  "exit_code": 1,
  "duration_s": 0.31,
  "totals": { "proved": 7, "failed": 1, "refused": 1, "skipped": 0 },
  "work_items": [
    {
      "id": "celebrimbor.format#a1f3c9",
      "check_id": "celebrimbor.format",
      "verdict": "fail",
      "kind": "format-dirty",
      "blocking": true,
      "found": "src/app/core.py: file is not formatted",
      "location": { "path": "src/app/core.py", "line": null },
      "claim": "every file is formatted",
      "action": "run `ruff format .`"
    }
  ],
  "skipped": []
}
```

Two things matter here, and the design guarantees them both:

- **A failure and a refusal stay distinct.** A `FAIL` carries `found` — the wrong
  thing it saw. A `REFUSED` instead carries `refused_because` — what the tool
  could not establish one way or the other. This keeps an agent from "fixing" a
  refusal by simply making the tool stop looking.
- **Nothing to game.** There is no severity, score, or ranking number for an agent
  to optimize toward. `blocking` is a plain yes/no, `totals` are counts, and the
  only decimal number anywhere in the object is `duration_s`.

A skipped check never becomes a work item — a skip is not a to-do. But it is
listed under `skipped`, so an agent can't quietly benefit from a deeper check that
nobody turned on.

### `--propose` — scaffold a falsifier for each surviving mutant

A *falsifier* is a way the code could be caught being wrong — in practice, a test
that fails when the code breaks. To check whether one really exists, mutation
testing makes a tiny change to your code (a *mutant*) and watches to see if any
test notices. A *surviving mutant* is a change no test caught — the missing
falsifier made concrete. The test that would catch that mutant is exactly the
proof the code is lacking. `--propose` turns each new survivor into a starting
point you can finish by hand — the mutant's identity, the surrounding code, a stub
test, and the steps to confirm your finished test really does catch the mutant —
written to `.celebrimbor/proposals/`.

```bash
$ celebrimbor gate --full --propose
```

It is fully predictable (no AI model, no extra tool run — it reads the same set of
surviving mutants the mutation check already collected), and it needs a source of
those survivors (`mutation_survivors`). With none, it reports *nothing to propose*
and writes nothing.

A generated scaffold is **never a proof**. It is a dated to-do: it lands in a
scratch directory no check reads, you never confirm it, and its presence changes
no result. Generating it just gets you past the blank page — finishing the test
and confirming it by hand is what actually moves the gate.

`--version` and `-h` / `--help` are available on every command.

## `celebrimbor watch`

Re-run the fast gate whenever a file that matters changes — the companion to
`gate --fast` while you work, so a problem shows up the instant you introduce it
instead of two minutes into CI.

```bash
celebrimbor watch [--root DIR]
```

| Option | Effect |
|---|---|
| `--root DIR` | project root (default: cwd) |

It watches, until you press `Ctrl-C`, for changes to the files a fast gate
actually depends on:

- `.py` files under `source` and `tests`,
- `celebrimbor.toml` and `pyproject.toml`,
- any `.celebrimbor/*.yaml` ledger.

Everything else — a README edit, a build artifact, a compiled `.pyc` — is
ignored. And it waits for the flurry of saves to settle before running, so one
save triggers exactly one run.

Each re-run is a **full fresh fast-stage run, identical to `gate --fast`**. That
is the whole safety story: watch keeps no cached "green" of its own, so it can
never claim green over a gate that is actually red — it re-runs the real gate and
prints the real report, every time. There is no shortcut engine to trust and no
saved state to go stale. (Faster, incremental re-runs are a later, separate
change; this version re-runs from scratch on purpose, because a from-scratch run
is obviously identical to the gate it stands in for.)

```console
$ celebrimbor watch
celebrimbor watch — /path/to/project
re-running the fast gate on every change; Ctrl-C to stop.

  ✓ celebrimbor.lint            ruff reports no violations
  …
  GREEN   9 proved   0 red   4 skipped   0.28s

changed: src/app/core.py

  ✗ celebrimbor.format          1 file(s) need formatting
  RED   7 proved   1 failed   0 refused   0.31s
^C
celebrimbor watch — stopped.
```

## `celebrimbor ratify`

*Ratify* means: you confirm, by hand, that a function's assigned job (its role) is
right, and that decision is locked to the code as it stands today. This command
does that — it confirms rows in your surface map (the list of every public
function and the job you've given each one) and pins them to the current code.

```bash
celebrimbor ratify [MODULES...] [--all] [--root DIR]
```

Confirming has two halves: deciding the job is right is *your* judgment; locking
the decision to the code's current shape is just arithmetic. This command does the
arithmetic, so that lock is never left off. Naming no modules and passing no
`--all` is an error — "confirm everything I haven't actually looked at" is the one
action nobody should take by accident.

## `celebrimbor explain`

Print the list of roles (the jobs a function can be assigned), the *capability*
budget (what pieces of the outside world — clock, network, files, randomness — a
role is allowed to reach for), and every registered check alongside its
*falsifier* (the test that would catch it failing). All of it is read from the
same tables the gate itself uses, so what you see can never drift from what is
enforced. It is the fastest way to see the rules a project is actually held to.

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
