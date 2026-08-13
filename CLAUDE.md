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

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes. Also: backend-shape errors get fixed at the backend (with redeploy), never papered over by client-side rewrites that break the other platform.