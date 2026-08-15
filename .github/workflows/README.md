# GitHub Actions Workflows

## Layout

```
.github/workflows/
├── release-intl.yml              Intl release pipeline (AWS S3)
├── release-cn.yml                CN release pipeline (Tencent Cloud COS)
├── lint-runner-labels.yml        Label-parity check for self-hosted runners
├── shared-appcast-generation.yml       S3 appcast (Intl)
├── shared-cos-appcast-generation.yml   COS appcast (CN)
├── shared-s3-latest-json.yml          S3 latest.json (Intl)
├── shared-cos-latest-json.yml         COS latest.json (CN)
├── shared-s3-upload.yml          Upload Intl artifacts to S3
├── shared-cos-upload.yml         Upload CN artifacts to COS
├── shared-download-links.yml     Download-links summary (Intl)
└── shared-cos-download-links.yml Download-links summary (CN)
```

## Two independent release pipelines

We ship two parallel releases — one per app. Each owns a fully closed loop
(validate → build → upload → appcast → status) on its own backend so the
two never share state, never depend on each other's secrets, and never
need to know `app='intl'|'cn'`.

| Workflow | Backend | Builds | Always uploads to | Appcast lives at |
|---|---|---|---|---|
| `release-intl.yml` | AWS S3 | windows, macos amd64 / aarch64, linux | `s3://ecan-updates/...` | `s3://ecan-updates/{env}/channels/{ch}/` |
| `release-cn.yml`   | Tencent COS | same four builds | `cos://.../...` | `cos://.../{env}/channels/{ch}/` |

### Why split?

* **Isolation** — a failure or refactor in one workflow cannot break the other.
* **Clear ownership** — every named artifact is owned by exactly one pipeline.
* **Smaller diffs** — touching windows code signing never touches CN's
  COS upload template.

### Sharing code

Build steps that are 100% identical between the two workflows (env setup,
artifact upload-to-GH pattern, signing decision) intentionally live twice.
We pay N lines for the locality gain. If a third backend ever appears,
promote shared bits to `.github/actions/*` (composite actions) and let
both workflows `uses:` them.

### Inputs

Both workflows accept the same surface so operator muscle memory transfers:

* `platform` — `all | windows | macos | linux`
* `arch` — `all | amd64 | aarch64`
* `ref` — branch or tag; empty = use workflow branch
* `environment` — `production | staging | test | development | ''` (auto-detect)
* `channel` — `stable | beta | nightly | dev | ''` (auto-detect)
* `upload_artifacts` — debug mirror to GH Artifacts (`true | false`)
* `runner_group` — `github-hosted | ecan-{os}-{arch}` self-hosted runner

### Tag rules

Both pipelines apply the same:

* Semver tag (`v1.0.0`, `v1.0.0-rc.1`, `songc_v1.0.0`)
* Reserved prefixes blocked: `rc beta alpha dev nightly pre preview snapshot`
* `production/stable` requires a clean tag (no branch builds)

See `validate-tag` job in either workflow for the full ruleset.

## Per-app pipeline shape (Intl as example; CN is mirrored)

```
              ┌── build-windows ─────────────┐
validate-tag ─┤── build-macos-amd64 ─────────┤
              ├── build-macos-aarch64 ───────┤── upload-to-s3 ── generate-appcast ──┬── latest.json
              └── build-linux ───────────────┘                                       ├── download-links
                                                                                     └── final-status
```

`generate-appcast` collapses the previous 4-way split (one job per
platform×arch) into a single invocation: the underlying
`generate_appcast.py --platform all --arch all --app <x>` produces all
six feed files in one pass.

## Reusable (shared-*) workflows

* `shared-s3-upload.yml`            — upload `*-s3-transfer` artifacts to S3, requires AWS secrets.
* `shared-cos-upload.yml`           — upload `*-s3-transfer` artifacts to COS, requires Tencent secrets.
* `shared-appcast-generation.yml`   — write Sparkle appcast XML to S3 (`--app intl`).
* `shared-cos-appcast-generation.yml` — write Sparkle appcast XML to COS (`--app cn` hardcoded).
* `shared-s3-latest-json.yml`       — render S3 latest.json (Intl).
* `shared-cos-latest-json.yml`      — render COS latest.json (CN).
* `shared-download-links.yml`       — render GH Actions Summary with download URLs (Intl only).
* `shared-cos-download-links.yml`   — render GH Actions Summary with download URLs (CN).

## Local linting

```sh
actionlint .github/workflows/release-intl.yml .github/workflows/release-cn.yml
python3 build_system/scripts/runner/check_label_parity.py --repo-root .
```

The label-parity check enforces that `release-intl.yml` and
`release-cn.yml` declare the same set of `ecan-*` self-hosted runner
labels as `build_system/scripts/runner/register_runner.{sh,ps1}` and
`build_system/scripts/runner/README.md`. Drifting any of those surfaces
fails the PR check.
