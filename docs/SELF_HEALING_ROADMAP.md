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
`strategy=semantic|selector|failed`; no behaviour change.

**Not a one-week study** (revised 2026-09-19). The event this whole design
exists for cannot be scheduled -- Feige shipped twice in two months with no
notice -- so an evidence plan that depends on someone watching during the right
week is not a plan. The counters run *always*, which buys three things instead:

1. **Dead-branch detection now.** Which of the six parsers still fire at all.
   `legacy_hashed_wrap` is already suspected unreachable.
2. **The next redesign is measured automatically**, whenever it lands, with a
   before/after nobody had to be present for.
3. **A change detector.** A redesign has a signature: the parser that was
   resolving nearly every row resolves none. `detect_drift()` reads exactly
   that and warns `POSSIBLE SITE CHANGE` on the FIRST scan after the change --
   typically well before a customer is stuck. Today the first signal is a
   complaint, days late.

**And the hypothesis does not need new traffic — it is already in our history.**
Both past incidents say the same thing. From `6da0d3e09` (ws193): *"mt062-era
hashed selectors, **which the latest redesign broke**"*, and the fix put the
broad/fuzzy readers *first*, keeping the hashed ones as "harmless secondary".
`b3e7db40e` (ws189) is the same shape for the preview parser. Structural
selectors died; semantic-ish ones survived; each repair moved semantics
earlier. That is two real redesigns of evidence, which is why **L2 does not
need to wait for a third** -- it converts the next one from "stuck customer,
multi-day repair" into "slower, still working".

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

**On CN residency, and why the proxy is not the answer by itself**
(revised 2026-09-19): forwarding CN -> AWS -> `api.typesafe.ai` changes *who
calls the model*, not *what crosses a border*. The page state still leaves the
CN box; it takes a longer path with an extra intermediary. Adding a hop does
not reduce a cross-border transfer.

What the proxy genuinely fixes, and is worth doing regardless: the vendor key
stays server-side instead of on every customer desktop; a CN desktop may not
reach a US API at all, so proxying can make it *work*; one place to kill it
globally without a client rollout; one auditable chokepoint.

**What actually settles residency is not sending the content.** L2's decisions
almost never need it -- choosing which element is the customer-name field is a
judgement about shape and position, which is exactly the heuristic a site's own
parser already uses ("short, not a number, not a duration"). So the resolver
minimises by default: free text is replaced by a description of its SHAPE.

    {"index": 2, "role": "listitem", "text_shape": "short text, 2 words, letters"}

A model can still pick that row over a digits-only badge and a duration-like
timestamp, and no name, message or order number leaves the machine.
`ECAN_RESOLVER_SEND_CONTENT=1` opts back in where the data is known to be
non-personal.

Note this was a real defect, not a hypothetical: the first cut of
`Candidate.for_prompt()` sent `text` and `nearby` verbatim, which for a sidebar
row is the customer's name and a message preview.

**On latency:** the extra hop *adds*, it does not save. Jev's 178 ms becomes
178 ms plus two CN<->AWS round trips. The comparison that matters is
Jev-via-proxy against strong-LLM-via-proxy, since both pay the same hop. And
shadow mode need not cost anything at all -- it does not gate execution, so it
should be fire-and-forget and never awaited on a turn.

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

---

# Part II — Detection, ground truth, and the fleet loop

*Added 2026-09-19, after the Phase 1-3 code landed. Part I is about how a run
heals. This part is about how we KNOW a site moved, and what happens across
thousands of installs that each heal on their own.*

## 10. What we actually built to detect a site change

Three independent watchers, all feeding one permanent record
(`agent/ec_skills/browser_use_extension/drift_journal.py`). They differ in how
early they fire and how much they prove.

| Watcher | Where | Fires when | Lead time |
|---|---|---|---|
| **Deploy marker** | `SIDEBAR_SHAPE_JS` → `sidebar_build_marker` | the site's build-hash tokens rotate | earliest — the day they ship, change or not |
| **Structural fingerprint** | `SIDEBAR_SHAPE_JS` → `sidebar_row` | a DOM anchor a parser depends on appears/vanishes | the day they ship something that matters |
| **ws field watcher** | `ws_protocol_watch.py` | a core frame field stops being populated | the day the backend moves |
| **Strategy collapse** | `element_targeting.detect_drift` | a parser that was carrying an element resolves nothing | lagging — only once we are already failing |

