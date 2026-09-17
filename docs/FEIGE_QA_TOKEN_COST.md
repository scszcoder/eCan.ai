# Feige customer-service token cost per query

What one customer question actually costs in model tokens, measured from
customer run logs rather than estimated.

_Measured 2026-09-15 from `customer_logs/eCan.log` (customer-clock run of 09-16 09:42→11:02)
and `customer_logs/eCan.log.1` (2026-09-08). 52 answered queries, 133 LLM calls._

---

## Headline

| per answered query | tokens |
|---|---|
| **input** | **~11,000** |
| **output** | **~116** |
| LLM calls | 2.6 |

The two samples agree closely, so treat ~11k in / ~116 out as the working number:

| sample | queries | in/query | out/query | calls/query |
|---|---|---|---|---|
| `eCan.log` (2026-09-16) | 15 | 12,223 | 124 | 2.7 |
| `eCan.log.1` (2026-09-08) | 37 | 10,477 | 113 | 2.5 |
| **combined** | **52** | **10,981** | **116** | **2.6** |

**Input dominates at roughly 95:1.** The replies really are one sentence
(60-70 tokens); essentially all the money is prompt. Cost work belongs in
prompt size, not in response length.

## Where it goes

One answered query is two or three LLM calls:

| stage | model | in/call | out/call | fires on |
|---|---|---|---|---|
| classify (`{"needs_rag":…,"category":…}`) | gpt-4o-mini | ~1,300 | 16 | every query |
| `rag_query` | gpt-5.4 | ~5,300 | 56 | 56% of queries |
| `send_chat` (the answer) | gpt-5.4 | ~6,900 | 67 | every query |

By model, per query: **gpt-5.4 ≈ 9,572 in / 98 out**, **gpt-4o-mini ≈ 1,409 in / 18 out**
— the expensive model carries **87% of the input tokens**.

Two shapes of a turn:

- **with RAG** (56%): classify → `rag_query` → answer. The answer prompt also grows
  to ~8,000 tokens because the retrieved passages are appended.
- **without RAG** (44%): classify → answer, answer prompt ~4,400 tokens.

So RAG roughly doubles a query's cost: it adds a 5,300-token call *and* inflates
the answer call.

## Why it is 11,000 tokens

Measured 2026-09-15 from the same logs, via the `recent_context summary` lines the
LLM node emits before each call (they give the message stack with per-message
`content_len`) and the `llm config: system_prompt_template=` dump.

The customer's own message is **180-1,050 chars — under 1.5% of the input**.
Everything else is the same text resent:

| call | message stack | in-tokens |
|---|---|---|
| classify | classifier system prompt 3,707 chars + input | ~1,300 |
| `rag_query` | Q&A system prompt 12.7-15.4k chars + input + **the classifier's system prompt again** (3,707 chars) + its AI reply | ~5,300 |
| answer | the same stack + the retrieved passages | ~7,000-9,700 |

A non-RAG turn is calls 1 and 3 only (~5,600). Weighted 56/44 that is ~10.1k,
which is the ~11k measured end to end.

The Q&A system prompt **template** is 11,426 chars ≈ 3.1k tokens and is sent on
every QA-agent call, so a RAG turn pays for it twice. Its sections:

```
1,937  ## Highest-priority output contract      1,029  ## Handling tool results
1,659  ## Routing decision from the classifier    912  ## Product card / shared link
1,517  ## Current-turn input only                 900  ## send_chat contract
1,226  ## Decision flow                           576  ## Reply style
  553  ## Query examples                          540  ## Media / image handling
  345  ## Forbidden outputs                       221  (header)
```

## Prompt caching is structurally impossible today

Caching matches on an **exact prefix**. In the Q&A template:

```
{{input}}  at char 2,223 of 11,426   (19% into the prompt)
{{events}} at char 3,334  and  3,569
```

The prompt diverges 19% in, so the stable prefix is ~2,223 chars ≈ **600 tokens —
below OpenAI's 1,024-token minimum for automatic prompt caching**. The hit rate is
therefore **0%**, whatever the proxy supports. Consistent with that, every usage
record in the logs carries `'prompt_tokens_details': None` and
`'input_token_details': {}` — nothing is cached, and nothing is even reported.

`{{input}}` does not need to be there at all: the same text is already the user
message (`user_prompt_template='{{input}}'`), so the turn is sent twice.

**Once the placeholders move out of the system prompt**, the whole ~3.1k-token
prompt becomes a stable prefix and the hit rate is set by traffic spacing. Measured
over the 133 calls, by gap since the previous call sharing that prefix:

| gap | QA-agent (n=81) | classifier (n=52) |
|---|---|---|
| <5 min — certain hit | 74% | 63% |
| 5-10 min — likely hit | 5% | 8% |
| >10 min — likely miss | 16% | 25% |

So expect **~75-80%**, the misses being idle gaps. Within one turn, calls 2 and 3
are seconds apart and would hit essentially always.

