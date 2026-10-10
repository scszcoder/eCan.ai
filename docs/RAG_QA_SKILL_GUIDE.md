# Using product knowledge in customer-service Q&A skills

The Q&A skills and prompts live in user data (`my_skills/`, `my_prompts/`), not in this repository, so this guide
describes the changes to make in the skill editor. Nothing breaks if you change nothing.

## What already happens automatically

`rag_query` checks product knowledge first (`knowledge/ks/agent_bridge.py`):

- The **store** comes from the task's `store_id` variable. Link it on Knowledge → Product Knowledge → Overview →
  "Add my eCan stores", or pick the app store in the store dialog.
- The **product** comes from the buyer's latest product card in the run state (`商品ID:<id>`). The item id also
  identifies the store, so a shared Q&A agent serving several shops gets the right shop's policy.
- When product knowledge is confident, `rag_query` returns its context immediately (typically 5–50 ms, no LLM
  call). Otherwise it falls through to LightRAG exactly as before.

The tool result keeps its old shape, with extra fields:

| field | meaning |
|---|---|
| `rag_answer` | labelled context: `[商品]`, `[商品信息]`, `[常见问题]`, `[店铺规则…]`, `[资料]` |
| `rag_confidence_score`, `rag_should_answer` | honest confidence; `false` means there is not enough knowledge |
| `rag_sensitivity` | `private` when the answer came from a private server or a confidential knowledge base |

## Recommended prompt changes

1. **Fold the RAG decision into the routing classifier.** `docs/OPEN_ITEMS.md` already proposes this; it saves
   about 3k tokens and one LLM turn per message. Call `rag_query` directly from an MCP node with the buyer's latest
   message as `query`; there is no need to let the LLM write the query.
2. **Trust the labels.** In the answer prompt:

   ```
   - [商品信息] and [常见问题] are authoritative for this product; answer from them word for word.
   - [店铺规则·…] is this store's rule. Never mix rules from other stores.
   - If rag_should_answer is false, do not guess: say you are checking and hand off to a human.
   - Price, stock and promotions are not in the knowledge base; use the product card or query_price/query_inventories.
   ```

3. **Do not pass `workspace` for product questions.** Scope comes from the run, not from the LLM.
4. **Private answers stay private.** If a skill can receive `rag_sensitivity=private`, its answer LLM must be a model on
   the private server (for example vLLM on the on-prem box). Otherwise the harness blocks the call; see
   `knowledge/ks/taint.py`.

## Checking a skill

Use Knowledge → Product Knowledge → Q&A test with the same store and product card the buyer would have. It shows
exactly what the agent will receive and how long retrieval took.
