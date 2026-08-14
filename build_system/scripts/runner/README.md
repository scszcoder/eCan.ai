# Self-hosted Runner Registration

These scripts register / refresh a GitHub Actions self-hosted runner for the
`eCan.ai` repository on **Linux**, **macOS**, or **Windows** hosts.

The labels written by these scripts match the matrix in
`.github/workflows/release.yml` exactly — do not change them.

| Platform        | Arch   | Runner option to pick in UI | Labels applied                                              |
| --------------- | ------ | --------------------------- | ------------------------------------------------------------ |
| Linux           | amd64  | `ecan-linux-amd64`          | `self-hosted, linux,  x64,  ecan-build`                       |
| Windows         | amd64  | `ecan-windows-amd64`        | `self-hosted, windows, x64,  ecan-build`                      |
| macOS           | amd64  | `ecan-macos-amd64`          | `self-hosted, macos,   x64,  ecan-build`                      |
| macOS           | arm64  | `ecan-macos-arm64`          | `self-hosted, macos,   arm64, ecan-build`                     |

The lowercase + `ecan-build` label is required — GitHub auto-appends
`self-hosted`, `Linux`/`macOS`/`Windows`, `X64`/`ARM64` on top of whatever
you pass, but the workflow matrix demands lowercase too. Mixing cases
(e.g. matrix says `linux`, runner only has `Linux`) silently fails to
match.

---

## One-time setup per host

1. Install `gh` CLI and run `gh auth login` with admin:org or admin:repo
   scope over the target repo (needed to mint registration tokens and verify
   labels afterwards).
2. Optional: pin the runner version with `RUNNER_VERSION` env var (default
   `2.323.0`). Match this against `actions/runner` releases.

## Generate the registration token (one-shot, ~1 hour TTL)

```bash
gh api -X POST /repos/{owner}/{eCan.ai}/actions/runners/registration-token --jq '.token'
```

Or click **New self-hosted runner** in GitHub UI → copy the token.

## Linux

```bash
# Default install dir: ~/actions-runner
GITHUB_OWNER=liuqiang GITHUB_REPO=eCan.ai \
    ./register_runner.sh "<paste-token-here>"
```

The script will:

1. Auto-detect `uname -m` → `x64`/`arm64`.
2. Download & extract `actions-runner-linux-x64-2.323.0.tar.gz` into
   `~/actions-runner` (idempotent — skips download if `config.sh` already
   exists).
3. Stop & uninstall any existing service, run
   `config.sh --unattended --replace --labels self-hosted,linux,x64,ecan-build`.
4. `sudo ./svc.sh install && sudo ./svc.sh start`.
5. Hit the GitHub REST API and print the resolved label set — fails loudly
   if the required lowercase / `ecan-build` label is missing.

Customisation:

| Env var        | Default                  | Notes                                          |
| -------------- | ------------------------ | ---------------------------------------------- |
| `GITHUB_OWNER` | (prompt)                 | auto-detected from `gh repo view` if available |
| `GITHUB_REPO`  | (prompt)                 | auto-detected from `gh repo view` if available |
| `RUNNER_NAME`  | `hostname -s`            | must be unique within the repo                 |
| `RUNNER_DIR`   | `$HOME/actions-runner`   |                                                |
| `RUNNER_VERSION` | `2.323.0`              | pin when matching a specific actions/runner tag |

To pipe the token instead of putting it on the command line:

```bash
./register_runner.sh --stdin < token.txt
```

## macOS

Identical to Linux — same script, auto-detects `Darwin` and switches to
the `actions-runner-osx-{arch}-*.tar.gz` package and the `macos` label.

```bash
GITHUB_OWNER=liuqiang GITHUB_REPO=eCan.ai \
    ./register_runner.sh "<paste-token-here>"
```

Note: the actions-runner macOS tarball for `x64` ships both as a universal
binary and an `x64` slice; the `arm64` slice only runs on Apple Silicon.
Detect via `uname -m`:

- `x86_64` → `ecan-macos-amd64`
- `arm64`  → `ecan-macos-arm64`

Service notes:

- macOS uses `launchd` via `./svc.sh install`. The service runs as the
  user that installed it; if you need it to run as a different account,
  log in as that user first.
- If you're on a Mac that's not permanently logged in (rare for build
  hosts), wrap the agent in `tmux`/`screen` instead of relying on the
  service.

## Windows

Run from an **elevated** PowerShell (Start → "PowerShell" → "Run as
administrator").

```powershell
$env:GITHUB_OWNER = "liuqiang"
$env:GITHUB_REPO  = "eCan.ai"
.\register_runner.ps1 -Token "<paste-token-here>"
```

Same flow as Linux:

1. Detects `amd64` (or `arm64`).
2. Downloads `actions-runner-win-x64-2.323.0.zip` if missing.
3. Stops & uninstalls existing service, runs
   `config.cmd --unattended --replace --labels self-hosted,windows,x64,ecan-build`.
4. Runs `svc.cmd install` + `start`, then verifies via API.

Notes:

- ARM64 Windows hosts are rare; if you hit one, flip `arch = "arm64"` —
  but verify the `actions-runner-win-arm64-*.zip` exists on
  github.com/actions/runner/releases first.
- The service installs under the name
  `actions.runner.<org>-<repo>.<runnerName>`. Check it via
  `Get-Service actions.runner.*`.

## What to expect after a successful run

- `Settings → Actions → Runners` shows your runner **online** with labels
  including `linux`/`windows`/`macos` lowercase and `ecan-build`.
- `Actions → Build & Release → Run workflow` exposes the corresponding
  `runner_group` option in the drop-down.
- Picking it in `workflow_dispatch` actually runs the job on your host —
  verify by checking that the job log shows your host's hostname and OS,
  not GitHub-hosted strings like `Runner Image: ubuntu-22.04`.

## Troubleshooting

| Symptom                                                  | Cause                                                                  | Fix                                                                  |
| -------------------------------------------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------- |
| UI drop-down doesn't show your `ecan-*` option          | Registration finished but the entry hasn't propagated to GitHub yet    | Wait up to a minute; `gh api /repos/{owner}/{repo}/actions/runners` to confirm |
| Job runs on GitHub-hosted even though labels are right   | You picked `runner_group: github-hosted` (default) instead of `ecan-*` | Re-run, choose the right drop-down                                     |
| Job first line says `Runner Image: ubuntu-22.04`         | Labels don't actually match the matrix (case mismatch)                  | Re-run the script with `--replace`; verify labels lowercase           |
| `Invalid registration token`                             | Token expired (>1 h old) or was already used                           | Mint a fresh one                                                      |
| `config.sh: command not found`                           | You're not inside `$RUNNER_DIR`                                        | `cd ~/actions-runner` first                                           |
| `--replace: unknown flag`                                | Runner < 2.298                                                          | Upgrade the runner package manually                                    |
| Service won't start on Linux                            | Missing `sudo` password prompt                                          | Make sure the user is in `sudoers` (or remove `--runasservice` and run interactively) |

## Security notes

- The registration token is **admin-scoped** for the repo. Don't commit
  it, don't echo it into logs, don't reuse it. Rotate if leaked by
  removing+re-creating the runner from GitHub UI.
- The runner itself is also admin-scoped within whichever repo it
  registers against. Don't reuse a runner for untrusted workloads.
- Keep the machine patched. The runner executes every script in jobs
  assigned to it with the host's user privileges.