The first three are leading indicators; the fourth is confirmation. That
ordering is the point: today the only signal is a customer complaining, which
is one step *after* the fourth.

### What the fingerprint contains

Anchor presence (`data_qa_id_nickname`, `name_line`, `legacy_hashed_wrap`, …
one per parser branch in `ROW_NAME_JS`), attribute names, tag names,
non-hashed class tokens, and a bucketed count of hashed ones. No text, no
attribute values except `data-qa-id` (a machine identifier), no build hashes
verbatim.

A test (`test_the_name_parser_and_the_fingerprint_probe_the_same_selectors`)
keeps the watched anchors tied to what the parser actually depends on. They
drifted apart once already — that is what ws193 was.

## 11. Ground truth — the honest part

**None of the four signals above is ground truth.** Every one has an innocent
explanation:

| Signal | Also caused by |
|---|---|
| fingerprint moved | logged out, wrong tab, partial render, different viewport, A/B bucket |
| deploy marker moved | CDN variant, a different set of rows sampled |
| core ws field silent | traffic mix (a window with no cards, no handovers) |
| strategy collapse | empty sidebar, page never loaded |

So what we have is **correlated evidence, not proof**, and the design says so
rather than implying otherwise. Three consequences worth being explicit about:

**1. We have no labelled positives.** Exactly two real events are known — the
June sidebar redesign (mt062/063) and the September rebuild (ws193, commit
`6da0d3e09`) — both diagnosed *after* the fact. The detector has never fired on
a real one. We cannot quote a false-positive rate, and should not pretend to.

**2. Local confidence comes from co-occurrence, not from any single signal.**
The journal timestamps all four kinds, so the question "did the site change or
is this machine broken?" is answered by whether they cluster:

- deploy marker + fingerprint + strategy collapse within one scan → very likely a real change
- fingerprint alone, nothing else → very likely this machine
- strategy collapse with no fingerprint movement → very likely this machine

**3. The only real ground truth is the run outcome.** Whether a customer got a
reply is the fact that matters; "the site changed" is just the usual cause.
Detection exists to shorten the path to a fix, never to replace the outcome as
the measure.

### Backtest before trusting it

The two known events are partly reconstructable: the commits that fixed them
record which selectors died. Building the before/after anchor sets from
`6da0d3e09` and the mt062/063 fixes and asserting the fingerprint would have
fired gives us **labelled positives today**, without waiting for a third
redesign. Do this before building anything on top of the detector.

## 12. The loop: ship → detect → heal → aggregate → ship

The decided architecture. Each step exists because of a specific failure of the
step before it.

```
  ┌─ 1. Build N ships with a BASELINE: expected shape + known-good descriptors
  │
  │  2. Machines compare against the SHIPPED baseline
  │     → drift detected on day 1, instead of silently adopting a redesign
  │       as "normal" (which is what a purely local baseline does on the
  │       first machine to see it)
  │
  │  3. Heal locally (L1 → L2 → L3). Fully autonomous; no cloud dependency,
  │     works offline, works for a CN install with no cloud access
  │
  │  4. Report the shape-only OUTCOME (~200 bytes, opt-in). Aggregate →
  │     corroboration count, heal rate, cost, descriptor durability →
  │     ranked list → a human picks
  │
  └─ 5. The winner becomes build N+1's baseline. Nobody has to heal again.
```

**Step 1 is the highest-value unbuilt piece** and needs no cloud at all. A
machine-local baseline can only detect a change *relative to what that machine
already saw*, so the first machine to meet a redesign records it as the new
normal and never flags it. Shipping the baseline makes every machine detect the
same event on day 1.

**Step 5 is deliberately human-gated.** See §14.

## 13. The three risks of per-machine healing

Each machine heals independently, and **they will not converge on the same
fix** — L2 is a model call, candidate tables differ by viewport and account,
and gray rollouts mean different machines legitimately see different pages.
That is acceptable. Uniformity is *not* the goal; forcing it would break
whichever machines are in the other bucket.

What is not acceptable is these three, in priority order.

### 13a. Unbounded, unobserved cost — **fix locally, now**

L2 is opus by decision ("no room for mistake"). A machine that never heals
retries forever, and nothing today stops it or reports it.

- Per-element, per-day cap on L2 calls (extend the existing `ResolverBudget`)
- Exponential backoff per descriptor, not per call
- **Circuit breaker**: after K failed resolutions for one element, stop calling
  L2 at all, go degraded and loud. Silence plus spend is the worst outcome
