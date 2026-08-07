# Ledgers

A ledger is a written record you keep next to your code — a list of promises and
the code that keeps each one. Three of celebrimbor's proving checks (the deeper
checks that make your code prove itself) read these records and hold them to the
code. They don't just read each line: they confirm every name in the record
points at something real, and they go red the moment the record and the code
drift apart. A record that can quietly fall out of step with the code is a record
nobody can trust.

## Producers — the no-blind-verifier gate

`celebrimbor.producers` enforces one rule: a function that builds something
can't be trusted on its own word. A `producer` is a function whose job is to
build an artifact — a file, a report, a bundle. The only thing that makes that
artifact trustworthy is a `verifier` (a function whose job is to check something)
that would turn red if the artifact were wrong. So every producer has to name, on
the record:

- the `verifier` that inspects its artifact, and
- a `negative_fixture` — a kept example of a bad artifact, with a test proving
  that verifier turns red on it.

```yaml
# .celebrimbor/producers.yaml
version: 1
producers:
  myapp.render:
    verifier: myapp.verify:verify_summary
    negative_fixture: tests/negative/test_render.py::test_empty_summary_caught
pending:
  myapp.export:
    reason: verifier not written yet
    review_by: 2026-09-01
```

The check confirms the named verifier is real code that you've actually
classified as a verifier, and that the fixture exists. A producer you haven't got
to yet can sit in `pending` — but out in the open, with a review date, on a list
that expires.

```mermaid
flowchart TD
    P["a producer<br/>(makes an artifact)"] --> Q{named in the<br/>ledger?}
    Q -->|"no · not pending"| R1([red])
    Q -->|"pending (dated)"| OK1([allowed — for now])
    Q -->|yes| V{verifier resolves<br/>AND is classified<br/>a verifier?}
    V -->|no| R2([red])
    V -->|yes| F{negative fixture<br/>exists?}
    F -->|no| R3([red])
    F -->|yes| G([proved])
```

!!! note "Override granularity"
    celebrimbor works out which functions are producers from the module's default
    role *plus* any per-function overrides — so a lone `producer` you flag by hand
    inside an otherwise `pure` module still needs its entry. Miss that, and the
    cheapest way to slip an unchecked artifact past the gate would be a one-line
    override.

## Invariants

`celebrimbor.invariants` checks a record of the promises your system makes — the
things that must always stay true, whatever else changes. We call each one an
*invariant*:

```yaml
# .celebrimbor/invariants.yaml
version: 1
invariants:
  order-has-customer:
    statement: every order references an existing customer
    enforced_by: myapp.orders:validate_order
    critical: true
    negative_proof:                       # one, or several — each is checked
      - tests/negative/test_orders.py::test_orphan_order_rejected
      - tests/negative/test_orders.py::test_deleted_customer_rejected
    limitations:                          # what the promise knowingly does NOT cover
      - soft-deleted-customers
  slug-is-unique:
    statement: no two posts share a slug
    enforced_by: myapp.posts:check_slug_unique
```

Every `enforced_by` name has to point at real code, and every `critical` promise
has to keep a real `negative_proof` — a kept example of the promise being broken,
with a test that catches it. If the code that enforces a promise is renamed or
deleted, the check goes red: a promise nobody enforces is not a promise.

`negative_proof` can be a single test or a **list** of them — a promise can be
caught being broken in several independent ways, and each named proof has to exist
(a proof you named and then deleted is drift, just like a renamed enforcer).
`limitations` records the cases the promise knowingly does *not* cover — debt
you've written down and can review — and, with
[`markers_cite_limitations`](fixtures.md#citing-limitations), it becomes the list
of allowed excuses a suppressed test must point to.

This is the producer record, generalized: a producer record is just an invariant
record narrowed to a single promise — "the artifact is correct."

!!! tip "Docs that cannot lie"
    The invariant record renders to plain, readable markdown — a living list of
    the promises your system makes. It can't drift into fiction, because the gate
    has already checked every line of it against the code. Documentation that a
    gate keeps honest is the only kind that stays true.

## The impact gate

`celebrimbor.impact` reads the invariant record against a git diff — not the whole
tree, but only what *changed*. This is the change-impact check, and it asks one
question about your edit: when you touch a module that decides or vouches for
something — a verifier, producer, parser, normalizer, or adapter — is any recorded
promise watching over it?

```mermaid
flowchart TD
    D{"can the diff<br/>be computed?"} -->|"no"| REF([refused — red])
    D -->|yes| M{"each changed<br/>module's role"}
    M -->|"pure / presenter"| OK([no obligation])
    M -->|"policy-bearing"| I{"named by an<br/>invariant?"}
    I -->|yes| OK
    I -->|no| RED(["red — a guarantee<br/>changed unwatched"])
```

A changed [policy-role](../concepts/roles.md#policy-roles-and-the-impact-gate)
module — one whose job is to decide or vouch for something — with no invariant
naming it as an enforcer is the gap, and it turns the check red. By default those
roles are `parser`, `normalizer`, `verifier`, `producer`, `adapter`, and
`orchestrator`; set `policy_roles` in config to match the set your project already
uses. What this catches is a guarantee quietly changed in a spot where no promise
was watching.

!!! important "Fail closed on an unknowable diff"
    If celebrimbor can't work out which files changed — not a repo, git absent, a
    base it can't resolve — the gate **refuses** rather than guessing: it fails
    closed. It won't treat "I couldn't tell what changed" as "nothing changed,"
    because that guess is exactly what would let a policy change slip through on
    the one run where git was having a bad day.
