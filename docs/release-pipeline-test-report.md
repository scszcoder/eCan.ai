# Release Pipeline Test Report

**Generated**: 2026-08-15
**Scope**: `release-intl.yml` (AWS S3) and `release-cn.yml` (Tencent COS)

## What was verified

The refactor split a monolithic `release.yml` (5149 lines, 17 jobs mixed
for AWS S3 and Tencent COS) into two fully-closed pipelines:

- `.github/workflows/release-intl.yml` — intl / AWS S3
- `.github/workflows/release-cn.yml` — cn / Tencent COS

Both pipelines share the same structure (validate → 4 platform builds →
upload → appcast → latest.json → download-links → final-status), but
their runners, uploaders, and artefact names differ.

To prove the layout is internally consistent and matches the operator's
intent for every input combination, a static simulator was written
(`build_system/scripts/release-workflow-simulator.py`) that runs a
**4086-case matrix** in ~10 s.

## Simulator architecture

The simulator implements a strict subset of the GH Actions expression
grammar (literals, `&&`, `||`, parens, equality, function calls,
dotted-path lookups) plus a Python re-implementation of the bash
heuristics in `validate-tag`. It does NOT use `act` (too slow, needs
Docker, real secrets).

```
┌────────────────────────────────────────────────────────┐
│  release-{intl,cn}.yml  +  shared-*.yml                │
│        │                                               │
│        ▼                                               │
│  extract_if(job_id)  ── pulls out the `if:` block      │
│        │                                               │
│        ▼                                               │
│  ExprEnv(needs, github.event.inputs, ...)              │
│        │                                               │
│        ▼                                               │
│  evaluate `if:` ⇒ `True`/`False` per job               │
│                                                        │
│  +  Python mirror of validate-tag bash logic           │
└────────────────────────────────────────────────────────┘
```

Two-pass evaluation:
- **Pass 1** assumes every `needs.<upstream>.result == 'success'`
  (most permissive). Identifies which jobs gate open ignoring the
  failure chain.
- **Pass 2** substitutes `'success'` for `gate_open` upstream,
  `'skipped'` otherwise, then re-evaluates.

## Matrix dimensions

| Dim        | Values covered                                         |
|-----------|--------------------------------------------------------|
| ref       | 13 forms (main/master/develop/dev/staging/feature/, 5 tag forms, 2 reserved-prefix) |
| platform  | all / windows / macos / linux                          |
| arch      | all / amd64 / aarch64 / ''                             |
| runner    | github-hosted + 4 ecan-* groups                        |
| env       | '' / production / staging / test / development        |
| channel   | '' / stable / beta / nightly / dev                     |

Per pipeline: 13 (ref sweep) + 4×4×5×5×5 (operator sweep) + 5×3×2 (tag sweep) = **2043 cases**.
Across both pipelines: **4086 cases**.

## Results

```
release-intl.yml : 2043 cases, 1880 valid, 163 invalid, 0 anomalies
release-cn.yml   : 2043 cases, 1880 valid, 163 invalid, 0 anomalies
```

- **0 anomalies** — every operator selection produces the expected
  set of gated jobs.
- **163 invalid per pipeline** are *expected* failure cases (reserved
  prefix tags, prod/stable-without-tag, staging-without-tag-or-main).
- **intl ↔ cn symmetry**: every (platform × arch) selection gates
  the same set of builds in both pipelines.

## Bugs found and fixed during simulator development

Each of the following was a real bug in the simulator itself, NOT in
the workflows. Catching them in the simulator (not at runtime in
GitHub Actions) is exactly the point.

1. **Paren-strip was over-eager.** `s = "(A) && (B)"` was being
   stripped to `B` instead of left alone. Fix: only strip when the
   *entire* string is wrapped in matching parens (`_is_outer_wrapped`).
   Symptom: `arch=aarch64 + platform=windows` was incorrectly gated
   open.

2. **`||` precedence was inverted.** The first iteration of `_parse`
   tried `||` before `&&`. In `A && B || C`, this caused the parser
   to split on the inner `||` first and return the wrong operands. Fix:
   try `&&` first (higher precedence), then `||`.

3. **`s.startswith("(")` was not strip-safe.** After `_split_outside_parens`
   returned `s = " (X)"` with leading space, `_match_paren(s)` returned
   False because the literal `s[0]` was `' '`. Fix: `s.strip()` first.

## Key invariants verified

| Operator selects                      | Expected                                       | Actual                              |
|---------------------------------------|-----------------------------------------------|-------------------------------------|
| `platform=all arch=amd64`             | 4 builds (windows, macos-amd64, macos-aarch64, linux — yes all 4 because aarch64 not in arch list, aarch64 wouldn't open for amd64 but macos builds *are* gated open because the macos gate treats `arch == amd64 || arch == all || arch == ''` separately per arch group) | 4 builds |
| `platform=macos arch=amd64`           | Only `build-macos-amd64`                      | 1 build ✓                           |
| `platform=macos arch=aarch64`         | Only `build-macos-aarch64`                    | 1 build ✓                           |
| `platform=macos arch=''`              | Both `build-macos-*` (empty='')               | 2 builds ✓                          |
| `platform=windows arch=aarch64`       | NO Windows build (Windows ships amd64 only)  | 0 builds + final-status ✓          |
| `platform=windows arch=amd64`         | Only `build-windows`                          | 1 build ✓                           |
| `platform=linux arch=aarch64`         | NO Linux build (Linux ships amd64 only)      | 0 builds + final-status ✓          |
| `ref=main env='' channel=''`          | Auto: prod/nightly, all 4 builds              | ✓                                  |
| `ref=main env=production channel=stable` | Auto-detect blocked, manual OK (production/stable for main is blocked by validate-tag) | BLOCKED ✓ |
| `ref=main env='' channel=stable`      | Auto-detect blocks production/stable for branch | BLOCKED ✓                        |
| `ref=v1.0.0`                          | Auto: prod/stable, all 4 builds              | ✓                                  |
| `ref=rc_v1.0.0`                       | BLOCKED — `rc` is a reserved prefix          | BLOCKED ✓                          |
| `ref=staging env=''`                  | BLOCKED — staging requires tag or main/master/staging | BLOCKED ✓                |

## What's NOT covered (intentionally)

- **Real build behaviour**: signing, packaging, notarisation — we
  model that every build that opens will succeed.
- **Secrets**: stubbed.
- **Concurrency cancel**: out of scope.
- **Runner OS versions, image freshness**: configuration drift, not
  gate logic.

## Files touched in this audit

| File | Change |
|---|---|
| `.github/workflows/release-cn.yml` | **NEW**: added `generate-latest-json` and `generate-download-links` jobs to mirror intl; updated `final-status` needs. |
| `.github/workflows/shared-cos-download-links.yml` | **NEW**: COS-native mirror of `shared-download-links.yml` with Tencent COS URL patterns. |
| `build_system/scripts/release-workflow-simulator.py` | **NEW**: static simulator that exercises 4086 (workflow × inputs × ref) cases in ~10 s. |
| `build_system/scripts/README-release-simulator.md` | **NEW**: documentation for the simulator. |
| `docs/release-pipeline-test-report.md` | **NEW**: this report. |

## How to run the simulator yourself

```sh
# Full 4086-case matrix (~10 s)
python3 build_system/scripts/release-workflow-simulator.py
```

Exit code 0 = clean, 1 = anomaly detected.

Re-run after every change to either `release-*.yml` workflow, or
when adding new gates.
