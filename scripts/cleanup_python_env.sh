#!/usr/bin/env bash
# Clean up PYTHON* environment variables from current session, launchctl (GUI env), and shell rc files (persistent)
# macOS-focused; safe, idempotent, with backups.
#
# Usage:
#   bash scripts/cleanup_python_env.sh           # perform cleanup
#   DRY_RUN=1 bash scripts/cleanup_python_env.sh # show what would change
#
set -euo pipefail

is_dry_run() { [[ "${DRY_RUN:-0}" != "0" ]]; }

echo_hdr() { printf "\n==== %s ====\n" "$*"; }
echo_act() { printf "[ACTION] %s\n" "$*"; }
echo_ok()  { printf "[ OK ] %s\n" "$*"; }
echo_skip(){ printf "[SKIP] %s\n" "$*"; }
echo_warn(){ printf "[WARN] %s\n" "$*"; }

ts() { date +%Y%m%d%H%M%S; }

VARS=(
  PYTHONHOME
  PYTHONPATH
  PYTHONNOUSERSITE
  PYTHONUSERBASE
  PYTHONDONTWRITEBYTECODE
  PYTHONSTARTUP
)

# 1) Show current session variables
show_current() {
  echo_hdr "Current session PYTHON* variables"
  env | grep -E '^PYTHON' || echo "(none)"
}

# 2) Unset from current session (if sourced). When executed as a script, this won't persist for parent shell.
unset_current() {
  echo_hdr "Unsetting PYTHON* in current shell session (best effort)"
  local any=0
  for v in "${VARS[@]}"; do
    if env | grep -q "^${v}="; then
      any=1
      if is_dry_run; then
        echo_act "unset ${v} (DRY RUN)"
      else
        unset "${v}" || true
      fi
    fi
  done
  [[ $any -eq 0 ]] && echo_skip "No PYTHON* vars set in current session"
}

# 3) Remove from launchctl (GUI environment for apps started by LaunchServices)
clean_launchctl() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo_skip "launchctl cleanup is macOS-only"
    return
  fi
  echo_hdr "Cleaning PYTHON* from launchctl user environment"
  local any=0
  for v in "${VARS[@]}"; do
    # Check value
    local val
    val=$(launchctl getenv "$v" || true)
    if [[ -n "$val" ]]; then
      any=1
      if is_dry_run; then
        echo_act "launchctl unsetenv $v (DRY RUN)"
      else
        launchctl unsetenv "$v" || true
      fi
    fi
  done
  [[ $any -eq 0 ]] && echo_skip "No PYTHON* vars set in launchctl"
}

# 4) Comment out exports in user shell rc files (persistent)
comment_in_file() {
  local file="$1"
  [[ -f "$file" ]] || { echo_skip "$file not found"; return; }

  echo_act "Scanning $file for PYTHON* exports"
  local backup="${file}.bak.$(ts)"

  # Build a temp file with changes
  local tmp
  tmp=$(mktemp)
  # Regex covers lines like: export PYTHON...=, PYTHON...=, setenv PYTHON... (csh), and PATH-style appends
  # We only comment lines that SET these variables, not references.
  if is_dry_run; then
    \
    awk '{print}' "$file" > /dev/null
    echo_act "Would backup to $backup and comment matching lines (DRY RUN)"
    return
  fi

  cp "$file" "$backup"
  # macOS sed requires -i ''
  # Comment beginning-of-line assignments/exports to PYTHON*
  sed -i '' -E \
    -e 's/^([[:space:]]*export[[:space:]]+PYTHON[A-Z_]*=)/# \1/g' \
    -e 's/^([[:space:]]*PYTHON[A-Z_]*=)/# \1/g' \
    -e 's/^([[:space:]]*setenv[[:space:]]+PYTHON[A-Z_]*[[:space:]]+)/# \1/g' \
    "$file"

  echo_ok "Updated $file (backup: $backup)"
}

clean_shell_rcs() {
  echo_hdr "Commenting PYTHON* exports in user shell startup files (persistent)"
  local files=(
    "$HOME/.zshrc"
    "$HOME/.zprofile"
    "$HOME/.zshenv"
    "$HOME/.bash_profile"
    "$HOME/.bashrc"
    "$HOME/.profile"
    "$HOME/.environment"
    "$HOME/.env"
  )
  for f in "${files[@]}"; do
    comment_in_file "$f"
  done
}

# 5) Summary after cleanup
summary() {
  echo_hdr "Post-cleanup session PYTHON* variables"
  env | grep -E '^PYTHON' || echo "(none)"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo_hdr "Post-cleanup launchctl PYTHON* variables"
    local found=0
    for v in "${VARS[@]}"; do
      local val
      val=$(launchctl getenv "$v" || true)
      if [[ -n "$val" ]]; then
        found=1
        printf "%s=%s\n" "$v" "$val"
      fi
    done
    [[ $found -eq 0 ]] && echo "(none)"
  fi
  echo_hdr "Cleanup finished"
}

main() {
  show_current
  unset_current
  clean_launchctl
  clean_shell_rcs
  summary
  echo
  echo "Tips:"
  echo "- 若你修改了 shell 启动文件，请新开一个 Terminal 以加载新配置"
  echo "- GUI 应用(双击 .app)继承 launchd 环境，已通过 launchctl 清理；必要时可重启或重新登录"
}

main "$@"
