#!/usr/bin/env bash
# Additive: a schema for the Knowledge Service (knowledge or knowledge_test), like `langgraph`.
set -euo pipefail
export PATH=$HOME/.local/bin:$PATH
ENV=sccb0-d0gc5398xf028be6a
SCHEMA="${1:-knowledge_test}"
case "$SCHEMA" in knowledge|knowledge_test) ;; *) echo "refusing schema $SCHEMA"; exit 2;; esac
run() { tcb db execute -e "$ENV" --json --sql "$1" 2>&1 | grep -o '"AffectedRows": *[0-9]*\|"message":"[^"]*"' | head -2; }
run "CREATE SCHEMA IF NOT EXISTS $SCHEMA"
run "GRANT USAGE, CREATE ON SCHEMA $SCHEMA TO ecanai"
run "ALTER DEFAULT PRIVILEGES IN SCHEMA $SCHEMA GRANT ALL ON TABLES TO ecanai"
run "ALTER DEFAULT PRIVILEGES IN SCHEMA $SCHEMA GRANT ALL ON SEQUENCES TO ecanai"
tcb db execute -e "$ENV" --json --sql "SELECT nspname, nspowner::regrole::text, has_schema_privilege('ecanai', nspname, 'CREATE') FROM pg_namespace WHERE nspname='$SCHEMA'" 2>&1 | grep -o '"Rows": *\[[^]]*\]'
