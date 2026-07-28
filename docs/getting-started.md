# Getting started

## Install

```bash
pip install celebrimbor              # core (click, rich, pyyaml)
pip install "celebrimbor[commodity]"     # + ruff, mypy, pytest, coverage
```

Celebrimbor runs the commodity tools as subprocesses and discovers them on your
`PATH`, so they are *your* pinned versions, not ones celebrimbor drags in. The
`[commodity]` extra is a convenience that installs a working set.

Requires Python 3.11+.

## Scaffold a project

```bash
celebrimbor init
```

This writes opinionated defaults into your `pyproject.toml` (ruff, mypy, pytest,
coverage), a `.pre-commit-config.yaml` whose one hook is `celebrimbor gate
--fast`, and a `tests/known-bad/` directory. It **never overwrites** a config
section you already have — re-running it only appends what is missing.

```text
your-project/
├── pyproject.toml            # + [tool.ruff] [tool.mypy] [tool.pytest] [tool.celebrimbor]
├── .pre-commit-config.yaml   # one hook: celebrimbor gate --fast
└── tests/
    └── known-bad/            # deliberately-wrong fixtures prove your checkers bite
```

## Run the gate

```bash
celebrimbor gate --fast
```

commodity runs lint, types, format, the structure gates, known-bad provenance, and
the marker grammar — targeting under ten seconds. On a conventional repo it goes
green quickly; where it is red, each finding tells you the file, the line, and
the fix.

```
✓ celebrimbor.lint            ruff reports no violations
✓ celebrimbor.types           mypy reports no errors
✗ celebrimbor.format          1 file(s) need formatting
    · src/app/core.py: file is not formatted
      → run `ruff format .`
✓ celebrimbor.structure.complexity   6 module(s) within structural budget
...
```

The three stages:

```bash
celebrimbor gate --fast    # pre-commit: lint, types, format, structure, fixtures  (~10s)
celebrimbor gate           # PR: adds coverage ratchet, invariants, impact          (~2min)
celebrimbor gate --full    # merge/release: adds mutation                           (as slow as it must be)
```

## Turn on the obligation engine

The obligation gates are opt-in — nothing here reddens until you author the map
they read.

```bash
celebrimbor init --surfaces
```

This runs role **inference** over your source and writes a pre-filled surface
map at `.celebrimbor/surfaces.yaml`. Every row it is confident about is filled
in and marked `inferred`; rows it is unsure about are left out entirely rather
than guessed. Every inferred row is **red until you ratify it** — inference
shrinks your job, it never manufactures green.

Review the roles, then ratify them (this also pins each row to the current code):

```bash
celebrimbor ratify --all         # or: celebrimbor ratify myapp.parsing myapp.render
```

Now `celebrimbor gate --fast` also runs the surface completeness, naming,
evidence, and capability gates against your ratified map. See
[Adopting an existing app](guides/adoption.md) for the full walkthrough,
including the producer and invariant ledgers.

## Use it from CI

CI is the **pinned environment**: celebrimbor detects `CI=1` and treats it as a
promise that the toolchain is present (a missing tool becomes red, not a skip)
and as the only place ratchets may take a baseline.

```yaml
# .github/workflows/gate.yml
- run: pip install celebrimbor[commodity]   # + your own test deps
- run: coverage run -m pytest               # produces the .coverage the ratchet reads
- run: celebrimbor gate                      # PR stage
```

Once you can see the enforced rules for a project at a glance with `celebrimbor
explain`, you know exactly what a green run is promising.

## Drive it from code

```python
import celebrimbor

report = celebrimbor.gate(stage="fast")
if not report.ok:
    for result in report.red:
        print(result.check_id, result.summary)
    raise SystemExit(report.exit_code)
```
