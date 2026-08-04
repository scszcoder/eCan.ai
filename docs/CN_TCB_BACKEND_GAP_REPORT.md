# CN TCB backend gap report

Run `npm --prefix cloudbase-graphql run schema:coverage` to refresh the result.

| API type | Matching AppSync operations | AppSync total | Coverage |
|---|---:|---:|---:|
| Query | 9 | 51 | 18% |
| Mutation | 13 | 75 | 17% |
| Subscription | 0 | 10 | 0% |

CN-only CRUD names are not counted as compatible. Matching a name also does not
prove argument, return-type, authorization, or behavioral compatibility.

Completed foundations: authentication/tenant isolation and the `reqFileOp`
COS adapter. The scheduler now has an SCF timer/Tencent Worker-launch provider,
and CN immediate `runCloudTasks` bypasses its legacy S3/ECS branch. RAG and
other Intl-only branches are reference implementations only and remain unchanged.
The CN equivalents of those branches have not yet been implemented. Remaining
delivery order: production migration SQL; RAG/skill-asset storage migration;
Skill Editor/long LLM tasks; A2A/WAN and subscriptions; then account, order,
API-key, RAG, and remaining operations.