- Record spend per incident in the journal, so "what did this change cost us"
  is answerable later

This is a financial exposure, it is purely local, and it should not wait for
anything else on this list.

### 13b. The invisible tail — **make it self-reporting locally, proactive via fleet**

At an 85% heal rate, 1000 installs means 150 broken ones, each discovered by an
angry customer. Locally, without any cloud:

- An unhealed element for more than N minutes is a **degraded** state, surfaced
  in the `[AGENT-STATUS]` readiness ledger and the Agents-page dots — the
  customer sees red in their own UI rather than silently getting no replies
- `ecan support upload` includes the drift journal, so the bundle already
  carries the evidence when they do report it

That converts an invisible tail into a *reactive* but honest one. The fleet
layer is what makes it proactive.

### 13c. Fragile fixes rot silently — **refuse the fragile ones, measure lifetime**

A descriptor like `position_hint: "item 2 of 3"` works until that customer has
a fourth conversation. Locally every cycle looks like a success: heal, break,
heal, break, forever.

- **Refuse to promote descriptors that are fragile by construction.**
  `learned_targets.record_success` already refuses non-semantic ones; extend it
  to position-only descriptors, which depend on collection size
- **Record lifetime**: promoted at T, retired at T+X. A local history of
  descriptor-kind lifetimes lets a machine prefer kinds that have survived
  longest *on this machine*
- Fleet comparison makes this far stronger (N machines × lifetimes), but the
  local version is already worth having

## 14. The fleet layer — what it is, and what it must never be

**What it is:** a small, opt-in, append-only stream of shape-only outcomes.

```json
{"site": "...", "element": "...", "old_strategy": "...",
 "new_descriptor_kind": "...", "healed": true, "attempts": 2,
 "l2_calls": 1, "build": "...", "marker_digest": "..."}
```

~200 bytes. No customer text, no selectors, no credentials — the data is
already shape-only by construction, which makes this the one category of local
data that does not collide with the local-only policy. It is still behavioural
(it reveals that an install runs a given site, and when), so: **anonymous
aggregate by default**, identified only for pilots who opt in.

It buys exactly four things:

1. **Corroboration → ground truth.** 200 machines seeing the same fingerprint
   delta within six hours is the site. One machine seeing it is that machine.
   *This is the only way to make that distinction*, and it is the strongest
   argument for the fleet layer — stronger than the cost and tail arguments.
2. Heal rate, and therefore the size of the tail
3. Cost per incident
4. Descriptor durability ranking → the next build's baseline

**What it must never be: a control plane.** It never pushes anything to a
machine.

### Why the rev stays human-gated

Auto-shipping fleet-derived descriptors is rejected on three grounds:

- **Supply chain.** Descriptors derive from page content, and pages are
  attacker-influenceable. An auto-rev path means a malicious page could in
  principle steer what every install targets.
- **Untested.** A fix that ships without anyone having run it is unverified by
  definition.
- **Unnecessary.** Nearly all the value is in *ranking* the candidates. A human
  merging the winner costs days, not months, and removes the catastrophic case.

## 15. Sequencing

0. **Rescue the emulation harness into version control** — see
   `EMULATION_HARNESS.md` §7. It is the validation foundation and it currently
   exists on one working copy, in no branch.
1. **Consume the site's distress signal** (§17) — `ws_reader.py:180` discards
   the wait warnings Feige already sends us. ~30 lines, and it is the only
   source of labelled failures we have in production.
2. **Layout-flip + mutation knob on the emulator**, then a detector stress
   harness (`EMULATION_HARNESS.md` §6a). Detection rate and false-positive rate
   per mutation class — better than the git-archaeology backtest, which becomes
   the fallback.
2b. **ws frame mutation replay** — labelled ws positives without a WS server.
2c. **Cost controls + circuit breaker** (§13a). The exposure is LATENT, not
   live: `resolver_enabled()` is off by default and L2 is not wired into any
   site path yet. This must land before we turn it on, not before the above.
3. **Shipped baseline** (§12 step 1) — local, makes day-1 detection real
4. **Degraded state surfaced locally** (§13b)
5. **Fragile-descriptor refusal + lifetime tracking** (§13c)
6. **Fleet layer** (§14) — *only after the local detector has caught one real
   change.* Aggregating thousands of machines through an unvalidated detector
   is building on sand.
7. Never: automatic rev.

## 17. Per-site declared signal sets

