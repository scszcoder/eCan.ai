# CN TCB backend gap report

Run `npm --prefix cloudbase-graphql run schema:coverage` to refresh the result.

| API type | Matching AppSync operations | AppSync total | Coverage |
|---|---:|---:|---:|
| Query | 36 | 69 | 52% |
| Mutation | 72 | 130 | 55% |
| Subscription | 0 | 14 | 0% |

CN-only CRUD names are not counted as compatible. Matching a name also does not
prove argument, return-type, authorization, or behavioral compatibility.

Completed foundations: authentication/tenant isolation; the `reqFileOp` COS
adapter; the SCF timer/Tencent Worker-launch scheduler; CN immediate
`runCloudTasks`; and the Intl-compatible relationship/skill/avatar/knowledge
CRUD surfaces. The realtime event channels use the `ecan-graphql-sse` SCF
(see services/sse-bridge.js + functions/ecan-graphql-sse/) — the legacy
`ecan-websocket` SCF and its WebSocket triggers have been removed (TCB API
Gateway WS triggers were deprecated 2026-08). The full
`appsync_schema_current.graphql` lists the remaining Intl-only operations
(camera/screen/scene/skill-runner/editor-cache/skill file
storage, etc.) that the CN backend has not yet implemented.

## Skill store snapshot (2026-08-06)

Audit of `AgentSkill` and surrounding surfaces in `cloudbase-graphql/`.

### Complete

- Schema: `AgentSkill` (27 fields), four relation tables
  (`AgentSkillRel`/`AgentSkillToolRel`/`AgentSkillKnowledgeRel`/`AgentTaskSkillRel`),
  and editor-state tables (`SkillEditorChatSession`/`SkillEditorChatMessage`/
  `EditorCache`/`SkillBreakpoint`/`SkillRunState`). Seed in
  `prisma/init.js:108` creates `skill-demo`.
- Resolver surface: both the typed CRUD (`getAgentSkills` / `addAgentSkills`
  / `updateAgentSkills` / `removeAgentSkills` in `resolvers/entities.js`) and
  the legacy compatible surface (`querySkills` / `addSkills` /
  `updateSkills` / `removeSkills` in `resolvers/legacy.js`).
- Tool/knowledge/task relations: `addSkillToolRelations` /
  `addSkillKnowledgeRelations` and the renamed equivalents
  (`addAgentSkillToolRels` / `addAgentSkillKnowledgeRels`).
- Skill-editor file storage: `services/cn-skill-editor.js` — list/read/
  write/open via COS signed URLs under `users/<owner>/skills/<name>/`,
  scaffold, breakpoint and run-state persistence.
- Real-time channel: `publishSkillEditorStreamEvent` Mutation +
  `onSkillEditorStreamEvent` Subscription over the in-process event-bus
  (`resolvers/subscriptions.js`, `resolvers/capabilities.js`,
  `event-bus.js`).
- Skill editor chat: full session/message/stream surface
  (`getSkillEditorChatSessions` / `getSkillEditorChatHistory` /
  `createSkillEditorChatSession` / `sendSkillEditorChatMessage` /
  `cancelSkillEditorChatGeneration` / `deleteSkillEditorChatSession`).
- Authorization: every mutation goes through `authenticatedOwner`
  (`auth.js:18`), enforcing owner scoping and rejecting cross-owner writes.

### Missing or stub

- Marketplace semantics: no rating / review model, no install/download
  counts, no favorites/bookmarks, no purchase/order flow that touches
  `AgentSkill` (the `commerce` resolver set is product/warehouse/label only,
  not skill-marketplace).
- Publish/visibility flow: `AgentSkill.isPublic` exists
  (`schema.prisma:73`) but no resolver filters on it — `skillsQuery` returns
  everything owned or named, so the "public catalog" is not actually
  enforced server-side.
- Search surface: `SkillQueryInput` (`index.js:868`) only supports
  `id`/`owner`/`name`/`category`. No tag/capability/level/price filter, no
  full-text, no sort.
- Off-store stubs: `services/cn-misc.js` still returns hard-coded
  placeholder payloads for `queryRAGs` (L14), `getFB` (L22), `queryChats`
  (L26), `reqScreenTxtRead` (L45), `reqScreenIconRead` (L49). These are
  not part of the skill-store surface but should be tracked separately.

### Scoring

- Skill editor (CRUD + debugger + realtime + files): ~9/10, production-ready.
- Skill marketplace (search/rate/install/monetize): ~2/10, only the
  `isPublic` flag is present and no flow uses it.
