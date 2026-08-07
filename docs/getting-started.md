# Getting started

## Install

```bash
pip install celebrimbor              # core (click, rich, pyyaml)
pip install "celebrimbor[commodity]"     # + ruff, mypy, pytest, coverage
```

celebrimbor doesn't bundle its own copies of the everyday tools (ruff, mypy,
pytest, coverage). It runs the ones already on your `PATH`, so you keep the exact
versions you've chosen — celebrimbor never drags in its own. The `[commodity]`
extra is just a convenience: it installs a working set to get you going.

Requires Python 3.11+.

## Scaffold a project

```bash
celebrimbor init
```

This writes good defaults into your `pyproject.toml` (ruff, mypy, pytest,
coverage), a `.pre-commit-config.yaml` whose one hook is `celebrimbor gate
--fast`, and a `tests/known-bad/` directory. That last one holds *known-bad
fixtures* — small examples of code that should be rejected, kept so you can prove
your checks still catch them. `init` **never overwrites** a config section you
already have; re-running it only adds what's missing.

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

`--fast` is the quick pre-commit pass. It runs lint, types, formatting, the
structure checks, a check that your known-bad fixtures are still caught, and the
test-marker grammar — aiming to finish in under ten seconds. On a conventional
repo it goes green quickly. Where it's red, each finding tells you the file, the
line, and the fix.

```
✓ celebrimbor.lint            ruff reports no violations
✓ celebrimbor.types           mypy reports no errors
✗ celebrimbor.format          1 file(s) need formatting
    · src/app/core.py: file is not formatted
      → run `ruff format .`
✓ celebrimbor.structure.complexity   6 module(s) within structural budget
...
```

There are three stages — how deep a run goes. A quick pre-commit pass, a fuller
pull-request pass, and the full merge-time pass:

```bash
celebrimbor gate --fast    # pre-commit: lint, types, format, structure, fixtures  (~10s)
celebrimbor gate           # PR: adds coverage ratchet, invariants, impact          (~2min)
celebrimbor gate --full    # merge/release: adds mutation                           (as slow as it must be)
```

## Turn on the proving checks

So far you've run the everyday checks. The deeper *proving checks* — the ones
that make your code prove it's what it claims — are opt-in. Nothing here turns
red until you write the map they read, so your first day stays green.

```bash
celebrimbor init --surfaces
```

That map is the **surface map**: a list of every public function in your code and
the job you've assigned each one. This command guesses each function's job — its
**role** (a parser parses, a verifier checks, and so on) — by reading your source,
and writes a pre-filled map at `.celebrimbor/surfaces.yaml`. Every guess it's
confident about is filled in and marked `inferred`. Where it's unsure, it leaves
the row out rather than guess wrong. Every inferred row stays **red until you
confirm it by hand** (you *ratify* it) — guessing shrinks your job, it never
turns anything green on its own.

Review the roles, then ratify them. Ratifying also *pins* each row to the code as
it stands today, so if someone later rewrites the function, the gate re-opens the
question:

```bash
celebrimbor ratify --all         # or: celebrimbor ratify myapp.parsing myapp.render
```

Now `celebrimbor gate --fast` also checks your ratified map: that every function
is accounted for, that roles are named consistently, that each function's code
actually matches its assigned job (the *evidence* check), and that no function
reaches for parts of the outside world it isn't allowed to touch — the clock, the
network, files — (the *capabilities* check). See
[Adopting an existing app](guides/adoption.md) for the full walkthrough,
including the producer and invariant ledgers.

## Use it from CI

CI is the one environment celebrimbor treats as fully trustworthy. It detects
`CI=1` and reads it as a promise that every tool is present — so a missing tool
turns red instead of quietly skipping — and it's the only place a *ratchet* (a
one-way gate, like test coverage, that can improve but can't quietly slip
backward) is allowed to set its starting line.

```yaml
# .github/workflows/gate.yml
- run: pip install celebrimbor[commodity]   # + your own test deps
- run: coverage run -m pytest               # produces the .coverage the ratchet reads
- run: celebrimbor gate                      # PR stage
```

Run `celebrimbor explain` to see every rule a project enforces at a glance — then
you know exactly what a green run is promising.

## Drive it from code

```python
import celebrimbor

report = celebrimbor.gate(stage="fast")
if not report.ok:
    for result in report.red:
        print(result.check_id, result.summary)
    raise SystemExit(report.exit_code)
```