*Decided 2026-09-19. This is the organising idea the rest of Part II hangs off,
and it is mostly a refactor rather than an invention.*

### The idea

Each site bundle **hand-declares its own first-signal tripwires** — the small
set of cheap, site-specific checks that fire before anything else when that
site changes or when we start failing on it.

Platform cannot know what failure looks like on a given site. Whoever built the
bundle does: they know that `用户已等待超30秒` means we missed someone, that
`qa-conversation-chat-item` is the load-bearing anchor, that the unread badge
total should track our in-flight count. That knowledge currently exists as
scattered constants and tribal memory. Declaring it makes it one table.

### It already exists, undeclared

The twelve anchors hard-coded in `SIDEBAR_SHAPE_JS` — `data_qa_id_nickname`,
`name_line`, `legacy_hashed_wrap`, `preview_msg_content`, … — *are* a
hand-crafted per-site signal set. They are just not declared as one: they are
not extensible without editing JS, they are not enumerable by anything else,
and `tmall_chat` cannot reuse the mechanism. That is the gap this closes.

### The split

Same boundary as everywhere else in this work:

- **Platform** owns the *vocabulary*: what a signal is, how it is evaluated,
  how often, what severity means, and how a trip is recorded (into the drift
  journal). Business-free — it never knows a site.
- **The bundle** owns the *list*: the actual selectors, strings and thresholds,
  hand-written by whoever knows that site.

### Four kinds

| Kind | Asks | Example (feige_chat) | Value |
|---|---|---|---|
| **distress** | is the site itself telling us we failed? | `用户已等待超30秒` on the ws system-event channel | closest thing to ground truth; free |
| **anchor** | does a feature a parser depends on still exist? | `[data-qa-id="qa-conversation-nickname"]` present on rows | fires the day they ship |
| **invariant** | do two independent observation paths agree? | unread badge total ≈ our in-flight conversation count | catches silent misses |
| **liveness** | is something that should happen still happening? | ws frames seen in the last N minutes; scans returning rows | catches total blindness |

`distress` and `invariant` are the two that address the dangerous case — a
customer arriving and us never noticing — because they do not depend on us
having attempted anything. `anchor` and `liveness` generalise what §10 already
does.

### What it buys

1. **Site #2 becomes a table, not a project.** Adding `tmall_chat` or a
   marketplace skill means filling in declared signals, not writing new
   detection code.
2. **It documents what we depend on.** One enumerable place answering "what do
   we actually rely on about this site?" — which is exactly what nobody could
   answer during ws193.
3. **It makes the detector testable.** The stress harness (§15 step 2) can
   enumerate a site's declared signals and assert each one trips when its
   condition is broken. A signal nobody can trip on demand is a signal nobody
   should trust.
4. **Severity becomes declarable.** A dead `legacy_hashed_wrap` is
   uninteresting; a dead `data_qa_id_nickname` is an incident. Today both are
   the same line in a report.

### Note on the distress signal

`ws_reader.py:180` currently does:

```python
continue  # .8 may be a JSON system-event string; skip here
```

The site emits its wait warnings on that exact channel, and we discard them.
That single unconsumed signal is the highest-value item in Part II: it is
supplied by the site, costs nothing, is independent of every parser we own,
and turns every real miss into a **labelled failure** — the labelled data §11
says we do not have.

## 18. Measured detector coverage (2026-09-19)

§11 said we had no labelled data and could not quote a detection rate. We can
now, without waiting for a third redesign.

`tests/unit/test_detector_stress.py` drives the **real** fingerprint
(`SIDEBAR_SHAPE_JS`, through `tools/emulation/fingerprint_probe.js`) and the
**real** decision path (`drift_journal.note_shape`) over the row layouts this
site has actually shipped (`tools/emulation/layouts.json`) plus synthetic
mutations. Nothing is reimplemented — a ported copy of either half would
measure the copy, which is the mistake ROW_NAME_JS exists to prevent.

### Both real events are caught

| Event | Change | Detected |
|---|---|---|
| June redesign (mt062/063) | hashed wrappers gone, semantic prefixes in | yes |
| September rebuild (ws193) | nickname `data-qa-id` no longer emitted | yes, and the delta names the vanished anchor |

### Coverage by class of change

