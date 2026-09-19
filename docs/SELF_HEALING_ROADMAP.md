# Runtime self-healing, and where the browser-agent stack is going

Written 2026-09-19 after reading four Browser Use repos end to end
(`browser-use`, `browser-harness`, `jev-ultrafast`, `workflow-use`, plus
`browsercode`) and the two essays they point at. Cloned as siblings of this
repo if you want to read along.

This is a plan, not a change. Nothing here is implemented.

---

## 1. The one thing everyone converged on

Two teams, two architectures, opposite directions, same conclusion:

**`jev-ultrafast`** gives the model an indexed table of live elements and lets
it return *an integer*. It cannot emit a selector — the executor resolves the
index to a DOM node it observed itself. *"Model output never becomes selectors,
coordinates, shell commands, or executable JavaScript."*

**`workflow-use`** records a human doing a task and replays it deterministically.
It shipped with CSS selectors, XPath and element hashes. Its schema now reads:

```python
cssSelector:  '[LEGACY] ... avoid in new workflows, use target_text instead.'
xpath:        '[LEGACY] ... avoid in new workflows.'
elementHash:  '[LEGACY] ... not required for semantic workflows.'

# PRIMARY: Text-based semantic targeting (non-brittle)
target_text:      'e.g. "Submit (in Personal Information)"'
container_hint:   'e.g. "Personal Information", "Billing Section"'
position_hint:    'e.g. "item 2 of 3", "first", "last"'
selectorStrategies: 'fallback strategies ordered by priority'
```

They built the brittle thing, shipped it, watched it rot, and deprecated it.

> **The durable identifier is what a human would say, not what the DOM says.**

That is our `ws189`, `ws193`, `mt062/063` and the June Feige redesign, written
down by someone who already paid for it.

## 2. Where we stand

We built the **authoring** half of the loop and none of the **healing** half.

| | us |
|---|---|
| design-time authoring | **strong** — skill editor, flowgram graph, `code_agent` validates and fixes |
| identity / anti-detect | **strongest of anyone read** — per-task fingerprint profiles, proxy relay, fail-closed |
| deterministic execution | **strong** — typed nodes, task vars, LLM only where we put it |
| runtime healing | **none** |
| knowledge accumulation | **none** |

Today's repair path when a site changes:

```
site changes → skill fails → customer notices → logs pulled →
feige_log_health.py + AGENT-STATUS read → selectors patched → build cut
```

That is a human auto-fix pipeline with multi-day latency. It ran at least four
times this year.

## 3. Target architecture: four layers

Ordered by cost to build and by how much each prevents rather than repairs.

```
L0  OBSERVE    one atomic snapshot → indexed element table (role, name, value, text)
L1  TARGET     steps name elements semantically; selectors demoted to fallback
L2  RESOLVE    when naming fails, a model picks from the live table (never writes a selector)
L3  LEARN      what L2 resolved is written back, scored, and reused
```

L0/L1 **prevent** breakage. L2 **survives** it. L3 **compounds** — the Feige
agent that figures out the new sidebar teaches every other agent.

We have a partial L0 already (`extract_dom`, `bu_normalize_page_state`,
`bu_inspect_dom_regions`). We have no L1, L2 or L3.

## 4. Roadmap

### Phase 1 — Semantic targeting (L1). *The urgent one.*

> **Status 2026-09-19: instrumentation shipped** on branch
> `feature/semantic-targeting-phase1` (`b08ad241a`). Measurement only; no
> behaviour change. Awaiting a week of real traffic.
>
> Already found without any traffic: `legacy_hashed_wrap` appears
> **unreachable** — it needs a short `title`, and the ws183 titled scan runs
> first and accepts exactly that. Kept and ordered last until the counter
> confirms, rather than deleted on a hunch.

Add `target_text` / `container_hint` / `position_hint` alongside existing
selectors in the Feige hook bundle. Resolution order: semantic first, selector
as fallback, and **log which one won**.

That log line is the whole point of Phase 1. The day semantic resolution starts
winning more often than selectors, we have evidence for Phase 2 rather than a
belief.

*Acceptance:* Feige runs unchanged; every element resolution records
`strategy=semantic|selector|failed`; a week of real traffic gives a baseline.
No behaviour change.

*Why first:* it prevents the failure instead of repairing it, needs no new
vendor, no new model, and is reversible.

### Phase 2 — Resolver fallback (L2)

When both semantic and selector resolution fail, don't fail the step. Build the
indexed table from the live DOM and ask a model to pick an index — the
`jev-ultrafast` shape. The model returns an integer; we resolve it to a node we
observed. It cannot invent a selector.

