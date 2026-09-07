# Feige Q&A response quality — the three levers

2026-09-07, from the 陆地飞鱼 / 钛斯特的小店 run. Customer report: product/attribute
questions get fobbed off — "这边帮您核实一下…稍后回复您" — instead of real answers.

## What the log actually showed

- **The run was 97e, not 97g.** OTA banner `Current version: 0.7.0-v0.9.97e`; the
  `97g` lines were the installer *downloading*. So ws195 (card attributes) was not
  running: `[FEIGE-CARD-JSON] stored attrs`=0, `属性:`=0.
- **RAG is wired but the knowledge base is empty.** The QA agent calls `rag_query`
  **270×** in the run, but every result is `refs=0`, `Confidence v2: 0.25
  (very_low)`, body `"Sorry, I'm not able to provide…"`. With nothing retrieved,
  the agent falls back to a generic promise-to-follow-up — which never happens
  (there is no human), so the customer waits and times out.

Two independent causes, two independent fixes, plus the durable one (RAG).

## Lever 1 — Card attributes in context (ws195, ships in 97g)

The card's own JSON (`get_product_list` / `getTemplateCardDataV2`) carries
`property_value_pair`: 面料材质, 适用年龄, 适用季节, 领型, 服装版型, 尺码大小, 袖长…
ws195 parses these into a whitelisted `属性:` line merged onto the card the QA agent
sees. This answers **product-specific** questions about the item in hand without any
RAG round-trip:

| Question | Answered from |
|---|---|
| 纯棉的吗 / 亲肤吗 / 会不会扎皮肤 / 会不会掉色 | 面料材质 |
| 偏大还是偏小 | 服装版型 / 尺码大小 |
| 适合什么季节 | 适用季节 |
| 长袖短袖 | 袖长 |

Whitelist (kept tight for token budget): 面料材质/材质/里料材质/适用年龄/尺码/功能/
适用季节/裤长/袖长/领型/版型/厚薄/弹力/颜色/服饰工艺 (≤5 attrs, ≤160 chars per card).
Kill switch `ECAN_FEIGE_CARD_JSON=0`. **Action: install 97g** and confirm
`[FEIGE-CARD-JSON] stored attrs` + `属性:` now appear.

Card attributes are deliberately narrow — they describe **only the one product on
the card**. Everything broader is Lever 2.

## Lever 2 — RAG knowledge base (the customer builds this; the real workload sink)

Card attributes can't answer store **policy** or **cross-product** questions:
包邮/邮费, 运费险, 发货时效, 退换货规则, 尺码对照表 (身高体重→码), 洗涤/护理,
材质工艺细节, 促销/优惠规则, 适用场景. These belong in a **customer-owned RAG
knowledge base** so `rag_query` returns real references (`refs>0`) instead of
"Sorry, I'm not able to provide".

**What to put in the KB (checklist):**
- 物流/发货: 是否包邮, 邮费规则, 发货时效 (48h…), 运费险, 偏远地区.
- 售后: 7天无理由, 退换货流程, 极速退款, 质量问题处理.
- 尺码: 每个品类的 身高/体重 → 建议码 对照表; 版型偏大/偏小说明.
- 材质/护理: 面料成分说明, 是否掉色/起球/缩水, 洗涤方式.
- 商品线: 各热销款的卖点、材质、适用年龄/季节 (so answers survive a card that
  didn't paint).
- 店铺政策: 优惠券使用规则, 会员, 发票, 定制.

**How to load it** (already in the product):
- GUI: the skill/knowledge panel → ragify documents.
- MCP tools available to the agent/CLI: `bu_ragify` / `bu_ragify_async` (ingest a
  file/folder), `bu_rag_replace_document` (update one doc), `bu_rag_query` (what the
  QA node calls). Keep docs short, Q&A-shaped, one topic per chunk — that's what
  `naive` fast-path retrieval (mt047A) matches best.
- Verify after loading: a `rag_query` on a KB topic should log `refs>N` (not 0) and
  `Confidence` above very_low.

This is the durable fix: as the store's catalog/policies grow, the KB carries the
load — no code change per new product or policy.

## Lever 3 — Prompt: stop the dead-end fob-off (business prompt, not core)

Even with attributes + a populated KB, the QA prompt currently lets the model
promise "核实后稍后回复您" when it's unsure — a dead end (no human follows up).
Recommended prompt guidance (apply to the 飞鸽客服问答 prompt via the prompt editor
/ `ecan prompts update` — it is business-specific and belongs in the feige prompt,
never in core):

> 回答规则：
> 1. 商品本身的属性问题（材质/尺码/版型/季节/袖长等）——优先用本轮消息里【商品卡片】
>    的“属性:”字段直接回答。
> 2. 政策/服务/跨商品问题（包邮/运费/发货/退换/尺码对照/护理）——先用 rag_query 检索
>    知识库并据此回答。
> 3. 只有当卡片属性和知识库都没有该信息时，才做“无法确认”的处理，并且：给出**基于常识的
>    谨慎建议或反问一个澄清问题**；**不要**承诺“核实后稍后回复”“帮您核实一下”这类无人
>    跟进的空头承诺。
> 4. 回答要针对客户**这一条**问题；不要答非所问（如把“包邮吗”答成版型）。

Item 4 targets the observed mis-answer: "包邮吗" → a 版型 reply. Worth re-checking
once the KB is populated (an empty KB pushes the model toward stale/generic text).

## Status

- Lever 1: ws195 in 97g (built). Whitelist widened (袖长/颜色/厚薄/弹力/服饰工艺) —
  staged for the next rev, **not yet built**.
- Lever 2: customer action — build the RAG KB (this doc's checklist).
- Lever 3: prompt edit — drafted above, apply via prompt editor; pairs with Lever 2.
