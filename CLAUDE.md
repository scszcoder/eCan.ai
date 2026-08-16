# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Cross-Platform / Multi-Backend Awareness

**eCan.ai runs on BOTH AWS AppSync and TCB (cloudbase-graphql). Changes must keep both healthy.**

Before touching shared code:
- **Identify the contract surface.** Anything in `agent/cloud_api/` (mapping files, GraphQL builder, schema registry) feeds both AWS and TCB. If the change is shape-specific to one backend, fix the backend instead.
- **Locate the canonical schema.** Each input/output has two definitions: `cloudbase-graphql/index.js` (CN SDL) and the AWS AppSync schema. They are *not* guaranteed identical. Read both before deciding.
- **Default to backend-side fixes for backend-side errors.** A `GRAPHQL_VALIDATION_FAILED` from a cloud function means the SDL on that backend is missing a field — fix the SDL and redeploy, do not rewrite the client to "match" the wrong shape.

Fix-the-cloud standard procedure:
1. Update the SDL/resolver in `cloudbase-graphql/` (or whichever backend surfaced the error).
2. Run schema unit tests: `node scripts/test-graphql-parity.js` and `node scripts/test-units.js` from `cloudbase-graphql/`.
3. Deploy via `./cloudbase-graphql/scripts/deploy-api.sh` (or `--dry-run` first to verify packaging).
4. Verify end-to-end with the same client request that previously failed.

Anti-patterns (avoid):
- Renaming client-side fields (`extra_data` → `extraData`) to satisfy one backend. This breaks the other backend *and* every AWS-bound consumer.
- Adding "if TCB then camelCase else snake_case" branching in client code. The contract is the contract; either backend accepts the same fields, or one backend's SDL is wrong.
- Editing mapping JSON (`agent/cloud_api/mappings/*.json`) to paper over a server-side validation error.

Ask yourself: "If a different backend later adopts this client, will the same fix still apply?" If no, you're fixing the wrong layer.

## 6. Error Classification Before Fixing

**Every error log must be classified before deciding whether to fix it. Wrong classification leads to wasted effort or hiding real bugs.**

### Error classification rules

| Class | Definition | Action |
|---|---|---|
| **True Bug** | Code path executes incorrectly (wrong logic, missing guard, exception) | Fix the code |
| **Expected Behavior** | Normal operation (e.g. expired token, auth rejection) | Downgrade log level; add user-facing hint |
| **Unknown** | Can't determine from log alone | Investigate root cause before classifying |

### Common expected behaviors (do NOT error-log)

- **Token expiry (401 from cloud):** Cloud returned UNAUTHENTICATED because the token genuinely expired. This is normal for WeChat 10min tokens or Cognito 60min tokens. Log as `WARNING`, not `ERROR`.
- **No refresh_token (WeChat):** WeChat OAuth tokens have no refresh_token by design. The SessionSupervisor handles expiry gracefully. Do not treat this as an error.
- **Startup cache-lag 401:** After login, CloudBase SCF gateway takes 30-60s to see a new JWT. First few API calls may 401. The AppSync wrapper handles retry. Do not emit error.
- **Cloud timeout (DB fallback):** If cloud is slow/unreachable at startup, the system falls back to local DB. This is by design.

### Common true bugs (fix immediately)

- **Session expired storm:** `Session expired` emitting repeatedly (e.g. every 30s). Root cause: `_tick` logic emitting `on_session_expired` when token is still valid or when `signed_in=False`. Fixed by ensuring `on_session_expired` fires at most once per real expiry event.
- **`_attempt_refresh` failure without GUI notification:** Refresh fails with `NotAuthorizedException` but `notify_session_cleared()` is not called, so the GUI never shows the logout banner. Fix: always call `notify_session_cleared()` after clearing credentials.
- **Session restore without supervisor notification:** `try_restore_session` / `try_restore_cloudbase_session` restore a valid token but don't call `notify_token_installed()`, leaving `OfflineSyncManager` in stale paused state. Fix: call `notify_token_installed()` after restore.
- **Startup without graceful cloud-auth fallback:** When cloud returns 401 at startup, the app logs ERROR and may fail task creation. Fix: treat cloud 401 as WARNING, fall back to DB/local data.
- **GRAPHQL_VALIDATION_FAILED on server:** Cloud returned "Cannot query field X on type Y". This is a TCB/AWS schema mismatch. Fix at the backend (SDL/schema.prisma), not client. See Section 5 procedure.

### When to add fallback vs error-log

- If a feature fails because cloud is unreachable or token is invalid → **graceful fallback** (log WARNING, use local/DB/cache data).
- If a feature fails because code is wrong → **error-log and fix the code**.
- If you can't tell which → **investigate first**. Never error-log expected cloud failures.

## 7. Release Pipeline Invariants

**Workflows are a contract with `build_system/`. Every hard-coded `dist\*` path or `--version` template in a workflow MUST match what `build_system/ecan_build.py` actually emits. Drift between the two is the #1 source of "looks green, builds broken" failures.**

Three regressions in this repo happened because this contract wasn't checked at commit time:

| Commit | What was written | What `build.py` actually emits | Symptom |
|---|---|---|---|
| `c082afd8` | `dist\eCan-{ver}-windows-amd64.exe` | `dist\eCan-{ver}-windows-amd64-Setup.exe` (template at `build_system/ecan_build.py:465`, `installer_filename = ...-Setup`) | New hard-fail `throw` tripped on every Windows build → red job masking what was meant to be a safety net |
| `42e38228` (and earlier) | `actions/checkout@v6` with `github-server-url: https://gitee.com` + `token:` | `actions/checkout` interprets `token:` as SSH key, falls back to HTTPS without injecting credentials | "fatal: could not read Username for https://gitee.com" — opaque 128 exit, no hint why |
| (uncommitted) | `run:` block written in bash syntax (`set -euo pipefail`, `${VAR:-...}`, `$(...)`) on a Windows self-hosted runner | PowerShell is the default Windows runner shell; bash silently fails the syntax | `.ps1 cannot be loaded because running scripts is disabled` masking the real shell mismatch |

### Mandatory cross-checks before touching any workflow

Before changing `.github/workflows/release-{intl,cn}.yml` (or adding a new build/upload step):

1. **Read the canonical emitter.** Open `build_system/ecan_build.py` and grep for the artifact you intend to reference: `installer_filename`, `dist_basename`, `app_version`, `OutputBaseFilename`. The Python file is the source of truth, not the comment above the workflow step.
2. **Cross-check the version template.** `validate-tag.outputs.version` is the substitution target for every `${{ needs.validate-tag.outputs.version }}` in `dist\*` paths. Confirm it produces what you wrote by reading `release-{intl,cn}.yml`'s validate-tag step (3 branches: tag, user-prefix tag, branch fallback). Branch fallback is `0.7.0-{branch}-{short_sha}` (e.g. `0.7.0-lq_dev_multi-c082afd8`) — this is the format most CI runs hit.
3. **Run the symmetry + smoke tests locally before pushing:**
   ```
   python3 -m pytest tests/unit/test_release_workflow_simulator.py tests/unit/test_workflow_smoke_test.py -x
   ```
   These do not catch filename drift yet (see "Known gaps" below) but they catch the most common adjacent regressions (missing `dist\` prefix, missing `Test-Path`, dropped `Validate Gitee credentials` step).
4. **If the workflow step is bash, pin `shell: bash`.** This is mandatory on Windows self-hosted runners, macOS self-hosted runners, and any job where `runs-on` may resolve to a non-Linux image. Without it, PowerShell parses `set -euo pipefail` as a literal cmdlet and the script silently does nothing. Reference: see commit `fd0ed0c0` for the canonical pin.

### Known gaps in the test surface (fix when you touch the area)

- **No contract test for installer path ↔ `build.py` template.** A ~30-line test in `tests/unit/test_release_workflow_paths.py` that asserts every `dist\eCan-*.exe` path in `release-{intl,cn}.yml` matches `installer_filename` in `build_system/ecan_build.py` would have caught `c082afd8` instantly. Add this before the next refactor of either file.
- **`test_default_cwd_is_repo_root_passes` in `tests/unit/test_release_workflow_simulator.py` currently fails** because `release-pipeline-symmetry-check.py`'s `normalize()` doesn't strip the `Prepare Gitee credential helper` step (CN-only). Pre-existing, not caused by recent commits. Fix in the symmetry-check script, not in either workflow.
- **`test_release_cn_has_validate_gitee_credentials_per_job` in `tests/unit/test_workflow_smoke_test.py` currently fails** because the test's `re.split(r"^\s{4}steps:\s*$", text)` only catches `\s{4}` indented `steps:` — it misses the `Final Status Summary` job's `Checkout from Gitee mirror` step (which legitimately has no validator, since that job doesn't checkout any source). The test's regex misses block 0, then evaluates `block.find("Checkout from Gitee mirror")` = -1 against block 1's `validator_pos` which exists. Fix in the test, not in either workflow. Pre-existing, not caused by recent commits.
- **`test_release_workflows_pass_smoke_test` fails 2 `cn-intl-body-mismatch` violations** at `validate-tag > Validate and extract version@403` and `build-linux > Prepare artifacts@2181`. The two pipelines have been allowed to drift by SMOKE-TEST settings; document the divergence or re-align. Out of scope for code fixes.
- **docs/OTA_PATH_STRUCTURE.md** still documents `eCan-{ver}-windows-amd64.exe` for the local checkout path; the S3 URL is `-Setup.exe`. Docs drift from reality. Out of scope for code fixes; refresh when next touching that doc.

### Self-review checklist for any release workflow PR

- [ ] Every `dist\*` path in the diff has been grep-matched in `build_system/ecan_build.py` (or whatever script emits it).
- [ ] Every `${{ needs.validate-tag.outputs.version }}` substitution has been confirmed against the 3-branch validate-tag logic.
- [ ] Every bash-syntax step (`set -euo pipefail`, `[ -z ... ]`, `$(...)`, `tr`, `sha256sum`) declares `shell: bash`.
- [ ] `python3 -m pytest tests/unit/test_release_workflow_simulator.py tests/unit/test_workflow_smoke_test.py -x` passes locally.
- [ ] If the change is backend-shape-specific, Section 5 procedure has been followed.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes. Also: backend-shape errors get fixed at the backend (with redeploy), never papered over by client-side rewrites that break the other platform. **And: release-pipeline PRs that introduce new hard-coded `dist\*` paths include a contract test against `build_system/`, not just a smoke test.**