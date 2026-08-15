# release-workflow-simulator.py

A static / dry-run evaluator for the new split release pipelines
(`release-intl.yml` and `release-cn.yml`).

## What it does

For every (workflow × inputs × ref) combination in a 4086-case test matrix,
the script:

1. **Mirrors** the bash heuristics in `validate-tag` (semver detection,
   reserved-prefix rejection, env auto-detect, channel auto-detect,
   production/stable + staging gate checks) and decides whether the
   release is allowed at all.

2. **Parses** each job's `if:` expression (a subset of GH Actions
   expressions — `&&`, `||`, parens, comparison, function calls,
   dotted-path lookups) and evaluates it against the simulated
   environment.

3. **Reports** which jobs would gate-open and which would skip —
   surfacing any mismatch where the operator asked for a build but no
   build fired (genuine anomaly) versus any expected zero-build case
   (e.g. `platform=windows arch=aarch64` — Windows only ships amd64).

4. **Cross-checks symmetry** between `release-intl.yml` and
   `release-cn.yml`: every (platform × arch) selection must gate the
   same set of builds in both pipelines; only the upload backend
   (S3 vs COS) and the artifact names should differ.

## Running

```sh
python3 build_system/scripts/release-workflow-simulator.py
```

Exits 0 on clean, 1 if any genuine anomaly was found. Runtime is
~10 s on a developer laptop for the full 4086-case matrix.

## How it works (one paragraph)

The script is **deliberately not `act`**. Running real GitHub Actions
locally needs Docker-in-Docker, real secrets, signing hardware, and
20 minutes per case. For our purposes — proving the new layout honours
every operator selection — a static evaluator that *understands* the
gate expressions and the bash heuristics is enough. It runs in
<100 ms per case and gives one definitive answer per case.

The evaluator implements a strict subset of the GH Actions expression
grammar: literals, `&&`, `||`, parens, equality, function calls
(`always`, `success`, `failure`, `cancelled`, `contains`, `fromJSON`),
and dotted-path lookups. Anything not in this subset is conservative
and returns empty-string (the GH Actions default for missing keys).

## What the matrix covers

| Dimension | Values covered |
|-----------|---------------|
| ref       | `main`, `master`, `develop`, `dev`, `staging`, `feature/foo`, semver tags (`v1.0.0`, `v1.0.0-rc.1`, `v1.0.0-beta.1`, `v1.0.0-alpha.1`), user-prefixed tags (`songc_v0.1.0`), reserved-prefix tags (`rc_v1.0.0`, `beta_v1.0.0`) |
| platform  | `all`, `windows`, `macos`, `linux` |
| arch      | `all`, `amd64`, `aarch64`, `''` (empty) |
| runner    | `github-hosted`, `ecan-windows-amd64`, `ecan-macos-amd64`, `ecan-macos-arm64`, `ecan-linux-amd64` |
| env       | `''`, `production`, `staging`, `test`, `development` |
| channel   | `''`, `stable`, `beta`, `nightly`, `dev` |

Total: 2043 cases per pipeline = 4086 across both. With `main` as the
base ref for the operator-input sweep and a tag sweep covering each
of the five tag forms.

## What is NOT covered

- **Real build behaviour**: signing, packaging, notarisation,
  upload — these are exercised only by their downstream job
  (`shared-{s3,cos}-upload.yml`) and the simulator assumes success
  whenever a build's gate opens.
- **Secrets**: all secrets are stubbed (`''`); the simulator only
  needs to evaluate `inputs.*`, not the actual credentials.
- **Concurrency cancel**: the simulator runs each case in isolation.
  Real-world `cancel-in-progress: true` will cancel earlier runs of
  the same `group` key — out of scope here.
- **Action-local node version**, OS image version, runner registration
  changes — these are configuration drift, not gate logic.

## Adding new gates

When you add an `if:` to a new job in either workflow:

1. Re-run the simulator to confirm no anomaly is introduced.
2. If the new gate expression uses a function not in the supported
   subset (e.g. `toJson`, `env`, `matrix.*`), add a stub in
   `ExprEnv._call` and a `RUNNER_PLATFORM` mapping if needed.
3. Update the "incompatible" combinations table in `report_anomalies`
   if your change adds a new genuinely-impossible (platform, arch)
   pair.

## Why two passes?

The simulator does a **two-pass** evaluation:

1. **Pass 1 — gate pre-scan**: assume every job's referenced
   `needs.<upstream>.result` is `success` (the most permissive
   reading). Determine which jobs *would* open ignoring the
   transitive failure chain.
2. **Pass 2 — final state**: replace each `needs.<upstream>.result`
   with `'success'` if pass 1 gated it open, else `'skipped'`,
   then re-evaluate.

This is a fixed-point iteration; for our gates (which are DAGs, not
cycles) one extra pass is enough. The benefit: we can detect
"appears to gate open but is blocked by a skipped upstream" cases
without simulating real failure modes.
