#!/usr/bin/env bash
# register_runner.sh — Register/refresh a GitHub Actions self-hosted runner for eCan.ai
#
# Supports:  Linux (x64)  +  macOS (x64 | aarch64)
# Behavior:  Detects OS/arch, downloads the matching actions/runner release,
#            configures it with --unattended + --replace (idempotent), installs
#            the system service, and verifies the labels via the GitHub REST API.
#
# Usage:
#   ./register_runner.sh <registration-token>
#
#   # OR pipe the token to avoid shell history leak:
#   ./register_runner.sh --stdin   < token.txt
#   cat token.txt | ./register_runner.sh --stdin
#
# Required env (or you'll be prompted):
#   GITHUB_OWNER      — e.g. "liuqiang"
#   GITHUB_REPO       — e.g. "eCan.ai"
#   RUNNER_NAME       — display name (default: hostname)
#
# The registration token is *one-shot* and valid for ~1 hour. Generate it from:
#   gh api -X POST /repos/$OWNER/$REPO/actions/runners/registration-token --jq '.token'
# Or: GitHub UI → Settings → Actions → Runners → "New self-hosted runner"

set -euo pipefail

# ---------------------------------------------------------------------------
# Config (edit here, or export env before invoking)
# ---------------------------------------------------------------------------
GITHUB_OWNER="${GITHUB_OWNER:-}"
GITHUB_REPO="${GITHUB_REPO:-}"
RUNNER_NAME="${RUNNER_NAME:-$(hostname -s 2>/dev/null || hostname)}"
RUNNER_VERSION="${RUNNER_VERSION:-2.336.0}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
WORK_DIR="${WORK_DIR:-_work}"

# Labels are frozen by .github/workflows/release.yml matrix. Do not change.
#   ecan-linux-amd64   -> self-hosted,linux,x64,ecan-build
#   ecan-macos-amd64   -> self-hosted,macos,x64,ecan-build
#   ecan-macos-aarch64  -> self-hosted,macos,aarch64,ecan-build
# Each platform/arch pair needs a matching custom `ecan-build` label.

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { printf '\033[1;34m[register]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

require() {
    command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
USE_STDIN=0
TOKEN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --stdin)  USE_STDIN=1; shift ;;
        --help|-h)
            sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        -*)  fail "unknown flag: $1" ;;
        *)   TOKEN="$1"; shift ;;
    esac
done

if [[ "$USE_STDIN" == "1" ]]; then
    TOKEN="$(cat)"
fi

[[ -n "$TOKEN" ]] || fail "no token provided. Pass it as arg or via --stdin."

# ---------------------------------------------------------------------------
# Detect OS / arch
# ---------------------------------------------------------------------------
OS_RAW="$(uname -s)"
ARCH_RAW="$(uname -m)"

case "$OS_RAW" in
    Linux)
        PLATFORM_OS="linux"
        LABEL_OS="linux"
        case "$ARCH_RAW" in
            x86_64|amd64) PLATFORM_ARCH="x64" ;;
            aarch64|arm64) PLATFORM_ARCH="aarch64" ;;
            *) fail "unsupported Linux arch: $ARCH_RAW" ;;
        esac
        RUNNER_PKG="actions-runner-${PLATFORM_OS}-${PLATFORM_ARCH}-${RUNNER_VERSION}.tar.gz"
        [[ "$PLATFORM_OS" == "linux" ]] && PLATFORM_OS_LONG="Linux"  # for label
        ;;
    Darwin)
        PLATFORM_OS="osx"        # tarball name: actions-runner-osx-x64-*.tar.gz
        LABEL_OS="macos"          # GitHub Actions label: self-hosted,macos,...
        case "$ARCH_RAW" in
            x86_64) PLATFORM_ARCH="x64" ;;
            aarch64)  PLATFORM_ARCH="aarch64" ;;
            *) fail "unsupported macOS arch: $ARCH_RAW" ;;
        esac
        RUNNER_PKG="actions-runner-${PLATFORM_OS}-${PLATFORM_ARCH}-${RUNNER_VERSION}.tar.gz"
        PLATFORM_OS_LONG="macOS"
        ;;
    *) fail "unsupported OS: $OS_RAW. Use register_runner.ps1 for Windows." ;;
esac

# Map runner labels (lowercase, comma-separated, matching workflow matrix).
# Note: LABEL_OS decouples the label name from the tarball PLATFORM_OS
# (which is "osx" for macOS runners because GitHub's tarball is named
# actions-runner-osx-x64-*.tar.gz).
LABELS="self-hosted,${LABEL_OS},${PLATFORM_ARCH},ecan-build"

log "Detected: ${PLATFORM_OS_LONG} ${PLATFORM_ARCH} (raw: ${OS_RAW} ${ARCH_RAW})"
log "Labels:   ${LABELS}"