**Use the strongest model available here — Opus 5 / Codex class, not the cheap
tier.** L2 runs rarely (only when naming has already failed) and it is choosing
what to click on a live customer's store. A wrong pick is not a slow reply, it
is the wrong action taken. The economics are the opposite of the hot path: cost
per call is irrelevant at this frequency, and a mistake is expensive. Same for
L3, which decides what gets *written back* and therefore what every later run
inherits -- a bad descriptor learned once is a bug that propagates.

*Acceptance:* a Feige run survives a selector break that would have failed it,
and says so loudly in the log. Bounded: N resolver calls per run, then fail.

*Guardrail:* resolver output is an index into our own table. Never a selector,
never JS. This is the `jev-ultrafast` invariant and it is not negotiable — it is
what keeps a hostile page from steering the agent.

### Phase 3 — Write it back (L3)

A successful L2 resolution is evidence. Persist the semantic descriptor it
matched, scoped to site + element role, with a score. Next run tries it before
calling the resolver. Bad descriptors lose score and retire.

This is `workflow-use`'s `healing/` module and the *"agents that actually
learn"* thesis, at our scale: one Feige agent learns the new sidebar, every
Feige agent has it.

*Acceptance:* resolver call count per run falls across a week on unchanged
sites; a deliberately broken selector self-repairs within one run and stays
repaired.

### Phase 4 — Site knowledge (domain skills)

`browser-harness` ships 97 hostname-keyed markdown playbooks — including
**etsy, ebay, amazon, shopify-admin, walmart, tiktok, xiaohongshu**. `goto_url()`
returns the matching filenames and the agent reads them before acting.

Our equivalent: `domain-knowledge/<host>/*.md`, injected into the
browser-automation node's context on navigation. Site *facts* (Etsy is behind
DataDome; Ctrip needs a full URL parameter schema) outlive DOM redesigns in a
way selectors never do.

Read theirs first — MIT, and the Etsy notes independently confirm our
fingerprint-browser direction.

## 5. What to borrow, by source

| From | Take | Phase |
|---|---|---|
| `workflow-use/schema/views.py` | the semantic step schema, near-verbatim | 1 |
| `workflow-use/healing/` | score / refine / retire a learned descriptor | 3 |
| `jev-ultrafast/model.py` | indexed action space; model returns an index, never a selector | 2 |
| `jev-ultrafast/snapshot.js` | one atomic DOM read per observation; freshness guards | 0/2 |
| `jev-ultrafast` | speculative parallel heads — several questions, one round trip | Jev track |
| `browser-harness` | `Emulation.setFocusEmulationEnabled` to keep background tabs rendering | now |
| `browser-harness` | daemon owns the CDP socket; everything else talks IPC | see §7 |
| `browser-harness/domain-skills` | 97 site playbooks, MIT — read now | 4 |
| *Web agents that actually learn* | knowledge is infrastructure, shared across runs | 3/4 |
| *Bitter lesson of agent harnesses* | **reject for our case** — see §7 | — |

## 6. The Jev experiment

Separate track from the roadmap. Do it in shadow mode; decide on evidence.

**Where to point it.** Not the customer reply — Jev cannot generate text. Point
it at **element resolution**: *"which of these observed elements is the send
button?"* That is a `choice` question over a small candidate set, which is
exactly its shape, and it sits on the critical path of the failure class we
care about. It is also Phase 2's resolver, so the experiment and the roadmap
share a seam.

**Shadow protocol.**

1. Wherever we resolve an element today, also build the indexed table and ask
   Jev. Change nothing about what executes.
2. Log: our pick, Jev's pick, Jev's probability and confidence, latency, tokens.
3. Ground truth is free — we already know whether the action that followed
   succeeded. Agreement is not the metric; **who was right when they disagreed**
   is.

**Feige is in scope** (decision 2026-09-19). We are still in alpha customer
piloting, so there is room to learn on the real surface rather than only on a
proxy for it -- and Feige is where the failure class actually lives.

**The condition is a kill switch, not a staging order.** Jev is very early, so
it rides along behind a flag that can be flipped off instantly, without a
build, without a restart:

- `ECAN_JEV_SHADOW=0|1` — off by default; shadow only, never executes
- flipping to `0` must take effect on the next resolution, not the next run
- any Jev error, timeout, or malformed answer disables it for the rest of the
  process and logs once -- it must never be able to slow or break a turn

The CN data-residency question is still open and still blocking *execution*:
`api.typesafe.ai` is US-hosted, so shadow mode on Feige sends page state
(including customer chat text) off-box. **Answer that before enabling it on CN
traffic at all** -- shadow or not. Until then, shadow on Etsy/eBay, and on
Feige only once residency is settled.

**Decide after ~1 week of real traffic:**

| signal | threshold |
|---|---|
| Jev right when we were wrong | materially > the reverse |
| p95 latency | < our current resolution path |
| cost | < the LLM call it would replace |
| calibration | high-probability answers are actually right |

