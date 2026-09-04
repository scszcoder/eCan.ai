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

* `shared-s3-upload.yml`            — fallback upload of `*-installer` artifacts to S3. Only
  runs when at least one build job did NOT direct-upload (see "Distribution" below).
  Requires AWS secrets.
* `shared-cos-upload.yml`           — fallback upload of `*-installer` artifacts to COS.
  Same skip-rule as the S3 variant. Requires Tencent secrets.
* `shared-appcast-generation.yml`   — write Sparkle appcast XML to S3 (`--app intl`).
* `shared-cos-appcast-generation.yml` — write Sparkle appcast XML to COS (`--app cn` hardcoded).
* `shared-s3-latest-json.yml`       — render S3 latest.json (Intl).
* `shared-cos-latest-json.yml`      — render COS latest.json (CN).
* `shared-download-links.yml`       — render GH Actions Summary with download URLs (Intl only).
* `shared-cos-download-links.yml`   — render GH Actions Summary with download URLs (CN).

## Distribution: direct-upload fast path vs GitHub-Artifact-Store fallback

Each build job in both pipelines does one of two things with the installer
it just built:

* **Direct upload** (self-hosted runners) — the build job calls
  `build_system/scripts/upload_to_{cos,s3}.py` with
  `--dist-dir artifacts` and pushes the installer straight to COS/S3.
  This skips the public-internet round-trip through GitHub's artifact
  blob store, cutting the installer's CI-to-CDN time from ~20 min to
  ~2 min for CN self-hosted runners and from ~10 min to ~3 min
  elsewhere. Each build job publishes a `cos-uploaded` / `s3-uploaded`
  output that records whether the direct upload succeeded.
* **GitHub-Artifact-Store fallback** (GitHub-hosted runners) — the
  build job uploads the installer as a `*-installer` artifact, and
  the shared-*-upload job downloads it back and re-uploads to COS/S3.
  This path is unchanged from the original pipeline and remains the
  default for `runner_group == github-hosted`.

The `upload-to-{cos,s3}` gate is the seam between the two paths. It
runs only when at least one succeeded build job did NOT direct-upload
(`needs.<job>.outputs.{cos,s3}-uploaded != 'true'`); when every
succeeded build job direct-uploaded, the slow fallback is skipped
entirely and the in-place artifacts are picked up directly by the
downstream `generate-appcast` / `generate-download-links` / `final-status`
jobs.

The `-transfer` artifact upload is also still produced on GitHub-hosted
runners (the upload steps' `if:` excludes self-hosted runners) so the
artifact store remains a debug-mirror surface for the
`upload_artifacts == 'true'` opt-in.

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
