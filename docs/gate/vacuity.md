# Vacuity

One of the everyday checks watches your *assertions* — because an assertion is the
smallest claim a test makes, and an assertion that holds for every possible input
makes no claim at all.

## Why a tautology proves nothing

```python
def test_orders_have_customers():
    orders = load_orders()
    assert True  # <-- looks like a test; cannot fail
```

`assert True` passes no matter what `load_orders` returns. So does `assert x == x`,
and so does `assert result or True`. Each is a *tautology* — a statement that's
true for every input, with no way to ever come out false. A test resting on one
can never turn red, which is exactly the blindness the rest of celebrimbor exists
to catch, now one level down, inside the assertion itself. It's the same
contradiction the [role-evidence gate](surface.md) names in a verifier whose every
return is truthy: a claim with no failing path isn't a claim.

`celebrimbor.vacuity` reads every `.py` file under both your source tree and your
test tree and reddens on any `assert` whose condition is provably true for every
input. It's an everyday check — no ledger to author, green on a clean repo — and
it runs at the `FAST` stage because it only reads your code's structure (its AST),
never runs it.

## What it fires on

Only three syntactically closed shapes, each true for every input:

| Shape | Example | Why it is vacuous |
|---|---|---|
| a constant truthy literal | `assert True`, `assert 1`, `assert "x"`, `assert (1, 2)` | holds for every input |
| a value compared to itself | `assert x == x`, `assert self.a is self.a` | true regardless of the value |
| an `or` short-circuiting to a truthy constant | `assert e or True`, `assert True or e` | the whole thing is truthy no matter what `e` is |

Self-comparison is restricted to **pure operands** — names, attributes, and
constants. `assert f() == f()` is left alone, because a call may have side effects
and isn't the same expression evaluated twice.

## What it never fires on

Being conservative here is the whole point: a vacuity check that fires on a real
assertion trains people to suppress it, and a suppressed check is a disabled check.
So whenever the truth of an assertion depends on any actual value, the gate holds
back. All of these have a reachable false case and are **never** flagged:

```python
assert x == y            # two different values
assert user.is_valid()   # a call could return False
assert len(items) >= 0   # not `==`/`is`, and could be a lie for a custom __len__
assert x is not None      # a real narrowing check
assert f() == g()         # different calls
assert x != x             # always FALSE — a contradiction, not a tautology
```

## Exclusions and fail-closed posture

- **Known-bad fixtures are skipped.** `tests/known-bad/` holds deliberately broken
  source, and one of those files failing to parse must not take the whole run
  down.
- **The configured `exclude` globs are honoured** — the same set the surface
  inventory uses.
- **An unparseable file refuses.** The gate only reads structure, so a file it
  can't read (and that *isn't* a known-bad fixture) is a claim it can't establish:
  it returns `REFUSED` rather than waving the file through. When it can't prove the
  file is clean, it stops — it fails closed.

Its falsifier — the way this gate itself can be caught failing to do its job — is
`tests/negative/test_vacuity_gate.py::test_tautological_assert_is_red`, the fixture
that proves the gate turns red on `assert True`. celebrimbor holds its own suite to
it, with zero grandfathered breaches.
