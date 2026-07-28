# Why celebrimbor

This page is the argument, made concretely. If you already believe the pitch and
want to use the tool, [Getting started](../getting-started.md) is the page you
want.

## What your existing tools cannot see

Take four functions. Every one of them passes `ruff`, passes `mypy --strict`,
and passes a test suite — including tests an AI wrote alongside the code.

```python
def verify_invoice(inv: Invoice) -> bool:
    """Check the invoice is well-formed."""
    if inv.total < 0:
        ...  # TODO: handle
    return True                      # (1) never returns False

def parse_config(raw: str) -> Config:
    """Parse the config."""
    data = json.loads(raw)
    return Config(**data)            # (2) never rejects malformed input;
                                     #     raises AttributeError, not a refusal

def slugify(title: str) -> str:
    """Normalize a title to a slug."""
    return f"{title.lower()}-{datetime.now():%s}"  # (3) 'pure' function reads the clock

def test_pricing():
    price = compute_price(cart)
    assert price is not None         # (4) asserts nothing that can fail meaningfully
```

1. A **blind verifier.** It has one job — reject bad invoices — and it cannot.
   Every call is green. Coverage is 100%. It is worse than no check, because it
   manufactures confidence.
2. A **parser that does not parse.** It transforms happy input and explodes on
   the rest with an incidental `AttributeError`. It never *refuses*; there is no
   negative fixture that could pin its behavior on bad input.
3. A **"pure" function with a hidden dependency.** Its output depends on wall
   time. No test can pin it, because there is no seam to substitute a clock
   through. What does it do at a leap second? Nobody can write that test.
4. A **test that cannot fail.** `is not None` passes for every non-`None` value,
   including a wrong one.

Linters check style. Type checkers check shapes. Tests check the cases you
thought to write. **None of them ask whether the code is what it claims to be.**
That question is unanswered by the entire commodity ladder, and it is precisely
the question that matters for code you did not write by hand — code from an AI,
or from six months ago, or from someone else.

## What celebrimbor does about each one

Celebrimbor assigns every callable a **role** — a claim about what proof it owes
— and then makes that claim *falsifiable*. Each failure above is caught by a
specific, mechanical check, not by a reviewer's diligence:

| Failure | Caught by | How |
|---|---|---|
| Blind verifier (1) | the evidence gate | a `verifier` whose every return path is a truthy literal *can never turn red* — detectable in the AST |
| Non-refusing parser (2) | the evidence gate | a `parser` with no reachable failing path is refused; and it owes a negative fixture that must reject malformed input |
| Impure "pure" (3) | the capability gate | `datetime.now()` is an *ambient* reach; a `pure` callable's capability budget is empty, so the un-injected clock is red |
| Vacuous test (4) | the marker gate | a test with no assertion cannot fail, so it proves nothing, and is rejected |

None of these are style opinions. They are structural facts about the code that
the gate reads directly. An author — human or model — cannot satisfy the gate by
being *plausible*; they have to produce code that carries its own falsifier.

## Why this is the right shape for AI-generated code

A language model is a plausibility engine. Given a task, it produces the most
likely-looking code, and likely-looking is exactly what slips past tools that
check form rather than proof. That is not a knock on models — it is what they
optimize for — but it means the review burden lands on you, and "looks correct"
is a burden that does not scale.

Celebrimbor moves the burden of proof onto the code, by construction. The gate
**fails closed**: when it cannot prove a claim, it refuses (red) rather than
guessing green. A model cannot talk its way past that, because there is no
argument to make — there is only a fixture that turns the gate red, or there
isn't. You review a red gate with a specific finding, not a plausible diff.

The project's own thesis is that *an agent building without a falsifier in reach
will produce something plausible and wrong.* Celebrimbor is the falsifier, kept
in reach.

## Why a framework, and not a pile of tools

The individual ideas here are old. Mutation testing, property-based testing,
dependency injection, the object-capability model, coverage ratchets, invariant
ledgers, provenance-checked fixtures, design-by-contract — each has a tool, a
paper, a community. If you assembled all of them yourself you would have eight
configs, eight mental models, and eight ways for them to disagree.

What celebrimbor contributes is the **coupling**. They are not eight tools; they
are one obligation engine keyed on a single spine — the role — so they reinforce
each other:

- The **capability gate** can only be trusted because the **evidence gate**
  proves the role it keys on is honest. (An `adapter` label with unrestricted
  budget would be a trivial escape — unless declaring `adapter` on a callable
  that adapts nothing is itself refused. It is.)
- The **impact gate** is only meaningful because the **surface map** is provably
  *complete* — every public callable is accounted for, checked by an AST
  inventory that never imports your code, so it cannot fall behind code that
  fails to import.
- A **producer** is only trustworthy because it names a **verifier**, and that
  verifier is only trustworthy because it names a **negative fixture proven to
  turn it red.** The chain of proof is enforced end to end.

No point tool gives you that, because each sees only its own slice. The value is
in the joins.

## Why it is adoptable: convention over configuration

A discipline this thorough would be unusable if you had to configure it. You
don't. The heavy lifting is convention:

- **Roles are inferred**, not authored — you *ratify* a pre-filled map one line
  at a time, and inference abstains rather than guessing wrong.
- **Known-bad is a directory**, not a config block.
- **Ratchets auto-baseline** in CI and thereafter only tighten.
- The config file exists for **exceptions only**.

`celebrimbor init` wires the commodity ladder with opinionated defaults;
`celebrimbor gate --fast` is green on a fresh repo in minutes. obligation gates are opt-in
and authored, so nothing reddens on day one. You grow into the guarantees.

Convention is also what makes it resistant to hallucination in the first place:
the rules are enforced *structurally*, in the gate, not left to a prompt, a
style guide, or a reviewer's attention on a Friday afternoon.

## What it is not

Being honest about the edges, because a tool that oversells gets disabled:

- It is **not a correctness prover.** The static checks are *necessary
  contradiction detectors* — they catch a verifier that provably cannot fail,
  not one that fails to catch a specific bug. The positive proof still lives in
  your tests; celebrimbor makes sure those tests exist and can bite.
- It does **not replace your test suite, types, or linters.** It runs them (the commodity ladder) and adds the layer that makes them mean something.
- It is **opinionated on purpose.** Omakase. If you want to configure everything,
  this is the wrong tool; the whole point is that you don't.

If that trade — strong conventions, a gate that fails closed, in exchange for
claims you can actually falsify — sounds right, [start here](../getting-started.md).
