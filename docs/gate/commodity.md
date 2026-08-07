# The everyday checks

These are the everyday checks — the tool's *commodity* family: lint, formatting,
types, structure, and a couple more. They need nothing from you, run in seconds,
and are green on a fresh project. For most projects this is the whole of
celebrimbor on day one — the easy way in, before you opt into anything deeper.

## Lint, format, types

Celebrimbor runs `ruff` and `mypy` as separate programs — it never imports them
into itself — so the versions that run are the exact ones *you* pinned in your
project. `celebrimbor init` writes a strict default ruleset, the same one
celebrimbor holds itself to.

- `celebrimbor.lint` — `ruff check`, parsed from its JSON output.
- `celebrimbor.format` — `ruff format --check`. Formatting is a check, not an
  autofix: a gate that silently rewrote your files would change what you're about
  to commit without telling you. The pre-commit hook does the rewriting; the gate
  only reports.
- `celebrimbor.types` — `mypy` in strict mode.

If a tool's output can't be read — a non-zero exit with text celebrimbor doesn't
recognize, usually a config error — the gate **refuses** rather than report
clean. A tool that told you nothing you could understand has not told you all is
well, so celebrimbor won't pretend it did:

```mermaid
flowchart TD
    T["run ruff / mypy<br/>(your pinned version)"] --> P{parse the<br/>output}
    P -->|clean| G([pass])
    P -->|"violations found"| F([fail — with findings])
    P -->|"can't read it"| R([refused — red])
```

In CI, where the toolchain was promised to be present, a *missing* tool is itself
a refusal — its absence is a real problem, not a free pass. On your own machine
the same gate just skips with a reason, so a contributor who hasn't installed
mypy isn't blocked by a check CI is going to run anyway.

## Structure

Celebrimbor reads these numbers straight from your code's structure (its abstract
syntax tree, or AST — the parsed shape of the source, before it runs) rather than
handing the job to another linter. So the limits track *your* codebase, not some
tool's next release. On a brand-new project every limit is a hard ceiling. On an
older, larger codebase the same gates
[ratchet](ratchets.md#structure-grandfather-the-debt-hold-the-line) instead: a
ratchet is a one-way gate, so any breach you already have is grandfathered in and
can only shrink from there, never grow. You never have to hand-write dozens of
exemptions just to adopt.

`celebrimbor.structure.complexity` enforces per-callable and per-module budgets:

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
| public callables per module | 20 |
| domains per module | 1 |

Positional and keyword-only parameters are counted separately on purpose. A long
positional list is easy to mis-order at the call site, while `f(a=1, ..., g=7)`
labels each argument for you. The return-statement limit is generous because
using many early returns — guard clauses — is how you *avoid* deep nesting, and
avoiding nesting matters more.

The same gate also enforces **one domain per module** — one subject per file. (It
reports this under `celebrimbor.structure.complexity`; there's no separate
`cohesion` gate id.) It doesn't do this by counting classes. Instead it maps how
the definitions in a module relate — which ones reference each other, and which
ones draw on the same imported vocabulary — and counts the separate clusters that
result. Five classes that are all about each other are one domain; a single class
sitting next to an unrelated family of functions is two. Counting classes alone
would wrongly flag a tight, cohesive module and wave through a genuinely mixed
one.

## Known-bad and markers

Two more everyday gates keep your *tests* honest — see
[Fixtures & markers](fixtures.md):

- `celebrimbor.known_bad` — you keep a folder of code that *should* be rejected,
  `tests/known-bad/`, and every file in it must be turned away by the checker it
  names, with the exact complaint it names. It's how you prove your checkers can
  still catch the bad thing they're meant to catch.
- `celebrimbor.markers` — a test with no assertion is red, because it can't fail
  and so proves nothing; and any `xfail` or `skip` has to state a reason.
