#!/bin/sh
# Install the eCan secret-scan pre-commit hook into this clone's .git/hooks.
# Run from the repo root:  sh scripts/git-hooks/install.sh
set -e
root=$(git rev-parse --show-toplevel)
src="$root/scripts/git-hooks/pre-commit"
dst="$root/.git/hooks/pre-commit"
cp "$src" "$dst"
chmod +x "$dst" 2>/dev/null || true
echo "Installed secret-scan pre-commit hook -> $dst"