Two caveats: the classifier's own prompt is ~1,000 tokens, right at the threshold,
so it may never cache even after the fix — merge it rather than tune it separately.
And it is unconfirmed that the CN proxy passes caching through at all: send an
identical prompt twice inside a minute and check whether
`prompt_tokens_details.cached_tokens` comes back non-null.

## Optimisation, ranked by measured saving

1. **Fold the RAG decision into the classifier.** It already emits
   `{"needs_rag":…,"category":…}`; the separate `rag_query` call pays the full
   3.1k-token prompt to emit a 46-token tool call. Removes 5,300 tokens on 56% of
   turns: **−3.0k/query, −27%**.
2. **Stop carrying the classifier's system prompt into the later calls.** It sits in
   `recent_context` for the rag and answer calls, instructing a classifier that has
   already run: **−1 to −2k/query**. This is a context-assembly leak, not prompt
   authoring.
3. **Stop interpolating `{{input}}` / `{{events}}` into the system prompt.** Removes
   the duplicated turn text and is the precondition for any caching at all.
4. **Skip the classifier for greetings** — ~1.3k on those turns, and the bigger
   latency win already tracked in [OPEN_ITEMS.md](OPEN_ITEMS.md).
5. **Trim the template**: the five largest sections are 7.4k of the 11.4k chars.

Items 1 + 2 take ~11k input down to ~6.5k; item 3 then makes most of what remains
cacheable.

## Notes that matter for costing

- **The front desk costs nothing.** The `前台小张` agent made **zero** LLM calls in
  both windows — its ~17k log lines are all WS/DOM dispatch. The numbers above are
  the whole model cost of a customer exchange, not one leg of it.
- **The classifier fires on every query**, including greetings, spending ~1,300
  input tokens to produce a 16-token JSON verdict (~12% of input). Listed in
  [OPEN_ITEMS.md](OPEN_ITEMS.md) as the biggest available latency win; it is a
  (smaller) cost item too.
- **No CNY figure here.** It depends on what the CN llm-proxy charges for `gpt-5.4`
  and `gpt-4o-mini`. The log's own `[llm_token_usage]` line read `0 tokens (0.00 CNY)`
  for this account, so there was no rate table worth trusting. Multiply the table
  above by the proxy's per-1k rates.

## How to reproduce on a new log

**Every LLM call is logged twice** (two loggers emit the same payload), and a third
line carries no scope tag. Counting raw lines double-counts — dedupe on the
`'id': 'chatcmpl-…'` inside `response_metadata`. Note this is *not* the `id='lc_run--…'`
that appears later on the same line.

A query is counted as answered when a `send_chat` call is made; the stage of each
call is read from its content (`needs_rag` → classify, `"rag_query"` → rag,
`"send_chat"` → answer).

```python
import re, io, collections

PAT   = re.compile(r"usage_metadata=\{'input_tokens': (\d+), 'output_tokens': (\d+)")
ID    = re.compile(r"'id': '(chatcmpl-[^']+)'")
MODEL = re.compile(r"'model_name': '([^']+)'")

def kind(l):
    if 'needs_rag' in l:   return 'classify'
    if '"rag_query"' in l: return 'rag'
    if '"send_chat"' in l: return 'answer'
    return 'other'

calls = {}
for path in ('eCan.log', 'eCan.log.1'):          # newest first
    for line in io.open(path, encoding='utf-8', errors='replace'):
        m, i = PAT.search(line), ID.search(line)
        if m and i:
            calls.setdefault(i.group(1), (int(m.group(1)), int(m.group(2)),
                                          kind(line), MODEL.search(line).group(1)))

answers = sum(1 for v in calls.values() if v[2] == 'answer')
ti = sum(v[0] for v in calls.values())
to = sum(v[1] for v in calls.values())
print(f"{answers} queries, {len(calls)} calls -> IN {ti/answers:,.0f}  OUT {to/answers:,.0f}")

stage = collections.defaultdict(lambda: [0, 0, 0])
for i, o, k, _ in calls.values():
    g = stage[k]; g[0] += 1; g[1] += i; g[2] += o
for k, (n, i, o) in stage.items():
    print(f"  {k:<9} n={n:<3} in/call={i//n:>7,} out/call={o//n:>4,}")
```

Run it from `customer_logs/` with `PYTHONIOENCODING=utf-8` (the skill names are
Chinese and the default Windows console codec will not encode them).

## Caveats

- Both samples are **one merchant, one store**. Prompt size scales with the product
  card, the RAG corpus and the conversation history kept per turn, so another
  merchant's numbers will differ.
- The 56% RAG hit rate is a property of what these customers asked (spec, size,
  suitability, shipping). A store with more greeting-type traffic pays less.
- History is wiped every turn (see `reference_feige_qa_context_anatomy`), so these
  are per-turn costs that do **not** grow over a long conversation.
