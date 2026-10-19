# Result feedback (ratings on agent results)

A result an agent posts to the chat's result panel (a chat notification) can
ask for review by setting `"review": true` in the notification body. Each item
in `Items` then shows 👍/👎, 1–5 stars, a comment box, and two buttons:

- **按意见修改 / Revise with this** — posts `【修改】<item>（<rating>）：<comment>`
  into the chat, as the user, to the agent that produced the result.
- **采用 / Accept** — posts `【采用】<item>（<rating>）[：<comment>]`.

The agent's skill decides what those messages do (e.g. 做图经理小李 redoes the
image or marks it accepted). The item key is the item's `product_name`
(falling back to `id`, then its index).

## Stored locally (desktop)

IPC `set_chat_notification_feedback {uid, itemKey, feedback}` →
`DBChatService.set_notification_feedback`, which merges into the notification
row's `content.feedback[itemKey]`:

```json
{"thumb": "up" | "down" | null, "stars": 1-5, "comment": "...", "accepted": true, "updatedAt": 1792350000000}
```

The panel reads it back from `content.feedback` when the chat is reopened.

## Cloud (not wired yet — needs the backend first)

These ratings are meant to feed a later self-improvement loop, so they should
also reach the cloud. The client does not send them yet: there is no backend
table or mutation, and sending to a missing mutation would only produce
`GRAPHQL_VALIDATION_FAILED` retries. Backend contract to add (private backend,
both TCB and AppSync per CLAUDE.md §5):

`ResultFeedback` row, upserted by `(notification_uid, item_key)`:

| field | type | notes |
|---|---|---|
| `id` | ID | server-generated |
| `owner` | String | the user (normalized cloud owner) |
| `chat_id` | String | |
| `notification_uid` | String | the chat notification's uid |
| `item_key` | String | e.g. `pi001-main` |
| `agent_id` | String | agent that produced the result |
| `skill_id` / `task_id` | String | what produced it, when known |
| `thumb` | String | `up` / `down` / null |
| `stars` | Int | 1–5, null |
| `comment` | String | |
| `accepted` | Boolean | |
| `media_url` / `media_path` | String | the image the rating is about |
| `created_at` / `updated_at` | AWSDateTime | |

Mutation `upsertResultFeedback(input: ResultFeedbackInput!)` and query
`queryResultFeedback(input: {owner, agent_id?, skill_id?, since?})`. Once
deployed, the client adds a `DataType.RESULT_FEEDBACK` sync from
`set_notification_feedback` through the offline sync manager (so it is cached
when offline), like the other entity syncs.
