#!/bin/bash
# Build the ecan-graphql-sse deployment package.
#
# TCB cos deployment packages each function as an independent zip. The SSE
# function only needs a small subset of the project's source tree:
#   services/sse-bridge.js
#   event-bus.js
#   tcb-app.js (lazy wrapper around @cloudbase/node-sdk for JWT auth)
#   functions/ecan-graphql-sse/*
#
# We copy the source into /tmp/sse-pkg, npm install the minimal deps, and zip it.
# The deployed package's `index.js` requires from /var/user/sse/... (we set that
# path in the scf_bootstrap; see the next note).
#
# Why not just include the whole project tree?
#   - The full project has @prisma/client (~50MB), graphql-yoga, etc. We don't
#     need any of it in SSE.
#
# Why is `node_modules` skipped inside the package?
#   - TCB's `installDependency: true` does the install on the platform. We set
#     that to false in cloudbaserc.json, so we ship a prebuilt node_modules.

set -e

WORK_DIR="/tmp/sse-pkg"
OUT_ZIP="/tmp/ecan-graphql-sse.zip"
SRC_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "[sse-bundle] cleaning $WORK_DIR"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

echo "[sse-bundle] copying shared sources"
cp "$SRC_ROOT/services/sse-bridge.js" "$WORK_DIR/sse-bridge.js"
cp "$SRC_ROOT/event-bus.js" "$WORK_DIR/event-bus.js"
# tcb-app.js shim — created by this script below
cp "$WORK_DIR/_tcb-app.shim.js" "$WORK_DIR/tcb-app.js" 2>/dev/null || true

# Layout: /var/user/sse/<file>.js, so the deployed index.js can
# `require('/var/user/sse/sse-bridge.js')`. TCB's default deployment root is
# /var/user/, so we structure the package accordingly.
mkdir -p "$WORK_DIR/sse"
cp "$WORK_DIR/sse-bridge.js" "$WORK_DIR/sse/services-sse-bridge.js" 2>/dev/null || true
# Simpler: align the package layout with the runtime layout.
rm -rf "$WORK_DIR/sse"
mkdir -p "$WORK_DIR/services"
cp "$SRC_ROOT/services/sse-bridge.js" "$WORK_DIR/services/sse-bridge.js"
cp "$SRC_ROOT/event-bus.js" "$WORK_DIR/event-bus.js"
rm -f "$WORK_DIR/sse-bridge.js"

# TCB places the zip's contents at /var/user/. We expect the deployed index.js
# to be at /var/user/index.js, with services/ and event-bus.js as siblings.
cp "$SRC_ROOT/functions/ecan-graphql-sse/index.js" "$WORK_DIR/index.js"
cp "$SRC_ROOT/functions/ecan-graphql-sse/package.json" "$WORK_DIR/package.json"
cp "$SRC_ROOT/functions/ecan-graphql-sse/scf_bootstrap" "$WORK_DIR/scf_bootstrap"
chmod +x "$WORK_DIR/scf_bootstrap"

# TCB's runtime Node 20 lookup checks /var/lang/node20.19/bin/node; the
# cloudbaserc.json sets runtime: Nodejs20.19, so the bootstrap launch path
# is provided by the platform. We drop the redundant cd shell logic.
cat > "$WORK_DIR/scf_bootstrap" <<'EOF'
#!/bin/bash
# SCF places the package at /var/user/. services/ and event-bus.js are siblings.
node /var/user/index.js
EOF
chmod +x "$WORK_DIR/scf_bootstrap"

# Minimal node_modules: only @cloudbase/node-sdk (for JWT verification, optional).
# We make it optional so the function still runs without it (anonymous mode).
if [ ! -d "$WORK_DIR/node_modules/@cloudbase/node-sdk" ]; then
  echo "[sse-bundle] installing @cloudbase/node-sdk"
  (cd "$WORK_DIR" && npm install --omit=dev --no-audit --no-fund @cloudbase/node-sdk@3.18.3 2>&1 | tail -5)
fi

# scf_ignore: keep deployment small
cat > "$WORK_DIR/.scfignore" <<'EOF'
.git
.gitignore
*.log
.env
.env.local
.DS_Store
README.md
EOF

echo "[sse-bundle] zipping → $OUT_ZIP"
cd "$WORK_DIR"
rm -f "$OUT_ZIP"
zip -r "$OUT_ZIP" . -x "*.DS_Store" -x ".git/*" >/dev/null
echo "[sse-bundle] done: $(du -h "$OUT_ZIP" | cut -f1)"
