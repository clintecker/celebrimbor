# celebrimbor on celebrimbor

A quality tool that cannot pass its own gate is asking you to do something it
will not. So celebrimbor runs its full obligation engine — every obligation gate
it has — against its own source, and ships green. This page is the receipt: what
that took, what it caught, and where it is honestly still incomplete.

Nothing here is a special case. The map, the ledgers, and the config are the
same files any adopter writes, in the same places, checked by the same code.

## The numbers

Run against celebrimbor's own `src/`:

| Measure | Count |
|---|---|
| Modules classified | 57 |
| Public callables accounted for | 242 |
| Surface-map rows, ratified and pinned | 49 |
| Producers proved through a real verifier | 14 |
| Producers admitted `pending`, with a date | 1 |
| Invariants recorded, all critical, each with a negative proof | 8 |
| Modules imported clean, no import-time effects | 57 |
| Gates green | 19 / 20 |
| Gates skipped | 1 (coverage — its baseline is taken in CI) |

Every one of the 242 callables carries a ratified role, and every role is
pinned to the shape of the code it was ratified against. Change the character of
any of them — make a parser open a socket, make a pure helper read the clock —
and its row reverts to un-ratified and the gate goes red until a human looks
again.

## What turning it on caught

Self-hosting is only worth anything if it finds things. It found three, and
none were cosmetic.

### A bug in the tool itself

A shape-pin is a `blake2s` hex digest. Roughly one digest in two hundred lands
in the characters `0`–`9` only. Written to YAML unquoted, such a pin reads back
as an **integer**, and the loader — which demands a string — then refused the
entire map. celebrimbor pointed at itself hit exactly this: one of 49 modules
pinned to an all-digit hash, and the whole obligation engine went dark with a
fail-closed refusal.

```mermaid
flowchart LR
    A["pin = all-digit<br/>blake2s hex<br/>e.g. 775376418253"] --> B["written to YAML<br/><em>unquoted</em>"]
    B --> C["read back<br/>as an <b>int</b>"]
    C --> D["loader demands<br/>a string"]
    D --> E(["whole map REFUSED<br/>— all of Tier 1 dark"])
```

That is the gate working — it refused rather than guessing — but it was still a
bug. The fix quotes pins on write and coerces the legacy form on read, and it
ships with [its own falsifier](../gate/fixtures.md): a round-trip test that
reddens if a numeric pin is ever dropped again.

### A dependency-injection violation

celebrimbor's thesis is *inject the world* — time, randomness, the filesystem —
so a test can substitute it. The capability gate, run on celebrimbor, found the
runner reaching straight for the ambient clock (`time.perf_counter`) to measure
how long a check took. The honest fix was not to reclassify the runner; it was
to do what the tool tells everyone else to do: take the clock as a parameter.
It now does, defaulted to the real clock, so its timing is a seam a test can
pin.

### The role a name promised but the map did not

The naming gate caught four `render_*` functions whose names decode to
`producer` — a name promising an artifact — while the map assigned them the
weaker `parser`. The map demanded less proof than the name advertised. Resolving
it meant classifying them as what they are (producers of serialized text) and
giving each a ledger entry naming the verifier that reads their output back.

## Where it is honestly incomplete

One producer — `scaffold:run_init`, which writes tool configs and the known-bad
directory — has no gate verifier that inspects a scaffold. It is exercised
end-to-end by the acceptance suite, but that is a test, not a role-classified
verifier, so the producer ledger cannot cite it.

Rather than invent a verifier or quietly drop the producer, it sits on the
ledger's `pending` list with a reason and a review date. That is the shrinking
allowlist the design asks for: a debt recorded in the open, with a deadline, not
a gap papered over. When the date passes, the gate reddens until someone writes
the verifier or re-justifies the wait.

This is the point of showing the whole picture. "19 of 20 green, one honest
pending, one CI-only skip" is a truthful state. "20 of 20, trust us" would be
the estimating behavior the tool exists to refuse.

## What it does not yet do to itself

- **Coverage and mutation** ratchets take their baselines in CI, the pinned
  environment, so a local run does not read a floor higher than CI will enforce.
  Locally they skip; in CI they baseline and then bite.
- **The impact gate** needs a diff base. In a pull request it resolves the merge
  base automatically; a local full run without `--diff-base` refuses rather than
  assuming nothing changed.

Both are the same fail-closed behavior an adopter sees. celebrimbor does not
exempt itself from them; it meets them exactly where you would.

## Reading it yourself

Everything above is in the repository, in plain files:

- `.celebrimbor/surfaces.yaml` — the 49 ratified, pinned rows
- `.celebrimbor/producers.yaml` — the 14 proofs and the 1 pending
- `.celebrimbor/invariants.yaml` — the 8 promises celebrimbor makes about itself
- `pyproject.toml` `[tool.celebrimbor]` — `import_check = true` and nothing else

```bash
git clone https://github.com/clintecker/celebrimbor
cd celebrimbor && pip install -e ".[dev]"
celebrimbor gate --diff-base HEAD      # the full obligation engine, on itself
```

If it is ever not green, that is a bug — [report it](https://github.com/clintecker/celebrimbor/issues).