**Kill criteria.** Confidently wrong on high-probability answers; or the CN
question can't be answered; or agreement is so high it adds nothing over the
cheap path.

**The `jev-ultrafast` ideas stay regardless of the outcome.** They are
architecture, not vendor: the indexed action space, a model that returns an
index rather than a selector, one atomic snapshot per observation, and
speculative parallel heads. If the Jev bake-off fails, Phase 2's resolver is a
strong LLM over the same indexed table -- one component swaps, the design does
not.

**Cost of the experiment is near zero** — `$0.042` per million input tokens
(vendor-stated), shadow only, no behaviour change, one env flag.

**A second, smaller probe worth running alongside:** their *speculative parallel
heads* trick. Several questions in one request, answered in parallel, where
*"adding questions barely changes the response time."* Our Feige turn asks
several things serially today (is this actionable? does it need a lookup? should
it escalate?). Even if Jev loses the element-resolution bake-off, that request
shape may be worth copying against any model.

## 7. What we are deliberately **not** doing

**Not adopting the bitter-lesson thesis.** *"Don't wrap the LLM. Don't wrap its
tools either"* — expose raw CDP, let the agent write its own helpers. That
argument is load-bearing on the driver being a frontier coding model. Ours are
DeepSeek/Qwen/gpt-4o-class, chosen *to control cost*. A weak model given raw CDP
is far worse than the same model given `click(index)`. Two further reasons: we
run unattended (an agent authoring browser code at 2am against a live store is a
different risk class), and we ship a 575 MB installer (a self-modifying harness
is not reviewable or versionable).

Note the same company contradicts it: `jev-ultrafast` is *maximally* wrapped.
They bet both ways depending on the driver. We are the constrained driver.

**Not migrating the browser layer.** `browser-harness` and `browsercode` are not
successors we can adopt — the first assumes an external coding agent, the second
is a TUI coding agent (peer product, not a component). Our `browser_node` +
`BrowserManager` + fingerprint profiles already *are* our harness, with identity
handling none of theirs has.

**But do reduce coupling.** `browsercode`'s `UPSTREAM.md` records that it forked
OpenCode, rewrote CDP in TypeScript, and **retired** the browser-harness
vendoring relationship. Browser Use's centre of gravity is a commercial
coding-agent product plus cloud. In that world `browser-use` the Python library
becomes top-of-funnel rather than where the engineering goes — a
maintenance-velocity risk on our actual dependency. `EC_Agent extends
browser-use Agent` inherits their *loop*, the most opinionated part. Loosening
that is cheap insurance. (We are pinned at 0.12.2; `workflow-use` already
requires 0.13.x, and `shutdown_browser` is already broken against 0.12's rename.)

## 8. TODO

**Now**
- [ ] Read the 8 marketplace domain skills in `browser-harness` (etsy, ebay,
      amazon, shopify-admin, walmart, tiktok, xiaohongshu, ctrip)
- [ ] Try `Emulation.setFocusEmulationEnabled` on the Feige detection tab

**Phase 1 — semantic targeting**
- [ ] Add `target_text` / `container_hint` / `position_hint` to the hook-bundle
      element schema; selectors become an ordered fallback
- [ ] Populate for the Feige sidebar/thread elements that broke this year
- [ ] Log `strategy=semantic|selector|failed` on every resolution
- [ ] One week of baseline on real traffic

**Phase 2 — resolver fallback**
- [ ] Indexed element table from the live DOM (extend `bu_normalize_page_state`)
- [ ] Resolver returns an index; executor resolves it to an observed node
- [ ] Bounded calls per run; loud logging when it fires

**Phase 3 — learn**
- [ ] Persist resolved descriptors per site+role, with scores
- [ ] Try learned descriptors before calling the resolver
- [ ] Retire descriptors that lose

**Phase 4 — site knowledge**
- [ ] `domain-knowledge/<host>/*.md`, injected on navigation

**Jev track**
- [ ] Shadow element resolution on Etsy/eBay behind `ECAN_JEV_SHADOW=1`
- [ ] Answer the CN data-residency question before any CN use
- [ ] Probe the parallel-question request shape against our current model

**Coupling**
- [ ] Map what `EC_Agent` actually uses from `browser-use.Agent`

## 9. What would invalidate this

- Semantic targeting turns out no more durable than selectors on Feige
  specifically (an Electron app, not a normal web page) — Phase 1's logging is
  designed to find this out before we build Phase 2.
- Jev's calibration is poor on our pages, making probability useless as a gate.
- The CN residency question closes off hosted decision models entirely, in which
  case Phase 2's resolver must be a local/cheap LLM rather than Jev. **The
  roadmap is deliberately written so that substitution changes one component.**