# ---------------------------------------------------------------------------
# Resolve GitHub owner/repo
# ---------------------------------------------------------------------------
if [[ -z "$GITHUB_OWNER" || -z "$GITHUB_REPO" ]]; then
    warn "GITHUB_OWNER / GITHUB_REPO not set; trying 'gh' CLI..."
    if command -v gh >/dev/null 2>&1; then
        REPO_INFO="$(gh repo view --json owner,name 2>/dev/null || true)"
        if [[ -n "$REPO_INFO" ]]; then
            GITHUB_OWNER="$(printf '%s' "$REPO_INFO" | sed -n 's/.*"login": *"\([^"]*\)".*/\1/p' | head -1)"
            GITHUB_REPO="$(printf '%s' "$REPO_INFO" | sed -n 's/.*"name": *"\([^"]*\)".*/\1/p' | head -1)"
        fi
    fi
fi

if [[ -z "$GITHUB_OWNER" || -z "$GITHUB_REPO" ]]; then
    printf '\nGitHub owner/repo required. Examples:\n'
    printf '  GITHUB_OWNER=liuqiang GITHUB_REPO=eCan.ai ./register_runner.sh <token>\n'
    printf '  export GITHUB_OWNER=liuqiang\nexport GITHUB_REPO=eCan.ai\n\n'
    read -r -p "Owner: " GITHUB_OWNER
    read -r -p "Repo:  " GITHUB_REPO
fi

[[ -n "$GITHUB_OWNER" && -n "$GITHUB_REPO" ]] || fail "owner/repo cannot be empty"
REPO_URL="https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}"

log "Repo URL: ${REPO_URL}"
log "Runner:   ${RUNNER_NAME}"

# ---------------------------------------------------------------------------
# Pre-flight: dependencies
# ---------------------------------------------------------------------------
require curl
require tar
case "$PLATFORM_OS" in
    linux)
        require systemctl  # service install needs systemd
        ;;
esac

# ---------------------------------------------------------------------------
# Download / refresh runner package
# ---------------------------------------------------------------------------
if [[ ! -d "$RUNNER_DIR" ]]; then
    log "Creating runner directory: $RUNNER_DIR"
    mkdir -p "$RUNNER_DIR"
fi
cd "$RUNNER_DIR"

if [[ ! -x "./config.sh" ]]; then
    log "Downloading actions-runner v${RUNNER_VERSION} (${RUNNER_PKG})"
    DL_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_PKG}"
    if ! curl -fL --retry 3 -o "${RUNNER_PKG}.tmp" "$DL_URL"; then
        fail "download failed. Check version/arch at https://github.com/actions/runner/releases"
    fi
    tar xzf "${RUNNER_PKG}.tmp"
    rm -f "${RUNNER_PKG}.tmp"
else
    log "Existing runner found at $RUNNER_DIR (skipping download)"
fi

# ---------------------------------------------------------------------------
# Stop existing service (if any) so --replace can update labels
# ---------------------------------------------------------------------------
if [[ -x "./svc.sh" ]]; then
    if sudo -n true 2>/dev/null; then
        log "Stopping existing service (if running)..."
        sudo ./svc.sh stop    2>/dev/null || true
        sudo ./svc.sh uninstall 2>/dev/null || true
    else
        warn "sudo requires password; will be prompted during service (un)install"
        sudo ./svc.sh stop    2>/dev/null || true
        sudo ./svc.sh uninstall 2>/dev/null || true
    fi
fi

# ---------------------------------------------------------------------------
# Configure (unattended, replace)
# ---------------------------------------------------------------------------
log "Configuring runner (--unattended --replace)"
./config.sh \
    --unattended \
    --replace \
    --url "$REPO_URL" \
    --token "$TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$LABELS" \
    --work "$WORK_DIR" \
    --runasservice 2>/dev/null || true
# `--runasservice` is silently ignored on macOS / when not root.

# ---------------------------------------------------------------------------
# Install + start service
# ---------------------------------------------------------------------------
log "Installing runner as a system service..."
sudo ./svc.sh install
sudo ./svc.sh start
sleep 3

log "Service status:"
sudo ./svc.sh status || true

# ---------------------------------------------------------------------------
# Verify labels via GitHub REST API
# ---------------------------------------------------------------------------
verify_labels() {
    local api="https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runners"
    local auth_header=()
    if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
        auth_header=(-H "Authorization: Bearer $(gh auth token 2>/dev/null)")
    fi

    local body
    body="$(curl -fsSL "${auth_header[@]}" "$api" || true)"
    if [[ -z "$body" ]]; then
        warn "could not query GitHub API to verify labels (skipping). Check UI manually."
        return 0
    fi

    echo ""
    log "Verifying labels via GitHub API..."
    python3 - "$RUNNER_NAME" "$LABELS" <<PY "$body"
import json, sys

body = json.loads(sys.stdin.read())
target_name = sys.argv[1]
expected = set(s.strip() for s in sys.argv[2].split(","))

runners = body.get("runners", [])
match = next((r for r in runners if r["name"] == target_name), None)
if not match:
    print(f"  ✗ runner '{target_name}' not found in {len(runners)} registered runners")
    print(f"    registered names: {[r['name'] for r in runners]}")
    sys.exit(2)

actual = set(l["name"] for l in match["labels"])
missing = expected - actual
extras  = actual - expected

print(f"  ✓ Found:  {match['name']}  (status={match['status']}, busy={match['busy']})")
print(f"    OS={match['os']}  arch={match['architecture']}")
print(f"    Labels ({len(actual)}): {sorted(actual)}")
if missing:
    print(f"  ✗ MISSING required labels: {sorted(missing)}")
    sys.exit(3)
else:
    print(f"  ✓ All required labels present: {sorted(expected)}")

if extras:
    print(f"    (additional labels: {sorted(extras)})")
PY
}

verify_labels
rc=$?

cat <<EOF

────────────────────────────────────────────────────────────────────────────
Done.

  Runner name : ${RUNNER_NAME}
  Repo        : ${REPO_URL}
  Labels      : ${LABELS}
  Next step   : In the 'Run workflow' UI, pick
                runner_group = ecan-${PLATFORM_OS}-${PLATFORM_ARCH}
                (e.g. ecan-linux-amd64 / ecan-macos-aarch64)

  Logs        : sudo journalctl -u actions.runner.${GITHUB_REPO//\//-}.${RUNNER_NAME} -f
────────────────────────────────────────────────────────────────────────────
EOF

exit $rc