| Mutation | Detected | Correct? |
|---|---|---|
| `drop_attribute` — a machine id stops being emitted | yes | required |
| `drop_anchor_element` — the element a parser keys on disappears | yes | required |
| `rename_hashes_all` — a rotation that also kills an anchor we name literally | yes | required |
| `add_attribute` — the site starts emitting something new | yes | good |
| `rewrap` — an extra wrapper appears | yes | good |
| `retag` — `div` becomes `section` | yes | good |
| `rename_hashes_routine` — rotation that leaves our anchors alone | **no** | **required** — see below |
| `renest` — same elements, one level deeper | yes | closed 2026-09-19, see §18a |

### The two negatives are not the same

`rename_hashes_routine` **must not** fire. The site rotates build hashes on
every deploy; reporting that on the structural record would write a phantom
change per deploy and bury the real ones. The deploy marker catches it instead
(§10), which is the whole reason the two live under separate keys.

Note the distinction the harness forced: rotating a hash we depend on *by
literal name* (`.Jv6FtqUv5VoYARd2pp4y`, `.MP1bk3ccfHC9V2SnPCGD`) is **not**
routine — that parser branch just died, and it is correctly reported. Only a
rotation that leaves those alone is noise.

### §18a. The re-nesting gap, and why it was worth closing

`renest` was a blind spot: the fingerprint recorded *sets* of names, not depth,
so moving elements a level deeper was invisible. That looked mostly harmless,
because it is invisible to `ROW_NAME_JS` too — it uses `row.querySelector(...)`
throughout, which is depth-agnostic.

The exception is what made it worth fixing: **`ROW_PREVIEW_FALLBACK_JS` walks
leaf nodes and compares `parentElement`**, so it *is* depth-sensitive. An extra
wrapper between leaves means siblings that used to share a parent no longer do,
and the preview comes back empty — with every class and attribute unchanged, so
a presence-only fingerprint stays silent. That is precisely the ws189 failure:
`skipped={'empty_preview': N==rows}` while the scan itself looked healthy.

So the fingerprint now records the **minimum depth of each anchor below the
row**. The minimum, not the depth per row: row variants legitimately nest
differently (a tagged row sits a level deeper than a plain one), and taking the
minimum keeps that from flapping the fingerprint on every scan while still
moving when the site inserts a wrapper above them all.

Two couplings this creates, both pinned by tests:

* The shipped baseline had to be regenerated. Any change to the fingerprint's
  shape makes every install report a day-one difference against a stale
  baseline — worth remembering before the next field is added.
* A test asserts the preview reader still compares `parentElement`. If it stops,
  this watch is no longer paying for itself; if the watch is dropped while the
  reader still does, the gap reopens silently.

### Three detector bugs the harness found immediately

All three would have produced false or missing records in production, and none
was visible by reading the code:

1. **`prefix-HASH` classes were treated as stable.** The hash test required no
   separator (`^[A-Za-z0-9_]{16,}$`), so `msgContent-JqEWJs` — *precisely* the
   scheme the June redesign introduced — was recorded verbatim. Every routine
   deploy would have fired a structural change. Now the prefix is kept as
   structure and the suffix counted as a hash.
2. **The hashed-class figure was an absolute count** over a variable number of
   sampled rows, so scroll position alone moved the fingerprint. Now normalised
   per row.
3. **The row element was invisible to itself.** `querySelectorAll('*')` returns
   descendants only, so the row's own attributes were never recorded — and
   `data-qa-id="qa-conversation-chat-item"`, the selector the entire scan
   depends on, lives there. A rename of it would have gone unrecorded.

This is the argument for the harness in one paragraph: the detector looked
correct, had tests, and was wrong in three ways that only showed up when
something drove real layouts through it.

### Still to do here

- The emulator renders its rows from hard-coded HTML in `static/app.js`; the
  layouts now live in `layouts.json` but only the harness reads them. Wiring the
  page to render from the same file gives browser-fidelity runs of the same
  cases (`EMULATION_HARNESS.md` §6a).
- The harness exercises `renest` against the fingerprint, but still not against
  the preview reader itself — it proves the change is *detected*, not that the
  reader would have broken. Driving the real reader over a re-nested row would
  close that last step.

## 16. What would invalidate Part II

- The fingerprint proves noisy in practice — fires on viewport or A/B variation
  often enough to be ignored. The backtest in §11 is the cheap way to find out.
- The two historical events turn out not to be reconstructable from git, in
  which case there is no labelled data and §15 step 6 has to wait for a real
  event.
- Customers decline the telemetry opt-in at a rate that makes corroboration
  statistically useless, which collapses §14's main argument and leaves the
  fleet layer as a cost dashboard only.
