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
CRUD surfaces. WebSocket event channels (WebSocket SCF) are stubbed for the
`skill-editor-stream` channel but the GraphQL Subscription surface itself is
not yet wired. The full `appsync_schema_current.graphql` lists the remaining
Intl-only operations (camera/screen/scene/skill-runner/editor-cache/skill file
storage, etc.) that the CN backend has not yet implemented.
