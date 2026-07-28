# Adopting an existing app

Celebrimbor is designed to be adopted incrementally. Tier 0 goes green in
minutes; Tier 1 you grow into. This guide walks a real, established codebase
through the whole path.

## 1. Tier 0 first

```bash
pip install "celebrimbor[tier0]"
celebrimbor init
celebrimbor gate --fast
```

On an established repo, expect the structure gates to find real issues — long
functions, mixed-domain modules. You have two honest responses to each: fix it,
or, if it is pre-existing debt you will address incrementally, note it. Do not
raise the limits globally to make it quiet; that discards the signal for
everyone.

Commit the config `init` wrote. Wire `celebrimbor gate` into CI (see
[Getting started](../getting-started.md#use-it-from-ci)).

## 2. Generate and ratify the surface map

```bash
celebrimbor init --surfaces
```

Inference pre-fills the rows it is confident about and abstains on the rest.
Open `.celebrimbor/surfaces.yaml` and review it. Every row is `inferred` and
**red** until you ratify it. For each module:

- If the inferred role is right, leave it — you will ratify in bulk next.
- If a single callable differs, add a one-line override.
- If inference abstained (no row), add the module by hand with `status:
  ratified`. The completeness gate names the exact modules that need this.

Then ratify — this also pins each row to the current code:

```bash
celebrimbor ratify --all       # after you've reviewed; or name modules individually
```

Now `gate --fast` runs completeness, naming, evidence, and capabilities. The
evidence and capability gates will surface real findings: a `verifier` that can't
fail, an `adapter` label on a pure helper, a `pure` function that reaches for the
clock. Each is a one-line override, a reclassification, or a genuine fix.

## 3. Ledgers (PR stage)

If you have producers, write the producer ledger — each names its verifier and a
negative fixture. Anything not ready goes in `pending:` with a review date.

If your system makes promises worth naming, write the invariant ledger. Start
with the critical ones; each needs a `negative_proof`. Once invariants exist, the
impact gate begins governing changes to your policy-role modules.

```bash
celebrimbor gate          # PR stage: + coverage ratchet, invariants, impact
```

The coverage ratchet auto-baselines on its first run *in CI* and only rises
after.

## 4. Mutation (release stage)

```bash
celebrimbor gate --full   # + mutation
```

## Migrating from an existing inline harness

If your project already has a hand-rolled quality harness (its own surface map,
invariants, ratchets), the conversion is mechanical:

- **Keep your data where it lives.** `[tool.celebrimbor.paths]` points celebrimbor
  at existing files — you do not have to reorganize your repo.

    ```toml
    [tool.celebrimbor.paths]
    surfaces = "quality/surfaces.yaml"
    invariants = "quality/invariants.yaml"
    coverage_baseline = "quality/coverage-baseline.yaml"
    ```

- **Extra fields are tolerated.** celebrimbor's invariant loader ignores fields it
  does not know (owner, risk, ticket links), so your annotations survive.
- **Adapt your checks to the seam.** An existing zero-argument `check_foo()` that
  raises on failure becomes a celebrimbor check with a thin wrapper — see
  [Writing custom checks](custom-checks.md). They then run in the same registry
  as the builtins, under the same completeness guarantee.
