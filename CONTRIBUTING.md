# Contributing to celebrimbor

Celebrimbor holds itself to its own gate. Contributions are welcome, and the
bar is the same one the tool sets for everyone else: **every claim carries a
falsifier, and the gate fails closed.**

## Development setup

```bash
git clone https://github.com/clintecker/celebrimbor
cd celebrimbor
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the gate on celebrimbor itself:

```bash
celebrimbor gate --full     # lint, types, format, structure, and the meta-gates
python -m pytest            # the full suite, including every gate's negative fixtures
```

Celebrimbor's own gate is green at every tier. A change that reddens it is not
ready.

## The one rule with no exceptions

**Every check you add must name the negative fixture that proves it can turn
red.** This is enforced by the framework — `@check` requires `falsified_by` and
has no default — and by a meta-test that resolves every `falsified_by` to a real
test function. A gate that has never been observed to fail is a blind gate, and
celebrimbor does not ship blind gates, including its own.

When you add or change a gate:

1. Write the gate.
2. Write a **negative fixture** — a small project or input that the gate must
   turn red — as a `@pytest.mark.negative` test in `tests/negative/`.
3. Point the gate's `falsified_by` at that test's node id.
4. Add, where it clarifies the boundary, the **converse** fixture: the case that
   must stay green, so the gate is useful and not merely loud.

The negative fixtures are the product, not scaffolding. Treat them that way.

## Style

- Match the surrounding code: precise names, comments that explain *why* a
  decision was made (especially where a subtler option was rejected), and
  docstrings that state the invariant a module upholds.
- The structure gate enforces complexity, nesting, length, and cohesion budgets.
  If it flags your code, the honest fix is almost always to split, not to raise
  the limit.
- Prefer making an illegal state unrepresentable over checking for it.

## Reporting bugs and proposing features

Use the issue templates. For a bug, the most useful thing you can give us is the
smallest input that reproduces it — ideally one that could become a negative
fixture.

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
