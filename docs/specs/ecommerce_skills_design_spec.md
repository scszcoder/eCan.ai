# E-Commerce Operating Playbooks & eCan.ai Skill Design Spec

> Repo-safe copy: reference-deployment specifics (stores, profiles, agent/skill/task/proxy ids, owner email, user paths) are replaced with `<PLACEHOLDER>` tokens. The real values live in KB records and local config (B8.3 rule 6).

| | |
|---|---|
| **Doc version** | **v1.0, frozen for build** (review round 9 applied: OQ-G1 role agents, OQ-G5 Rufus simulated only, OQ-G18 default list stands, owner edits later). Later changes are v1.x rows in E4 |
| **Date** | 2026-11-09 |
| **Author** | Claude (for <OWNER_EMAIL>) |
| **Status** | FROZEN v1.0 (2026-11-09): architecture + planning only, no code. Implementation starts on <BUILD_HOST> (E1.1) |
| **Source corpus** | `C:\ideas\ecommerce\` (55 files; 7 are exact duplicates) |
| **Target runtime** | eCan.ai (local repo `C:\\Users\\<USER>\PycharmProjects\eCan.ai`): Flowgram skills, LangGraph state, MCP tools, browser-use nodes, A2A agents |

## How to review this doc

- **Part A** distills the corpus into per-platform playbooks. This is the knowledge that will be baked into system prompts, variables and rule tables. Check that it is faithful and that the thresholds are numbers you agree with.
- **Part B** is the architecture: layers, conventions, canonical data shapes, the shared variables catalog and the tool catalog. Push back hardest here, because everything else depends on it.
- **Part C** is the skill to-do list plus a design spec for each skill: inputs, outputs, data shapes, flow, guardrails, acceptance tests and open questions.
- **Part D** is the Manager skill, covering orchestration, task lifecycle, evaluation and escalation.
- **Part E** covers the roadmap, global open questions and the review log.

Item IDs (`A2.3`, `AMZ-05`, `OQ-G7`, …) are stable, so feedback can point at them directly ("AMZ-05: change the negate threshold to 25 clicks").

Markers used throughout:
- `[SRC:tag]` = from the corpus.
- `[INF]` = my inference or industry default, not in the corpus. Confirm or replace these.
- `⚠` = risky or ToS-sensitive.

---

## 0. Executive summary

1. **The corpus.** It has about 12 real SOPs, about 30 course outlines that are mostly topic lists without the method, and 4 data files. The most valuable sources are:
   - Amazon: the ads rule trees (xmind + "10 strategies"), the ad-dependency check, the prompt library with the Rufus→GEO→compliance loop, and the 90-day GTM calendar.
   - TikTok Shop: the 12-daily-tasks SOP, the GMV Max SOP + cheat sheet, the "traffic but no conversion" tree, and the content 4-elements SOP.
   - Reddit: the full Reddit SOP.
   - DTC, Google/Meta, Walmart and visual: outlines only. Their skills will rely more on `[INF]` defaults that you need to confirm.
2. **The key design principle, taken from the corpus itself.** AI reads, analyzes, recommends, drafts and alerts. Humans approve every write to Seller Central, ad accounts, prices and outbound messages. The architecture encodes this as approval levels (B3.4). The material is consistent on it: "read-only AI ops", one change at a time, and every change carries evidence, a baseline and a review date.
3. **Architecture.** There are 5 layers:
   - L0: data/connectors.
   - L1: deterministic MCP tools for math, rules and parsing. Numbers are never left to the LLM.
   - L2: LLM worker skills.
   - L3: browser-automation skills.
   - L4: one **Manager** skill that runs declarative **Playbooks** (DAGs of skill calls) on schedules or events, dispatches to role agents over A2A, verifies results, routes approvals and scores agents.
4. **Deliverable (v0.5).**
   - **56 behaviours** (the IDs in Part C), implemented as **about 24 shop- and product-agnostic capability skills** plus **platform packs**: data bundles of rules, recipes, policy, prompt fragments and KPIs (B9.2).
   - **Plus:** 6 existing skills adopted through adapters (B8), about 45 MCP tools, about 30 canonical data shapes, and the browser recipe/extractor registry (B6).
   - **The Manager is a chat agent** whose standing goal is the user's profit (D9, B9.5).
   - **First build (P0 + P1):**
     - The chat Manager.
     - Store onboarding.
     - The profit ledger.
     - Shopify + Google Ads.
     - The first experiment → learning loop.
5. **Excluded tactics.** The corpus contains several tactics that are ToS violations: fake orders/补单, account matrices/anti-linkage, junk-content A+ unlocking, Reddit vote rings and sockpuppets, counterfeit "brand interception", and scraping and re-creating competitor creative. They are listed in A9 and **deliberately not turned into skills**.
6. **v0.2 decisions (review round 1).**
   - **Data comes in through the browser (OQ-G2).** Logged-in browser profiles per store are the only data path for the MVP. Acquisition runs in three tiers, cheapest first:
     - T1: deterministic **recipes** that download reports.
     - T2: reviewed in-page **JS extractors** run via `in_browser_execute_javascript`.
     - T3: the LLM browser agent, used only as a fallback. Each T3 rescue produces a patch proposal for a human to review.
     - The full design is in B6. A new skill, X-12, maintains the registry. SP-API, ERP and other APIs are deferred.
   - **Approvals go out by email + SMS (OQ-G4).**
     - Each approval request sends a signed, single-use link to a mobile approval page; high-risk actions also need an SMS PIN.
     - The same page handles "needs input" prompts, e.g. "log in to profile X" or "enter OTP".
     - The full design is in B7, and X-09 and X-10 are updated.
7. **v0.3 decisions (review round 2).**
   - **Approval page hosting (OQ-G13):** eCan cloud.
   - **Providers (OQ-G14):** AWS SES for email and AWS SNS for SMS.
   - **In-page fetch (OQ-G15):** JS extractors never call `fetch`; they read the DOM and the page's own export buttons only.
   - **Approver (OQ-G16):** the user only. The user can delegate approvals by granting the Manager permission to read a PIN file (B7.1).
   - **Existing work (OQ-G17):** 6 skills already built on <BUILD_HOST> (Amazon/Shopify/Etsy/eBay daily checks, Review Miner, Idea Reality Check) plus report code and signed-in store profiles. They are surveyed in B8 and adopted. Their conventions now override this spec where the two differ, eBay and Etsy join the platform list, and AMZ-11 (account health) moves to P1.
8. **v0.4 decisions (review round 3).**
   - **Shopify + Google Ads is the first priority.**
     - DTC-03 (Google Ads) is expanded.
     - Three new prerequisite skills sit around it: **DTC-09** (Merchant Center feed), **DTC-10** (conversion-tracking audit) and **DTC-11** (Shopify product optimizer).
     - A new playbook, A10, covers Shopify + Google Ads.
   - **eBay and Etsy get growth skills (OQ-G20 yes):**
     - **EBY-01** listing optimizer, **EBY-02** Promoted Listings, **EBY-03** seller-standards recovery.
     - **ETS-01** listing SEO, **ETS-02** Etsy Ads.
     - Playbooks A11 and A12 cover them.
   - **New cross-platform skills:**
     - **X-14** store growth diagnosis: the entry point for "make the stores sell".
     - **X-13** buyer-message drafter: response rate matters on eBay and Etsy.
   - **All five platforms are live but selling poorly (OQ-G19).** The roadmap is now growth-first:
     - P1: Shopify + Google.
     - P2: marketplace basics (health, listings, messages).
     - P3: marketplace ads + creative.
     - P4: research and expansion.
     - P5: scale and autonomy.
   - **OpenAI is the fallback model (OQ-G6).**
   - **The build happens on <BUILD_HOST>** once this doc is final (OQ-G21).
9. **v0.5 principles (review round 4).**
   - **Shop- and product-agnostic.**
     - No skill hard-codes a store, product, category, URL or profile.
     - Everything specific is discovered at onboarding (X-15) or learned, and lives in the knowledge base. Specific values resolve in this order: immutable core → user instructions → learned values → pack defaults → corpus priors (B9.3).
   - **Learns and corrects itself toward making money.**
     - The Manager's objective is **contribution profit**, measured by the profit ledger (X-16), within your constraints.
     - It forms hypotheses, designs experiments (MGR-04) for operator agents to run, and records results as `Learning`s.
     - It adjusts thresholds, prompts, playbooks and recipes through a versioned change pipeline (MGR-05): offline eval → shadow → canary → promote.
     - An **immutable core** (red list, approval rules, budgets, user instructions) can never be self-modified (B9.6–B9.8).
   - **The Manager is a chat agent.** It talks with you to work out what you need, interviews you during onboarding, answers with evidence, takes instructions ("teach"), runs work and reports back in the chat (D9).
   - **Many open questions move to runtime.** Budgets, categories, account states and similar are now asked by the Manager in chat (E2).
10. **v0.6 decisions (review round 5).**
   - **A product for every seller (B9.10).** The author's stores are only the reference deployment (B8).
     - Every record is tenant-scoped.
     - There are no owner-specific defaults.
     - The store owner provides product costs (COGS), through several easy routes.
   - **Chat (OQ-G25):** eCan chat first. WhatsApp and WeChat are added later through a channel-agnostic message envelope.
   - **In-chat approvals (OQ-G26):** low- and medium-risk actions can be approved in chat. High risk still goes through the portal + PIN.
   - **Exploration settings (OQ-G27):** the 20% budget share and 2 experiments per store are per-tenant defaults the owner changes in chat at any time.
   - **Tuning grant (OQ-G28):** none at launch.
   - **Profit (OQ-G29):** contribution includes **AI cost** (tokens + browser runs) as its own line.
11. **v0.7 decisions (review round 6).**
   - **No cross-seller learning (OQ-G30).** Learnings stay within one tenant.
   - **Shared AI cost (OQ-G31)** is allocated to stores pro rata by gross sales.
   - **Single owner per tenant in v1 (OQ-G32).**
   - **Local-first data (OQ-G33).** Tenant data stays on the seller's machine, and the cloud holds only what must be reachable remotely (B9.10).
12. **v0.8 decision (review round 7): model tiers (OQ-G6b, B3.7).**
   - The **Manager** (chat, planning, experiment design, evaluation, ChangeProposals) runs on `gpt-6.1-sol`.
   - **General web interaction** (browser steps, extraction, verification, routine drafting) runs on `gpt-6-luna`.
   - **Exploratory work** starts on luna and may **escalate to `gpt-6.1-terra`** on defined triggers, within a capped budget, with every escalation logged and costed.
13. **v0.9 decisions (review round 8).**
   - **Language (OQ-G8):** each store has a language selection. Owner-facing text follows the store's owner language; customer-facing text follows the store's customer language(s), and replies match the buyer's language (B3.3 `StoreProfile.languages`).
   - **Storage (OQ-G10, B9.10):** local SQLite (records) + Parquet/DuckDB (report tables) is the source of truth; the seller can turn on cloud **backup** or **sync** (summaries mirrored to eCan cloud).
   - **Legal entities (OQ-G11):** the reference deployment is one entity; the design carries `legal_entity_id` per store for sellers who have several.
   - **Playbooks (OQ-G12):** JSON is the source of truth, with a generated Markdown view; edits go through the Manager chat and a ChangeProposal.
   - **Buyer replies (OQ-G24):** the agent sends replies itself. It holds a reply for the owner only when it is not confident, or when money is involved in a dispute and the answer is not clearly covered by store policy (X-13 auto-send policy).
14. **v1.0 freeze (review round 9).**
   - **Agents (OQ-G1):** role agents shared across stores; browser-operator instances are per store/profile.
   - **Rufus (OQ-G5):** simulated only. AMZ-03b and the `amz.rufus.ask` recipe are **not built**; AMZ-03 keeps `mode: "simulated"`.
   - **Never-delegated list (OQ-G18):** the B7.1 list stands as the default. The owner will edit it later; it is owner-editable config in the immutable core, never changed by an agent or a ChangeProposal.

---

## 1. Source corpus & quality map

| Tag | File | Type | Value |
|---|---|---|---|
| ADS10 | 精细化技巧——亚马逊广告10大策略技巧.docx | SOP | ★★★ bids, budgets, placements, dayparting, waterfall |
| ADSXM | 亚马逊广告进阶优化（含SP+AMC组合打法）.xmind | rule tree | ★★★ ACOS cascade, negate/bid matrix, AMC |
| DEP | 广告依赖度自查与优化.pdf | SOP | ★★ ad-dependency gap test |
| ADSC | Codex & 亚马逊广告高阶操盘SOP.pptx + Codex AI 广告高阶自动化搭建SOP【杭州】.pdf | outline | ★★ 5-layer ad structure, 5-step diagnosis, experiment/review cards |
| AIAD | AI赋能亚马逊推广.pdf | outline | ★★ Rufus/COSMO, AI daily-ad loop, review alerts |
| ROI | ROI快速测算表.xlsx | calculator (formulas lost) | ★★ unit-economics & yearly cash model structure |
| PLC | 广告位报告-每日明细.xlsx | data | ★★ placement report schema (LingXing-style export) |
| PL | AI运营Prompt模板库(1).docx | prompt library | ★★★ 13 templates + Rufus→GEO→compliance loop |
| CDX | Codex AI Agent 亚马逊全链路自动化实战 (×2) + 实操陪跑 + 90天陪跑 + AI时代 + 3000分钟 | outline | ★★ 7-module automation architecture, read-only red lines |
| TEAM | AI驱动-亚马逊团队管理&绩效激励.pdf + 亚马逊各部门薪资范畴以及考核标准.xlsx | HR | ★★ role ladder, KPIs → agent scorecards |
| DEV | 亚马逊高阶产品开发+运营…85%.pdf + 开发+推广+cosmo…pptx | outline | ★★ intent-led selection, feasibility checks |
| NSP | 非标品产品开发课SOP大纲.docx | outline | ★ non-standard product pipeline |
| SHEET | 亚马逊调研表和分析表及尺寸工具包.xlsx | template | ★★★ research sheet schema, demand estimation |
| KW | 亚马逊TOP5万选品关键词数据.xlsx | data (2019) | ★ ABA schema only, data stale |
| RC | Rufus+Cosmo，亚马逊高阶运营.pptx | outline | ★★ visual hammer, machine-readable listing, off-site "fishing" |
| GMV | 拆解年度GMV 5亿+爆品操盘手全周期SOP.pdf | outline | ★★ lifecycle stages, keyword roles, cadence |
| GTM | 90天新品GTM上市作战日历 .docx + .xlsx | SOP | ★★★ W-12→W0→W+30 calendar, checklist, dashboard |
| APLUS | 新店铺快速刷出高级A+ SOP | ⚠ tactic | excluded |
| RESTR | 警惕违规！亚马逊受限商品与申诉指南 | SOP | ★★★ restricted classes, trigger words, appeal path |
| SCAN | 2026亚马逊扫号预测&安全防控.pptx | outline | ★ (contains ⚠ black-hat items) |
| ADDR | 二审…25位官方地址编码.docx | SOP | ★★ address consistency |
| WMT | 沃尔玛0-1运营增长实战SOP.pptx | outline | ★★ Walmart migration, pricing, WFS, reports |
| TT12 | TikTok Shop操盘手每日十二项工作SOP | SOP | ★★★ |
| TTNC | TikTok广告有流量无成交排查SOP | SOP | ★★★ decision tree |
| TT4E | TK带货素材四要素执行SOP | SOP | ★★★ content brief/storyboard/QC |
| GMVM | Gemini 3 Pro速通GMVMax冷启动SOP + GMVmax高阶技巧.xlsx | SOP | ★★★ |
| TTRS | TikTok逆向选品秘籍 | outline | ★ (contains ⚠ counterfeits) |
| TTC | TikTok & Gemini 3 Pro + Codex TikTok 特训 | outline | ★★ creator CRM, BF planning |
| SCRIPT | 素材爆破！爆款脚本+低成本拍摄剪辑 (×2) | SOP (partial, image pages) | ★★ matrix scripts, compliance list |
| VIS | AI做图PS创成式填充 + Codex视觉营销 + 视觉优化旗舰店 | SOP/outline | ★★ visual brief pipeline, main-image rules |
| RDT | 2026_Reddit独立站推广超全实战指南.docx | SOP | ★★★ the most complete SOP in the corpus |
| DTC | 独立站8大知识板块 + 千万美金店铺 pptx/pdf + 365天陪跑 (×2) | outline | ★ |
| GMETA | 谷歌广告&Meta高阶玩法-Eren.pptx | outline | ★★ Search 3-series, PMax 4-tier, ABO→CBO→DPA |
| SEO | Ahrefs/Semrush查找反链 | click-path | ★ |
| SOC | 品牌化社媒全链路打造操盘手sop + 品牌社媒运营思路 | outline/article | ★★ founder-led, Partnership Ads, 5-channel model |

**Gaps that skills must fill with `[INF]` defaults and flag for confirmation:**
- Meta/Google numeric thresholds.
- TACOS targets.
- Backend attribute checklist.
- POA template.
- Creator scoring weights.
- Selection scoring weights.
- Walmart thresholds.
- SKU health tier definitions.

---

# PART A: Distilled per-platform playbooks

## A1. Cross-platform operating principles (apply to every skill)

| # | Principle | Encoded as |
|---|---|---|
| P1 | **Read-first AI.** AI reads, analyzes, recommends, drafts and alerts. Humans approve writes. [SRC:CDX, TT12, AIAD] | approval levels (B3.4) |
| P2 | **Compute, don't guess.** Every number comes from a deterministic tool, never from LLM arithmetic. [SRC:GMVM "compute with Python, don't guess"] | L1 calc tools; LLM nodes receive pre-computed tables |
| P3 | **Fact discipline.** Every change records object ID, evidence, before/after, effective time and review date. [SRC:TT12] | `DecisionRecord`, `ProposedAction` shapes |
| P4 | **One variable at a time.** At most 2 ad adjustments per object per day. Don't toggle on hourly swings. [SRC:GMVM, TT12, ADSC] | Manager change-throttle guard |
| P5 | **Sample guard.** Below the minimum sample, the verdict is "observe" with a review date, never act. [SRC:TTNC ≥1000 impr & ≥30 clicks; ADSXM 15/30 clicks] | `thresholds` var, `status: observe` |
| P6 | **Stage before tactics.** Identify the lifecycle stage first (test/launch → growth → stable → clearance, or stop-bleed → stabilize → scale) and then pick the tactic. [SRC:GMV, ADSC] | `lifecycle_stage` input to every ads/listing skill |
| P7 | **Decision output format.** Judgment, Evidence, Cause, Action, Acceptance criteria. [SRC:ADSC] | `DecisionRecord` |
| P8 | **Experiment card.** Problem, Hypothesis, Baseline, Action, Window, Success threshold, Stop-loss. [SRC:ADSC] | `ExperimentCard` shape + registry |
| P9 | **No double counting.** Never sum ad-attributed revenue into store GMV. Creator, video and ad layers overlap. GMV Max ROI includes organic. [SRC:TT12, GMVM] | metric definitions in calc tools |
| P10 | **Compliance gate on all customer-facing text.** [SRC:PL, RESTR] | `x_compliance_gate` mandatory step |
| P11 | **Data provenance.** Every claim like "X×, Y%" needs a source, or it is marked "needs supporting data". [SRC:PL] | `claims[]` with `evidence_ref` in `ProductFacts` |
| P12 | **Cadence ladder.** Daily: anomaly, act or don't act. Weekly: structure review. Monthly: allocation. Quarterly: direction. [SRC:GMV, ADSC] | Playbook schedules (D4) |
| P13 | **Agnostic by construction (v0.5).** Skills take a `store_id` and discover or resolve everything else. No store, product or category literals in skills or prompts | B9.1–B9.4 |
| P14 | **Learn toward profit (v0.5).** Every recommendation is a hypothesis with an expected effect. Outcomes are measured and kept as `Learning`s, and priors (corpus, `[INF]`) are replaced by evidence over time | B9.5–B9.8, MGR-02/04/05 |

## A2. Amazon playbook

### A2.1 Product selection & development
- **Intent-led selection.** Start from search intent clusters (scenario / persona / problem), not from category trees. Each cluster is a sub-market, and each sub-market is a product line. [SRC:DEV]
- **Feasibility checks** [SRC:DEV]:
  - BSR volatility (life stage).
  - Price-volume trend (profit ceiling).
  - Keyword trend + seasonal drift.
  - Monopoly (head-brand cadence, top-3 click share).
  - Price tier × share.
  - Review barrier vs achievable share.
  - Satisfaction gap (rating sensitivity).
  - Abnormal review/sales risk flags.
- **Demand estimate** [SRC:SHEET]:
  - Total sales ≈ reviews ÷ review rate (1–5%, default 3%).
  - Cross-check against rank-based estimates.
  - Seasonality check via Google Trends is mandatory (worked example: a pool float drops to 0 outside May–Aug).
- **ABA concentration reading** [SRC:KW, INF]:
  - Low top-3 click share means a fragmented, enterable market.
  - Conversion share ≫ click share means a strong incumbent.
  - Exclude brand/IP terms.
- **Unit economics** [SRC:SHEET, ROI]:
  - Price − (COGS + first-mile + FBA + commission 15% + returns + promo + other) = net.
  - Track platform margin, net margin, and **cash efficiency = profit ÷ cash used**.
  - Volumetric weight: L×W×H ÷ 6000 (air), ÷ 5000 (express).
- **Differentiation** [SRC:DEV, PL 3-A/3-B]:
  - Cluster competitor reviews and find "semantic conflicts" (the same feature praised and criticized).
  - Build intent personas and a doubt map.
  - Write an expert-editor comparison.
- **Non-standard products** [SRC:NSP]:
  - Pipeline: trend → score (long-term vs short-term) → elements → go/no-go.
  - Product matrix: basic / trend / profit / test SKUs.
  - Health metrics: CTR, CVR, sell-through, returns.
  - Extend a hit via colors, functions, scenarios and bundles.
- **Price matrix** [SRC:DEV]: traffic SKU + profit SKU + anchor SKU, priced by variation.

### A2.2 Listing (A9 + COSMO + Rufus/GEO)
- **Formats** [SRC:PL]:
  - Title ≤200 chars, with core keywords + the differentiator up front.
  - 5 bullets of 10–25 words each, in **Benefit → Feature → Advantage** form.
  - Description 150–200 words. The source says 字 in one place and words in another; words assumed. OQ-A1.
- **Hard bans** [SRC:PL]:
  - Competitor brands.
  - Unsupported superlatives (best/only/most/fastest/#1/100%/top-rated/best-selling).
  - Promo words (affordable/cheap/sale/discount).
  - Uncertified eco claims.
  - Health/medical claims (cure/prevent/disease, and hair-care "reduces breakage").
  - Antimicrobial words without registration.
  - Time-sensitive words (now/latest/new).
  - External contact info.
  - Non-ASCII symbols (℉ × ° → —).
- **Certification format** [SRC:PL]: `[Body] [Cert] [Year]`, e.g. "FCC Certified 2025".
- **COSMO** [SRC:RC, AIAD]:
  - The listing must answer **who it is for, which scenario, and what problem it solves**.
  - Translate specs into solutions for the "origin audience".
  - Fill every backend attribute (machine-readable), and embed scenario and use-case terms.
- **Visual hammer** [SRC:RC]: one image/video that ties value to aspiration in under 1 second, consistent across images, video, A+ and the store.
- **Rufus loop** [SRC:PL]: probe (10 buyer-voice questions) → research (ask Rufus live) → GEO audit (score /100) → rewrite → compliance gate.
  - Question allocation by listing symptom, 13 slots in total that the model trims to 10:
    - Scenario ×3
    - Decision drivers ×3
    - Comparison ×3
    - Friction ×2
    - Shopper language ×2
  - GEO scorecard:
    - Scenario Coverage 20
    - Audience Match 15
    - Decision Drivers 20
    - Positioning 15
    - User-Language 15
    - AI-Readable Structure 15
  - Grade bands: ≥85 Excellent, 60–84 Adequate, <60 Weak.
  - Batch mode: run the full loop on one representative ASIN, then apply its "generic gaps" to sibling SKUs. This skips Rufus for those SKUs.
- **Rufus signal** [SRC:AIAD]: traffic ↑ with CVR ↓ means exploratory Rufus traffic is arriving. Deepen the listing rather than adding budget. Keep a library of 20–30 Q&As.
- **Localization** [SRC:PL 1-B/1-C]:
  - Two-stage: machine translation, then cultural adaptation (tone, native search terms, sensitivity, units and currency).
  - Arabic: right-to-left, Modern Standard Arabic, keep digits.
- **Variants for A/B** [SRC:PL 2-A/2-B/2-C]:
  - Title angles: price / performance / scenario / user-type / tech.
  - Bullet strategies: spec / scenario / comparative / assurance.
  - Ad copy: headline ≤30 chars, description ≤90 chars.
  - Known conflicts:
    - The "affordable" title angle is banned by compliance check #3, so it is resolved in favour of compliance (OQ-A2).
    - "safe" in the assurance strategy is also on the ban list.

### A2.3 Advertising
**Structure**
- **5 layers** [SRC:ADSC]:
  - Exploration: auto + category targeting.
  - Scaling: core terms, phrase/exact.
  - Profit: high-certainty terms and placements.
  - Defense: brand terms and page-1 positions.
  - Remarketing: SD / AMC audiences.
- **Match type by stage** [SRC:ADS10]:
  - New product: Exact, aimed at Top of Search (TOS).
  - Once rank is reached: Phrase, aimed at Rest of Search (ROS).
  - When Phrase hits its ceiling: Broad, aimed at Product Pages (PP).
- **Auto campaigns** [SRC:ADS10]:
  - Standard products: close-match + substitutes only.
  - Non-standard products: all 4 auto match types.
- **Keyword roles** [SRC:ADSC, GMV]:
  - Core = presence and the volume ceiling.
  - Mid-tail = most of the GMV.
  - Long-tail = ROI repair.
  - Brand = defense.
  - Competitor = conquest.
  - Judge a keyword by its structural role, not by its own ROI alone.
- **Naming convention** [SRC:PLC]: `SP-<SKU>-<term type>-<goal KPI>-<match>-<note>`. Adopt it as the standard (B3.6).

**Bidding** [SRC:ADS10, ADSXM, ADSC]
- The suggested-bid range is the baseline.
- Test fast at 1.2–1.5× suggested, then correct by ±10–20%.
- A "bargain-picking" (捡漏) campaign bids $0.2–0.3.
- **Waterfall test**: 3 copies at high / suggested / low, judged on day 3–5.
- **Strategy choice:**
  - Fixed bids for new campaigns.
  - Down-only when rank is already high, the listing is stable, or the campaign underspends with ACOS above average.
  - Up & down only without placement multipliers, because the effects stack: bid × (1+TOS%) × 2.
- **Raise / lower / negate / don't touch rule:**
  - Raise when conversion is proven and there is share to gain.
  - Lower when the traffic is relevant but marginal clicks are expensive.
  - Negate when intent mismatches or there is no sale after a sufficient sample.
  - Don't touch when the sample is small, the attribution window is still open, or the problem isn't the ads.

**Search-term rules** [SRC:ADSXM] (to encode in `thresholds.amz_ads`):

| Condition | Action |
|---|---|
| 0 orders, clicks > 30 | negative exact |
| 0 orders, 15 < clicks ≤ 30, strongly relevant | bid −50% |
| 0 orders, 15 < clicks ≤ 30, weakly relevant | negative exact |
| High sales share, high ACOS, organic CVR < ad CVR | bid −10% |
| High sales share, high ACOS, organic CVR > ad CVR | bid −20% + move exact→phrase/broad |
| High sales share, low ACOS, low impression share | check placement, raise bid |
| Low sales share, high ACOS, organic CVR < ad CVR | bid −20% |
| Low sales share, high ACOS, organic CVR > ad CVR | bid −40% or negative exact |
| Low ACOS, low impression share | raise bid |
| Root word with high frequency and 0 conversions | bulk-negate the root word |
| Root word performing well | expand via phrase/broad |

`[INF]` "High" and "low" are relative to the campaign or portfolio average unless a target ACOS is set. Break-even ACOS = pre-ad margin %. OQ-A3.

**Placements** [SRC:ADS10, ADSXM]
- Rank push: aim for TOS, with either
  - a normal bid + TOS 50–100% (then low bid + TOS 100–300% if needed), or
  - suggested bid + TOS 30%, stepped up from there.
- Efficiency: shift weight to the lowest-ACOS placement.
- PP lock-in: low bid + PP 30–100%.
- Report rule: the best placement gets a higher multiplier and the others lower.
- ⚠ The corpus "law" (CVR TOS > ROS > PP) is **contradicted by the real data**: PP 7.3% vs TOS 3.6% on category terms. Rules must be data-driven per campaign.

**Budget** [SRC:ADS10, ADSXM]
- Daily budget ≥ 1× CPO (≈ 4–5 clicks).
- Ramp from $10, adding about +5 clicks' cost at 00:00 site time while the campaign keeps spending out.
- Cut budgets that are long-term over-allocated.
- Portfolio reallocation:
  - High sales contribution: raise the budget where ROAS > average.
  - Low sales contribution: cut where ROAS is >20% below average (non-head terms).
- **Dayparting** is off by default. Use it only when spend is fast and conversion poor on a stable listing.
  - Daypart the budget, not bids.
  - Example: peak 100%, shoulders 30%, trough $2. Heaviest weekday +20%.

**Three-level ACOS cascade** [SRC:ADSXM]: portfolio budget → campaign placement → ad-group terms and root words.

**Ad dependency** [SRC:DEP]
- Gap = Amazon ad-order share (ERP) − third-party ad-traffic share (Xiyou). A gap > 15% means ads are over-credited.
- Success criteria: ad spend −≤15%, organic +≥15%, total sales stable.

**AMC** [SRC:ADSXM]
- Lookalikes of purchasers, and of add-to-cart minus purchasers.
- Retargeting of detail-page viewers, of add-to-cart minus purchasers, and of purchasers (for cross-sell). All via SP bid boost.

**Five-step diagnosis** [SRC:ADSC]:
1. Did demand change? (POE/ABA)
2. Where does the funnel leak? (SQP: impression → click → add-to-cart → purchase)
3. Where are competitors taking share?
4. Does the ad structure fit the stage?
5. Assign the ad role: validate / amplify / occupy / defend / harvest / exit.

**Lifecycle red lines** [SRC:GMV]:
- Stop-bleed: controlling ROI too tightly leads to a rank death spiral.
- Stabilize: "ROI-only" thinking.
- Scale: burning cash without building assets.

### A2.4 Launch: 90-day GTM [SRC:GTM]
- Plan backwards from W0 over 13 weeks: research W-12 → definition W-11 → validation W-10 → pages, assets, influencers W-9 → production W-7 → outreach W-6 → warm-up W-4 → ops readiness W-3 → price and tracking W-2 → QA W-1 → launch W0.
- Each task has a single owner, a deliverable, dependencies, a status and a risk.
- Reviews at W0+48h (can it sell?), +7d (what works, what wastes money?) and +30d (how do we repeat it?).
- Default 7-day dashboard: 100k impressions, 5% engagement, 2% landing-page CTR, 12% CVR, 500 orders, $50k revenue, CAC $25, ROAS 3. At 30 days: 30 reviews/UGC and branded search +20%.
- 12-item pre-launch checklist: sample = production unit, unified USP and banned list, stock, FAQ, page QA, tracking, assets, influencer dates, schedule, ad setup, reply scripts, launch-day war-room.
- Three-stage hit launch [SRC:GMV]: base (COSMO-ready listing, light ad share) → small-budget validation → Deal + ads to scale.

### A2.5 Store operations & monitoring [SRC:CDX, AIAD]
- **Weekly report:**
  - Sales, inventory, returns, settlement.
  - SKU health tiers.
  - Restock priority.
  - Return attribution.
  - Rough P&L.
  - Strategy suggestions.
- **Patrol** (24/7 alerts):
  - Listing hijacked or variation broken ("变狗").
  - Hijackers (跟卖).
  - Buy Box lost.
  - Review attacks.
  - Listing suppressed.
- **Negative-review alert:**
  - Capture new 1–3★ reviews and tag them (logistics / quality / …).
  - When a tag passes its threshold, alert and contact the buyer.
  - Report the weekly top 3 issues to product.

### A2.6 Account health & compliance [SRC:RESTR, ADDR, SCAN]
- **Violation classes:**
  - **Prohibited:** acknowledge. The listing stays gone and the violation counts toward repeats.
  - **Restricted:** appeal with documents (COA, certificates, six-side photos).
  - **False positive:** fix via flat-file template upload, then appeal.
  - Replies usually come within 72h. Unresolved records persist for 180 days.
- **Restricted categories:**
  - Medical: "FDA approved", treat, prescription.
  - Auto: delete kit, bypass, HID kit.
  - Cosmetics: glycolic >70%, salicylic >30%, microbeads.
  - Pesticide claims: antibacterial, antifungal, disinfect, repel. These need an EPA registration number.
  - FCC/RF: signal boosters.
  - Region-restricted: pepper spray, umbrella knives.
- **Prevention:**
  - 1–2 designated reviewers.
  - Periodic full-catalog audits.
  - Supplier document checks.
  - When syncing across marketplaces, check both sites' policies.
- **Verification:** the address must be identical across the business licence, Seller Central, utility bills and invoices. Use the fixed English format, and the official 25-digit address code when it genuinely matches the premises.
- **Appeal (POA) structure:** root cause → corrective actions taken → evidence → preventive measures. Optionally frame it with Amazon's Leadership Principles.

## A3. TikTok Shop playbook

### A3.1 Daily 12 tasks [SRC:TT12]
Read data in the backend timezone, using complete statistical days only.

**Anomaly classes:**
- **Immediate:** product can't be bought, price error, order near timeout, or spend over the cap. Contain first.
- **Same-day:** deviation on a complete day, a problem concentrated on one SKU, or a creative shortage.
- **Observe:** must carry a review time.

| # | Task | Window | Key rules |
|---|---|---|---|
| 1 | Store core data | AM | Compare with D-1, same weekday last week, and the 7-day average. Keep orders, SKU orders and units separate. Measure refund rate by cohort, never yesterday's refunds ÷ yesterday's GMV |
| 2 | Hero & new links | AM | Don't change price, image and title together. New low-data links are "observe". Symptom table: impressions ↓ / CTR ↓ / CVR ↓ / negative reviews clustering |
| 3 | After-sales & negative reviews | AM+PM | Sort by time remaining. Classify as product / logistics / service / misunderstanding. Never trade refunds or gifts for reviews |
| 4 | Inventory | AM | cover_days = sellable ÷ 7-day average daily sales. Trigger when cover days < replenishment cycle + buffer. Exclude in-transit stock with an uncertain ETA. A shipping label is not a carrier pickup |
| 5 | Own video data | AM | Tag each video main / pending / declining. Don't compare videos of different ages. Map plays → opening, CTR → demo, CVR → PDP fit, comments → objections |
| 6 | Creative production | all day | Shoot, edit and publish counts are separate. Pre-publish QC covers claims, rights, link, SKU, promo dates and disclosure |
| 7 | Ad patrol | AM/noon/PM | Pre-define the cap, test spend, acceptable loss and window. GMV Max ROI = gross revenue ÷ cost, which is not profit |
| 8 | Campaigns & promos | AM | Flag anything ending within 72h. Re-check stacked final price and margin. "Submitted" ≠ "live" |
| 9 | Creators/affiliates | day | Funnel counts: invites → replies → confirmed → shipped → received → published → creators with orders. Confirm authorization before reusing content |
| 10 | Competitors | day | Fixed list of 3–5. Tag each item as fact / estimate / opinion. Never copy |
| 11 | Selection/test | day | Fully-costed test card. Verdict is scale / observe / stop |
| 12 | Daily review | PM | Standard report. Next-day priority: risk → growth → observe. Handover checklist |

**Anomaly log fields:** found_at, object_id, scope, evidence, impact, action, owner, deadline, review_result.

### A3.2 GMV Max [SRC:GMVM]
- **Auction:** eCPM = bid × CTR × CVR × 1000.
- **ROI decomposition:** ROI = AOV ÷ CPA, where CPA ≈ (CPM/1000) ÷ (CTR × CVR).
- **Setup:** hero products get their own campaign; merge the rest.
- **Control:** change one parameter at a time, at most 2 per day.
  - ROI good: raise the budget.
  - ROI bad: add creatives, or lower the ROI target.
- **Not spending:**
  1. Add 3–5 new videos with a strong first 2s.
  2. Then loosen the ROI target a step (e.g. 3.0 → 2.5).
  3. Then check the budget.
- **Creative lifecycle:**
  - An original lasts 5–10 days; a remix adds 5–7.
  - Add 3–7 new originals per week.
  - Replace creatives with CTR < 1% or CPM > 30.
  - Test remixes in VSA before GMV Max.
- **Remix formula:** 20% new hook + 30% differentiation + 40% reused elements + 10% trend.
- **Quadrant (cost × ROI):**
  - Winners: push.
  - Bleeders: kill.
  - Potentials: duplicate to test.
  - Others: ignore.
  - Bleeder with high CTR and low CVR: mismatch or clickbait.
  - Low CTR with high CVR: weak opening.
- ⚠ Compensation rule: spend >$100 and 24h ROI <50% of target qualifies for a claim. Verify current policy (OQ-T1).

### A3.3 "Traffic but no conversion" tree [SRC:TTNC]
Steps:
0. Align the report:
   - Filter to Shop source.
   - Use destination clicks, not "all clicks".
   - Sample guard: ≥1000 impressions & ≥30 destination clicks.
1. Audience: check reach against the target persona. If it is off-target, A/B two first-3s versions.
2. Destination CTR (internal flag 3%, priority below 1%):
   - Low CTR: reshoot the first 3s.
   - High plays but low clicks: bring the selling point, price and scene forward.
   - CTR OK: stop touching hooks.
3. Post-click:
   - Click → PDP-view loss: link or SKU problem.
   - PDP → checkout loss: the biggest purchase doubt.
   - Checkout → purchase loss: shipping, delivery, stock or payment.
4. Verify on the same placement, budget, attribution window and complete dates. Log card verdict: keep / rollback / observe.

### A3.4 Content: 4 elements + scripts [SRC:TT4E, GMVM, SCRIPT]
- **One video = one audience + one pain + one selling point + one scene.**
  - Map the audience to a 5A stage (Aware / Appeal / Ask / Act / Advocate).
  - Pain types: functional / usage concern / emotional / aesthetic.
  - Replace "super/magic" with a visible action and result.
- **30s storyboard (6 segments):**
  - 0–3s: pain close-up, no brand.
  - 3–7s: scene.
  - 7–11s: product.
  - 11–20s: continuous demo.
  - 20–25s: same-angle result.
  - 25–30s: correct use + CTA.
- **3 hook types:** question / scene / verification.
- **Paid creative formula:** emotional opening → S-tier point → A/B-tier points → scene immersion → close → promo. Length 15–30s, never over 60s.
- **Selling-point tiers:** S (1–2, in every clip), A (2–3), B (2–3, price/promo).
- **Matrix shooting:** 5 attributes × usage × proof ≈ 125 combinations of ~15s clips.
- **QC rejects:**
  - Features with no user problem.
  - Pain that doesn't match the demo.
  - A cut in the proof.
  - Captions covering the proof.
  - An unverified claim stated as fact.
- **Specs:** 9:16, ≥1080p. Never repost others' videos.
- **File naming:** `MMDD_product_stage_scene_version_shot`.
- **Iteration table:**
  - Early drop-off: change the opening.
  - Views but no clicks: change the proof shot.
  - Clicks but weak purchase: fix the PDP.
  - Repeated questions in comments: add an explanation segment.

### A3.5 Creators & selection [SRC:TT12, TTC, TTRS]
- **Creator tiers:**
  - Amplify / stable / long-tail test / observe.
  - Each tier has its own sample, commission and follow-up policy.
- **CRM status chain:** outreach → reply → sample → receipt → video → publish → authorization → sales.
- **Message rules:** humans send messages and set terms.
- **Selection score:** market size, growth, competition, content suitability, fulfillment risk.
- **Black Friday checks:** gift-ability, price sensitivity, bundling, seasonality, return risk.

## A4. DTC (independent store) playbook

### A4.1 Strategy & CRO [SRC:DTC, GMETA]
- Four levers: **AOV, CVR, LTV, CAC**. Every plan says which lever it moves.
- Four niche gates: policy, ad-platform permissibility, supply, compliance.
- Product structure: hero + long-tail + bundles.
- Differentiation: value proposition + emotional value + visual hammer.
- **Health KPIs** [SRC:GMETA]:
  - Brand-search share 40–60%.
  - Brand search YoY +30–80%.
  - Acquisition cost ratio (ad spend ÷ revenue) moving from 30%+ to under 25%.
- **Product page:**
  - FAB structure + trust badges + social proof.
  - Diagnose the funnel stage by stage (browse → ATC → checkout → pay).
  - Ad → landing-page message match.
- **Landing-page 5-point check** [SRC:RDT]:
  1. The first screen answers the problem.
  2. Price, shipping, returns and stock are visible.
  3. Evidence comes first.
  4. Mobile is fast and the CTA is clear.
  5. There is a soft path for non-buyers.
- **GA4 events** `[INF]`: view_item, view_item_list, add_to_cart, begin_checkout, add_shipping_info, add_payment_info, purchase.

### A4.2 Google & Meta [SRC:GMETA]
- **Google Search, 3 series:**
  - Bottom-of-funnel harvest: exact/phrase.
  - Category exploration: broad/phrase.
  - Competitor and brand defense.
- **Google PMax, 4 tiers:**
  - Hero product-page tier.
  - Pure-feed Shopping tier.
  - Non-brand exploration tier, with brand exclusions `[INF]`.
  - Event/landing-page tier.
- **GSC loop:** feed real query data into Search keywords and negatives.
- **Meta:**
  - ABO creative race (KOC/UGC) → CBO/ASC scale → DPA retargeting.
  - Current default: broad audience + many creatives + ASC. Interest packs are the fallback.
  - Partnership Ads beat whitelisting.
  - Decision KPIs: CPM, CTR, ATC rate, CVR.
  - Thresholds are **not in the corpus**. Defaults `[INF]`, OQ-D1:
    - link CTR ≥1%
    - ATC rate ≥5–8%
    - store CVR ≥1–2%
    - kill an ad at 1.5–2× target CPA with no purchase
    - scale +20–30% every 48–72h
    - ~50 conversions per ad set per week to exit learning

### A4.3 SEO / GEO / backlinks [SRC:SEO, SOC, RDT]
- **Backlinks:**
  - Ahrefs: Site Explorer → Backlinks.
  - Semrush: Backlink Analytics → Backlinks.
  - `[INF]` Then filter dofollow, sort by DR/traffic, classify link type, run a link gap across 3–5 competitors, and build an outreach list.
- **GEO** (content that is searchable, understandable and verifiable):
  - Reddit questions, KOL experience and PR quotes become comparison pages, buying guides, FAQs and seasonal pages.
- **Reddit query patterns:**
  - `site:reddit.com [category] best|recommendation|worth it`
  - `[A] vs [B]`
  - `[category] problem|regret`
  - `[competitor] alternative`

### A4.4 Reddit [SRC:RDT] (most complete SOP)
- **Product fit:** 5 dimensions scored 0–2 each:
  - Demand, research intensity, evidence, differentiation, team capacity.
  - 8–10 = priority, 5–7 = test, ≤4 = fix messaging first.
- **Community score:** 5 criteria scored 1–5 each:
  - Relevance, activity, promotion tolerance, intent, sustainable content.
  - Below 15 = skip.
  - Week 1: screen 20 subs, keep 5–8.
- **VOC table:** sub/link, verbatim quote, stage, evidence, objection, action + owner.
- **Account:** compliant warm-up only.
  - Disclose affiliation.
  - Join 10–20 subs.
  - Answer from real experience.
- **Plays:**
  1. Reply interception on threads <24h old, three-part reply: solve → evidence → limits + disclosure.
  2. Mod-approved AMA with 20 prepared questions.
  3. Product-testing posts.
- **Daily routine (30 min):** 10 min find, 10 min filter, 10 min answer.
- **Six post templates:** problem-help, comparison, test recap, guide, co-creation, AMA.
- **Ads:**
  - DPA prerequisites: Pixel/CAPI, a consistent feed, separate prospecting and retargeting.
  - Start with 1–3 keywords, 1–5 communities, ~$100/day, a 7–14 day window.
- **UTM:**
  - `utm_source=reddit`
  - `utm_medium=organic_post|organic_comment|creator|paid`
  - `utm_campaign=<category>_<problem>_<yyyyqN>`
  - `utm_content=<angle>`
- **Stop lines:**
  - Repeated removals.
  - Visits without product-page arrival.
  - CAC over the limit after the learning window.
  - Negative feedback clustering on one product issue.
- **30/60/90-day plan:**
  - 0–30: community map, rule library, VOC table, 20 comments.
  - 31–60: 6 topics, 3 compliant posts, landing-page v1, UTM system.
  - 61–90: KOL test, ad test, retargeting, review.

### A4.5 Brand social & KOL [SRC:SOC]
- Prioritize conversion over exposure: 90% evergreen content (founder story, education, real experience) and 10% trends.
- **Production models:**
  - Founder on camera + Partnership Ads (low cost).
  - In-house creator ($1.2–1.8k per month + bonus).
  - Creator retainer ($1–4k per month).
- **Five-channel model:** Social = awareness, Reddit = real needs, KOL = experience proof, PR = third-party proof, SEO/GEO = search capture. Shared theme, assets and rhythm.
- **12-week peak calendar:** T-12 prep → warm-up → peak → tail → asset consolidation.
- **Kept libraries:** creative, user questions, KOLs, PR media, topics.

## A5. Walmart playbook [SRC:WMT] (outline-level; thresholds are OQ-W1)
- Copy the *conditions* of an Amazon hit, not the listing itself. Re-verify demand, competition, price band, WFS fees and margin before moving a SKU.
- **Migration order:**
  1. Asset inventory.
  2. Rules and user differences.
  3. SKU screen.
  4. Rebuild content and keywords.
  5. Ad cold start.
  6. Expand to a matrix.
- **Pricing:**
  - Plan daily, promo and was-price in advance. Last-minute changes break the strikethrough and event eligibility.
  - Watch for price-competitiveness unpublishing.
- **Ads:**
  - Never read ROAS alone. Cross-read Item Health, Item, Keyword, Placement and Custom reports.
  - Run auto and manual together.
  - Locate the failure as CTR, CVR or ROAS.
- **WFS:**
  - Model fees.
  - Handle inbound delays and lost units.
  - Don't scale ads beyond supply and receiving lead time.

## A6. Creative / visual playbook [SRC:VIS, TT4E]
- **Pipeline:** visual diagnosis → user insight → FABE → **Visual Brief** (why this image exists) → model choice → generate → failure diagnosis → targeted fix → AI review → human review → channel adaptation ("change the channel, not the facts") → asset library.
- **Input hygiene:** keep the 5 input types separate (facts / references / product / user / strategy). The **product truth** file (shape, color, material, proportions, logo position) is immutable.
- **QC failure modes:**
  - Product distortion.
  - Wrong proportions.
  - Awkward people.
  - Fake scenes.
  - Brand-style drift.
  - "Fake localization".
- **Main image:** consensus elements + a differentiating anchor + trust evidence, readable in 3s without text.
- **Gallery ("golden 6"):** one problem per image, ordered sensory → rational → trust.
- **A+:** brand claim → core points → craft evidence → comparison → scenes → brand assets.
- **Store page in 5 beats:** awareness → attraction → trust → guidance → action.
- **Generative-fill recipes** (expand, remove, replace scene, garment, accessory) apply only to assets you own or license.
- **"Onion" diagnosis:** rule out traffic, price, reviews, stock and competitors before blaming the visuals.

## A7. Organization & KPIs (basis for agent scorecards) [SRC:TEAM]
- **Ops ladder:** Specialist → Senior → Supervisor → Brand Manager → Director.
  - Hard floor: net margin ≥6%.
  - Attainment bands: 80 / 85 / 130 / 150%.
- **Design team:**
  - Workload units: 0.1 per image set, 0.05 per A+ small image, 0.5 per video edit.
  - Monthly targets: ≥6–8 units, on-time ≥95–100%.
  - Product CTR ≥0.2% (definition unclear, OQ-G9).
  - ≥1–2 products at CVR ≥10%.
  - Video view rate ≥80–90%.
- **Mapping to agents** (D6):
  - Throughput = tasks completed and on-time rate.
  - Quality = schema-valid %, compliance pass %, human acceptance %, rerun stability.
  - Outcome = KPI movement on decisions after their review date (e.g. ACOS change after negations).

## A8. Operating cadence (all platforms)

| Cadence | Amazon | TikTok Shop | DTC/Reddit | Manager |
|---|---|---|---|---|
| Intraday | patrol alerts (hijack/BB/suppression) | ad patrol ×3 | — | route alerts |
| Daily AM | ads anomaly + search-term harvest | tasks 1–5, 7, 8 | Reddit thread scan | dispatch daily playbooks |
| Daily PM | — | task 12 daily review | engagement follow-up | daily digest |
| Weekly | ops report, ad retrospective, placement/budget, competitor deltas, review insights | GMV Max quadrant, creative cadence, creator funnel | Meta/Google review, Reddit Fri sync, funnel | weekly scorecard, experiment evaluations |
| Monthly | dependency audit, lifecycle and stage review, ROI model refresh | selection tests | SEO/backlink gap, content calendar | agent KPI review, threshold tuning |
| Event | launch GTM, Deal pre/during/post, appeals | BF back-planning | peak 12-week | approvals, escalations |

## A9. ⚠ Excluded tactics (red list; never build, never recommend)

| Tactic | Source | Why excluded |
|---|---|---|
| Junk-content Basic A+ ×15 + Brand Story to unlock Premium A+ | APLUS | gaming eligibility with meaningless content |
| 补单 / keyword fake orders / paid review channels / "batch review intervention" / manual push to page 1 | DEV, SCAN | review and search manipulation |
| Account matrix, black/white-hat isolation, fingerprint anti-linkage | SCAN, DTC (phone farm) | multiple-account policy circumvention |
| TRO as a weapon / fake infringement complaints | SCAN | abuse of IP enforcement |
| Reddit upvote teams, mutual-upvote groups, sockpuppets, bought aged accounts, undisclosed affiliation | RDT (TOC) | vote manipulation / astroturfing |
| Brand page "disguised" as an unbranded content page | SOC | disclosure (FTC, Meta authenticity) |
| Counterfeit "brand replica interception" + COD | TTRS | trademark counterfeiting |
| Scrape competitor ad creative, images, copy or reviews and re-create them | TTRS | copyright / platform IP |
| Removing others' watermarks | VIS | copyright circumvention |
| Meta "account borrowing" | GMETA | ad-account policy |
| Trading refunds or gifts for reviews | TT12 (forbidden there too) | review policy |
| "Avoid Asian faces" | SCRIPT | discriminatory; replaced with "match the target-market demographics, with portrait rights" |

**Grey zone (requires your decision, OQ-G5):** automating Rufus queries on amazon.com via CDP (PL rufus-research). It uses a live shopper session, so it is a ToS and fragility risk. The proposed mitigation is in AMZ-03b.

## A10. Shopify + Google Ads playbook (v0.4; the corpus gives structure [SRC:GMETA], and most numbers are `[INF]`)

**Order of work.** Run in this order and don't skip steps. Most failing Shopify + Google setups fail at steps 1–2, not in bidding.

1. **Measurement first** (DTC-10).
   - Exactly one *primary* purchase conversion, usually from the Google & YouTube Shopify app or a GA4 import, but not both as primary.
   - The value is passed, and counting is "every".
   - Shopify orders vs Google Ads conversions vs GA4 purchases should agree within about 25%.
   - Add enhanced conversions and consent mode where required (EU/UK).
2. **Merchant Center healthy** (DTC-09).
   - **Account-level checks:**
     - Domain verified and claimed.
     - Business name, address and phone shown.
     - **Return/refund, shipping, privacy, terms and contact pages** present and linked in the footer.
     - Checkout works and prices match.
     - Missing any of these commonly leads to *misrepresentation* suspensions on new Shopify stores.
   - **Item-level checks:** GTIN/brand/MPN (or identifier_exists=false for custom goods), accurate price and stock, clean primary image, correct google_product_category.
3. **Site converts** (DTC-01/02/11).
   - Product pages answer the buyer's questions, with price, shipping and returns visible and fast on mobile (A4.1).
   - Without a store CVR around 1% `[INF]`, ads mostly buy data, not sales.
4. **Campaign ladder by budget** (`thresholds.gads`, `[INF]`):

   | Daily budget | Structure |
   |---|---|
   | **Small**, < $30 | One feed-only **PMax** (no or minimal assets) or **Standard Shopping**, split by `custom_label_0` (hero / others). Plus **Search – brand** if brand searches exist. Bidding: Maximize conversion value with no target at first |
   | **Medium**, $30–150 | Add **Search – BOF** on exact/phrase terms for the top-converting product types. PMax tiers from GMETA: hero pages / pure feed / non-brand with brand exclusions |
   | **Large**, > $150 | Add category-exploration Search, competitor Search, and event/landing tiers (GMETA 4-tier). **Never mix exploration with harvest** |

5. **Bidding ladder:**
   - Max clicks (with a CPC cap) only while there is no conversion history.
   - Maximize conversions or conversion value once there are ≥15 conversions in 30 days.
   - Add a tROAS target at about observed ROAS −10% after ≥30 conversions in 30 days.
   - Change targets by at most 15% every 2 weeks.
   - Allow 2–3 weeks of learning, with no structural change in the first 7 days except stop-loss.
6. **Weekly optimization:**
   - **Search terms:**
     - 0 conversions and cost ≥ 2× target CPA: negative exact.
     - Irrelevant intent (free/DIY/used/jobs/wholesale/…): negative phrase in a shared list.
     - A converting term (≥2 conversions, ROAS ≥ target): add as exact in BOF.
   - **Products:**
     - ≥50 clicks and 0 conversions: label "zombie", lower its priority or exclude it.
     - ROAS ≥ 1.3× target: "hero".
     - New items get a "new" label for 30 days.
   - **Budget:**
     - "Limited by budget" and ROAS ≥ target: +20%, at most once every 3 days.
     - ROAS < break-even for 14 days after learning: −20%, or pause the tier.
   - **Stop-loss:** spend ≥ 3× target CPA with 0 conversions in 7 days: propose a pause.
7. **Feed is the creative for Shopping.**
   - Title formula: `Brand + product type + key attributes (material/size/color/gender/qty) + model`, with the important words in the first ~70 characters (limit 150).
   - Price competitiveness (Merchant Center report) explains low CTR more often than bids do.
   - Free listings come with a healthy feed.
8. **Diagnosis map:**
   - Low impressions → feed approval, budget, or bids/quality (lost impression share by rank vs budget).
   - Low CTR → titles, images, price.
   - High CTR but low CVR → landing page, price, shipping, trust.
   - ROAS < break-even → product mix (labels), margin, AOV (bundles).
9. **Never:**
   - Turn on Google "auto-apply recommendations". If found on, report it.
   - Edit billing or payment settings.
   - Let a tool change account settings.
   - Mis-state business identity in Merchant Center.
10. **KPIs:**
   - Spend, conversions, conversion value, ROAS vs break-even ROAS (X-03), CPA, CTR, CVR.
   - Search impression share lost to budget and to rank.
   - Feed approval rate.
   - Brand-search share (GMETA health: 40–60%).

## A11. eBay playbook (v0.4; not in the corpus, so everything here is `[INF]` platform guidance)

- **Visibility (Best Match / Cassini):**
  - Relevant title (≤80 characters; buyer search words; brand + model + key specifics; no filler like "L@@K").
  - **All required and recommended item specifics** filled.
  - Correct category.
  - 8–12+ photos (max 24).
  - Competitive price and shipping.
  - Handling time of 1–2 days.
  - 30-day returns (free returns help).
  - Best Offer turned on.
  - Seller performance level, which feeds visibility.
- **Pricing:** compare with sold comps in Seller Hub → **Research (Terapeak)**. A price more than 15% above the sold median with low sell-through is flagged.
- **Funnel per listing** (Seller Hub → Performance → Traffic):
  - 0 impressions → category, specifics or title.
  - Impressions but CTR < ~1% → title, photo, price, free shipping.
  - Views but no sales → price, shipping, returns, description.
- **Promoted Listings:**
  - **General** (cost per sale): start near the suggested/trending ad rate, capped by margin (ad rate ≤ gross margin − target net margin).
  - **Priority** (CPC): only for top items. Pause keywords with ≥30 clicks and 0 sales.
  - Watch for ad fees charged on sales that would have happened organically (an ad-dependency check like DEP).
- **Seller standards:**
  - Transaction defect rate: out-of-stock cancellations and cases closed without seller resolution.
  - Late shipment rate and on-time tracking upload.
  - "Below Standard" cuts visibility and raises fees.
  - Recovery:
    - Keep quantities accurate (out-of-stock option, end dead listings).
    - Set a realistic handling time and upload tracking the same day.
    - Reply to every buyer within 24h.
    - Resolve issues before they become cases.
- **Cadence:**
  - Daily: messages, orders, cases (EX-04 + X-13).
  - Weekly: traffic funnel + Promoted Listings.
  - Monthly: seller-standards projection before the evaluation date.
- **Policies:** VeRO (don't use brand names you don't own), no keyword spam, no off-eBay contact or links.

## A12. Etsy playbook (v0.4; not in the corpus, so everything here is `[INF]`)

- **Search (relevance + listing quality + customer/market experience):**
  - Title ≤140 characters, readable, key phrase first.
  - **13 tags**, each ≤20 characters, multi-word long-tail phrases, without wasting them on words the category or attributes already cover.
  - Every attribute filled (color, material, occasion, holiday, recipient…).
  - Correct category.
  - Photos and video:
    - 5–10 photos plus a video.
    - A thumbnail that reads at small size.
    - The listing-photo visibility factors flagged by the existing skill.
- **Listing quality signals:** CTR, favorites, conversion. Use **Stats → search terms** to refine tags.
- **Shipping:** free shipping on US orders ≥ $35 is favoured in US search. Keep processing times realistic.
- **Customer experience:**
  - Star Seller criteria: reply to messages within 24h (≥95%), dispatch on time with tracking (≥95%), average rating ≥4.8.
  - The surveyed shop's **25% response rate** is a primary blocker, handled by X-13.
- **Etsy Ads:**
  - Start at $1–5/day on the listings that convert best organically.
  - Judge after ≥14 days.
  - Turn off listings with ≥40 clicks and 0 orders.
  - Keep ROAS ≥ break-even.
- **Offsite Ads:** a fee of 15% of the sale (12% and mandatory above $10k/yr). Include it in unit economics.
- **Policies:** no trademarked terms in tags or titles (IP takedowns), no keyword stuffing, original photos.
- **Cadence:**
  - Daily: messages and orders (EX-03 + X-13).
  - Weekly: Stats funnel + Ads.
  - Monthly: listing SEO refresh for the bottom performers.

---

# PART B: Architecture on eCan.ai

## B1. eCan.ai primitives used by this design (verified from the local repo)

| Primitive | What it is | Where it's defined |
|---|---|---|
| **Skill** | A LangGraph workflow: a Flowgram diagram (`diagram_dir/<name>.json` + `_bundle.json`) or Python code. Stored at `my_skills/<name>_skill/`. The entry sheet must be named `main`; sub-sheets are wired with `sheet-call` / `sheet-inputs` / `sheet-outputs`. | `gui_v2/src/modules/skill-editor/doc/skill_editor_help.md` |
| **Node types** | `start`, `end`, `llm`, `browser-automation`, `mcp`, `code` (py/js/ts), `http`, `condition`, `loop` (`loopWhileExpr`), `group`, `pend_event_node`, `comment`, `block-start/end` | `agent/ec_skills/build_node.py`, `node_schemas.json` |
| **State** | A shared dict: `attributes`, `metadata`, `prompt_refs`, `tool_input`, `tool_result`, `http_response`, `result.llm_result`. Loops stop on `state.result.llm_result.all_done`. | `docs/mapping-dsl.md` |
| **Prompt** | `my_prompts/*.json`: `{id:"pr-xxxx", title, topic, sections:[goals|guidelines|rules|examples], variables?}`. LLM nodes reference it via `systemPromptId` / `promptId`. | `my_prompts/` |
| **Variables** | `{{var}}` in prompts. Resolution order: `state.prompt_refs` (seeded from `task.metadata.task_vars`) → the prompt's `variables[]` → skill `mapping_rules.prompt_variables` → builtins (`tools_schema`, `skills_schema`, `current_time`, `agent_id`, `task_id`, `human_input`, …) → `""`. Each declaration has `{name, source: builtin|static|state_path|code|api, …}`. | `docs/prompt-variable-resolution.md` |
| **Tools** | About 130 MCP tools in `agent/mcp/server/tool_schemas.py`. The LLM picks a tool through `{{tools_schema}}`, returning `{"tool_name","tool_input":{"input":{…}}}` or `multi_tool_calls: serial|parallel`. An `mcp` node with `callable.id="llm-auto-select"` executes the choice. | `docs/MCP_TOOL_AUTO_SELECT.md`, `MULTI_TOOL_CALLS.md` |
| **Browser node** | Runs browser-use with: `profile`, `cdpPort`, `allowedActions`/`excludedActions`, `maxSteps`, `keepBrowserAlive`, `nodeTimeoutSeconds` (≥300), escalation models, `tabPolicy`, `autoDispatch` | `docs/BROWSER_AUTOMATION_NODE_CONFIG.md` |
| **Data mapping** | `data_mapping.json` `{developing|released:{mappings:[{from,to,on_conflict}]}, node_transfers, event_routing}` | `docs/mapping-dsl.md` |
| **Agent / Task** | An agent hosts tasks; each task is bound to one skill and runs on a human command, a schedule, or as an A2A recipient. `task_vars` are passed in. Agents are discoverable by skill. | README, `docs/agent-discovery.md`, `CLI_GUIDE.md` |
| **A2A + waiting** | `send_chat(sender_agent_id, recipient_agent_id, message, chat_id)`; replies come back via `pend_event_node` (timer / webhook / human / agent-in-loop) and are mapped into state | `my_travel_agent0_coordinator…`, `rpa_supervisor_*` tools |
| **Existing reusable tools** | `in_browser_*` (navigate, click, extract, upload, **`in_browser_execute_javascript`**, `in_browser_wait_for_element`…), `os_read_document`, `os_write_file`, `nas_*`, `add_timer`, `rpa_supervisor_scheduling_work`, `rpa_operator_dispatch_works`, `rpa_operator_report_work_results`, `python_run_extern`, `os_screen_analyze`, `rag_query` | `tool_schemas.py` |

⚠ **Security finding (outside this spec's scope, but you should act on it):** `my_skills/my_test_llm_tools_skill/diagram_dir/my_test_llm_tools_skill.json` contains a hardcoded OpenAI key in the LLM nodes' `apiKey`. Rotate it. Convention C7 below forbids keys in skill files.

## B2. Layered architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ L4  MANAGER  (mgr_ecom_manager_skill on agent "ecom-manager")                │
│     playbook registry · task board · scheduler hooks · approval router ·     │
│     verifier · agent scorecards · digests                                    │
└───────────────┬───────────────────────────────┬──────────────────────────────┘
        A2A send_chat(TaskEnvelope)        pend_event_node(SkillResult)
┌───────────────▼───────────────────────────────▼──────────────────────────────┐
│ ROLE AGENTS (each hosts several skills; found by skill)                      │
│  data-analyst · listing-writer · ads-optimizer · creative-studio ·           │
│  compliance-officer · browser-operator · community-manager · store-ops       │
└───────────────┬──────────────────────────────────────────────────────────────┘
┌───────────────▼──────────────────────────────────────────────────────────────┐
│ L2  WORKER SKILLS (LLM)         │ L3  BROWSER SKILLS (browser-automation)     │
│  amz_* tts_* dtc_* wmt_* x_*    │  x_browser_extract, amz_rufus_research,     │
│  sys-prompt + vars + tools      │  report downloaders, patrol, backlinks      │
└───────────────┬─────────────────┴───────────────┬────────────────────────────┘
┌───────────────▼─────────────────────────────────▼────────────────────────────┐
│ L1  DETERMINISTIC MCP TOOLS (no LLM): parse/normalize reports, SQL over      │
│     tables, metric calc, rules engine, compliance lexicon, unit economics,   │
│     bulk-file builder, decision log, artifact store, notify/approval         │
└───────────────┬──────────────────────────────────────────────────────────────┘
┌───────────────▼──────────────────────────────────────────────────────────────┐
│ L0  DATA (v0.2 browser-first, B6): per-store logged-in browser profiles →    │
│     T1 recipes (report downloads) · T2 in-page JS extractors · T3 LLM agent  │
│     fallback → files/JSON → X-01 ingest → analytic DB. APIs/ERP: later.      │
│     KB store (store profile, product truth, history) on local DB / NAS       │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Why the layers are split this way:**
- **L1 holds every number and every rule threshold.** The corpus's own failures (arithmetic typos, contradictory thresholds) show that this logic must be deterministic and testable. LLMs only classify relevance, explain, write and plan.
- **L2 skills are platform-specific but share one I/O envelope (B3.2).** That way the Manager treats every skill the same.
- **L0 is browser-first (v0.2).** All platform data is acquired through the user's own logged-in sessions. Deterministic recipes and JS extractors do the routine work at zero LLM cost. The LLM browser agent is only the repair path (B6).
- **L3 browser skills are isolated and read-only by default.** They are the most fragile and the riskiest part, so they sit behind a single contract: `x_browser_extract`.
- **Role agents, not one agent per skill.** In eCan a task binds to a skill and an agent hosts several tasks. Grouping by role keeps the agent count small (8) and matches the corpus's org chart (A7), which makes the scorecards meaningful. OQ-G1.

## B3. Conventions (every skill must follow)

### B3.1 Naming
- **Skill folder:** `<domain>_<capability>_skill`. Domains: `x` (cross-platform), `amz`, `tts` (TikTok Shop), `dtc`, `wmt`, `mgr`.
- **Prompt id title:** `<skill>__<node>` (e.g. `amz_ads_search_term_optimizer__classify`).
- **New MCP tools:** prefix `ec_` (e.g. `ec_rules_eval`).
- **Skill version:** semver in the skill JSON `version`. Bump the minor version when the output schema changes.

### B3.2 Standard I/O envelope
Every skill is invoked with a **TaskEnvelope** (seeded into `state.attributes.task` and its `inputs` into `prompt_refs` via `task_vars`). Browser steps also get a human-readable rendering in `state.attributes.current_invocation_input`. This follows the existing convention: top-level state keys are dropped between steps (B8.3). Every skill returns a **SkillResult** on its `end` node. This extends eCan's existing prompt rule `{success, summary, result, errors}`, so current prompts stay compatible.

```ts
type TaskEnvelope = {
  task_id: string;            // uuid, Manager-assigned
  parent_task_id?: string;    // playbook run id
  playbook_id?: string;       // e.g. "amz_daily_ads"
  skill: string;              // target skill name
  skill_version?: string;     // pin; default latest released
  requested_by: "manager" | "human" | "schedule" | "event";
  store_id: string;           // key into StoreProfile
  platform: "amazon" | "tiktok_shop" | "shopify" | "etsy" | "ebay" | "walmart" | "reddit" | "google_ads" | "meta" | "multi";
  marketplace?: string;       // "US","DE","UK","SA"...
  inputs: Record<string, any>;        // skill-specific, see each spec
  artifacts_in?: ArtifactRef[];       // files/tables to read
  vars_override?: Record<string, any>;// override shared vars for this run
  approval_level_max: 0 | 1 | 2 | 3;  // highest autonomy allowed (B3.4)
  mode?: "run" | "explore";   // v0.8: default "run"; only "explore" may escalate luna → terra (B3.7). Set by the Manager only
  deadline?: string;          // ISO datetime
  dry_run?: boolean;          // never write, even if approved
  locale_out?: string;        // v0.9 (OQ-G8): owner-facing language; default = StoreProfile.languages.owner, else Tenant.owner.locale
};

type SkillResult = {
  success: boolean;
  task_id: string;
  skill: string; skill_version: string;
  summary: string;                    // ≤ 5 lines, human-facing, in locale_out
  status: "done" | "partial" | "needs_input" | "needs_approval" | "failed";
  result: Record<string, any>;        // skill-specific payload, see each spec
  decisions?: DecisionRecord[];
  actions_proposed?: ProposedAction[];
  anomalies?: Anomaly[];
  artifacts?: ArtifactRef[];          // reports, CSVs, bulk files, images
  followups?: FollowupRequest[];      // ask Manager to run other skills
  warnings?: string[];
  errors?: { code: string; message: string; details?: any }[];
  metrics: { started_at: string; ended_at: string; llm_tokens?: number; llm_cost_usd?: number; browser_steps?: number;
             model_used?: string; escalated_from?: string; escalation_trigger?: string; fallback_used?: boolean };  // v0.8 (B3.7)
  all_done: true;                     // eCan loop convention
};
```

### B3.3 Shared data shapes (canonical)
These are defined once in `ec_schemas` (a JSON Schema registry, B6) and referenced by name in every spec.

```ts
type ArtifactRef = { id: string; kind: "csv"|"xlsx"|"json"|"md"|"html"|"png"|"jpg"|"mp4"|"pdf";
  uri: string;            // nas:// or file:// path
  schema?: string;        // canonical table name if tabular, e.g. "amz_search_term_rows"
  rows?: number; sha256?: string; created_at: string; source?: string; date_range?: [string,string] };

type DecisionRecord = {   // P7 Judgment/Evidence/Cause/Action/Acceptance
  id: string;
  object: EntityRef;                        // what it is about
  judgment: string;                         // one sentence
  evidence: { metric: string; value: number|string; baseline?: number|string; window: string; source: string }[];
  cause?: string;
  action: "act" | "observe" | "no_action" | "escalate";
  action_ids?: string[];                    // → ProposedAction.action_id
  acceptance?: { metric: string; target: string; review_at: string };  // e.g. "ACOS<=28% by 2026-11-23"
  confidence: "high" | "medium" | "low";
  rule_id?: string;                         // which L1 rule fired, if any
};

type ProposedAction = {
  action_id: string;
  type: "bid_change"|"budget_change"|"placement_change"|"negate_keyword"|"add_keyword"|"campaign_create"|
        "campaign_pause"|"listing_update"|"price_change"|"promo_create"|"inventory_reorder"|
        "message_send"|"post_publish"|"appeal_submit"|"ticket_create"|"other";
  platform: string; target: EntityRef;
  before?: any; after: any;                 // exact values
  rationale_decision_id: string;
  risk: "low"|"medium"|"high";
  reversible: boolean; rollback?: any;
  required_level: 1|2|3;                    // see B3.4
  execution: { mode: "bulk_file"|"api"|"browser"|"manual"; artifact_id?: string };
  status: "proposed"|"approved"|"rejected"|"executed"|"failed"|"rolled_back";
};

type EntityRef = { type: "store"|"sku"|"asin"|"listing"|"campaign"|"ad_group"|"keyword"|"search_term"|
  "placement"|"video"|"creator"|"product"|"subreddit"|"thread"|"page"|"order"|"review"; id: string; name?: string; parent?: EntityRef };

type Anomaly = { id: string; class: "immediate"|"same_day"|"observe"; object: EntityRef;
  metric: string; value: number; baseline: number; delta_pct: number; window: string;
  detected_at: string; hypothesis?: string; owner_role?: string; deadline?: string; review_at?: string };

type ExperimentCard = { id: string; problem: string; hypothesis: string; baseline: Record<string,number>;
  change: ProposedAction[]; window_days: number; success: string; stop_loss: string;
  started_at?: string; evaluate_at: string; verdict?: "keep"|"rollback"|"extend"|"inconclusive" };

type FollowupRequest = { skill: string; reason: string; inputs: Record<string,any>; priority: "p0"|"p1"|"p2" };
```

**Domain entities (KB records):**

```ts
type StoreProfile = { store_id: string; platform: string; marketplace: string; currency: string; timezone: string;
  brand: string; categories: string[]; erp?: "lingxing"|"saihu"|"none"; data_access: ("browser"|"file_drop"|"sp_api"|"ads_api"|"erp_mcp")[];  // v0.2 MVP: ["browser"]
  browser_profiles: { site: string /*e.g. "amazon_seller_central","amazon_ads","amazon_shopper","tiktok_seller","tiktok_ads","ga4","shopify","meta_ads","google_ads","reddit"*/; profile: string /*eCan/AdsPower profile id*/ }[];
  targets: { monthly_revenue?: number; net_margin_min: number /*0.06*/; target_acos?: number; target_tacos?: number; target_roas?: number };
  approval_policy_id: string;
  notify: { email: string[]; sms_e164: string[]; quiet_hours?: [string,string] /*local "22:00","08:00"; immediate-class alerts ignore*/ };   // v0.2: email + SMS only
  owners: Record<string /*role or action type*/, { name: string; email?: string; phone_e164?: string }>;
  languages: { owner: string;      // v0.9 (OQ-G8): the language the owner selected for this store: digests, alerts, chat about it. Default at onboarding: the seller-UI language detected on the platform, else Tenant.owner.locale
               customer: string[] }; // listing, ads and message languages for the marketplace. Default: the marketplace primary language. Buyer replies use the buyer's language if it is in this list, else customer[0]
  legal_entity_id: string;          // v0.9 (OQ-G11): which Tenant.legal_entities entry owns this store
};

type ProductFacts = {                    // the immutable "product truth" (A6) + claims with evidence (P11)
  sku: string; asin?: string; title_internal: string; category: string; marketplaces: string[];
  specs: Record<string, string|number>;  // dims, weight, materials, wattage...
  features: { name: string; detail: string }[];
  claims: { text: string; evidence_ref?: string; status: "verified"|"needs_data"|"banned" }[];
  certifications: { body: string; name: string; year: number; doc_ref?: string }[];
  target_users: string[]; scenarios: string[]; differentiators: string[];
  price: { list: number; current: number; floor?: number }; cogs: number; first_mile_per_unit?: number; fees?: Record<string,number>;
  images_ref?: string[]; product_truth_images?: string[]; restricted_flags?: string[] };

type Listing = { platform: string; marketplace: string; id: string /*asin/product_id*/; title: string; bullets: string[];
  description?: string; backend_terms?: string; attributes?: Record<string,string>; aplus_modules?: any[]; images?: string[]; language: string; version: string };

type KeywordMetric = { term: string; source: "aba"|"sqp"|"sellersprite"|"xiyou"|"cerebro"|"gsc"|"tiktok"; marketplace: string;
  search_volume?: number; sfr?: number; trend_12m?: number[]; click_share_top3?: number; conv_share_top3?: number;
  intent?: "scenario"|"persona"|"problem"|"feature"|"brand"|"competitor"|"generic"; cluster_id?: string };

type Review = { platform: string; object_id: string; review_id: string; rating: number; title?: string; text: string; date: string; verified?: boolean; variant?: string; lang?: string };
```

**Canonical report tables** (produced by `ec_report_normalize`, consumed through `ec_table_query`):

| Table | Key columns |
|---|---|
| `amz_search_term_rows` | date, campaign, ad_group, targeting, match_type, search_term, impressions, clicks, spend, orders, sales, units |
| `amz_placement_rows` | date, ad_type, campaign, placement(`TOS`/`ROS`/`PP`/`OTHER`), impressions, clicks, spend, orders, sales, direct/indirect, ntb_*, video_* (mapping from the PLC export schema) |
| `amz_campaign_rows` | date, campaign, portfolio, ad_type, state, budget, bid_strategy, tos_pct, pp_pct, ros_pct, spend, sales, orders, impr_share? |
| `amz_business_rows` | date, sku, asin, sessions, page_views, units, orders, sales, buy_box_pct |
| `amz_sqp_rows` | week, query, query_volume, impr_total/brand, clicks_total/brand, atc_total/brand, purch_total/brand |
| `amz_inventory_rows` | date, sku, fulfillable, inbound, reserved, unfulfillable, days_of_supply? |
| `amz_orders_hourly` | ts_local, order_id, sku, units, sales (for dayparting) |
| `tts_shop_daily` | date, gmv, orders, sku_orders, units, buyers, refunds_cohort, channel_mix |
| `tts_ad_rows` | date, campaign, ad_id, cost, impressions, clicks_dest, pdp_views, checkouts, purchases, gross_revenue |
| `tts_gmvmax_creative_rows` | video_id, creator, spu_id, publish_date, auth_type, cost, gross_revenue, orders, impressions, clicks, ctr, cvr, view_2s, view_6s |
| `tts_video_rows` | video_id, account, age_h, plays, completion, product_impr, product_clicks, orders, comments |
| `tts_creator_rows` | creator_id, handle, followers, category, gmv_30d, videos, ad_authorized, status, last_contact |
| `dtc_ga4_funnel` | date, source/medium, sessions, view_item, add_to_cart, begin_checkout, purchase, revenue |
| `meta_ad_rows` / `gads_rows` | date, campaign, adset/ad_group, ad, spend, impressions, clicks, cpm, ctr, atc, purchases, revenue |
| `gads_search_term_rows` | date, campaign, ad_group, search_term, match_type, impressions, clicks, cost, conversions, conv_value |
| `gads_product_rows` | date, campaign, item_id, title, product_type, custom_label_0..4, impressions, clicks, cost, conversions, conv_value |
| `gads_campaign_rows` | date, campaign, type, status, budget, bidding, target, spend, conv, conv_value, search_is, lost_is_budget, lost_is_rank |
| `gmc_issue_rows` | scope(account\|item), item_id?, issue, severity, detail, destinations |
| `shopify_product_rows` | product_id, handle, title, product_type, vendor, tags, status, price, compare_at, inventory, seo_title, seo_description, image_count |
| `ebay_listing_rows` | listing_id, title, category, price, qty, specifics_missing[], photos, impressions, ctr, views, sales_conv, promoted_rate |
| `etsy_listing_rows` | listing_id, title, tags[], attributes, price, visits, views, favorites, orders, conversion, ads_spend, ads_revenue |

Every normalized table carries `_source_file`, `_ingested_at`, `_store_id`, `_currency` and `_tz`.

### B3.4 Approval levels (autonomy ladder)

| Level | Name | Allowed | Default for |
|---|---|---|---|
| 0 | **Read-only** | read, compute, report, alert | all analytics skills |
| 1 | **Draft** | produce drafts, bulk files and messages; nothing leaves the system | listing, ads, creative, reddit, appeals |
| 2 | **Execute-with-approval** | execute a `ProposedAction` after a human approves it via `x_approval_gate` | ad changes, listing pushes, price changes |
| 3 | **Delegated approval (v0.3)** | the Manager approves on the user's behalf by reading the PIN file the user granted (B7.1). Only inside the grant's scope (stores, action types, risk ≤ medium, caps, counts, expiry), with an email/SMS notice afterwards | **off until the user creates a grant** (B7.1, OQ-G18) |

**Hard rules:**
- `message_send`, `post_publish`, `appeal_submit` and `price_change` can never be level 3, even under a delegation grant (OQ-G18).
- Platform-mandated personal actions are never executed by an agent at any level. Examples: identity or business-information verification, and Amazon INFORM / "Review your account information" certification. The seller does these personally.
- Reddit posts and creator DMs always need a human to send them (A4.4, A3.5).
- **Buyer replies (v0.9, OQ-G24)** are the exception: under the owner's auto-send policy (X-13), confident replies are sent by the agent without approval. Held replies need the owner's own approval and are never PIN-delegated.

### B3.5 Evidence & provenance
- Every LLM claim about a metric must cite a `DecisionRecord.evidence[]` that came from an L1 tool output.
- The verifier (D5) rejects results whose numbers don't match the referenced table.
- Copy claims trace to `ProductFacts.claims[].evidence_ref`, or carry the tag `needs_data`.

### B3.6 Ads naming standard (adopted from the PLC data)
`<AdType>-<SKU|合集>-<TermType>-<GoalKPI>-<Match>-<Note>`, for example `SP-UI04C-品类词-ROAS-EM-类目大词`.

| Field | Values |
|---|---|
| TermType | 品牌词 brand / 品类词 category / 竞品 competitor / 长尾 longtail / ASIN / 类目 category-target / AUTO |
| GoalKPI | ROAS / CVR / RANK / DEF |
| Match | EM (exact) / PM (phrase) / BM (broad) / AU (auto) / PT (product targeting) |

`ec_campaign_name_parse` turns names into layer tags. Campaigns that don't parse are flagged `unclassified`, and the user is asked for a mapping (OQ-A4).

### B3.7 Secrets & models
- No API keys in skill JSON. LLM nodes use `apiKey: {type:"template", content:"{{secret:openai}}"}` resolved from eCan's key store.
- Current default (B8): the eCanAI proxy with `gpt-6-luna`. That model sometimes returns non-JSON, and six failures in a row end a browser step, so every role also names a `fallback` model.
- **Fallback provider (v0.4 decision OQ-G6): OpenAI.**
  - Configured as an eCan provider with its key in eCan's key store, never in skill JSON.
  - LLM nodes switch to it after a provider error or 2 invalid-JSON answers. Browser nodes use `escalationModels`.
  - The fallback uses the **same model id** as the primary tier through the direct OpenAI provider (OQ-G6c confirms the ids exist there).
- **Model tiers (v0.8, OQ-G6b).** Nodes reference a **role**, never a model name. `model_policy` maps roles to three tiers:

| Tier | Model | Used for |
|---|---|---|
| `manager` | `gpt-6.1-sol` | The `ecom-manager` agent: the chat turn (D9), intent and goal interviews, playbook planning, MGR-01…05 (task routing, experiment evaluation, hypothesis and experiment design, ChangeProposals), weekly synthesis and digests |
| `web` | `gpt-6-luna` | Default for operator agents: browser-automation steps (T3 and recipe-guided), header mapping, verify/relevance checks, extraction clean-up, routine copy and buyer-message drafts, per-store diagnosis that matches a known playbook |
| `explore` | `gpt-6.1-terra` | **Escalation only**, for exploratory work (below). It is never the default for a node |

```ts
type ModelPolicy = {
  tiers: { manager: string; web: string; explore: string };       // "gpt-6.1-sol" | "gpt-6-luna" | "gpt-6.1-terra"
  roles: Record<"manager_chat" | "planning" | "analysis" | "writing" | "vision" | "cheap" | "browser", keyof ModelPolicy["tiers"]>;
        // v0.8 default: manager_chat, planning → manager; everything else → web
  escalation: {
    enabled: boolean;                       // default true
    from: "web"; to: "explore";
    applies_to_modes: ("explore")[];        // only tasks whose TaskEnvelope has mode = "explore"
    triggers: { invalid_json_after: number;          // default 2
                no_progress_steps: number;           // browser: default 8 steps without state change
                step_cap_hit: boolean;               // default true
                self_confidence_below: number;       // default 0.6
                verifier_rejected: boolean };        // default true
    caps: { per_store_per_day: number;      // default 5 escalated tasks
            explore_token_share_max: number;// default 0.25 of the tenant's daily AI budget
            per_task_max: 1 };              // one escalation per task, then fail or ask
  };
  fallback: { provider: "openai"; same_model_id: true; after_provider_errors: 1; after_invalid_json: 2 };
};
```

- **What counts as exploratory** (`TaskEnvelope.mode = "explore"`; the Manager sets it, operators cannot set it on themselves):
  - Experiment arms that run inside the exploration budget (MGR-04, B9).
  - X-12 recipe authoring or repair, and T3 runs on pages that have no recipe or extractor yet (B6).
  - X-14 diagnosis when no known playbook pattern matches.
  - P4 research skills (market, competitor and product research).
  - Onboarding discovery of a new store or a new platform pack.
- **Escalation rules:**
  - A task escalates **once**. If terra also fails, the task returns `status: "failed"` with evidence, or raises an InputRequest. It does not loop.
  - Routine (`mode: "run"`) tasks never escalate. They fall back to OpenAI on provider errors only.
  - When a cap is hit, the task continues on luna or is deferred, and the Manager mentions it in the digest.
  - Every escalation is recorded on the SkillResult: `model_used`, `escalated_from`, `trigger`, and tokens. Its cost goes to the AI-cost line of the profit ledger (B9.10).
- **Learning from escalations (D10):**
  - The Manager tracks the success rate of luna vs terra per task type.
  - If terra keeps being needed for a task type, it proposes a ChangeProposal: either make terra the default for that type, or build a recipe/extractor so luna can do it.
  - If escalation rarely changes the outcome, it proposes tightening the triggers.
  - Changing tiers or caps is a level-2 approval (the user approves). Raising `explore_token_share_max` is on the never-delegated list.
- The Manager itself does not escalate: sol is its only tier, plus the OpenAI fallback.

### B3.8 Prompt structure standard
Every LLM node's system prompt uses eCan's prompt sections in this order:
1. `goals`: the role and the one job of this node.
2. `guidelines`: the distilled playbook rules from Part A, cited by ID.
3. `rules`: hard constraints, including "never compute numbers; use provided tables", "cite evidence ids", "output ONLY JSON matching `{{output_schema}}`", the red list A9, and the approval level.
4. `examples`: 1–2 few-shot examples.

Shared rule text lives in reusable prompt fragments: `frag_fact_discipline`, `frag_json_only`, `frag_red_list`, `frag_compliance_basics`, `frag_decision_record`. These are injected via variables so one edit updates every skill.

## B4. Shared variables catalog

Each variable is resolved via `source: api` from the KB (tool `ec_kb_get`) unless noted. Skills declare which ones they read.

| Var | Shape | Purpose |
|---|---|---|
| `{{store_profile}}` | StoreProfile | currency, timezone, targets, approval policy |
| `{{product_facts}}` | ProductFacts (per SKU) | product truth + claims |
| `{{policy_pack}}` | `{market, category, banned_terms:{absolute[],promo[],eco[],safety[],antimicrobial[],medical[],time[],competitor_brands[]}, required_formats:{title_max:200,bullet_words:[10,25],desc_words:[150,200]}, cert_format}` | compliance lexicon per market × category (A2.2, A2.6) |
| `{{thresholds}}` | `{amz_ads:{negate_clicks:30, gray_clicks_min:15, bid_cut_strong_rel:0.5, bid_cut_hi_hi_lo:0.1, bid_cut_hi_hi_hi:0.2, bid_cut_lo_hi_lo:0.2, bid_cut_lo_hi_hi:0.4, roas_cut_below_avg:0.2, dependency_gap:0.15, test_bid_mult:[1.2,1.5], adj_step:[0.1,0.2], min_budget_cpo_mult:1.0, waterfall_eval_days:[3,5]}, tts:{min_impr:1000, min_dest_clicks:30, ctr_flag:0.03, ctr_priority:0.01, creative_ctr_min:0.01, creative_cpm_max:30, max_adj_per_day:2, roi_loosen_step:0.5, promo_expiry_h:72}, dtc_meta:{…[INF]}, reddit:{fit_priority:8, fit_test:5, community_min:15}, anomaly:{z:2.0, pct:0.25}}` | every numeric rule. Versioned. Editable only by a human |
| `{{lifecycle_stage}}` | per SKU: `launch|growth|stable|clearance` + `stop_bleed|stabilize|scale` | P6 |
| `{{brand_voice}}` | `{tone, do[], dont[], sample_copy[]}` | writing skills |
| `{{model_policy}}` | `ModelPolicy`: `{tiers:{manager:"gpt-6.1-sol", web:"gpt-6-luna", explore:"gpt-6.1-terra"}, roles, escalation, fallback}` | B3.7 (v0.8) |
| `{{approval_policy}}` | `{level_max_by_action_type, caps:{bid_change_pct_max, budget_change_pct_max, actions_per_day_max}, approvers_by_action_type, link_ttl_h:24, link_ttl_immediate_h:2, pin_required_for_risk:"high", resend_after_h:4}` | B3.4, B7 |
| `{{browser_registry}}` | `{recipes: BrowserRecipe[], extractors: JsExtractor[], selectors: Record<string,string>}` (versioned, B6.2) | X-08, X-12 |
| `thresholds.gads` / `.growth` / `.ebay` / `.etsy` | v0.4 rule numbers from A10–A12 and X-14 (all `[INF]` until confirmed): e.g. `gads:{budget_tiers:[30,150], conv_for_maxconv:15, conv_for_troas:30, target_step_max:0.15, learning_days:7, neg_cost_mult_cpa:2, zombie_clicks:50, hero_roas_mult:1.3, budget_step:0.2, stop_loss_cpa_mult:3, tracking_gap_warn:0.25}` | DTC-03/09/10, EBY-*, ETS-*, X-14 |
| `thresholds.browser` | `{default_min_interval_s:8, pages_per_site_per_day:{amazon_shopper:300, seller_central:200, tiktok_seller:200, reddit:300}, async_poll_s:300, async_max_min:180}` `[INF]` | B6 |
| `{{output_schema}}` | JSON Schema of this node's result | injected per node |
| `{{frag_*}}` | text | shared prompt fragments (B3.8) |
| `{{competitor_set}}` | per SKU: `[{asin|product_id|domain, name, role}]` (3–5) | competitor tracking |
| `{{calendar}}` | events: Prime Day, BFCM, Deals, peak windows per marketplace | planning skills |
| builtins | `current_time_local`, `task_id`, `agent_id`, `tools_schema`, `human_input` | from eCan |

## B5. Tool catalog

### B5.1 Reuse existing eCan tools
- **Browser:** `in_browser_execute_javascript` (T2 extractors), `in_browser_wait_for_element`, `in_browser_go_to_url`, `in_browser_extract_content`, `in_browser_click_element_by_*`, `in_browser_input_text`, `in_browser_upload_file`, `in_browser_save_href_to_file`, `os_connect_to_chrome`, `os_connect_to_adspower`.
- **Files:** `os_read_document`, `os_write_file`, `nas_save_text`, `nas_upload_file`, `nas_read_file`.
- **Execution and scheduling:** `python_run_extern`, `add_timer`, `rpa_supervisor_scheduling_work`, `rpa_operator_dispatch_works`, `rpa_operator_report_work_results`.
- **Messaging and retrieval:** `send_chat`, `rag_query`.

### B5.2 New MCP tools to build (L1, deterministic)

| Tool | Input | Output | Notes |
|---|---|---|---|
| `ec_schemas_get` | `{name}` | JSON Schema | registry for all B3 shapes |
| `ec_report_detect` | `{artifact_id}` | `{report_type, platform, confidence, header_map}` | fingerprints headers (CN and EN variants, ERP exports) |
| `ec_report_normalize` | `{artifact_id, report_type?, store_id}` | `{table:string, artifact:ArtifactRef, rows, warnings[]}` | cleans sentinels ("有花费无销售额", "--", "N/A"), %→float, currency, tz; writes to the local analytic DB (DuckDB/SQLite) |
| `ec_table_query` | `{sql, params?, limit?}` | `{columns[], rows[][], row_count}` | read-only SQL over normalized tables. **The main way LLM nodes get numbers** |
| `ec_metrics_calc` | `{table, group_by[], metrics[], window}` | rows with ctr, cvr, cpc, cpa, acos, roas, tacos, cpo, aov | single source of metric definitions (P9) |
| `ec_baseline_compare` | `{table, metric, keys, current_window, baselines:["d-1","same_wd_lw","avg7"]}` | rows with deltas, z-scores | anomaly basis (A3.1) |
| `ec_rules_eval` | `{ruleset_id, table|rows, thresholds_ref}` | `{matches:[{rule_id, entity, inputs, suggested_action}]}` | encodes A2.3/A3.2/A3.3 rule tables as data (`rulesets/*.json`) |
| `ec_ngram_rootwords` | `{table, text_col, n:[1,2,3], metrics}` | root-word aggregates | root-word negation/expansion |
| `ec_unit_economics` | `{price, cogs, first_mile, fba_fee, referral_pct, return_pct, promo_pct, other, fx}` | `{net, net_margin, platform_margin, breakeven_acos, breakeven_roas, cash_efficiency}` | A2.1, ROI sheet |
| `ec_cash_plan` | `{unit_econ, target_units_yr, quarterly_share[], ad_order_ratio_by_q[], lead_time_d, payout_ratio}` | quarterly cash need, ROI | ROI sheet model (formulas rebuilt) |
| `ec_inventory_cover` | `{sku_rows, window:7, lead_time_d, buffer_d}` | `{cover_days, reorder_flag, reorder_qty}` | A3.1 #4 |
| `ec_freight_calc` | `{l,w,h,cm, weight_g, mode}` | volumetric/billable weight | ÷6000 / ÷5000 |
| `ec_demand_estimate` | `{reviews, review_rate?, bsr?, category}` | `{sales_low, sales_mid, sales_high}` | SHEET |
| `ec_compliance_lint` | `{text_fields:{title,bullets[],desc,...}, policy_pack_ref, market, category}` | `{findings:[{field, rule, term, span, severity}], ascii_ok, length_ok}` | deterministic first pass (A2.2) |
| `ec_text_metrics` | `{fields}` | char/word counts per field | length checks |
| `ec_bulk_file_build` | `{platform:"amazon_ads"|"google_ads"|"gmc_supplemental"|"shopify_products"|"ebay", actions:ProposedAction[]}` | ArtifactRef (bulk-operations xlsx) | execution mode `bulk_file`, uploaded by a human or by L3 with approval |
| `ec_campaign_name_parse` | `{names[]}` | parsed layer, term type, KPI, match | B3.6 |
| `ec_decision_log` | `{op:"append"|"query", records}` | ids / records | durable history of decisions and actions |
| `ec_experiment` | `{op:"create"|"due"|"evaluate", card}` | card(s) | P8 registry; Manager polls `due` |
| `ec_kb_get` / `ec_kb_put` | `{collection, key}` / `{collection, key, value, version}` | record | store_profile, product_facts, policy_pack, thresholds, competitor_set |
| `ec_snapshot_diff` | `{collection, key, new_snapshot}` | `{changes[]}` | competitor and listing deltas |
| `ec_notify` | `{channel:"email"\|"sms", to[], template_id, vars, attachments[]?}` | `{message_ids[]}` | v0.2: email (HTML digest + links) and SMS (≤140 chars, counts + short link only). Quiet hours, one resend. Providers (v0.3): **AWS SES** (email) and **AWS SNS** (SMS + PIN) |
| `ec_approval_request` | `{actions:ProposedAction[], summary_md, approvers, expires_at, require_pin_for_risk}` | `{approval_id, links[]}`; webhook event `approval.decided` on submit | creates an `ApprovalRequest` + signed single-use URLs on the approval portal (B7); paired with `pend_event_node` |
| `ec_delegate_approve` | `{approval_id, grant_id}` | `{approved[], fell_back_to_manual[], reason_by_action}` | v0.3, B7.1. The only component that reads the PIN file. Checks the grant's scope and caps, then submits as the user. Never exposes the PIN to LLM nodes, logs or artifacts |
| `ec_input_request` | `{kind:"login"\|"otp"\|"missing_data"\|"review_patch", store_id, message, form_schema?, expires_at}` | `{input_id, link}`; webhook event `input.submitted` | same portal: "I've logged in → resume", small forms, patch review |
| `ec_session_check` | `{profile, site}` | `{logged_in:bool, account_hint?, blocker?:"login"\|"2fa"\|"captcha"}` | cheap registry JS check before any acquisition |
| `ec_browser_recipe_run` | `{recipe_id, version?, profile, params, dry_run?}` | `{status, downloads[], data?, step_log[], blocked?}` | T1 deterministic runner over `in_browser_*` tools (no LLM); enforces rate limits and allowlists |
| `ec_js_extract` | `{extractor_id, version?, profile, url?, args}` | `{data, schema_valid, url, duration_ms}` | T2: runs a **registry** snippet via `in_browser_execute_javascript`, with timeout; validates output |
| `ec_download_watch` | `{profile, filename_pattern, since_ts, timeout_s}` | ArtifactRef | moves the new file from the profile's download dir to NAS `inbox/<store>/` |
| `ec_registry` | `{op:"get"\|"list"\|"propose"\|"promote"\|"rollback", kind:"recipe"\|"extractor", id, version?, patch?}` | records | versioned recipe/extractor store; `promote` requires an approved review id |
| `ec_task_dispatch` | `{envelope:TaskEnvelope, target:"auto"|agent_id}` | `{task_id, agent_id}` | wraps agent discovery by skill + `send_chat` / `tasks add` |
| `ec_task_status` | `{task_ids[]}` | statuses | Manager polling fallback |
| `ec_utm_build` | `{source, medium, campaign, content, url}` | url | A4.4 schema |
| `ec_image_generate` | `{brief_ref, prompt, refs[], size, n, model_role}` | ArtifactRef[] | wraps the image-gen provider (OQ-C1) |
| `ec_image_review` | `{image, product_truth_images[], checklist}` | `{deviations[], verdict}` | vision model; A6 QC |

### B5.3 External connectors (DEFERRED by v0.2 decision OQ-G2: browser-first; kept as future options)
Exception: public, key-free web APIs that need no account login (e.g. PageSpeed Insights) may be called from an `http` node.

- **Amazon:** SP-API (reports, listings read, notifications), Ads API (reports, bulk), Brand Analytics (SQP/ABA).
- **Third-party data:** Keepa API, SellerSprite / Sorftime / Xiyou MCP, LingXing / SaiHu ERP.
- **TikTok:** TikTok Shop Partner API, TikTok Ads (Marketing API).
- **DTC and ads:** Shopify Admin, GA4 Data API, GSC API, Google Ads API, Meta Marketing API, PageSpeed Insights API.
- **Other:** Reddit API (read), Feishu Open API.

### B5.4 Browser extraction contract
All platform data acquisition goes through `x_browser_extract_skill` (X-08). It runs registry recipes (T1) and JS extractors (T2), and falls back to an LLM browser agent (T3) when they fail. See B6.

## B6. Data acquisition via browser (v0.2 decision OQ-G2)

### B6.1 Three tiers

| Tier | Mechanism | Used for | Cost / fragility |
|---|---|---|---|
| **T1 Recipe** | Deterministic navigation script (URL templates + fixed clicks/waits/asserts + download) run by `ec_browser_recipe_run` over the existing `in_browser_*` tools. **No LLM.** | Routine report downloads: Seller Central reports, Ads console reports (async), Brand Analytics, TikTok exports, GA4/Shopify/Meta/Google exports | 0 tokens. Breaks on UI change; detected by `assert` steps |
| **T2 JS extractor** | Reviewed, versioned JS snippet run in the page via `in_browser_execute_javascript` (`ec_js_extract`). It returns JSON matching a schema: from DOM tables, embedded page state, or by clicking the page's own export | Pages without exports: PDP snapshots, offers, reviews, account health, dashboards, Reddit rules, session checks | 0 tokens, fast. Breaks on DOM change; detected by schema validation |
| **T3 Agent** | eCan `browser-automation` node (browser-use + LLM), read-only action allowlist | Fallback when T1/T2 fail; one-off or exploratory pulls; sites without a recipe yet | Tokens and slower, but adapts. Every rescue produces a **patch proposal** (X-12) |

**Escalation:** run T1/T2. On `layout_changed`, `schema_invalid` or `timeout`, T3 completes this run, and X-12 proposes a fix. A human reviews the fix through the portal (B7), and the registry gets a new version. **LLM-written JS is never auto-promoted.**

### B6.2 Registry shapes

```ts
type BrowserRecipe = {
  id: string /*e.g. "amz.ads.report_request"*/; version: string; site: string; kind: "read" | "write";
  purpose: string; params_schema: object /*JSON Schema: marketplace, date_from, date_to, report_type...*/;
  session_check: string /*JsExtractor id*/;
  steps: RecipeStep[];
  async_report?: { request_steps: RecipeStep[]; poll: { every_s: number; max_min: number; ready_check: string /*extractor id*/ }; download_steps: RecipeStep[] };
  output: { kind: "download" | "json"; report_type?: string /*→ X-01*/; filename_pattern?: string; schema?: string };
  allowlist: { domains: string[]; submit_selectors?: string[] /*only report-request / search forms; write recipes: the upload form*/ };
  rate_limit: { min_interval_s: number; daily_max: number };
  last_verified_at: string; owner: string; notes?: string };

type RecipeStep = { id: string; op: "goto"|"click"|"input"|"select"|"wait_for"|"wait_s"|"scroll"|"js"|"download"|"upload"|"assert";
  target?: { css?: string; text?: string; xpath?: string; selector_ref?: string /*→ browser_registry.selectors*/ };
  value?: string /*supports {{param}}*/; js_id?: string; timeout_s?: number; optional?: boolean; on_fail?: "abort" | "fallback_t3" };

type JsExtractor = { id: string /*e.g. "amz.pdp.snapshot"*/; version: string; site: string; page_match: string /*URL regex*/;
  code_ref: string /*reviewed file in registry*/; args_schema: object; returns_schema: string /*canonical schema name*/;
  side_effects: "none"; uses_same_origin_fetch: false /*always false: v0.3 decision OQ-G15*/; timeout_ms: number; last_verified_at: string };

type RecipePatchProposal = { proposal_id: string; target_id: string; from_version: string; to_version: string;
  reason: string; diff: string; dry_run: { ok: boolean; sample?: any; schema_valid: boolean }; static_checks: { rule: string; ok: boolean }[];
  status: "proposed" | "approved" | "rejected" | "promoted"; reviewer?: string };
```

**JS extractor rules** (enforced by X-12 static checks and code review):
- Read-only. No form submits, no navigation, no `localStorage` or cookie writes.
- **No `fetch`, XHR, WebSocket or beacon calls at all** (v0.3 decision OQ-G15). Extractors read only the DOM and click the page's own export buttons.
- No `eval` or `Function` on page-provided strings.
- Return plain JSON only. The output is validated against `returns_schema`.
- A hard timeout applies.

### B6.3 Initial recipe & extractor catalog
★ = P0 (MVP). Write recipes run only after level-2 approval.

| ID | Site / page | Tier | Output → table | Consumers |
|---|---|---|---|---|
| ★ `amz.sc.business_report` | Seller Central → Business Reports → Detail Page Sales & Traffic by child item (daily, date range) | T1 | `amz_business_rows` | AMZ-08, 09 |
| ★ `amz.ads.report_request` | Ads console → Sponsored ads reports (search term, placement, campaign, targeting, advertised product) — async request → poll → download | T1 async | `amz_search_term_rows`, `amz_placement_rows`, `amz_campaign_rows` | AMZ-05, 06, 07, 08 |
| ★ `amz.ads.bulk_download` | Ads console → Bulk operations → download current structure (bids, budgets, placements, negatives) | T1 async | `amz_bulk_structure` | AMZ-04, 05, 06 (before/after values) |
| ★ `amz.ba.sqp` | Brand Analytics → Search Query Performance (ASIN view, weekly) | T1 | `amz_sqp_rows` | AMZ-05, 07, 08 |
| ★ `amz.sc.inventory` | Inventory → FBA inventory report / Manage inventory export | T1 | `amz_inventory_rows` | AMZ-06, 09 |
| ★ `amz.session_check.*` | per profile: seller, ads, shopper | T2 | `{logged_in}` | all |
| `amz.sc.all_orders` | Reports → Fulfillment → All Orders (30d) | T1 async | `amz_orders_hourly` | AMZ-06 dayparting |
| `amz.sc.returns` | Reports → FBA customer returns | T1 | `amz_returns_rows` | AMZ-09 |
| `amz.ba.top_search_terms` | Brand Analytics → Top Search Terms | T1 | `KeywordMetric` | AMZ-01 |
| `amz.sc.account_health` | Performance → Account Health (+ policy violations list) | T2 | `amz_account_health` | AMZ-10, 11 |
| `amz.sc.suppressed` | Manage inventory → suppressed / inactive listings | T2 | `amz_listing_status` | AMZ-10 |
| `amz.pdp.snapshot` | public PDP (shopper profile): title, bullets, images hash, price, Buy Box seller, offer count, rating, review count, BSR, variations | T2 | `amz_pdp_snapshot` | AMZ-10, X-05, AMZ-03 |
| `amz.pdp.reviews` | review pages, sorted by recent, N pages (rate-limited) | T2 | `Review` | X-04 |
| `amz.rufus.ask` | Rufus panel on PDP (only if OQ-G5 is approved) | T3 / T2 | answers | AMZ-03b |
| `amz.ads.apply_bulk` ✎ write | Ads console → Bulk operations → upload the file built by `ec_bulk_file_build` → read the processing report | T1 write | upload result | Manager execution (level 2) |
| `tts.sc.analytics_overview` | Seller Center → Analytics → overview / product / video | T1 / T2 | `tts_shop_daily`, `tts_video_rows` | TTS-01 |
| `tts.ads.custom_report` | Ads Manager → custom ad-level report (destination clicks, Shop columns) | T1 | `tts_ad_rows` | TTS-01, 03 |
| `tts.ads.gmvmax_creative` | GMV Max → Creative Hub export | T1 | `tts_gmvmax_creative_rows` | TTS-02 |
| `tts.affiliate.creators` | Affiliate Center → creators / collaborations | T2 | `tts_creator_rows` | TTS-04 |
| `tts.sc.campaigns` | Marketing → Campaigns (end dates, status) | T2 | `tts_campaigns` | TTS-01 #8 |
| `tts.sc.after_sales` | Customer service / returns / reviews queues | T2 | `tts_cases` | TTS-01 #3 |
| ★G `gads.campaigns_report`, `gads.search_terms_report`, `gads.shopping_products_report` | Google Ads → Reports / Insights → download CSV | T1 | `gads_campaign_rows`, `gads_search_term_rows`, `gads_product_rows` | DTC-03, X-14 |
| ★G `gads.conversions_summary`, `gads.change_history`, `gads.auto_apply_status` | Google Ads → Goals → Conversions; Change history; Recommendations → auto-apply | T2 | tracking / audit records | DTC-10, DTC-03 |
| `gads.bulk_upload` ✎ write | Google Ads → Tools → Bulk actions → Uploads (CSV from `ec_bulk_file_build(google_ads)`) → preview → apply | T1 write | upload result | Manager execution (level 2) |
| ★G `gmc.diagnostics`, `gmc.products_export` | Merchant Center → Products → Diagnostics / All products → download | T1 / T2 | `gmc_issue_rows` | DTC-09 |
| `gmc.supplemental_feed_upload` ✎ write | Merchant Center → Data sources → supplemental source → upload file | T1 write | — | DTC-09 execution |
| ★G `ga4.funnel_export`, `gsc.performance_export` | GA4 report/exploration export; Search Console → Performance → export | T1 | `dtc_ga4_funnel`, gsc rows | DTC-02, 03, 10 |
| ★G `shopify.products_export`, `shopify.orders_export`, `shopify.analytics_overview`, `shopify.customer_events` | Shopify admin exports; Analytics; Settings → Customer events (pixels) | T1 / T2 | `shopify_product_rows`, orders, sessions/CVR | DTC-09, 10, 11, X-14 |
| `shopify.products_csv_import` ✎ write | Products → Import (overwrite matching handles; only changed columns) | T1 write | — | DTC-11 execution |
| `shopify.pdp_snapshot`, `site.policy_pages` | public storefront | T2 | PDP content, policy presence | DTC-01, 09, 11 |
| `meta.ads_export` | Ads Manager export | T1 | `meta_ad_rows` | DTC-04 |
| `ebay.sh_listings_export`, `ebay.traffic_report`, `ebay.pl_reports`, `ebay.terapeak_sold`, `ebay.performance` | Seller Hub → Listings download / Performance → Traffic / Advertising reports / Research / Performance (seller level) | T1 / T2 | `ebay_listing_rows`, standards | EBY-01/02/03, X-14 |
| `ebay.sh_bulk_upload` ✎ write | Seller Hub → Reports → Uploads | T1 write | — | EBY-01/02 execution |
| `etsy.listings_export`, `etsy.stats`, `etsy.ads_report`, `etsy.search_visibility` | Shop Manager → Download data / Stats / Marketing → Etsy Ads / search visibility page | T1 / T2 | `etsy_listing_rows` | ETS-01/02, X-14 |
| `etsy.listing_edit` ✎ write | per-listing edit form (no native bulk import), serialized and slow | T1 write | — | ETS-01 execution |
| `reddit.search`, `reddit.sub_rules`, `reddit.top_30d`, `reddit.thread` | reddit.com (shopper-like read profile) | T2 | Reddit tables | DTC-05, 06, X-04 |
| `ahrefs.backlinks_export` / `semrush.backlinks_export` | A4.3 click paths → export | T1 | `backlink_rows` | DTC-07 |
| `keepa.product`, `sellersprite.keyword_export`, `xiyou.*`, `fastmoss.*` | only if subscribed | T1 / T2 | various | AMZ-01, AMZ-07, X-05 |
| `shopify.orders_open`, `shopify.inbox` | Shopify admin order list / Inbox (profiles `<SHOPIFY_PROFILE_1>`, `<SHOPIFY_PROFILE_2>`) | T2 | `StoreDailyCheck` parts | EX-02 (to cut T3 cost) |
| `etsy.orders_sold`, `etsy.messages`, `etsy.violations` | Etsy Shop Manager verified URLs (B8) | T2 | `StoreDailyCheck` parts | EX-03 |
| `ebay.sh_orders`, `ebay.messages`, `ebay.performance` | eBay Seller Hub verified URLs (B8). ⚠ The `<EBAY_PROFILE>` profile is no-touch, so extractors only run inside the existing skill's own browsing session | T2 | `StoreDailyCheck` parts | EX-04 |
| ★L `amz.sc.payments_report`, `shopify.payouts_export`, `ebay.payouts_report`, `etsy.payments_csv`, `tts.finance_settlements`, plus ads spend reports | payouts / transaction / settlement reports per platform (v0.5) | T1 | `ProfitLedgerRow` inputs | X-16, the Manager objective |
| `wmt.sc.reports` | Walmart Seller Center reports | T1 | Walmart tables | WMT-01 (P5) |

**Build priority (v0.4, growth-first; replaces the v0.3 list).**
1. **`*.session_check` for every profile.** This includes the new Google and TikTok profiles (OQ-D5, OQ-T5).
2. **★G Shopify + Google set:** Shopify exports, Google Ads reports + conversions summary, Merchant Center diagnostics/products, GA4/GSC exports.
3. **Marketplace traffic/catalog reports for X-14:** `amz.sc.business_report`, `ebay.traffic_report` + `ebay.sh_listings_export`, `etsy.stats` + `etsy.listings_export`, `tts.sc.analytics_overview`.
4. **Health:** `amz.sc.account_health`, `ebay.performance`.
5. **Write recipes** (once the approval portal works): `gads.bulk_upload`, `gmc.supplemental_feed_upload`, `shopify.products_csv_import`, `ebay.sh_bulk_upload`, then `amz.ads.apply_bulk`.
6. **Later (P3+):** Amazon / eBay / Etsy / TikTok ads reports, `amz.pdp.reviews`, everything else.

## B7. Approvals & human input via email + SMS (v0.2 decision OQ-G4)

**Flow:**
1. X-09 calls `ec_approval_request`.
2. The tool creates an `ApprovalRequest` and one signed single-use link per approver.
3. **Email:** HTML summary (decisions, a before → after table, evidence highlights, expiry) + the link.
4. **SMS:** "[eCan] US-1: 12 ad changes await approval, expires 18:00 → https://…/a/Xy7k". Counts and the link only, no details.
5. The approver opens the **mobile approval page**.
6. They approve, reject or edit each action, or bulk-approve low-risk actions.
7. If risk is ≥ the PIN level, they enter the 6-digit SMS PIN.
8. On submit, the page re-validates the actions server-side and fires the webhook `approval.decided`.
9. The eCan `pend_event_node` resumes and the Manager executes the approved actions.

```ts
type ApprovalRequest = {
  approval_id: string; run_id: string; store_id: string; created_at: string; expires_at: string;
  actions: ProposedAction[]; summary_md: string;
  approvers: { name: string; role: string; email?: string; phone_e164?: string }[];
  links: { approver: string; url: string; token_sha256: string; single_use: true; opened_at?: string }[];
  require_pin_for_risk: "high" | "medium" | "never";
  status: "pending" | "decided" | "expired" | "cancelled";
  decision?: { approver: string; decided_at: string; approved: string[]; rejected: { action_id: string; reason?: string }[];
    edited: { action_id: string; after: any }[]; pin_verified: boolean; ip?: string; user_agent?: string } };

type InputRequest = { input_id: string; run_id?: string; store_id: string; kind: "login" | "otp" | "missing_data" | "review_patch";
  message: string; form_schema?: object; link: string; expires_at: string; status: "pending" | "submitted" | "expired"; response?: any };
```

**Approval page:**
- Mobile-first. Actions are grouped by type: negations, bid changes, budgets, placements, listing updates, uploads.
- Each row shows before → after, rule/evidence, risk and reversibility.
- Edit fields are clamped to `approval_policy.caps`.
- There is an "approve all low-risk" button and an expiry countdown.

**The same portal also serves:**
- `InputRequest` pages: "I've logged in → Resume", OTP relay, missing-data forms, patch review with diff + dry-run sample (X-12).
- Digest pages linked from X-10 emails.

**Security:**
- Tokens are random 128-bit values, stored only as SHA-256.
- Links are single-use per approver.
- TTL is 24h, or 2h for the immediate class. HTTPS only.
- The PIN is a second factor for high-risk actions.
- On submit, the server re-checks that each action's target hasn't changed since it was proposed (stale → rejected).
- Rate limiting is applied, and the full audit trail goes to `ec_decision_log`.
- SMS bodies never contain prices, bids or account data.

**Delivery rules:**
- Quiet hours suppress non-immediate SMS, and email is always sent.
- One SMS reminder goes out at `resend_after_h`.
- When a request expires, nothing executes and the digest lists it as "expired".

**Hosting (v0.3 decision OQ-G13): eCan cloud.** This is the intl AppSync + Lambda stack (`lambda_functions/`, `eCan_lambda`). Server work items:
1. **API:** `createApprovalRequest`, `getApprovalPage(token)`, `submitApprovalDecision(token, pin?, decisions)`, `createInputRequest`, `submitInput(token, payload)`.
   - Store `approvals` and `input_requests` (token hashes, TTL) in DynamoDB.
2. **Page:** a public mobile page, e.g. a static page on S3 + CloudFront that calls the API.
3. **Delivery to the desktop:** an AppSync subscription to the user's agent. It needs the intl `onA2AMessage` subscription, which is **undefined today** (handoff server item 5).
   - A polling fallback (desktop polls `getApprovalStatus` every 60s while a `pend_event_node` waits) means a missed event never loses a decision.
4. **Providers (v0.3 decision OQ-G14):**
   - **AWS SES** for email: verify the sender domain and leave the SES sandbox.
   - **AWS SNS** for SMS and the PIN: US numbers need a registered origination identity (toll-free or 10DLC); other countries have their own rules.
   - The approver is the user only, so a single phone number and email need configuring at first.

### B7.1 Delegated approval via a PIN file (v0.3 decision OQ-G16)
The approver is **the store owner** (the tenant owner; in the reference deployment, the user). The owner may also let the Manager approve on their behalf by giving it permission to read a file that contains their PIN.

```ts
type DelegationGrant = {
  grant_id: string; created_by: "user"; created_at: string;
  expires_at: string;                 // required; max 30 days, renewable
  pin_file: string;                   // absolute local path outside any repo/skill/prompt folder, e.g. C:\\Users\\<USER>\.ecan\secrets\approval_pin.txt
  scope: { store_ids: string[]; action_types: ProposedAction["type"][]; max_risk: "low" | "medium";
           caps: { bid_change_pct_max?: number; budget_change_pct_max?: number; max_spend_delta_per_day?: number;
                   max_actions_per_run: number; max_actions_per_day: number } };
  notify_after: boolean;              // default true: email + SMS summary of what was auto-approved
  status: "active" | "revoked" | "expired" };
```

**Rules:**
- **Who reads the PIN:** only the deterministic tool `ec_delegate_approve`. The PIN never goes into an LLM node, a prompt variable, `state`, logs, artifacts or the decision log. It is checked against the portal's stored hash exactly as if the user had typed it.
- **Flow:**
  1. X-09 calls `ec_delegate_approve(approval_id, grant_id)`.
  2. The tool checks that the grant is active and unexpired, that each action is inside its scope and caps, that verify (D5) passed, and that no target is stale.
  3. It submits the in-scope actions as `approver: "user (delegated: <grant_id>)"`.
  4. Every other action falls back to the normal email + SMS link.
- **Never delegated:**
  - `message_send` that X-13 **held** (v0.9), Reddit posts and creator DMs; `post_publish`, `appeal_submit`, `price_change`.
  - Refunds, returns, replacements, compensation and case responses (the money action itself, whatever the message said).
  - Any action with risk "high".
  - Any write on a profile marked no-touch.
  - Anything platform-mandated as personal (B3.4).
  - Confirm or relax this list in OQ-G18.
- **Revocation:** delete or rename the PIN file, revoke the grant on the portal, or set `automation_paused`. A missing file means every action falls back to manual approval.
- **Protection:**
  - An NTFS ACL limits the file to the user's account.
  - The file holds the PIN only.
  - The portal rate-limits PIN checks, and a failed check revokes the grant and alerts the user.
- **Audit:** each delegated decision is logged with its `grant_id`. Digests list such actions under "auto-approved under grant G-…".

## B8. Existing assets on <BUILD_HOST> (v0.3, from OQ-G17)

> **v0.6:** B8 describes the **reference deployment** (the author's own stores and machine). It is instance data for development, testing and migration, not product design. Nothing here may leak into skills, packs or defaults (B9.1, B9.10).

**Sources:**
- `\\\\<BUILD_HOST>\\Users\\<USER>\PycharmProjects\eCan.ai` (branch `us_ec_skills`).
- Its handoff doc `docs/handoff/2026-10-27_intl_cloud_sync_and_amazon_skill.md`.
- The Claude project memory under `\\\\<BUILD_HOST>\\Users\\<USER>\.claude\projects\C--Users-<USER>-PycharmProjects-eCan-ai\memory\`.

This was a read-only survey; nothing on that machine was changed. `.claude\skills` there holds only the standard synced Claude skills, nothing eCan-specific.

### B8.1 Skills already built (status as of 2026-11-08)

| Skill (folder, id) | Agent / task | Browser profile | Prompt | What it does | Status | Role in this spec |
|---|---|---|---|---|---|---|
| `amazon_after_sales_skill` (<SKILL_ID>) | <AGENT_ID> / <TASK_ID> | `<AMZ_SELLER_PROFILE>` | <PROMPT_ID> | Read-only Seller Central daily check: FBM orders, buyer messages, account health, red flags (clicks into each) → report | Works. Daily ~13 steps / ~162k tokens; deep dives hit the 40-step cap (~530k) | **EX-01**; base for AMZ-10, feeds AMZ-11 |
| `shopify_after_sales_skill` (<SKILL_ID>) | <AGENT_ID> / <TASK_ID> (schedule) | `<SHOPIFY_PROFILE_1>`, `<SHOPIFY_PROFILE_2>` | <PROMPT_ID> | Daily check of 2 stores | Works; in-app settings-page render stall still open | **EX-02** |
| `etsy_after_sales_skill` (<SKILL_ID>) | <AGENT_ID> / <TASK_ID> | `<ETSY_PROFILE>` (proxied) | <PROMPT_ID> | Daily check, allowlisted Shop Manager URLs only | Works | **EX-03** |
| `ebay_after_sales_skill` (<SKILL_ID>) | <AGENT_ID> / <TASK_ID> | `<EBAY_PROFILE>` (proxied, strict no-touch) | <PROMPT_ID> | Daily check; stops on CAPTCHA with `login_required` | Works | **EX-04** |
| `review_miner_skill` (<SKILL_ID>) | <AGENT_ID> / <TASK_ID> | `<AMZ_SHOPPER_PROFILE>` (shopper account) | <PROMPT_ID> | Niche → leading listings' critical reviews → complaints / praise / ideas / competitors | Compiles; blocked by the eCanAI gateway returning empty `choices` | **EX-05**; base for X-04 (Amazon source) |
| `idea_reality_check_skill` (<SKILL_ID>) | <AGENT_ID> / <TASK_ID> | `<AMZ_SHOPPER_PROFILE>` | <PROMPT_ID> | Product idea → blunt verdict | Same blocker | **EX-06**; base for AMZ-01 `evaluate` mode |

**Common shape:** `Start → code_set_<store> → browser-automation triage → code_save (report) → End`. A run is started by `run_agent_task`, or by `send_chat` to the agent, in which case the chat text is appended to the browser task as "Current Invocation Input".

### B8.2 Reusable code (adopted)
- **`agent/ec_skills/reports/report_store.py`:**
  - Writes reports to the dated folder `C:\reports\<category>\<store>\<date>\`.
  - Uploads them through a presigned S3 PUT, which is pending the server mutation `requestReportUploadUrl` (handoff server item 3).
  - Provides `day_title`.
- **`store_report.py`:**
  - Per-platform rendering (`PLATFORMS`: amazon / shopify / etsy / ebay).
  - Report keys: `orders`/`fbm_orders`, `buyer_messages`/`customer_messages`, `account_health`, `red_flags`, `login_required`.
  - A failed or wrong-store run is filed as **"CHECK DID NOT COMPLETE", never as an all-clear.**
- **Research reports:** `review_report.py` and `idea_verdict.py` (a run that found nothing is "MINING DID NOT COMPLETE").
- **Profile plumbing:**
  - The `browser_profiles.json` registry.
  - Local-server `browser_profile.launch/status/stop`.
  - Relay revival, `--restore-last-session`, and CDP `Browser.close`.

**Spec changes that follow:**
- X-10 and every skill's artifact saving reuse `report_store`, with category = the skill's domain.
- `ArtifactRef.uri` is the local report path, plus the S3 key once upload works.
- The "never an all-clear on failure" rule applies everywhere: a `failed` or `partial` SkillResult renders as CHECK DID NOT COMPLETE in digests.

### B8.3 Conventions adopted (they override earlier parts of this spec where different)
1. **State:** pass data between steps in `state.attributes.*`; top-level state keys are dropped. Browser steps read their instructions from `state.attributes.current_invocation_input`.
2. **Browser step on a registered profile:** `browser: "fingerprint"`, `browserProfileId: <id>`, `cdpPortAuto: true`. Registered profiles get no page-level fingerprint injection.
3. **Profiles are the stores' logins:**
   - Only launch, attach and read. Never save, delete, import or reset them, and never touch their cookies, Preferences or storage.
   - Close windows from the app (`browser_profile.stop`), not with the window's X.
   - When a session expires, the seller signs in again; in this design that is `ec_input_request(kind:"login")`.
   - `<EBAY_PROFILE>` and `<ETSY_PROFILE>` are especially sensitive (proxied; eBay forced a CAPTCHA once). No probing navigation: B6 extractors only run inside those skills' own sessions.
4. **Prompts and diagrams:**
   - Prompts saved through the local server need `"format": "md"` and `mdContent`.
   - Prompts and diagrams are read at app start, so the implementation checklist includes a restart after changing either.
5. **Seller Central language:** English (answers the UI-language half of OQ-G17).
6. **Git hygiene:**
   - Code changes go on branch `us_ec_skills`.
   - Never commit `mcp_tools_schema.json`, `apitoken.txt`, `ads_profiles/`, `skills/` or `resource/skills/`.
   - Store and account specifics stay out of the repo, in KB records and local config. That includes the store names and agent ids in this doc's B8 tables.
7. **Model:** the eCanAI proxy. Existing skills (EX-01…06) run on `gpt-6-luna` (tier `web`). The Manager uses `gpt-6.1-sol`, and exploratory tasks may escalate to `gpt-6.1-terra` (B3.7, v0.8). Every node has an **OpenAI** fallback.

### B8.4 What the survey changes
- **Cost evidence for B6.** A T3-only daily Amazon check costs ~162k tokens. Deep dives cost ~530k and hit the step cap. Reading Account Health directly over CDP was far cheaper. So the first T2 extractors target exactly those pages (B6.3 build priority).
- **Platforms.**
  - eBay and Etsy are live and are added to the enums.
  - Their daily-check skills join the Manager unchanged, through adapters (B8.5).
  - No eBay/Etsy growth skills are planned yet (OQ-G20).
- **Priorities.**
  - The Amazon store had pending critical account items (business-information / INFORM verification) and listing removals, so account-health work is a live need. AMZ-11 moves to P1, in draft-only mode; the certification itself stays personal (B3.4).
  - Ads skills AMZ-04–07 stay in the plan, but their phase depends on OQ-G19.
- **Server dependencies now block P0** (handoff open items, listed in E1):
  - The eCanAI proxy's empty `choices` (item 6).
  - The report-upload mutation (item 3).
  - The intl API key (items 4 and 7).
  - The missing intl `onA2AMessage` subscription (item 5).

### B8.5 Adapters for adopted skills (EX-01…EX-06)
The Manager dispatches the existing skills without changing them. A thin adapter (a Manager-side code node) converts each skill's report into a SkillResult.

```ts
type StoreDailyCheck = {            // existing report.json written by store_report.py
  store: string; platform: "amazon" | "shopify" | "etsy" | "ebay";
  orders?: any[]; fbm_orders?: any[]; buyer_messages?: any[]; customer_messages?: any[];
  account_health?: any;
  red_flags?: { title: string; detail?: string; date?: string; asin?: string; severity?: string }[];
  login_required?: boolean };
```

**Mapping to SkillResult:**
- **`status`:** parsed → `done`; not parsed → `failed` (CHECK DID NOT COMPLETE); `login_required` → `needs_input`, which also sends `ec_input_request(kind:"login")` by email and SMS.
- **`summary`:** the existing `day_title` ("N orders, N processed, N todos, N redflags").
- **`anomalies`:**
  - Account-health, deactivation-risk and payment red flags → `class:"immediate"`.
  - Other red flags → `same_day`.
  - Unanswered buyer messages older than 24h → `same_day`.
- **`followups`:**
  - Amazon listing or policy red flags → AMZ-11 (draft POA / fix plan).
  - Review-related flags → X-04.
  - Shopify, Etsy and eBay → none; the digest lists them for the user.
- **`artifacts`:** the `report.md` / `report.json` paths from `report_store`.

| ID | Existing skill | Adapter output | Used by playbook |
|---|---|---|---|
| EX-01 | `amazon_after_sales_skill` | StoreDailyCheck → SkillResult | `stores_daily_check` |
| EX-02 | `shopify_after_sales_skill` | same | `stores_daily_check` |
| EX-03 | `etsy_after_sales_skill` | same | `stores_daily_check` |
| EX-04 | `ebay_after_sales_skill` | same | `stores_daily_check` |
| EX-05 | `review_miner_skill` | review_report.json → X-04 `result` shape (complaints / praise / opportunities, quotes kept) | `amz_new_product`, on demand |
| EX-06 | `idea_reality_check_skill` | idea_verdict → AMZ-01 `candidates[]` (verdict, reasons) | `amz_new_product`, on demand |

## B9. Agnostic design, learning & self-correction (v0.5)

### B9.1 Design rules for agnostic skills
1. **Inputs are ids, not literals.**
   - A skill receives `store_id` (and optionally `sku`/`listing_id`).
   - Platform, marketplace, currency, timezone, browser profile, category, policy pack, thresholds and brand voice all resolve from the KB (`ec_kb_get` with a scope).
2. **No literals in skills or prompts.**
   - Diagrams and prompts may not contain store names, URLs, ASINs, product nouns or category-specific word lists.
   - Category-specific content (e.g. the corpus's hair-care banned claims) lives in `policy_pack` layers keyed by category.
   - Lint check: `ec_skill_lint` (B9.9) rejects literals that match known store/product names.
3. **Platform differences live in packs, not in skill logic** (B9.2).
4. **Unknown is a valid state.**
   - When something isn't known yet (a new store, an unseen page, an unmapped report column), the skill returns `needs_input` or triggers discovery (X-15, X-08 T3 + X-12). It never guesses.
5. **Existing per-store skills migrate.** EX-01…04 hard-code stores (`code_set_<store>` nodes). They keep running through adapters, and in P2 the generic `x_store_daily_check_skill` (X-17) plus platform packs replace them.

### B9.2 Capability skills + platform packs
A **capability skill** is one generic flow (diagram + prompts with variables). A **platform pack** is a versioned data bundle loaded at run time:

```ts
type PlatformPack = {
  pack_id: string /*e.g. "listing.etsy"*/; version: string; capability: string; platform: string;
  recipes: string[];              // B6 recipe/extractor ids used for this capability on this platform
  schemas: { input: object; output: object; tables: string[] };
  rulesets: string[];             // ec_rules_eval ruleset ids (thresholds come from the B9.3 layers)
  policy_pack: string;            // compliance lexicon / format limits (title 80/140/200 chars...)
  prompt_fragments: Record<string, string>;   // platform know-how injected as {{pack.fragments.*}}
  kpis: { name: string; formula_ref: string; benchmark_ref?: string }[];
  write_recipes?: string[];       // execution paths (level 2)
  experiment_methods: ("native_ab"|"cohort_vs_control"|"pre_post"|"switchback")[];   // what B9.6 may use here
  source_specs: string[];         // the Part C behaviour IDs this pack implements
};
```

**Capability skills and their packs.** The Part C IDs are the behaviour specs that the packs implement.

| Capability skill | Packs (→ Part C behaviour specs) |
|---|---|
| `cap_store_onboarding` (X-15) | amazon, shopify, ebay, etsy, tiktok_shop, google (Ads/GMC/GA4/GSC), walmart |
| `cap_store_daily_check` (X-17) | amazon (EX-01, AMZ-10), shopify (EX-02), etsy (EX-03), ebay (EX-04), tiktok_shop (TTS-01) |
| `cap_listing_optimize` | amazon (AMZ-02, AMZ-03), ebay (EBY-01), etsy (ETS-01), shopify (DTC-11), gmc_feed (DTC-09 titles), tiktok_shop |
| `cap_ads_optimize` | amazon (AMZ-04/05/06/08), google (DTC-03), meta (DTC-04), ebay (EBY-02), etsy (ETS-02), tiktok (TTS-02/03) |
| `cap_account_health` | amazon (AMZ-11), ebay (EBY-03), gmc (DTC-09 account part), others as discovered |
| `cap_measurement_audit` | google/ga4/meta/shopify (DTC-10), marketplace attribution notes |
| `cap_site_cro` | shopify (DTC-01, DTC-02) |
| `cap_messages` (X-13) | all platforms |
| `cap_growth_diagnosis` (X-14) | all platforms |
| `cap_voc` (X-04) | amazon reviews (EX-05), etsy/ebay reviews, tiktok comments, reddit |
| `cap_competitors` (X-05) | per platform |
| `cap_opportunity` | amazon (AMZ-01, EX-06), tiktok (TTS-05), walmart (WMT-01) |
| `cap_creative` | images (X-06), video (X-07) |
| `cap_community` | reddit (DTC-05/06), social (DTC-08), creators (TTS-04), seo (DTC-07) |
| `cap_planning` | launch (X-11), ads dependency (AMZ-07), weekly ops (AMZ-09) |
| Foundation | X-01, X-02, X-03, X-08, X-09, X-10, X-12, X-16 |
| Manager | MGR-01 (chat), MGR-02 (evaluate), MGR-03 (scorecards), MGR-04 (experiment design), MGR-05 (change management) |

**Benefit:** adding a platform or marketplace means writing a pack (recipes + rules + fragments), not new skills. Learnings (B9.6) attach to scopes, so one store's lesson can be proposed for others on the same platform or in the same category.

### B9.3 Knowledge layering: how any value is resolved
Every rule threshold, prompt fragment, benchmark, policy term and default resolves through `ec_kb_resolve(key, scope)`. The highest layer wins:

1. **Immutable core.** The A9 red list, B3.4 hard rules, B7.1 never-delegated list, platform-mandated personal actions, and the user's budget caps. Read-only to every agent.
2. **User instructions.** Things you told the Manager in chat, stored as `UserInstruction` and confirmed (D9).
3. **Validated learnings** at store → SKU/listing scope.
4. **Validated learnings** at category scope.
5. **Validated learnings** at platform scope.
6. **Platform pack defaults.**
7. **Priors:** corpus `[SRC]` values and `[INF]` defaults. Lowest priority, and meant to be replaced.

`ec_kb_resolve` returns `{ value, layer, provenance_id }`. Every DecisionRecord stores the provenance of the thresholds it used, so the Manager knows which learning or prior produced each action.

### B9.4 Onboarding & discovery
X-15 (`x_store_onboarding_skill`, spec in C3) turns a new store into KB records. The steps:
1. **Discover the store from its signed-in profile.** Catalog, settings, policies, payouts, ads accounts, health, and 30–90 days of performance.
2. **Draft the records.** `StoreProfile`, `ProductFacts` per product, a category map and `competitor_set` candidates.
3. **Interview you in chat** for what can't be discovered: goals, budgets, COGS or margin, constraints, risk appetite.
4. **Write the confirmed records** to the KB.

Re-running onboarding refreshes the records and lists any differences.

### B9.5 Objective & the profit ledger
- **The Manager's objective** (`Goal`, created in chat, D9): **maximize monthly contribution profit** across the in-scope stores, subject to your constraints.

```ts
type Goal = { goal_id: string; statement: string; metric: "contribution_profit"|"revenue"|"orders"|"roas"|"custom";
  target?: number; period: "week"|"month"|"quarter"; scope: { store_ids: string[] | "all" };
  constraints: { ad_spend_cap_month: Record<string, number>; min_net_margin: number; max_risk: "low"|"medium";
                 health_must_not_degrade: true;
                 exploration_share_max: number /*default 0.2*/; max_concurrent_experiments_per_store: number /*default 2*/;   // owner-adjustable in chat (v0.6)
                 no_go: string[] };
  priority: number; status: "active"|"paused"|"done"; created_from: "chat"|"onboarding"; updated_at: string };

type ProfitLedgerRow = { date: string; store_id: string; platform: string; currency: string;
  gross_sales: number; refunds: number; platform_fees: number; ad_spend: number; cogs_est: number; shipping_cost: number;
  ai_cost: number;       // v0.6: LLM tokens + browser-run cost attributed to this store (B9.10)
  other_costs: number;
  contribution: number;  // gross_sales − refunds − platform_fees − ad_spend − cogs_est − shipping_cost − ai_cost − other_costs (confirmed v0.6, OQ-G29)
  cogs_coverage: number; // share of units sold with owner-provided (not estimated) COGS
  completeness: "complete"|"partial"|"estimated"; source_refs: string[] };
```

- **X-16 (`x_profit_ledger_skill`)** builds the ledger daily from payout/settlement reports (B6.3 rows added in v0.5) plus ads reports and the COGS from onboarding.
- Every experiment's primary metric ties back to contribution, or to a leading indicator with a documented link (e.g. CTR → sessions → orders).

### B9.6 Learning loop: hypothesis → experiment → learning

```
 observe (ledger, X-14 diagnosis, anomalies, chat requests)
   → hypothesize  (Hypothesis records, ICE-ranked)
   → design       (MGR-04: ExperimentDesign within exploration budget & one-variable rule)
   → approve      (X-09; experiments that change spend/listings are level-2 actions)
   → run          (operator agents execute arms via capability skills)
   → evaluate     (MGR-02: ec_experiment_analyze, guardrails, stop rules)
   → learn        (Learning records with scope + confidence)
   → adjust       (MGR-05: ChangeProposals to thresholds/prompts/playbooks/recipes)
   → repeat
```

```ts
type Hypothesis = { id: string; statement: string; expected_effect: { metric: string; direction: "up"|"down"; size_pct?: number };
  scope: { platform?: string; category?: string; store_id?: string; unit_ids?: string[] };
  source: "diagnosis"|"anomaly"|"learning_transfer"|"corpus"|"user"|"benchmark_gap";
  ice: { impact: number; confidence: number; ease: number; score: number }; status: "open"|"testing"|"supported"|"refuted"|"dropped" };

type ExperimentDesign = ExperimentCard & {
  hypothesis_id: string; unit: "campaign"|"ad_group"|"keyword"|"listing"|"sku"|"product_group"|"store";
  method: "native_ab"        /*Google Ads experiments, Amazon Manage Your Experiments*/
        | "cohort_vs_control"/*treated listings vs matched control listings*/
        | "pre_post"         /*with seasonality-adjusted baseline*/
        | "switchback";      /*alternating periods, for bids/budgets*/
  arms: { name: string; actions: ProposedAction[] }[]; control_selection?: { method: "matched"|"random"; matched_on: string[] };
  primary_metric: string; guardrail_metrics: { metric: string; max_degradation_pct: number }[];
  min_sample: { metric: string; n: number }; max_duration_days: number; budget_cap: number;
  operator_agent: string; analysis: "bayesian_uplift"|"diff_in_diff"|"sequential"; stop_rules: string[] };

type Learning = { id: string; statement: string;
  scope: { platform?: string; category?: string; store_id?: string; sku?: string };
  kind: "threshold"|"tactic"|"copy_pattern"|"creative_pattern"|"ui_recipe"|"benchmark"|"audience"|"pricing";
  evidence: { experiment_ids: string[]; effect: { metric: string; uplift_pct: number; ci90: [number, number] }; n: number };
  confidence: "low"|"medium"|"high"; status: "hypothesis"|"validated"|"refuted"|"superseded";
  applies_to?: { kb_key: string; value: any };          // e.g. thresholds.gads.zombie_clicks = 35 for store X
  transfer_candidates?: { scope: object; reason: string }[];  // propose testing in similar stores/categories
  created_at: string; review_at: string };
```

**Small-data reality.** These stores have low volume. So:
- **Prefer Bayesian / sequential analysis** with minimum windows and guardrails over fixed-sample tests.
- **Allow "directional" learnings.** These are low-confidence, used only as priors, and never promoted to stores beyond the one tested without a new test.
- **Pool evidence across similar units** (listings in one category) when the design says so.
- Analysis is deterministic: `ec_experiment_design` (sample size, matched controls) and `ec_experiment_analyze` (uplift, CI, guardrail checks).

**What each platform supports:**
- **Google Ads:** native experiments (campaign drafts / experiments) or switchback.
- **Amazon:** Manage Your Experiments (titles, images, A+) when the store is eligible; otherwise cohort or pre/post.
- **Shopify:** cohort or pre/post. Theme A/B needs an app (OQ).
- **eBay / Etsy:** listing cohort vs matched controls.
- **Bids and budgets anywhere:** switchback or cohort.

### B9.7 Self-adjustment: how agents change themselves and each other
Learnings turn into `ChangeProposal`s, handled by MGR-05 (spec in D6).

```ts
type ChangeProposal = { id: string;
  target: { kind: "threshold"|"prompt_fragment"|"prompt"|"playbook"|"schedule"|"recipe"|"model_route"|"pack_version"|"skill_version"; ref: string; scope: object };
  from_version: string; to_version: string; diff: string; reason: string; learning_ids: string[]; requested_by: "manager"|"x12"|"user";
  eval: { offline?: { suite: string; passed: number; failed: number; regressions: string[] };
          shadow?: { runs: number; agreement_pct: number; disagreements_sample: string[] };
          canary?: { store_id: string; days: number; kpi_delta: Record<string, number>; guardrails_ok: boolean } };
  stage: "proposed"|"offline_eval"|"shadow"|"canary"|"awaiting_approval"|"promoted"|"rolled_back"|"rejected";
  immutable_core_touched: false;      // proposals touching the core are rejected automatically
  approval_id?: string; promoted_at?: string; rollback_trigger: { metric: string; threshold: string; window_days: number } };
```

**Pipeline:**

| Stage | What happens |
|---|---|
| Offline eval | Run the versioned **regression suite**: fixtures per skill/pack from the acceptance tests in Part C, plus recorded real cases. Any regression stops the proposal |
| Shadow | For prompts and rules, the new version runs beside the current one on live inputs. Only the current version acts. Agreement and differences are reported |
| Canary | One store or unit for N days, with guardrails |
| Promote | Needs **the owner's approval**. **v0.6: no tuning grants at launch (OQ-G28).** An owner can create one later, within ±X% of the current value |
| Auto-rollback | If a rollback trigger fires after promotion, the previous approved version is restored automatically (safe, since it was already approved), and you are notified |

**Who may change what:**

| Target | Proposed by | Promoted by |
|---|---|---|
| thresholds, playbook schedules, model routes, pack versions | Manager (MGR-05) | user approval, or a tuning grant |
| operator prompts / prompt fragments | Manager | user approval (after offline eval + shadow) |
| recipes / JS extractors | X-12 | user approval (B6) |
| the Manager's own prompt (goals/guidelines sections only) | Manager | user approval only, never grant-covered |
| immutable core, approval policy, budgets, red list, delegation grants | — | **user only, outside the agent system** |
| skill code / L1 tools | — | developers (normal code review); the Manager can file a request |

### B9.8 Exploration vs exploitation
- **Exploration budget:** at most `Goal.constraints.exploration_share_max` (default 20%) of ad spend, and of listing-change volume, goes to experiments. The rest follows validated learnings and pack defaults.
  - **Adjustable (v0.6, OQ-G27):** this and `max_concurrent_experiments_per_store` are owner settings, changed in chat ("use 10% for exploration on eBay").
  - The Manager may *suggest* new values, with evidence, but can't set them; they are user-owned constraints.
- **Concurrency:**
  - At most 2 active experiments per store.
  - At most 1 per unit, which keeps P4's "one variable at a time".
  - A unit inside an experiment is locked against routine optimizations that would touch the tested variable.
- **Priority** is the ICE score × goal gap (the stores or metrics furthest from target first). Hypotheses that come from your instructions get a priority boost.
- **Learning transfer.** A validated learning in one scope makes MGR-04 propose a *transfer experiment* in sibling scopes. It is not applied blindly.

### B9.10 Built for every seller: multi-tenant product design (v0.6)
This is a product for all sellers. The author's stores and machine (B8) are the **reference deployment**, used for development and testing only.

```ts
type Tenant = { tenant_id: string;
  owner: { name: string; email: string; phone_e164?: string; locale: string /*zh-CN, en-US…*/; timezone: string };
  edition: "intl" | "cn"; store_ids: string[];
  // v0.7 (OQ-G32): single owner in v1. A `members` list with roles is reserved for a later version
  llm: { primary: "ecanai"; fallback: "openai"; byo_keys: boolean };
  channels: { chat: ("ecan" | "whatsapp" | "wechat")[]; email: string; sms_e164?: string };
  defaults: { exploration_share_max: number /*0.2*/; max_concurrent_experiments_per_store: number /*2*/; tuning_grant: null };
  cross_tenant_learning: "off";                                                 // v0.7 (OQ-G30): off; no cross-seller sharing in v1
  data_location: "local_first";                                                 // v0.7 (OQ-G33)
  cloud_data: "off" | "backup" | "sync";                                         // v0.9 (OQ-G10): default "off"; set by the owner
  legal_entities: { id: string; name: string; country: string; tax_id_ref?: string /*KB secret ref, never inline*/ }[] };   // v0.9 (OQ-G11): ≥1; reference deployment has one
```

**Isolation:**
- Every KB record, table row, artifact, learning, experiment, approval, decision and chat thread carries `tenant_id`.
- Every tool filters by the caller's tenant.
- Cloud parts never mix tenants: the approval portal, and report S3 keys, which already use `<user_id>/…`.

**Legal entities (v0.9, OQ-G11).**
- A tenant has one or more legal entities. Each store points to one. The reference deployment has a single entity for all stores; other sellers may have several.
- **What the entity changes:**
  - The profit ledger rolls up per store, per entity and per tenant. Shared AI cost is split pro rata by gross sales across all stores (OQ-G31), then summed per entity.
  - Digests and the weekly review can be filtered by entity.
  - Approvers and notify contacts can differ per entity (via `StoreProfile.owners`).
  - Tax ids and business documents are KB secret refs, never put in prompts.
- **What it does not change:**
  - Each store keeps its own browser profile (one profile per store, as before), whether or not entities differ.
  - The system never helps disguise links between accounts. Multiple accounts on one marketplace must have the platform's legitimate business reason, which the seller declares (A9). Identity and business verification stay personal actions (B3.4).

**No owner-specific defaults:**
- Thresholds, benchmarks and prompt fragments start as platform-pack priors that are identical for every tenant.
- They diverge only through that tenant's own learnings and instructions (B9.3).
- B8 instance data must never appear in packs or skills; `ec_skill_lint` checks this.

**Product costs (COGS) come from the store owner.** The system offers the easiest path available, in this order:
1. **Discovered** where the platform stores it, e.g. Shopify "Cost per item", or an ERP if one is connected later.
2. **Chat:** "the 11oz mugs cost me $3.20 landed". The Manager confirms and stores a UserInstruction of kind `fact`.
3. **Upload:** a CSV/sheet template (`sku, unit_cost, currency, freight, duty, packaging`) via chat attachment or portal.
4. **Estimate:** a category margin from the owner ("about 40% margin on candles"). Ledger rows built from it are marked `estimated`.

The Manager keeps asking proactively (D9) until `cogs_coverage` ≥ 80% of units sold. Until then, decisions based on break-even ROAS carry `confidence: "low"` and say so.

**AI cost is a business cost:**
- `ai_cost` = LLM token cost (eCan metering: `llm_pricing.py` / `metering.py`, and `SkillResult.metrics.llm_cost_usd`) + browser-run cost.
- Tasks with a `store_id` are charged to that store. Shared work (chat, cross-store diagnosis, manager loops) is allocated **pro rata by gross sales** (v0.7, OQ-G31). A store with no sales in the period gets an equal share of a small floor, so its cost is never hidden.
- Experiments and playbooks are budgeted in money *including* AI cost.
- The Manager prefers cheap paths (T1/T2 recipes, cheap models, fewer T3 steps) when the expected value is small, and reports AI cost as a share of contribution.

**Onboarding for anyone:** X-15 assumes nothing about edition, language (zh/en at minimum), marketplaces, currency or catalog size. A seller with no Google Ads or no Etsy simply has no pack activated for it.

**Learning across sellers:**
- Default: tenant-scoped only.
- **v0.7 (OQ-G30): off.** No tenant contributes to or reads another tenant's learnings. Layer-7 priors are only the corpus `[SRC]` and `[INF]` defaults shipped with the platform packs. Opt-in aggregate sharing may be revisited in a later version.

**Data location: local-first (v0.7, OQ-G33).**
- **Local** (the seller's eCan desktop, in the local DB / NAS folders):
  - KB records: StoreProfile, ProductFacts, COGS, goals, user instructions.
  - Analytic tables and the profit ledger.
  - Learnings, experiments and the decision log.
  - Chat history.
  - Browser profiles.
  - Reports and artifacts.
  - The recipe/extractor registry.
- **Cloud (eCan intl/cn)** holds only what must be reachable when the desktop is unreachable:
  - Approval and input requests: action summaries, token hashes, decisions, TTL-expired (B7).
  - SES/SNS delivery.
  - Report uploads, only if the seller enables them (the existing `report_store` S3 path).
  - Agent/skill sync as eCan already does.
  - Approval pages show only what the approver needs (before→after, reason). Raw tables, COGS and the ledger never leave the machine unless the seller exports them.
- **Consequences:**
  - The Manager and scheduled playbooks run only while the desktop app is running. Missed schedules run at the next start (the existing eCan schedule behaviour).
  - Decisions made in the portal while the desktop is offline wait in the cloud and are applied after re-validation (stale-target check) when it reconnects.
  - Backups are local; `ec_kb_export` / `ec_kb_import` can copy them to a folder the seller chooses. Cloud backup or sync is optional (below).

**Storage engines (v0.9, OQ-G10; recommendation adopted).**
- **Local, source of truth.** Everything is embedded, with no database server to install:
  - **SQLite** file per tenant, `ec_data.db` (WAL mode), for records: KB records, COGS, goals, the profit ledger, decision log, learnings, experiments, change proposals, the approval mirror, chat-derived instructions, and the recipe/extractor registry.
    - It is a separate file from eCan's `ks.db`, so app upgrades and eCan's own schema changes cannot break seller data, and export/backup is one file.
  - **Parquet** files for normalized report tables (search terms, campaigns, orders, traffic), partitioned `store/report_type/date`. They are append-only and cheap to keep for years.
  - **DuckDB** (embedded, inside the tool process) runs `ec_table_query`: read-only SQL over the Parquet tables, with `ec_data.db` attached for joins (COGS, ledger).
  - All access goes through one storage interface (`ec_store`: `get/put/query/export/snapshot`). Skills never open files directly, so the backend can change later.
- **Cloud, optional (`Tenant.cloud_data`), set by the owner:**
  - `off` (default): the cloud holds only approvals, input requests and message delivery (as above).
  - `backup`: a nightly encrypted snapshot of `ec_data.db` plus the Parquet folder goes to eCan cloud S3 (`<tenant_id>/backup/…`). It is encrypted on the desktop with a key from eCan's key store; the cloud cannot read it. `ec_kb_import` restores it onto a new machine.
  - `sync`: backup, plus a **read-only mirror** of summaries in eCan cloud: daily ledger per store and entity, digests, decision-log headlines, experiment status, and open approvals. The owner can then see status on a phone or in the portal while the desktop is off, and the portal can show richer context.
    - Raw report rows, COGS per SKU, browser data and chat history are never mirrored.
  - The desktop is the only writer. The cloud never writes back, except approval and input decisions (B7), which are re-checked on arrival.
  - Switching `cloud_data` down to `off` deletes the cloud copies after a 7-day grace period.
  - Multi-device chat in v1 means the eCan chat on the same desktop. Remote chat over WhatsApp/WeChat later goes through the channel bridges to the running desktop.

### B9.9 Extra tools (v0.5)

| Tool | Input → Output | Notes |
|---|---|---|
| `ec_kb_resolve` | `{key, scope}` → `{value, layer, provenance_id}` | B9.3 resolution; used by every skill instead of raw `ec_kb_get` for rules and fragments |
| `ec_experiment_design` | `{hypothesis, units, method, metric, mde?}` → `{arms, controls, min_sample, duration}` | deterministic (power / sample size, matched-control selection) |
| `ec_experiment_analyze` | `{design_id, data_refs}` → `{uplift, ci90, prob_better, guardrails, verdict}` | Bayesian / DiD / sequential |
| `ec_learning` | `{op: add|query|update|transfer, record}` → records | the learning store, with scopes |
| `ec_change` | `{op: propose|eval|shadow|canary|promote|rollback, proposal}` → stage | versioned config registry for packs, prompts, thresholds, playbooks |
| `ec_eval_suite_run` | `{suite_id, version_ref}` → results | regression fixtures per skill/pack |
| `ec_skill_lint` | `{skill_dir|prompt_id}` → findings | rejects store/product literals and keys in skill files (B9.1, B3.7) |
| `ec_ledger` | `{op: build|query, store_ids, date_range}` → `ProfitLedgerRow[]` | X-16 backend |
| `ec_store_snapshot` | `{op: snapshot|upload|restore, target: local_path|cloud}` → `{snapshot_id, bytes, sha256}` | v0.9 (OQ-G10): encrypted snapshot of `ec_data.db` + Parquet; `cloud` only when `cloud_data` ≠ off |
| `ec_cloud_mirror` | `{tables: ("ledger_daily"|"digests"|"decision_headlines"|"experiments"|"approvals_open")[]}` → `{pushed, skipped}` | v0.9: runs only when `cloud_data = "sync"`; pushes summaries only |
| `ec_kb_export` / `ec_kb_import` | `{tenant_id, target_dir}` → archive / restore | v0.7 local-first backup (B9.10) |

---

# PART C: Skills to build

## C1. Skill to-do list

**Phase key:**
- **P0:** foundation.
- **P1:** Amazon read-only analytics + listing.
- **P2:** Amazon growth + creative.
- **P3:** TikTok Shop.
- **P4:** DTC / Reddit / Google / Meta.
- **P5:** Walmart, write-execution, scorecards.

**Node key:** LLM = llm node, BR = browser-automation node, MCP = mcp tool node, CODE = code node, PEND = pend_event_node.

| ID | Skill folder | Role agent | Purpose (one line) | Nodes | Lvl | Phase |
|---|---|---|---|---|---|---|
| X-01 | `x_report_ingest_skill` | data-analyst | Detect, normalize and validate any downloaded report into canonical tables | MCP, LLM (fallback header map) | 0 | P0 |
| X-02 | `x_compliance_gate_skill` | compliance-officer | Lint and fix all customer-facing copy (lexicon + semantic + format), per platform policy pack | MCP, LLM | 0 | P0 |
| X-03 | `x_unit_economics_skill` | data-analyst | Unit economics, break-even ACOS/ROAS, cash plan, freight, demand estimate | MCP, LLM (explain) | 0 | P0 |
| X-08 | `x_browser_extract_skill` | browser-operator | All data acquisition: recipe (T1) / JS extractor (T2), LLM agent fallback (T3); downloads → ingest | MCP, BR, CODE, PEND | 0 (write recipes: 2) | P0 |
| X-09 | `x_approval_gate_skill` | ecom-manager | Email + SMS approval links, delegated approval, wait for decision, record it | MCP, PEND | – | P0 |
| X-10 | `x_report_composer_skill` | ecom-manager | Daily/weekly digests via email (SMS for decisions and immediate alerts) | LLM, MCP | 0 | P0 |
| MGR-01 | `mgr_ecom_manager_skill` | ecom-manager | **Chat agent (v0.5)** + orchestrator: understands requests, interviews, answers with evidence, runs playbooks, verifies, escalates, reports | LLM, MCP, PEND, loop | – | P0 |
| X-15 | `x_store_onboarding_skill` | data-analyst | **New v0.5.** Discover a store from its profile → draft StoreProfile/ProductFacts → chat interview → KB | BR(T1–T3), MCP, LLM | 0 | P0 |
| X-16 | `x_profit_ledger_skill` | data-analyst | **New v0.5.** Daily contribution-profit ledger per store from payouts + ads + COGS: the Manager's objective metric | MCP, LLM (explain) | 0 | P0 |
| X-14 | `x_store_growth_diagnosis_skill` | data-analyst | **New v0.4.** Per-store funnel → binding constraint → 30-day growth plan; the entry point for "make the stores sell" | MCP, LLM | 0 | P1 |
| X-13 | `x_buyer_message_drafter_skill` | community-manager | **New v0.4.** Draft buyer replies on every platform to raise response rate and time; the user sends | LLM, MCP | 1 | P1 |
| DTC-10 | `dtc_tracking_audit_skill` | data-analyst | **New v0.4.** Verify Google Ads / GA4 / Meta / Shopify conversion tracking before any spend | BR(T2), MCP, LLM | 0 | P1 |
| DTC-09 | `dtc_merchant_feed_skill` | listing-writer | **New v0.4.** Merchant Center health, feed titles/attributes, custom labels, supplemental feed | MCP, LLM | 1 | P1 |
| DTC-11 | `shopify_product_optimizer_skill` | listing-writer | **New v0.4.** Shopify product titles, descriptions, SEO and alt text; CSV import pack | LLM, MCP | 1 | P1 |
| DTC-01 | `dtc_cro_audit_skill` | data-analyst | Landing/PDP audit: message match, 5-point check, FAB/trust, policy pages, speed | BR, MCP, LLM | 0 | P1 |
| DTC-02 | `dtc_funnel_diagnosis_skill` | data-analyst | GA4/Shopify funnel drop-offs → traffic vs ads vs site cause → fix plan | MCP, LLM | 0 | P1 |
| DTC-03 | `dtc_google_ads_skill` | ads-optimizer | **Expanded v0.4.** Readiness gate; Shopping/PMax/Search plan + launch pack; daily stop-loss; weekly optimize; diagnosis | MCP, LLM | 1→2 | P1 |
| MGR-04 | `mgr_experiment_designer_skill` | ecom-manager | **New v0.5.** Hypotheses → experiment designs within the exploration budget; assigns operator agents | MCP, LLM | 1 | P1 |
| MGR-05 | `mgr_change_manager_skill` | ecom-manager | **New v0.5.** Learnings → ChangeProposals → offline eval / shadow / canary → approval → promote / rollback | MCP, LLM, PEND | – | P1 (offline eval + approval) → P2 (shadow, canary) |
| AMZ-11 | `amz_account_health_skill` | compliance-officer | Classify violations, draft POA, check document/address consistency | LLM, MCP | 1 | P2 |
| EBY-03 | `ebay_seller_standards_skill` | compliance-officer | **New v0.4.** Below Standard → recovery plan (defects, late shipment, cases, stock accuracy) | MCP, LLM | 1 | P2 |
| AMZ-02 | `amz_listing_writer_skill` | listing-writer | Generate, rewrite, localize or variant listings (PL templates) | LLM, MCP (X-02) | 1 | P2 |
| AMZ-03 | `amz_rufus_geo_optimizer_skill` | listing-writer | Probe → research → GEO audit → rewrite → compliance loop (simulated Rufus) | LLM, sheet-calls | 1 | P2 |
| X-04 | `x_voc_miner_skill` | data-analyst | **Extends EX-05 `review_miner_skill`.** Reviews/comments/threads → praise, complaints, persona, doubt map, phrases | LLM, MCP | 0 | P2 |
| EBY-01 | `ebay_listing_optimizer_skill` | listing-writer | **New v0.4.** Titles, item specifics, photos, shipping/returns, sold-comp pricing; bulk upload pack | MCP, LLM | 1 | P2 |
| ETS-01 | `etsy_listing_seo_skill` | listing-writer | **New v0.4.** Titles, 13 tags, attributes, photos, shipping; Stats search terms loop | MCP, LLM | 1 | P2 |
| TTS-01 | `tts_daily_ops_skill` | store-ops | The 12 daily tasks: am/midday/pm runs → anomaly log + daily report | sheet-calls, MCP, LLM | 0 | P2 |
| X-12 | `x_recipe_maintainer_skill` | browser-operator | Turn T3 rescues and health-check failures into reviewed recipe/JS patches | LLM, MCP, CODE | 0 | P2 |
| MGR-02 | `mgr_experiment_evaluator_skill` | ecom-manager | Evaluate due experiments and decisions past review → `Learning` records (v0.5) | MCP, LLM | 0 | **P1** (v0.5) |
| X-17 | `x_store_daily_check_skill` | browser-operator | **New v0.5.** Generic daily store check (platform packs) replacing per-store EX-01…04 | BR, MCP, LLM | 0 | P2 |
| AMZ-08 | `amz_ads_diagnosis_skill` | data-analyst | Daily anomaly + 5-step diagnosis + lifecycle stage + ad role per SKU | MCP, LLM | 0 | P3 |
| AMZ-05 | `amz_ads_search_term_optimizer_skill` | ads-optimizer | Harvest, negate and re-bid from search-term reports; root words; bulk file | MCP, LLM | 1→2 | P3 |
| AMZ-06 | `amz_ads_placement_budget_skill` | ads-optimizer | Placement multipliers, portfolio budget, budget ramp, dayparting | MCP, LLM | 1→2 | P3 |
| AMZ-04 | `amz_ads_launch_planner_skill` | ads-optimizer | Launch ad structure, budgets, naming, test/harvest/negate calendar | LLM, MCP | 1 | P3 |
| EBY-02 | `ebay_promoted_listings_skill` | ads-optimizer | **New v0.4.** Promoted Listings General ad rates + Priority CPC campaigns | MCP, LLM | 1→2 | P3 |
| ETS-02 | `etsy_ads_skill` | ads-optimizer | **New v0.4.** Etsy Ads listing on/off, budget, Offsite Ads economics | MCP, LLM | 1→2 | P3 |
| TTS-02 | `tts_gmvmax_analyzer_skill` | ads-optimizer | Quadrant, funnel, 2s↔ROI, creative cadence, P0/P1 actions | MCP, LLM | 1 | P3 |
| TTS-03 | `tts_ad_noconv_diagnoser_skill` | data-analyst | "Traffic but no conversion" decision tree | MCP, LLM | 0 | P3 |
| X-06 | `x_visual_brief_skill` | creative-studio | Visual Brief → prompts → generate → AI review vs product truth → fixes | LLM, MCP | 1 | P3 |
| X-07 | `x_video_script_skill` | creative-studio | 4-element brief → storyboard → hooks → matrix → QC checklist | LLM, MCP | 1 | P3 |
| AMZ-01 | `amz_product_opportunity_skill` | store-ops | **Extends EX-06 `idea_reality_check_skill`.** Keyword clustering, scoring, go/no-go memo, dev brief | MCP, LLM | 0 | P4 |
| TTS-05 | `tts_product_test_skill` | store-ops | Selection score + costed test card + scale/observe/stop verdict | MCP, LLM | 0 | P4 |
| TTS-04 | `tts_creator_crm_skill` | community-manager | Creator discovery, scoring, tiering, CRM, outreach drafts | BR/API, LLM, MCP | 1 | P4 |
| X-05 | `x_competitor_tracker_skill` | browser-operator | Snapshot 3–5 competitors and diff | BR, MCP, LLM | 0 | P4 |
| X-11 | `x_gtm_launch_planner_skill` | store-ops | 90-day GTM calendar, checklist, dashboard targets, reviews | LLM, MCP | 1 | P4 |
| AMZ-10 | `amz_store_patrol_skill` | browser-operator | **Extends EX-01 `amazon_after_sales_skill`.** Hijacker, Buy Box, suppression, variation, review-spike checks | BR, MCP | 0 | P4 |
| DTC-04 | `dtc_meta_ads_skill` | ads-optimizer | ABO creative race → CBO/ASC graduation, kill/keep, DPA | MCP, LLM | 1 | P4 |
| DTC-05 | `dtc_reddit_research_skill` | community-manager | Product fit, subreddit scoring, rules library, VOC table | BR, LLM, MCP | 0 | P4 |
| DTC-06 | `dtc_reddit_engage_skill` | community-manager | Daily thread scan + reply drafts + post/AMA drafts | BR, LLM, X-02 | 1 | P4 |
| DTC-07 | `dtc_seo_backlink_skill` | data-analyst | Backlink gap, outreach list, GEO content plan | BR, LLM | 0 | P4 |
| DTC-08 | `dtc_social_calendar_skill` | community-manager | Evergreen calendar, peak plan, KOL briefs, Partnership Ads checklist | LLM | 1 | P4 |
| AMZ-07 | `amz_ads_dependency_audit_skill` | data-analyst | Ad-dependency gap test + keyword budget restructure | MCP, LLM | 0 | P5 |
| AMZ-09 | `amz_store_weekly_report_skill` | data-analyst | Weekly ops: sales, SKU tiers, restock, returns, rough P&L | MCP, LLM | 0 | P5 |
| MGR-03 | `mgr_agent_scorecard_skill` | ecom-manager | Monthly per-agent/skill KPI scorecards | MCP, LLM | 0 | P5 |
| WMT-01 | `wmt_migration_ops_skill` | store-ops | Amazon→Walmart screen, pricing, WFS model, report diagnosis | MCP, LLM | 0 | P5 |
| AMZ-03b | `amz_rufus_research_skill` | browser-operator | Live Rufus questions. **Not built** (OQ-G5: simulated only) | BR | 0 | — |

**Adopted existing skills (B8.5), wrapped in P0:** EX-01 Amazon, EX-02 Shopify, EX-03 Etsy, EX-04 eBay daily checks; EX-05 Review Miner; EX-06 Idea Reality Check.

**v0.5 note:** the IDs in this table are **behaviour specs**. They are implemented as about 24 capability skills + platform packs (B9.2), so "skills to build" means capabilities + packs.

**Totals:** 56 behaviour specs (51 from v0.4 + X-15, X-16, X-17, MGR-04, MGR-05):
- 14 cross-platform/foundation: X-01…X-14 and the support skills.
- 12 Amazon, 5 TikTok Shop, 11 DTC, 3 eBay, 2 Etsy, 1 Walmart, 3 Manager.
- Plus 6 adopted skills, about 40 L1 tools, and the B6 registry.

**First build (P0 + P1):** the chat Manager, onboarding (X-15), the profit ledger (X-16), the Shopify + Google Ads packs, X-13/X-14, and the learning loop (MGR-02/04/05 with offline eval), plus the EX adapters.

## C2. Spec template (each skill below follows it)

> **Purpose** · **Sources** · **Trigger/cadence** · **Inputs** (`TaskEnvelope.inputs`) · **Vars read** · **Tools** · **Flow** (node sheet) · **LLM node prompts** (goal + key rules) · **Output** (`SkillResult.result`) · **Guardrails** · **Acceptance tests** · **Open items**

All outputs are wrapped in the SkillResult envelope (B3.2). Only the `result` payload is specified below.

---

## C3. Cross-platform & foundation skills

### X-01 `x_report_ingest_skill`
- **Purpose:** Turn any export into a canonical table (B3.3) with validation, so that downstream skills never parse files themselves.
- **Sources:** PLC (schema and sentinels), TTNC (column alignment), DEP (multi-source).
- **Trigger:** a file lands in the watched folder `inbox/<store_id>/`, a downloader skill finishes, or the Manager calls it.
- **Inputs:**
  ```ts
  { artifact_ids: string[]; expected_report_type?: string; store_id: string; date_range_hint?: [string,string] }
  ```
- **Vars:** `store_profile` (currency, timezone).
- **Tools:** `ec_report_detect`, `ec_report_normalize`, `ec_table_query`, `ec_kb_put`.
- **Flow:**
  1. `start`
  2. `loop` over artifacts:
     - `mcp:ec_report_detect`
     - `condition`: is confidence < 0.8?
       - Yes: `llm:map_headers` proposes a `header_map` from the header row + 5 sample rows, then a second `ec_report_detect` call verifies it.
       - No: continue.
     - `mcp:ec_report_normalize`
     - `code:validate` checks row counts, the date range, nulls in key columns, and duplicate days already ingested.
  3. `end`
- **LLM prompt (map_headers):**
  - Goal: map unknown column headers (CN or EN) to the canonical columns of `{{target_schema}}`.
  - Rules: output only `{canonical: source_header | null}`, and never invent a column.
- **Output:**
  ```ts
  { tables: { table: string; artifact: ArtifactRef; rows: number; date_range: [string,string]; dup_days_skipped: string[] }[];
    unrecognized: { artifact_id: string; reason: string }[] }
  ```
- **Guardrails:**
  - Idempotent: a re-ingest of the same sha256 is a no-op.
  - Currency and timezone must be explicit.
  - Partial days are tagged `partial_day=true` (TT12: use complete days only).
- **Acceptance:**
  - The PLC sample xlsx parses into 299 `amz_placement_rows`.
  - Sentinel strings become null, with the flags `spend_no_sales` and `spend_no_orders`.
  - Re-running produces 0 new rows.
- **Open:** OQ-X1. Confirm the exact export variants in use (LingXing vs Seller Central vs Ads console; CN or EN headers). Sample files are needed for each.

### X-02 `x_compliance_gate_skill`
- **Purpose:** The mandatory final gate on any listing, ad copy, video caption, Reddit draft, email or appeal before it reaches a human or a platform.
- **Sources:** PL appendix + amazon-compliance step; RESTR; TT4E; RDT (disclosure).
- **Trigger:** called by any writing skill, or on demand.
- **Inputs:**
  ```ts
  { content_type: "amz_listing"|"amz_ad_copy"|"tts_listing"|"video_script"|"reddit_post"|"reddit_comment"|"email"|"poa"|"dtc_page";
    market: string; category: string;
    fields: Record<string, string | string[]>;   // e.g. {title, bullets[5], description, backend_terms}
    product_facts_ref?: string;                    // to check claims against evidence
    auto_fix: boolean }
  ```
- **Vars:** `policy_pack` (market × category), `product_facts`, `frag_red_list`.
- **Tools:** `ec_compliance_lint`, `ec_text_metrics`.
- **Flow:**
  1. `mcp:lint` runs the deterministic checks: lexicon, ASCII, length, contact info, competitor brands, certification format.
  2. `llm:semantic_review` checks implied health or medical claims, implied superlatives, unverifiable numbers against `product_facts.claims`, misleading comparisons, and Reddit/TikTok disclosure.
  3. If `auto_fix` is set, `llm:fix` rewrites only the flagged spans.
  4. `mcp:lint` runs again on the fixed text.
  5. `end`
- **LLM prompt (semantic_review):**
  - Rules: never approve a claim without an evidence_ref; competitor comparisons may be generic only ("compared to ordinary X").
  - Output: findings, using the same shape as the lint findings.
- **Output:**
  ```ts
  { verdict: "pass" | "pass_with_fixes" | "fail";
    findings: { field: string; rule: string; term?: string; span?: [number,number]; severity: "block"|"warn"; source: "lexicon"|"semantic"; suggestion?: string }[];
    fixed_fields?: Record<string, string|string[]>;
    lengths: Record<string, {chars:number; words:number; ok:boolean}> }
  ```
- **Guardrails:**
  - A `block` finding fails the gate; writing skills cannot override it.
  - The policy pack is versioned and the version used is echoed in the result.
- **Acceptance:**
  - A test suite of 50 strings: one per banned term × category, plus false-positive cases (e.g. "safety lock" when "safe" is banned). Target: recall ≥ 98% on lexicon terms.
  - The fix loop converges within 2 iterations.
- **Open:**
  - OQ-A2: should promo words like "affordable" be banned in titles? PL contradicts itself.
  - OQ-X2: which categories and markets are in the initial `policy_pack`? (The PL lexicon is hair-care and small-appliance specific.)

### X-03 `x_unit_economics_skill`
- **Purpose:** One place for profitability math: per-SKU economics, break-even ACOS/ROAS, a quarterly cash plan, freight and demand estimates.
- **Sources:** SHEET, ROI, TT12 (unit contribution), GMVM.
- **Trigger:** called by AMZ-01, TTS-05, AMZ-04, WMT-01 and AMZ-09, or on demand.
- **Inputs:**
  ```ts
  { mode: "unit"|"cash_plan"|"freight"|"demand"|"price_sweep";
    sku?: string; overrides?: Partial<ProductFacts>; marketplace: string; platform: string;
    cash_plan?: { target_units_yr: number; quarterly_share: number[]; ad_order_ratio_by_q: number[]; lead_time_d: number; payout_ratio: number };
    price_sweep?: { prices: number[] } }
  ```
- **Tools:** `ec_unit_economics`, `ec_cash_plan`, `ec_freight_calc`, `ec_demand_estimate`, `ec_kb_get`.
- **Flow:**
  1. `mcp:ec_kb_get(product_facts)`
  2. `mcp:calc`, chosen by mode.
  3. `llm:explain` (optional) writes a 3–5 line explanation and flags assumptions (stale fees, FX).
- **Output:**
  ```ts
  { unit?: { price:number; net:number; net_margin:number; platform_margin:number; breakeven_acos:number; breakeven_roas:number; cash_efficiency:number; cost_breakdown: Record<string,number> };
    cash_plan?: { quarters: { q:string; units:number; ad_spend:number; cash_out:number; cash_in:number; roi:number }[]; first_batch_investment:number };
    freight?: { volumetric_kg:number; billable_kg:number }; demand?: { low:number; mid:number; high:number; method:string };
    sweep?: { price:number; net_margin:number; breakeven_acos:number }[];
    assumptions: string[] }
  ```
- **Guardrails:**
  - Fee tables are versioned, and the skill warns if they are older than 90 days.
  - The 2017 FBA and FX data in SHEET is never used.
- **Acceptance:** reproduces the SHEET worked example: pool float, ¥75 cost, $29.90 price. Expected platform margin ≈ 33% and net margin ≈ 9.4%, within ±0.5pp once its fee assumptions are entered.
- **Open:** OQ-X3. Where do current FBA, TikTok and WFS fee tables come from: SP-API fee preview, manual entry, or the ERP?

### X-04 `x_voc_miner_skill`
- **Purpose:** Turn raw reviews, Q&A, TikTok comments and Reddit threads into structured insight for listing, creative, product and CS.
- **Sources:** PL 3-A, 3-B, 3-C; RDT VOC table; DEV "semantic conflicts"; AIAD negative-review tags.
- **Trigger:** weekly (own and competitor reviews), before AMZ-02/AMZ-03/X-07, or on a negative-review spike.
- **Inputs:**
  ```ts
  { corpus: { reviews?: ArtifactRef; comments?: ArtifactRef; threads?: ArtifactRef };
    object: EntityRef; competitors?: EntityRef[]; category: string;
    modes: ("insight"|"qa_doubt_map"|"competitor_compare"|"negative_tagging")[];
    max_items?: number /*default 500, sampled by recency+rating*/ }
  ```
- **Tools:** `ec_table_query` (sampling, counts), `ec_kb_put` (stores the insight).
- **Flow:**
  1. `mcp:sample+count`
  2. `loop` over chunks of 100 items: `llm:extract`, which tags each item {theme, polarity, scenario, persona_clue, verbatim}.
  3. `mcp:aggregate`: frequencies are computed by code, not by the LLM.
  4. `llm:synthesize`: top-5 praise and complaints, semantic conflicts, doubt map, improvement opportunities, buyer phrasing.
  5. `end`
- **Output:**
  ```ts
  { praise: {point:string; freq:number; quotes:string[]}[]; complaints: {point:string; freq:number; quotes:string[]; tag:"product"|"logistics"|"service"|"misunderstanding"}[];
    conflicts: {feature:string; praise_quote:string; complaint_quote:string; inferred_need:string}[];
    personas: {who:string; scenario:string; motive:string; frequency?:string}[];
    doubt_map: {question:string; freq:number; place:"title"|"bullet"|"aplus"|"qa"|"video"|"faq"; answered_in_listing:boolean}[];
    substitutes_mentioned: {brand:string; count:number; context:string}[];   // internal only
    opportunities: {opportunity:string; linked_complaint:string; priority:"H"|"M"|"L"; direction:string}[];
    buyer_phrases: string[];
    negative_alerts?: {tag:string; count_window:number; threshold:number; breached:boolean}[] }
  ```
- **Guardrails:**
  - Quotes are verbatim, with their review_id kept.
  - Competitor brand names stay internal; downstream copy uses `buyer_phrases` only.
  - "Do not beautify negatives" (PL).
- **Acceptance:**
  - Every frequency equals the code count.
  - ≥ 90% of quotes are found verbatim in the corpus.
- **Data (v0.2):**
  - Amazon reviews via X-08 extractor `amz.pdp.reviews` (own + competitor ASINs, shopper profile, rate-limited).
  - TikTok comments via a `tts.sc.*` extractor.
  - Reddit via `reddit.thread`.
- **Open:** OQ-X4. What is the acceptable number of review pages per day per marketplace?

### X-05 `x_competitor_tracker_skill`
- **Purpose:** Track a fixed list of 3–5 competitors per SKU on a daily or weekly basis, and report deltas tagged fact / estimate / opinion.
- **Sources:** TT12 #10, PL 4-A/4-B/4-C, ADSC (competitor rhythm).
- **Trigger:** daily (TikTok) or weekly (Amazon), after a change event.
- **Inputs:**
  ```ts
  { platform: string; sku: string; competitor_set?: EntityRef[]; fields: ("price"|"title"|"bullets"|"images"|"rating"|"reviews"|"bsr"|"coupon"|"deal"|"videos"|"creators")[]; depth: "snapshot"|"teardown"|"forecast" }
  ```
- **Vars:** `competitor_set`.
- **Tools:**
  - `x_browser_extract` (sub-skill call) with extractors `amz.pdp.snapshot`, plus TikTok product snapshots and the web UIs of Keepa / FastMoss / Kalodata if subscribed (v0.2 browser-first).
  - `ec_snapshot_diff`, `ec_kb_put`.
- **Flow:**
  1. `loop` over competitors:
     - `sheet-call x_browser_extract` (or `mcp:keepa`)
     - `mcp:ec_snapshot_diff`
  2. `condition`: depth?
     - teardown: `llm:teardown` (PL 4-A: title structure, bullet order rationale, blind spots, keyword layout, 3 title directions).
     - forecast: `llm:forecast` (PL 4-C: stance, price anchor, warning table, 3 actions this week).
  3. `end`
- **Output:**
  ```ts
  { changes: { competitor: EntityRef; field: string; before:any; after:any; observed_at:string; kind:"fact"|"estimate" }[];
    teardown?: { competitor: EntityRef; title_structure:string; bullet_order:{n:number; theme:string; rationale:string}[]; blind_spots:{gap:string; concern:"H"|"M"|"L"; we_can_cover:boolean}[]; keyword_gaps:string[]; title_directions:string[] }[];
    forecast?: { competitor: EntityRef; stance:"offensive"|"defensive"|"wait"; next_move:string; warnings:{item:string; urgency:"H"|"M"|"L"; response:string}[]; actions_this_week:string[] }[] }
  ```
- **Guardrails:**
  - Never store or reuse competitor images or copy beyond analysis (A9).
  - Opinions are labelled as such.
- **Open:** OQ-X5. What is the data source per platform (Keepa license? FastMoss/Kalodata license?), and what are the scrape frequency limits?

### X-06 `x_visual_brief_skill`
- **Purpose:** Produce on-brand, product-true images (main, gallery, A+, ad, storyboard frames) through a brief-first pipeline with AI QC.
- **Sources:** VIS (Visual Brief, five inputs, failure modes, golden-6 gallery, A+ order), AIAD creative SOP, PS recipes.
- **Trigger:** on demand, from X-11 (GTM asset list), or from AMZ-03 recommendations.
- **Inputs:**
  ```ts
  { sku: string; channel: "amz_main"|"amz_gallery"|"amz_aplus"|"tts_cover"|"meta_ad"|"dtc_pdp"|"storyboard";
    purpose: string;               // the doubt/message this image must resolve
    insight_ref?: string;          // X-04 output
    references?: ArtifactRef[];    // style refs, kept separate from product truth
    n_candidates?: number /*default 10*/; sizes: string[] }
  ```
- **Vars:** `product_facts` (truth images and specs), `brand_voice`, `policy_pack` (image rules, e.g. Amazon white-background main image).
- **Tools:** `ec_image_generate`, `ec_image_review`, `nas_upload_file`.
- **Flow:**
  1. `llm:brief` writes the VisualBrief.
  2. `llm:prompt_compose`
  3. `mcp:generate ×n`
  4. `loop` over candidates: `mcp:ec_image_review` → `condition` on the verdict:
     - fix: `llm:targeted_fix_prompt`, then regenerate, at most 2 times.
     - regenerate, or keep.
  5. `end`. The best 2–3 go to a human (level 1).
- **Data shapes:**
  ```ts
  type VisualBrief = { why_this_image:string; audience:string; scene:string; one_message:string; evidence_shown:string;
    composition:{ format:string; product_area_pct:number; angle:string }; lighting_style:string;
    must_not:string[]; locale:string; text_overlay?:string };
  ```
- **Output:**
  ```ts
  { brief: VisualBrief; candidates: { artifact: ArtifactRef; review: { deviations:{type:string; detail:string}[]; verdict:"usable"|"fix"|"regenerate" } }[]; shortlist: string[] }
  ```
- **Guardrails:**
  - Product truth images are never altered: no changes to shape, color, logo or parts count.
  - No fake certification badges.
  - No competitor or celebrity likeness.
  - Model releases are required for any human likeness taken from references.
- **Open:**
  - OQ-C1: which image-generation provider and model (the corpus names "Nano Banana 2" / Gemini image)? Is there an API key?
  - OQ-C2: should the Photoshop generative-fill steps stay manual (recommended) or be automated through an OS-level tool?

### X-07 `x_video_script_skill`
- **Purpose:** Briefs and scripts for short videos (TikTok, Reels, Amazon video, SB video) using the 4-element method, with batch matrix generation.
- **Sources:** TT4E, GMVM golden formula and S/A/B tiers, SCRIPT matrix and compliance list, A3.4.
- **Inputs:**
  ```ts
  { sku: string; platform: "tiktok"|"reels"|"amazon_video"|"sb_video"|"youtube_short"; purpose: "organic"|"paid";
    audience_hint?: string; stage_5a?: "A1"|"A2"|"A3"|"A4"|"A5"; insight_ref?: string;
    n_scripts?: number; matrix?: { attributes: string[]; usages: string[]; proofs: string[] };
    remix_of?: { video_id: string; highlight_frames?: any } }
  ```
- **Tools:** `x_compliance_gate` (sub-skill), `ec_table_query` (video metrics for a remix), `os_write_file` (shot-list CSV).
- **Flow:**
  1. `llm:four_elements` picks 1 audience, 1 pain, 1 selling point and 1 scene, and maps the S/A/B tiers.
  2. `llm:storyboard` writes the 6 segments and 3 hooks.
  3. `condition`: matrix requested? If so, `code:combine` builds the combinations and `llm:batch_scripts` writes them.
  4. `sheet-call x_compliance_gate`
  5. `code:shotlist_csv`
  6. `end`
- **Output:**
  ```ts
  { scripts: { id:string; four_elements:{audience:string; stage:string; pain:string; selling_point:string; scene:string};
      hooks:{type:"question"|"scene"|"verification"; line:string}[];
      storyboard:{ t:string; shot:string; action:string; line_or_caption:string }[];
      must_shots:string[]; claims_to_verify:string[]; disclosure_label_required:boolean; length_s:number }[];
    shotlist_csv: ArtifactRef; qc_checklist:string[] }
  ```
- **Guardrails:**
  - Never reuse others' footage.
  - Any speed-up must be labelled.
  - Branded-content disclosure is flagged on paid or creator content.
  - Model demographics match the target market, with portrait rights (A9 replacement rule).
- **Acceptance:** for the TT4E carpet example input, the output reproduces the 6-segment structure with 3 hooks, and no claim appears outside `product_facts`.

### X-08 `x_browser_extract_skill`
- **Purpose:** The single entry point for all platform data acquisition (v0.2: browser-first). It runs registry recipes (T1) and JS extractors (T2) deterministically, falls back to the LLM browser agent (T3) only on failure, and hands downloads to X-01.
- **Sources:** eCan browser node config + `in_browser_*` tools (incl. `in_browser_execute_javascript`); PL rufus-research known issues; decision OQ-G2; B6.
- **Inputs:**
  ```ts
  { store_id: string;
    job: { recipe_id?: string; extractor_id?: string; version?: string; params: Record<string, any> }                      // T1/T2 (registry-driven)
       | { adhoc: { site: string; goal: string; start_url: string; extract_schema?: object;
                    download_expect?: { filename_pattern: string; report_type: string } } };                             // T3 only
    allow_fallback_agent?: boolean;                           // default true for reads, always false for writes
    write?: { approval_id: string; action_ids: string[] };    // ONLY for kind:"write" recipes (e.g. amz.ads.apply_bulk)
    ingest?: boolean;                                         // default true for downloads
    dry_run?: boolean }                                       // X-12 / health checks: run asserts, no download
  ```
- **Vars:** `store_profile.browser_profiles`, `browser_registry`, `thresholds.browser`.
- **Tools:** `ec_session_check`, `ec_browser_recipe_run`, `ec_js_extract`, `ec_download_watch`, `ec_registry`, `ec_input_request`, `x_report_ingest` (sub-skill).
- **Flow:**
  1. `mcp:ec_session_check(profile, site)`. If blocked (login, 2FA or captcha):
     - `mcp:ec_input_request(kind:"login"|"otp")` sends an email + SMS.
     - `pend_event_node` waits for `input.submitted` or a timeout.
     - Then the check runs again.
  2. `condition` on the job type:
     - recipe: `mcp:ec_browser_recipe_run`. For async reports: request → `pend_event_node` timer poll → download.
     - extractor: `mcp:ec_js_extract`.
     - adhoc: go to step 4.
  3. `condition`: did it succeed?
     - Yes: go to step 5.
     - No, and `allow_fallback_agent` is set: go to step 4.
     - Otherwise: fail with `blocked`.
  4. `browser-automation` (T3) with the goal + schema. Then `code:trace_to_patch` saves the successful action trace and emits a FollowupRequest to X-12.
     - Node config: `allowedActions = go_to_url, click, input_text, scroll, extract_content, wait_for_element, switch_tab, save_href_to_file, execute_javascript(read-only)`, `keepBrowserAlive=true`, `maxSteps=40`, `nodeTimeoutSeconds=600`, `loopHistoryMode=trim:10`, `useVision=true`, escalation model after 15 steps.
  5. Output handling:
     - Download: `mcp:ec_download_watch`, then `sheet-call x_report_ingest`.
     - JSON: `code:validate_json_schema`, then save as an artifact.
  6. `end`
- **T3 system prompt rules:**
  - Operate only on `{{site}}`.
  - Read-only: never purchase, message, edit listings, change settings, or submit forms other than report-request and search forms.
  - On login, captcha or 2FA, stop and return `needs_input`. Never type credentials.
  - Return JSON only, per `{{extract_schema}}`.
  - Take a screenshot of each page.
- **Output:**
  ```ts
  { tier_used: "T1"|"T2"|"T3"; recipe_or_extractor?: { id: string; version: string };
    data?: any; downloads?: ArtifactRef[]; ingested_tables?: string[]; screenshots: ArtifactRef[]; step_log: ArtifactRef;
    pages_visited: number; duration_s: number;
    blocked?: { reason: "login"|"captcha"|"2fa"|"layout_changed"|"rate_limited"|"report_not_ready"|"schema_invalid"|"timeout"; at_step: string };
    patch_followup?: FollowupRequest }
  ```
- **Guardrails:**
  - Read-only by default.
  - A `kind:"write"` recipe runs only when `write.approval_id` refers to approved actions, re-verified via `ec_decision_log`, and never with a T3 fallback. Initially the only write recipe is `amz.ads.apply_bulk`.
  - Rate limits and page budgets are enforced by the runners.
  - In-page JS comes only from the reviewed registry.
  - Captcha solvers are never used on platform logins.
- **Acceptance:**
  - Each ★ recipe (B6.3) runs unattended on 5 consecutive days.
  - A deliberately broken selector triggers a T3 rescue plus an X-12 patch proposal.
  - A logged-out profile produces an email + SMS input request within 1 min, and the run resumes after **Resume**.
- **Profiles:** the existing registry (`browser_profiles.json`): `<AMZ_SELLER_PROFILE>` (seller), `<AMZ_SHOPPER_PROFILE>` (shopper; used for `amz.pdp.*` and Rufus), `<SHOPIFY_PROFILE_1>`, `<SHOPIFY_PROFILE_2>`, `<ETSY_PROFILE>`, `<EBAY_PROFILE>`. Profile rules are in B8.3.
- **Open:** OQ-X6 (Ads console: does it run in the same seller profile?).

### X-09 `x_approval_gate_skill`
- **Purpose:** Human-in-the-loop approval for every level-2 action, via **email + SMS links to the mobile approval page** (v0.2 decision OQ-G4, B7). It is also used for level-1 sign-off when requested.
- **Inputs:**
  ```ts
  { actions: ProposedAction[]; decisions: DecisionRecord[]; summary_md: string;
    approvers?: string[];                 // owner keys; default = store_profile.owners by action type
    expires_in_h?: number;                // default approval_policy.link_ttl_h (24), immediate class 2
    require_pin_for_risk?: "high"|"medium"|"never";   // default "high"
    sms?: boolean }                       // default true
  ```
- **Tools:** `ec_approval_request`, `ec_delegate_approve` (B7.1), `ec_notify(email|sms)` via SES/SNS, `ec_decision_log`; `pend_event_node` (subscription `approval.decided`, with a 60s polling fallback; timeout = expiry).
- **Approver:** the store owner (OQ-G16; v0.6 generalized). Before the link flow:
  1. If an active DelegationGrant covers some actions, `ec_delegate_approve` handles those.
  2. **In-chat approval (v0.6, OQ-G26):** the remaining **low/medium-risk** actions are shown in the Manager chat as an approval card (approve / reject / edit, with bulk approve). The decision is recorded exactly like a portal decision.
  3. **High-risk** actions, and anything not decided in chat, go to email + SMS → portal (+ PIN).
  - On WhatsApp/WeChat (later), in-chat approval is allowed only once the channel identity is verified and linked to the tenant.
- **Flow:**
  1. `code:group_and_rank` groups actions by type and risk and marks the bulk-approvable low-risk ones.
  2. `mcp:ec_approval_request` creates the ApprovalRequest and a signed link per approver.
  3. `mcp:ec_notify(email)` sends the HTML summary: decisions, a before → after table, evidence and the link.
  4. `mcp:ec_notify(sms)` sends the counts, expiry and a short link (respecting quiet hours).
  5. `pend_event_node(approval.decided | timeout)`. With no decision after `resend_after_h`, one SMS reminder is sent.
  6. A mapping writes the decision to `state.attributes.approvals`, then `mcp:ec_decision_log(append)`. Edited actions are flagged for re-validation.
  7. `end`
- **Output:**
  ```ts
  { approval_id:string; approved: string[]; rejected: {action_id:string; reason?:string}[]; edited: {action_id:string; after:any}[]; expired: string[];
    approver:string; decided_at:string; opened_via:"email"|"sms"; pin_verified:boolean }
  ```
- **Guardrails:**
  - On expiry, nothing executes.
  - Edits are re-validated by the originating skill's rules and caps (Manager re-dispatch) before execution.
  - Links are single-use.
  - On submit, the portal rejects stale actions (their target changed since the proposal).
- **Acceptance:**
  - SMS link → approve on a phone → run resumes in under 1 min.
  - A reused or expired link executes nothing.
  - A high-risk action without a valid PIN is not approved.
- **Open:** OQ-G18 (the never-delegated list).

### X-10 `x_report_composer_skill`
- **Purpose:** Turn many SkillResults into one digest (daily or weekly), in the user's language, with the structure used in TT12 #12 and CDX weekly reports.
- **Inputs:**
  ```ts
  { period: "daily_am"|"daily_pm"|"weekly"|"monthly"|"event"; store_ids: string[]; results: string[] /*task_ids*/; audience: "operator"|"manager"|"exec" }
  ```
- **Tools:** `ec_task_status`, `ec_decision_log(query)`, `ec_notify`, `os_write_file` (md/html).
- **Delivery (v0.2):**
  - Email (HTML digest + portal link).
  - SMS only for the headline + link, and only when `decisions_needed` is non-empty or an immediate anomaly exists.
- **Output:**
  ```ts
  { digest_md: ArtifactRef; sections: { title:string; bullets:string[] }[]; decisions_needed: { action_ids:string[]; due:string }[]; sent_to: string[] }
  ```
- **Digest structure:**
  1. Headline (one business conclusion).
  2. KPIs vs targets.
  3. Anomalies (immediate → same-day → observe).
  4. Actions proposed and awaiting approval.
  5. Actions executed and their results.
  6. Experiments due.
  7. Tomorrow's / next week's priorities (risk → growth → observe).
- **Guardrails:** numbers are copied from results, never recomputed. Every line links back to its task_id.

### X-11 `x_gtm_launch_planner_skill`
- **Purpose:** Generate and track the 90-day new-product GTM plan across Amazon, DTC, TikTok and social.
- **Sources:** GTM docx/xlsx (full), GMV 3-stage launch, AMZ-04 hook.
- **Inputs:**
  ```ts
  { sku: string; launch_date: string; channels: ("amazon"|"dtc"|"tiktok_shop"|"social"|"email"|"pr"|"influencer")[];
    team: Record<string,string> /*role→owner*/; budget_cap?: number; targets_override?: Partial<GtmTargets> }
  ```
- **Tools:** `os_write_file` (xlsx/md Gantt), `ec_kb_put`, `add_timer` (milestone reminders), `ec_experiment` (registers the 48h/7d/30d reviews).
- **Data shape:**
  ```ts
  type GtmTask = { id:string; phase:string; name:string; owner_role:string; start_week:number /*-12..+4*/; end_week:number; deliverable:string; depends_on:string[]; status:"todo"|"doing"|"done"|"blocked"; priority:"P0"|"P1"|"P2"; risk?:string; skill_hint?:string /*e.g. "x_visual_brief_skill"*/ };
  type GtmTargets = { impressions_7d:number; engagement:number; lp_ctr:number; cvr:number; orders_7d:number; revenue_7d:number; cac:number; roas:number; reviews_ugc_30d:number; brand_search_lift_30d:number };
  ```
- **Output:**
  ```ts
  { plan: GtmTask[]; calendar: { date:string; channel:string; content:string; goal:string }[]; checklist: { item:string; owner_role:string; due_week:number; done:boolean }[]; targets: GtmTargets; reviews: { at:"48h"|"7d"|"30d"; questions:string[]; metrics:string[] }[]; gantt: ArtifactRef }
  ```
- **Manager hook:**
  - Tasks with a `skill_hint` are auto-proposed as dispatches when their start week arrives.
  - Reminders fire at the start and due date of each task.
- **Open:** OQ-X8. Are the GTM default targets (GTM xlsx: 500 orders / $50k in 7 days, and so on) placeholders, or should they be derived from the SKU's economics?

### X-12 `x_recipe_maintainer_skill`
- **Purpose:** Keep the browser registry (B6) working. It turns T3 rescue traces and failed health checks into minimal, reviewed patches for recipes and JS extractors, and never auto-promotes them.
- **Trigger:** a FollowupRequest from X-08 after a T3 rescue, or a failure in the daily `browser_registry_health` playbook.
- **Inputs:**
  ```ts
  { target: { kind: "recipe"|"extractor"; id: string; version: string };
    failure: { reason: string; step_id?: string; screenshot: ArtifactRef; dom_snapshot?: ArtifactRef; url: string };
    rescue_trace?: ArtifactRef /*T3 actions + element refs, if a rescue succeeded*/ }
  ```
- **Tools:** `ec_registry(get|propose)`, `x_browser_extract` (dry run of the candidate version), `ec_input_request(kind:"review_patch")`.
- **Flow:**
  1. `llm:diagnose` identifies what changed: a selector, URL, new modal, renamed column, or new export flow.
  2. `llm:propose_patch` writes the minimal diff to steps, selectors or JS.
  3. `code:static_checks` (JS rules in B6.2: no cross-origin calls, no submits or navigation, no storage writes, no eval, schema-shaped return).
  4. `sheet-call x_browser_extract(dry_run, candidate version)`
  5. `mcp:ec_registry(propose)`
  6. `mcp:ec_input_request(review_patch)` sends an email link showing the diff + dry-run sample.
  7. `pend_event_node(input.submitted)`. If approved: `ec_registry(promote)`.
  8. `end`
- **Output:**
  ```ts
  { proposal: RecipePatchProposal; promoted: boolean }
  ```
- **Guardrails:**
  - Promotion requires human approval.
  - The previous version is kept for one-click rollback.
  - A failed static check blocks the proposal.
  - While a ★ recipe is broken, its playbooks continue on T3 fallback (with cost caps), and the digest flags them as "degraded".
- **Acceptance:** a renamed export button produces a correct patch whose dry run validates against the schema. A JS patch that adds `fetch` to another origin is blocked.

### X-13 `x_buyer_message_drafter_skill` (new v0.4)
- **Purpose:** Raise response rate and speed on every platform by drafting replies for the user to send. Both live findings point here: the Etsy response rate was 25% against an 80% target, and eBay had unread account-risk messages and lost a case.
- **Trigger:** the `messages_sla` playbook, twice a day, after the EX-01…04 daily checks.
- **Inputs:**
  ```ts
  { store_id: string; platform: "amazon"|"shopify"|"etsy"|"ebay"|"tiktok_shop";
    messages: { message_id: string; buyer: string; order_id?: string; received_at: string; text: string; thread?: string[] }[];   // from EX report buyer_messages / customer_messages, or an extractor
    store_policies?: { returns: string; shipping: string; processing_days: number } }
  ```
- **Vars:** `policy_pack` (platform messaging rules: no off-platform contact, no review solicitation for incentives), `brand_voice`, `product_facts`, `buyer_reply_policy` (v0.9).
- **Tools:** `x_compliance_gate` (content_type: `buyer_message`), `ec_kb_get` (order and listing facts when available).
- **Output:**
  ```ts
  { drafts: { message_id:string; topic:"shipping"|"return"|"product_question"|"cancel"|"complaint"|"inr"|"inad"|"other"; urgency:"now"|"today"; draft:string; needs_info:string[]; due_by:string;
              language:string; confidence:number /*verifier*/; money_involved:boolean; dispute:boolean;
              send_decision:"sent"|"held"; hold_reason?:"low_confidence"|"missing_info"|"money_dispute_uncovered"|"forced_topic"|"cap_reached"|"compliance"; sent_at?:string }[];   // v0.9 (OQ-G24)
    sla: { unanswered:number; oldest_unanswered_h:number; over_24h:number } }
  ```
- **Execution (v0.9, OQ-G24): auto-send unless unsure.** The owner's `buyer_reply_policy` (default `auto`, confirmed at onboarding) lets the agent send replies itself through the per-platform write recipe. Each draft gets a **send decision**:
  - **Send** when all of these hold:
    - `x_compliance_gate` passed.
    - Confidence ≥ `buyer_reply_policy.min_confidence` (default 0.8). Confidence comes from a **separate verifier step** that checks the draft against order facts, listing facts and store policy, not from the drafter's self-rating.
    - `needs_info` is empty.
    - Money is not involved, or it is involved but the answer is clearly covered by store policy (for example, "returns accepted within 30 days, here is how").
  - **Hold for the owner** when any of these hold:
    - Confidence is below the threshold, or facts are missing.
    - **Money is involved in a dispute and the answer is not clearly covered by policy:** refund or partial refund requests, compensation, chargebacks, A-to-Z / eBay money-back / Etsy cases, INR/INAD with a claim open, or a buyer asking for a discount to keep or close a complaint.
    - Forced-hold topics, treated as "not confident" automatically: legal threats, injury or safety reports, platform or account-health notices, harassment, and messages in a language outside `StoreProfile.languages.customer`.
  - A held reply goes to the owner as an in-chat approval card (B7, D9), with email/SMS if it is urgent. The owner can edit, approve or reply personally. The agent then sends exactly the approved text.
  - **The message is not the money action.** A sent reply may say "we'll refund you per our policy", but issuing a refund, return label or replacement is a separate `ProposedAction` at level 2 with its own approval.
  - **Caps and audit:**
    - At most `max_auto_per_store_per_day` auto-sends (default 50); after that, replies are held.
    - The digest lists every auto-sent reply in one line each. The Manager samples 10% for a quality re-check and reports misses.
    - Repeated misses in a topic move that topic to "hold" via a ChangeProposal.
    - The owner can switch the policy to `hold_all` from chat at any time.

```ts
type BuyerReplyPolicy = { mode: "auto" | "hold_all"; min_confidence: number /*0.8*/;
  max_auto_per_store_per_day: number /*50*/; hold_topics_extra?: string[];   // owner additions
  money_rules?: { topic: "return"|"refund"|"replacement"|"shipping_fee"; covered_text: string }[] };   // policy text the verifier may treat as "clearly covered"
```
- **Guardrails:**
  - Never promise a refund, replacement or return outside the store policy.
  - Never ask a buyer to change or remove a review.
  - No contact details or links outside the platform.
  - INR/INAD/case replies offer a resolution before escalation (A11) but leave the decision to the user.

### X-14 `x_store_growth_diagnosis_skill` (new v0.4)
- **Purpose:** The entry point for "make the stores sell". For each store it finds the **binding constraint** and produces a ranked 30-day growth plan. The Manager turns that plan into tasks and review dates.
- **Trigger:** the `growth_weekly_review` playbook (Monday), or on demand.
- **Inputs:**
  ```ts
  { store_ids: string[] | "all"; window_days: 30; focus_platforms?: string[]; budget_hint?: Record<string, number> /*monthly ad budget per store, OQ-G22*/ }
  ```
- **Data (all via X-08):**
  - EX-01…04 daily checks: health, red flags, messages.
  - Amazon business report.
  - Shopify analytics + GA4.
  - Google Ads / Merchant Center summaries.
  - eBay Traffic + listings.
  - Etsy Stats + listings.
  - TikTok analytics.
  - Ads reports wherever present.
- **Logic:**
  1. **Health first.** Account at risk, Below Standard, Merchant Center suspended, or login required → constraint `account_health` / `access`.
  2. **Funnel per store and its top SKUs:** reach (impressions) → visits/sessions → conversion → AOV → repeat. The math is code (`ec_metrics_calc`).
  3. **Compare against `thresholds.growth` `[INF]` benchmarks:**
     - Amazon unit session % ~10–15%.
     - Shopify CVR ~1–2%.
     - eBay views → sales ~1–3%.
     - Etsy conversion ~1–3%.
     - Listing-quality minimums per platform.
  4. **Classify the constraint:** `account_health` | `access` | `no_traffic` | `low_ctr` | `low_cvr` | `price` | `catalog_quality` | `reviews` | `stock` | `fulfillment` | `response_rate` | `tracking`.
  5. **Map constraints to skills:**

     | Platform | Constraint | Skills |
     |---|---|---|
     | Shopify | no_traffic | DTC-10 → DTC-09 → DTC-03 |
     | Shopify | low_cvr | DTC-01 / DTC-11 |
     | eBay | catalog_quality / price | EBY-01 |
     | eBay | account_health | EBY-03 |
     | Etsy | catalog_quality | ETS-01 |
     | Any | response_rate | X-13 |
     | Amazon | account_health | AMZ-11 |
     | Amazon | low_ctr / low_cvr | AMZ-02 / AMZ-03 / X-06 |
     | TikTok | any | TTS-01 / TTS-03 |

  6. The LLM writes the narrative and the plan. It must cite evidence ids.
- **Output:**
  ```ts
  { stores: { store_id:string; platform:string; health:"ok"|"at_risk"|"blocked"; funnel:Record<string,number>; benchmarks:Record<string,number>;
              constraint:string; evidence:DecisionRecord["evidence"]; top_skus:{ id:string; issue:string }[] }[];
    plan_30d: { week:1|2|3|4; store_id:string; skill:string; inputs:Record<string,any>; expected_effect:string; kpi:string; review_at:string; owner:"agent"|"user" }[];
    user_actions: string[];     // only-the-user items: sign-ins, certifications, budgets, policy pages, payments
    data_gaps: string[] }
  ```
- **Manager hook:**
  - `plan_30d` items become ad-hoc playbook steps plus DecisionRecords with `review_at`.
  - MGR-02 evaluates them, and the next weekly X-14 run re-ranks.

### X-15 `x_store_onboarding_skill` (new v0.5)
- **Purpose:** Make every other skill shop- and product-agnostic by turning a signed-in store into KB records: discovery plus a chat interview (B9.4).
- **Trigger:**
  - The Manager in chat ("add my new Etsy shop").
  - A new profile in the `browser_profiles.json` registry.
  - A monthly refresh.
- **Inputs:**
  ```ts
  { platform: string; profile: string; store_hint?: string; depth: "quick"|"full"; refresh_of?: string /*store_id*/ }
  ```
- **Tools:** `x_browser_extract` (pack onboarding recipes, with the T3 explorer for unknown pages), `x_report_ingest`, `ec_kb_put`, `ec_learning(query)` (priors for this platform/category), and `send_chat` (interview questions go through the Manager).
- **Flow:**
  1. Session check.
  2. Discover the account: store name, marketplace(s), currency, timezone, plan/subscription, payout method present (no details read).
  3. Discover the catalog: products/listings with attributes, prices, stock, images count, status.
  4. Discover policies and settings: returns, shipping, processing time, policy pages.
  5. Discover performance over 30–90 days: traffic, orders, conversion, fees, ads accounts and spend.
  6. Discover health: account-health / standards pages.
  7. `llm:categorize`: map each product to a category taxonomy, feeding policy-pack and benchmark selection.
  8. `llm:draft_records`: StoreProfile, ProductFacts (claims marked `needs_data` unless found on the listing), `competitor_set` candidates.
  9. `llm:interview_plan`: the questions only you can answer.
  10. Hand off to the Manager chat, wait on `pend_event_node` for the answers, then `ec_kb_put` (versioned).
- **Interview questions (asked in chat, only when not discoverable):**
  - Goal for this store.
  - Monthly ad budget cap.
  - COGS (v0.6): discovered first (e.g. Shopify cost per item). Otherwise the owner gives it in chat, by CSV upload, or as a category margin estimate (B9.10).
  - Fulfillment model.
  - Products to push or exclude.
  - Brand voice.
  - Hard no-gos.
  - Risk appetite.
- **Output:**
  ```ts
  { store_profile: StoreProfile; products: ProductFacts[]; category_map: Record<string,string>; competitor_candidates: EntityRef[];
    discovered: { ads_accounts: string[]; health: any; performance_30d: Record<string,number> };
    interview: { question: string; why: string; answered?: any }[]; gaps: string[]; diff_vs_previous?: any }
  ```
- **Guardrails:**
  - Read-only. Never reads or stores payment details or passwords.
  - Discovery navigation follows the profile rules (B8.3): low page budgets, and no probing on no-touch profiles beyond their skills' own sessions.

### X-16 `x_profit_ledger_skill` (new v0.5)
- **Purpose:** The Manager's objective metric: daily contribution profit per store and platform (B9.5).
- **Trigger:** daily after the payout and ads report downloads. Backfills 90 days at onboarding.
- **Inputs:**
  ```ts
  { store_ids: string[] | "all"; date_range: [string, string] }
  ```
- **Data:**
  - The ★L payout/settlement recipes and the ads spend reports of each platform.
  - COGS from ProductFacts / owner input (B9.10).
  - Shipping costs where reported, otherwise estimated with a flag.
  - **AI cost** from eCan metering (per task `llm_cost_usd` + browser runs, tagged with `tenant_id` / `store_id`; shared work allocated pro rata, B9.10).
- **Logic:**
  - Code computes the `ProfitLedgerRow`s.
  - Platform rows are reconciled against the order count.
  - `completeness` is marked, because settlement lags and estimates are labelled.
- **Output:**
  ```ts
  { rows: ProfitLedgerRow[]; totals: Record<string, { contribution:number; margin:number; ad_spend:number }>; vs_goal: { goal_id:string; actual:number; target?:number; gap:number }[]; data_quality: string[] }
  ```
- **Guardrails:**
  - Estimated components are never presented as actuals.
  - Currencies are converted with a dated FX source, which is recorded.

### X-17 `x_store_daily_check_skill` (new v0.5)
- **Purpose:** One generic daily check for any store, driven by the platform pack. It replaces the per-store EX-01…04 in P2 and keeps their report format (`StoreDailyCheck`, B8.5) and their "never an all-clear on failure" rule.
- **Inputs:**
  ```ts
  { store_id: string; sections?: ("orders"|"messages"|"health"|"red_flags"|"payments"|"listings")[] }
  ```
- **Flow:**
  1. Resolve the pack.
  2. Run T1/T2 extractors per section.
  3. T3 only for sections without an extractor.
  4. Click into each red flag (the existing Amazon rule) using T2 detail extractors.
  5. `store_report`-compatible output, then the adapter mapping (B8.5).
- **Acceptance:** for each of the 4 existing stores, its report matches EX-0x's report on the same day (shadow run in P2) before EX-0x is retired.

---

## C4. Amazon skills

### AMZ-01 `amz_product_opportunity_skill`
- **Purpose:** Run the selection entry modes (no direction / ASIN or keyword go-no-go / seed-word expansion) and produce a scored decision memo plus a development brief.
- **Sources:** DEV, NSP, SHEET, KW, CDX module 4, AIAD selection checklist.
- **Inputs:**
  ```ts
  { mode: "explore_category"|"evaluate"|"expand_seed"; marketplace: string; category?: string; asin_or_keyword?: string; seed?: string;
    product_type: "standard"|"non_standard"; constraints?: { price_band?: [number,number]; max_weight_g?: number; exclude_restricted: boolean; min_net_margin?: number } }
  ```
- **Tools:**
  - Data (v0.2 browser-first, all via X-08): Brand Analytics Top Search Terms (`amz.ba.top_search_terms`), SellerSprite / Sorftime / Xiyou web exports if subscribed, Keepa product pages, and Google Trends.
  - Calc and reviews: `x_unit_economics` (sub-skill), `ec_demand_estimate`, `x_voc_miner` (sub-skill on the top-10 competitor reviews).
- **Flow:**
  1. `mcp:keyword_pull`
  2. `llm:cluster_intents` assigns an intent label and a cluster to each term.
  3. `mcp:concentration_metrics` (top-3 click share, conversion share vs click share, brand share).
  4. `loop` over the top-N clusters:
     - `mcp:keepa+trend` (BSR volatility, price trend, seasonality)
     - `sheet-call voc_miner`
     - `sheet-call unit_economics`
     - `mcp:score` (rubric)
  5. `llm:memo`
  6. `llm:dev_brief` for go candidates.
  7. `end`
- **Scoring rubric** (0–5 each; weights in `thresholds.selection`, `[INF]` defaults, OQ-A5):

  | Criterion | Default weight |
  |---|---|
  | Demand and trend | 15% |
  | Seasonality risk | 5% |
  | Intent clarity | 10% |
  | Concentration | 10% |
  | Review barrier vs achievable share | 10% |
  | Satisfaction gap | 10% |
  | Profit ceiling and unit economics | 15% |
  | Social validation | 5% |
  | Visualizability | 5% |
  | Compliance / IP risk | 10% (gate) |
  | Resource fit (ad budget vs competitors) | 5% |

- **Output:**
  ```ts
  { clusters: { cluster_id:string; label:string; intent:string; terms:string[]; volume:number; top3_click_share:number; conv_gap:number }[];
    candidates: { cluster_id:string; score:number; subscores:Record<string,number>; verdict:"go"|"watch"|"no_go"; reasons:string[]; seasonality:string; demand:{low:number;mid:number;high:number}; unit:{net_margin:number; breakeven_acos:number}; risks:string[] }[];
    dev_briefs?: { cluster_id:string; positioning:string; usps:string[]; specs:Record<string,string>; target_cost:number; target_price:number; matrix_role:"basic"|"trend"|"profit"|"test"|"traffic"|"anchor"; sampling_requirements:string[]; risks:string[] }[];
    memo_md: ArtifactRef }
  ```
- **Guardrails:**
  - A compliance or IP risk score of 0 forces `no_go`.
  - Brand and IP terms are excluded.
  - Demand estimates are shown as ranges.
- **Open:** OQ-A5 (weights), OQ-G2 (which data subscriptions you hold).

### AMZ-02 `amz_listing_writer_skill`
- **Purpose:** Write or rewrite Amazon listings (title, 5 bullets, description, backend terms, attribute suggestions, A+ outline). Also localizes them and produces A/B variants and ad copy.
- **Sources:** PL 1-A, 1-B, 1-C, 2-A, 2-B, 2-C and Rewrite step; RC (COSMO, visual hammer); A2.2.
- **Inputs:**
  ```ts
  { sku: string; mode: "create"|"rewrite"|"localize"|"variants_title"|"variants_bullets"|"ad_copy"|"aplus_outline";
    marketplace: string; target_language?: string; current_listing?: Listing;
    keyword_clusters?: { term:string; priority:number; placement_hint?:"title"|"bullets"|"backend" }[];
    insight_ref?: string; audit_ref?: string /*AMZ-03 gaps*/; n_variants?: number;
    ad_copy?: { campaign_type:"SP"|"SB"|"SD"; goal:"launch"|"hero"|"promo"|"defense" } }
  ```
- **Vars:** `product_facts`, `policy_pack`, `brand_voice`, `lifecycle_stage`.
- **Tools:** `x_compliance_gate` (sub-skill, `auto_fix=true`), `ec_text_metrics`, DeepL API (localize stage 1, optional, OQ-A6).
- **Flow:**
  1. `condition` on mode.
  2. `llm:write`, using the PL template for that mode.
  3. `mcp:text_metrics`
  4. `sheet-call compliance_gate`
  5. `condition`: did the gate fail after 2 fix rounds?
     - Yes: return `needs_input` with the findings.
     - No: continue.
  6. `end`
- **Prompt rules (from A2.2):**
  - B→F→A bullets; scenario-led bullets come first when an audit_ref is present.
  - Title ≤200 characters, differentiator first.
  - Use `buyer_phrases` from the insight.
  - Every number must be present in `product_facts`, or the field is set to "needs_data".
  - Answer who / scenario / problem for COSMO.
  - Localize means native search terms, not literal translation.
  - Arabic: right-to-left, Modern Standard Arabic, keep digits, metric units.
- **Output:**
  ```ts
  { listing?: Listing; variants?: { id:string; angle:string; title?:string; bullets?:string[] }[];
    ad_copy?: { style:"benefit"|"problem_solution"|"social_proof"|"cta"; headline1:string; headline2?:string; description:string }[];
    aplus_outline?: { module:string; message:string; visual_brief_hint:string }[];
    change_rationale?: { field:string; change:string; reason:string; geo_value?:string }[];
    keyword_coverage: { term:string; placed_in:string[] }[]; needs_data: string[]; compliance: { verdict:string; policy_version:string } }
  ```
- **Guardrails:**
  - Level 1 only: pushing a listing is a separate `listing_update` ProposedAction that goes through X-09.
  - Never use competitor brands.
- **Acceptance:**
  - The PL hair-dryer example passes the gate.
  - Bullet lengths are within 10–25 words.
  - The output is deterministic in structure across 3 reruns (PL principle "test stability").

### AMZ-03 `amz_rufus_geo_optimizer_skill`
- **Purpose:** The 5-step Rufus × GEO × compliance optimization loop for one ASIN. It also has a batch mode for sibling SKUs.
- **Sources:** PL loop (full); AIAD Rufus five-question method; RC.
- **Inputs:**
  ```ts
  { asin: string; sku: string; marketplace: string; scenario: "launch"|"defense"|"overtaken"|"batch_siblings";
    current_listing: Listing; core_search_terms: string[] /*5–10*/; competitor_positioning?: string;
    rufus_mode: "live"|"simulated"; sibling_skus?: string[] }
  ```
- **Sheets:**
  - `probe` (LLM): generates 10 buyer-voice questions. Allocation is driven by listing symptoms (A2.2 table), with a purpose for each question and a priority summary.
  - `research`:
    - `live`: `sheet-call amz_rufus_research_skill` (AMZ-03b).
    - `simulated`: an LLM role-plays Rufus, grounded only on the listing + reviews + Q&A, and flags answers that go "beyond listing".
  - `audit` (LLM): GEO scorecard /100 across 6 dimensions, an expectation map, gaps with severity, recommended changes (H/M/L, location, change, GEO value), and a one-line takeaway. The scores are summed by a code node.
  - `rewrite`: `sheet-call amz_listing_writer(mode="rewrite", audit_ref)`.
  - `compliance`: performed inside AMZ-02.
- **Output:**
  ```ts
  { questions: { dim:"scenario"|"drivers"|"comparison"|"friction"|"language"; q:string; purpose:string }[]; priority_summary: { primary:string; secondary:string; tertiary:string; reason:string };
    research: { q:string; answer_excerpt:string; followups:string[]; competitor_mentions:Record<string,number>; beyond_listing:boolean }[]; research_quality: "strong"|"moderate"|"thin";
    audit: { scores:{scenario:number; audience:number; drivers:number; positioning:number; language:number; structure:number; total:number}; grade:"excellent"|"adequate"|"weak"; gaps:{opportunity:string; severity:"H"|"M"|"L"; issue:string}[]; changes:{priority:"H"|"M"|"L"; location:string; change:string; geo_value:string}[]; takeaway:string };
    rewrite: Listing; change_rationale: any[]; generic_gaps?: string[] /*for batch siblings*/; sibling_rewrites?: { sku:string; listing:Listing }[];
    qa_library: { q:string; a:string; source:"listing"|"reviews"|"needs_content" }[] /*20–30 items*/ }
  ```
- **Acceptance:**
  - The audit total equals the sum of its sub-scores, each within its cap (20/15/20/15/15/15).
  - The rewrite passes the compliance gate.
  - The QA library has ≥ 20 items.
- **Open:**
  - OQ-A7: the 13-slot allocation is trimmed to 10. Should the priority come from the symptoms, or always use 2/2/2/2/2?
  - OQ-G5: live vs simulated mode.

### AMZ-03b `amz_rufus_research_skill` ⚠ (NOT BUILT, v1.0: OQ-G5 = simulated only; kept for reference)
- **Purpose:** Ask Rufus a list of questions on the product page and capture the answers.
- **Sources:** PL rufus-research (CDP runner, 8s wait, `#rufus-text-area`, `.nav-rufus-content`).
- **Inputs:**
  ```ts
  { asin: string; marketplace: string; questions: string[]; profile: string /*shopper profile, NOT seller account*/; wait_s?: number /*≥8*/ }
  ```
- **Implementation:**
  - Use the eCan browser-automation node, not a raw CDP script. Steps: `goto amazon.<tld>/dp/<asin>`, then for each question type into the Rufus input, submit, wait ≥8s, and extract the answer panel.
  - `allowedActions` are restricted to navigation, input, wait and extract.
  - The selectors are variables, because they change.
- **Output:**
  ```ts
  { answers: { q:string; answer:string; captured_at:string; screenshot:ArtifactRef }[]; summary: { frequent_followup_terms:string[]; competitor_brand_counts:Record<string,number> }; failures: { q:string; reason:string }[] }
  ```
- **Guardrails:**
  - ⚠ Use a separate shopper profile that is never logged into a seller account.
  - At most 10 questions per ASIN per day, with randomized pacing.
  - If OQ-G5 is declined, AMZ-03 uses simulated mode.

### AMZ-04 `amz_ads_launch_planner_skill`
- **Purpose:** A day-0 ad structure and 30-day plan for a new ASIN, or a rebuild for an existing one.
- **Sources:** CDX module 5, ADS10 (match by stage, auto settings, waterfall, budget ≥ CPO), ADSC 5 layers, B3.6 naming.
- **Inputs:**
  ```ts
  { sku: string; asin: string; marketplace: string; product_type: "standard"|"non_standard"; monthly_budget: number;
    keyword_clusters: { term:string; role:"core"|"mid"|"long"|"brand"|"competitor"; suggested_bid?: [number,number,number] }[];
    competitor_asins?: string[]; has_brand_registry: boolean; stage: "launch"|"rebuild" }
  ```
- **Tools:** `x_unit_economics` (break-even ACOS), `ec_bulk_file_build` (campaign_create actions), `ec_experiment` (waterfall test cards).
- **Flow:**
  1. `mcp:unit_econ`
  2. `llm:structure`: layers → campaigns → ad groups → targets, with a bid formula per target (`suggested×mult`).
  3. `code:budget_split`: the daily budget of each campaign is ≥ CPO estimate (CPC_est × 1/CVR_est), and the total stays ≤ the monthly budget.
  4. `llm:calendar`
  5. `mcp:bulk_file`
  6. `end`
- **Output:**
  ```ts
  { campaigns: { name:string /*B3.6*/; layer:"explore"|"scale"|"profit"|"defense"|"remarketing"; ad_type:"SP"|"SB"|"SD"; targeting:"auto"|"keyword"|"product"|"audience"; match?:string; auto_groups?:("close"|"loose"|"substitutes"|"complements")[]; bid_strategy:"fixed"|"down_only"|"up_down"; placement:{tos_pct:number; pp_pct:number}; daily_budget:number; ad_groups:{ name:string; targets:{ value:string; bid:number }[] }[] }[];
    calendar: { day_range:string; actions:string[]; checkpoints:{ metric:string; rule:string }[] }[];   // test → harvest → negate cadence
    experiments: ExperimentCard[]; budget_summary: { by_layer:Record<string,number>; total_daily:number };
    bulk_file: ArtifactRef; assumptions: string[] }
  ```
- **Guardrails:**
  - Level 1: the bulk file is uploaded by a human, or by level 2 after approval.
  - Standard products get auto close + substitutes only.
  - Never use up&down bidding together with placement multipliers above +50%, unless it is a flagged bargain campaign.
- **Open:**
  - OQ-A8: what are the budget shares by layer for launch? (They are not in the corpus. `[INF]` explore 30 / scale 40 / defense 10 / profit 10 / remarketing 10.)

### AMZ-05 `amz_ads_search_term_optimizer_skill`
- **Purpose:** Run the daily or weekly harvest and negation engine on search-term data, using A2.3 rules plus LLM relevance judgments.
- **Sources:** ADSXM (rule matrix + root words), ADS10, CDX module 6, AIAD daily loop.
- **Trigger:** daily after report ingest (the 7-day rolling window). A deeper 30-day pass runs weekly.
- **Inputs:**
  ```ts
  { store_id: string; marketplace: string; window_days: 7|14|30; campaigns_filter?: string[]; include_root_words: boolean;
    target_acos?: number /*else from store_profile or breakeven*/; listing_refs?: Record<string, Listing> /*for relevance*/ }
  ```
- **Vars:** `thresholds.amz_ads`, `lifecycle_stage`, `store_profile.targets`.
- **Tools:** `ec_table_query`, `ec_metrics_calc`, `ec_rules_eval(ruleset="amz_search_term_v1")`, `ec_ngram_rootwords`, `ec_bulk_file_build`, `ec_decision_log`.
- **Flow:**
  1. `mcp:metrics` aggregates per search term × campaign/ad group over the window, and joins SQP organic CVR when available.
  2. `mcp:rules_eval` marks each term `negate_candidate`, `bid_down_xx`, `bid_up`, `harvest`, `hold` or `insufficient_sample`.
  3. `llm:relevance` judges the gray-zone terms (15–30 clicks, 0 orders) and harvest candidates as strongly or weakly relevant, given the listing.
  4. `mcp:rules_eval(pass 2, with relevance)`
  5. `mcp:rootwords` (optional)
  6. `llm:explain`, which writes DecisionRecords.
  7. `mcp:bulk_file`
  8. `end`
- **Output:**
  ```ts
  { summary_kpis: { spend:number; sales:number; acos:number; orders:number; wasted_spend_0_order:number };
    negatives: { term:string; level:"campaign"|"ad_group"; match:"negative_exact"|"negative_phrase"; campaign:string; ad_group?:string; clicks:number; spend:number; rule_id:string }[];
    bid_changes: { target:EntityRef; current_bid:number; new_bid:number; pct:number; rule_id:string }[];
    harvest: { term:string; to_campaign:string; match:"exact"|"phrase"|"broad"; start_bid:number; evidence:{orders:number; cvr:number; acos:number} }[];
    root_words: { root:string; n:number; clicks:number; orders:number; action:"negate_phrase"|"expand"|"watch" }[];
    listing_feedback: { term:string; issue:string }[];   // "problem is the listing, not ads"
    decisions: DecisionRecord[]; actions: ProposedAction[]; bulk_file: ArtifactRef }
  ```
- **Guardrails:**
  - Never negate brand terms or a term that is currently harvest-protected.
  - Never act inside the attribution window: the last 2 days are excluded for SP and the last 14 days for SB/SD, unless overridden.
  - Per-day change caps come from `approval_policy`.
  - Per P4, an entity already changed in the last 72h is skipped.
- **Acceptance:** fixture tables, one per A2.3 row, produce the exact action. The waste total equals SQL spend where orders = 0.
- **Open:**
  - OQ-A3: definitions of "high or low sales contribution" and "high or low ACOS" (relative to average, or to target).
  - OQ-A9: should negations default to campaign level or ad-group level?

### AMZ-06 `amz_ads_placement_budget_skill`
- **Purpose:** Placement multipliers, portfolio budget reallocation, the budget ramp and the dayparting schedule, implementing the three-level ACOS cascade (A2.3).
- **Sources:** ADS10 (placements, budget ramp, dayparting), ADSXM (cascade), PLC data.
- **Trigger:** weekly. The dayparting check runs monthly.
- **Inputs:**
  ```ts
  { store_id: string; window_days: 14|30; goals_by_campaign?: Record<string, "rank"|"efficiency">; include: ("placement"|"portfolio_budget"|"budget_ramp"|"dayparting")[] }
  ```
- **Tools:** `ec_table_query`, `ec_metrics_calc`, `ec_rules_eval(ruleset="amz_placement_v1"|"amz_budget_v1"|"amz_daypart_v1")`, `ec_bulk_file_build`.
- **Logic:**
  - **Placement:** per campaign, compare TOS/ROS/PP on CVR, ACOS and CPC.
    - Goal "rank": push TOS using the ADS10 recipe steps.
    - Goal "efficiency": raise the multiplier on the lowest-ACOS placement and lower the others. The base bid is lowered a little when TOS% rises (ADSXM).
  - **Portfolio budget:**
    - Compute each campaign's sales contribution and ROAS against the average.
    - High contribution and ROAS > average: raise the budget, subject to inventory cover (from AMZ-09/inventory).
    - Low contribution and ROAS < average × (1 − 0.2), non-head: cut.
    - Underspending with ACOS > average: switch to down-only.
  - **Budget ramp:** for campaigns that spent out ≥ 3 of the last 5 days, raise the budget by 5 × CPC at 00:00 local site time. Campaigns spending < 50% of budget for 7 days are flagged for a cut.
  - **Dayparting:**
    - Gate: the listing must be stable and the campaign must spend fast with poor CVR.
    - Then build an hour × weekday distribution from `amz_orders_hourly` (≥ 30 days) and propose the schedule (100% peak / 30% shoulder / floor $2; heaviest weekday +20%).
- **Output:**
  ```ts
  { placement_changes: { campaign:string; before:{base_bid?:number; tos_pct:number; pp_pct:number; ros_pct?:number}; after:{…}; reason:string; evidence:any }[];
    budget_changes: { campaign:string; before:number; after:number; rule_id:string }[]; strategy_changes: { campaign:string; from:string; to:string }[];
    daypart_schedule?: { campaign:string; weekday_mult:Record<string,number>; hourly:{ hour:number; budget_pct:number }[] } | { gated_out_reason:string };
    decisions: DecisionRecord[]; actions: ProposedAction[]; bulk_file?: ArtifactRef }
  ```
- **Guardrails:**
  - Max effective bid = bid × (1+TOS%) × (2 if up&down). It is computed and capped by `approval_policy.caps`.
  - Dayparting requires a third-party tool or an API scheduler. Execution mode `manual` is the default (OQ-A10).
  - The CVR TOS>ROS>PP heuristic is never assumed; decisions use the data only.
- **Acceptance:** on the PLC data, `SP-UI06-品类词` gets a recommendation to shift toward PP (CVR 7.3% vs TOS 3.6%).

### AMZ-07 `amz_ads_dependency_audit_skill`
- **Purpose:** The monthly 5-step ad-dependency check (DEP).
- **Inputs:**
  ```ts
  { store_id: string; asins?: string[]; window_days: 30; sources: { erp_ad_order_share: ArtifactRef; third_party_traffic_share: ArtifactRef /*Xiyou*/; sqp: ArtifactRef; search_terms: ArtifactRef } }
  ```
- **Logic:**
  1. gap = ad_order_share − ad_traffic_share, per ASIN. Flag if > `thresholds.amz_ads.dependency_gap`.
  2. Classify keywords: top-converting SQP terms are "concentrate"; low-CTR head/mid/long terms are "cut or pause"; a low third-party ad share with a high ad-order share is "waste".
  3. Restructure the budget.
  4. Create a tracking ExperimentCard. Success: spend −≤15%, organic +≥15%, total sales stable.
- **Output:**
  ```ts
  { by_asin: { asin:string; ad_order_share:number; ad_traffic_share:number; gap:number; flagged:boolean }[];
    keywords: { term:string; class:"concentrate"|"cut"|"pause"|"waste"; evidence:any }[];
    budget_plan: { campaign:string; before:number; after:number }[]; experiment: ExperimentCard; caveats: string[] }
  ```
- **Guardrails:** the caveat "metrics are non-comparable (attributed orders vs estimated traffic)" is always included.
- **Open:** OQ-A11. Do you have Xiyou (西柚) access? If not, use the SQP brand-vs-total share as a proxy.

### AMZ-08 `amz_ads_diagnosis_skill`
- **Purpose:** The daily "situational awareness" run (anomaly → attribution → recommendation) and the on-demand 5-step diagnosis assigning a lifecycle stage and ad role per SKU.
- **Sources:** ADSC 5-step, GMV stages and red lines, AIAD daily loop, P12.
- **Inputs:**
  ```ts
  { store_id: string; mode: "daily"|"deep"; skus?: string[]; date: string }
  ```
- **Tools:** `ec_baseline_compare` (D-1 vs same weekday last week vs 7-day average), `ec_metrics_calc`, `ec_table_query` (SQP funnel, business report), `ec_kb_put(lifecycle_stage)`.
- **Flow (daily):**
  1. `mcp:baseline_compare` on spend, sales, ACOS, CPC, CVR, sessions and TACOS, per SKU and campaign.
  2. `code:classify_anomalies` (immediate / same-day / observe, by thresholds).
  3. `llm:attribute` proposes a hypothesis per anomaly from the joined evidence (inventory, price, Buy Box, competitor changes from X-05, listing changes).
  4. `llm:recommend` decides act or don't act, with followups (e.g. AMZ-05, AMZ-10, AMZ-02).
- **Flow (deep):** 5 steps (demand → funnel → competitors → structure fit → ad role), each computed from tables and then judged.
- **Output:**
  ```ts
  { anomalies: Anomaly[]; decisions: DecisionRecord[]; followups: FollowupRequest[];
    sku_stage?: { sku:string; lifecycle:"launch"|"growth"|"stable"|"clearance"; ad_posture:"stop_bleed"|"stabilize"|"scale"; ad_role:"validate"|"amplify"|"occupy"|"defend"|"harvest"|"exit"; bottleneck:"demand"|"traffic"|"ctr"|"cvr"|"price"|"inventory"|"competition"|"structure"; red_line_warnings:string[] }[] }
  ```
- **Guardrails:** "Don't touch" is a valid recommendation and must state a review date.

### AMZ-09 `amz_store_weekly_report_skill`
- **Purpose:** The weekly operations report (CDX module 3).
- **Inputs:**
  ```ts
  { store_id: string; week: string /*ISO week*/; include_pnl: boolean }
  ```
- **Logic:**
  - KPIs vs target: revenue, units, sessions, CVR, ad spend, ACOS, TACOS, net margin (≥6% floor).
  - SKU health tiers `[INF]`, OQ-A12:
    - A = profitable and growing.
    - B = profitable and flat.
    - C = unprofitable but strategic (launch).
    - D = unprofitable, not strategic, so clear.
  - Restock: cover days vs lead time + buffer, with a reorder qty.
  - Returns: rate by SKU and top reasons.
  - Rough P&L: revenue − COGS − fees − ads − returns.
- **Tools:** `ec_table_query`, `ec_metrics_calc`, `ec_inventory_cover`, `ec_unit_economics`, `x_report_composer` (render).
- **Output:**
  ```ts
  { kpis: Record<string,{value:number; target?:number; wow:number}>; sku_tiers: { sku:string; tier:"A"|"B"|"C"|"D"; reason:string }[];
    restock: { sku:string; cover_days:number; lead_time_d:number; reorder_qty:number; urgency:"now"|"this_week"|"ok" }[];
    returns: { sku:string; rate:number; top_reasons:string[] }[]; pnl?: { revenue:number; cogs:number; fees:number; ads:number; returns:number; net:number; net_margin:number };
    strategy_suggestions: DecisionRecord[]; report_md: ArtifactRef }
  ```

### AMZ-10 `amz_store_patrol_skill`
- **Purpose:** Asset monitoring: hijackers, Buy Box loss, listing suppression or "变狗" (broken variation or detail-page takeover), price errors and review spikes.
- **Sources:** CDX 陪跑 part 5, AIAD negative-review alert.
- **Trigger:** every 2–4h for hero ASINs, daily for all others (variable).
- **Inputs:**
  ```ts
  { store_id: string; asins: string[]; checks: ("offers"|"buybox"|"listing_status"|"title_image_change"|"variation"|"price"|"rating"|"new_low_reviews")[] }
  ```
- **Tools:**
  - v0.2: `x_browser_extract` with the T2 extractors `amz.pdp.snapshot` (title, image hash, price, Buy Box seller, offer count, rating, variations), `amz.sc.suppressed` and `amz.sc.account_health`.
  - SP-API notifications remain a future option.
  - Plus `ec_snapshot_diff` and `x_voc_miner(negative_tagging)`.
- **Output:**
  ```ts
  { alerts: { asin:string; type:"hijacker"|"buybox_lost"|"suppressed"|"content_changed"|"variation_broken"|"price_anomaly"|"rating_drop"|"negative_review_spike"; severity:"immediate"|"same_day"; evidence:any; suggested_ticket:string }[]; snapshot_refs: string[] }
  ```
- **Guardrails:** read-only. Tickets such as "file a brand-registry report" go to a human. Never auto-file infringement complaints (A9).

### AMZ-11 `amz_account_health_skill`
- **Purpose:** Classify an account-health or listing violation, choose the right path, draft a concise POA, and check document and address consistency for verification.
- **Sources:** RESTR (classes, paths, 72h / 180d, prevention), ADDR, SCAN (POA framing), CDX (POA drafting).
- **Inputs:**
  ```ts
  { mode: "classify_and_draft"|"prevention_audit"|"address_check";
    notice_text?: string; listing?: Listing; category?: string; marketplace: string;
    evidence_available?: ArtifactRef[]; documents?: { type:"license"|"utility_bill"|"invoice"|"sc_profile"; artifact:ArtifactRef }[] }
  ```
- **Tools:** `os_read_document` (OCR), `ec_compliance_lint` (catalog audit), `x_compliance_gate`.
- **Output:**
  ```ts
  { classification?: { class:"prohibited"|"restricted"|"false_positive"|"ip"|"performance"|"other"; path:"acknowledge"|"appeal_with_docs"|"fix_then_appeal"|"escalate_human"; reasoning:string; required_docs:string[] };
    poa_draft?: { root_cause:string; corrective_actions:string[]; evidence_list:string[]; preventive_measures:string[]; text:string /*concise*/ };
    fix_plan?: { field:string; remove_or_change:string; method:"flat_file"|"edit" }[];
    audit_findings?: { asin:string; issue:string; severity:"block"|"warn" }[];
    address_check?: { fields:{ doc:string; address:string }[]; consistent:boolean; diffs:string[]; standardized_en?:string } }
  ```
- **Guardrails:**
  - `appeal_submit` is a human action only.
  - Drafts must contain only facts the user supplied; anything not provided becomes a "[FILL: …]" placeholder.
  - Never advise fabricating documents or addresses.

---

## C5. TikTok Shop skills

### TTS-01 `tts_daily_ops_skill`
- **Purpose:** Run the operator's 12 daily tasks (A3.1) as three scheduled runs and produce the anomaly log and the daily report.
- **Trigger** (store timezone + Beijing operator time): `am` 09:00, `midday` 13:00 (ad patrol only), `pm` 17:00.
- **Inputs:**
  ```ts
  { store_id: string; run: "am"|"midday"|"pm"; date: string; data: { shop_daily: ArtifactRef; ad_rows?: ArtifactRef; video_rows?: ArtifactRef; inventory?: ArtifactRef; campaigns?: ArtifactRef; after_sales?: ArtifactRef; creators?: ArtifactRef } }
  ```
- **Sheets** (one per task, each emitting `Anomaly[]` and `DecisionRecord[]`):

  | Sheet | Tasks covered | Notes |
  |---|---|---|
  | `t01_core` | 1 | |
  | `t02_links` | 2 | |
  | `t03_aftersales` | 3 | drafts replies only |
  | `t04_inventory` | 4 | uses `ec_inventory_cover` |
  | `t05_videos` | 5 | |
  | `t06_production` | 6 | |
  | `t07_ads` | 7 | |
  | `t08_promos` | 8 | |
  | `t09_creators` | 9 | delegates to TTS-04 |
  | `t10_competitors` | 10 | delegates to X-05 |
  | `t11_tests` | 11 | delegates to TTS-05 |
  | `t12_review` | 12 | |

  **Which sheets each run executes:**
  - `am`: t01–t05, t07, t08.
  - `midday`: t07.
  - `pm`: t03, t07, t12.
- **Rules:** encoded in `ec_rules_eval(ruleset="tts_daily_v1")` with the thresholds from A3.1/A3.2:
  - Refund rate by cohort.
  - Orders, SKU orders and units kept separate.
  - Comparisons on complete days only.
  - New links marked "observe".
  - The 72h promo expiry flag.
- **Output:**
  ```ts
  { anomaly_log: (Anomaly & { action:string; owner_role:string; review_result?:string })[];
    module_results: Record<"core"|"links"|"aftersales"|"inventory"|"videos"|"production"|"ads"|"promos"|"creators"|"competitors"|"tests", { conclusion:string; items:any[] }>;
    cs_reply_drafts?: { case_id:string; draft:string; due:string }[];
    daily_report_md?: ArtifactRef /*pm only*/; next_day_plan?: { priority:"risk"|"growth"|"observe"; task:string; owner_role:string }[]; handover_checklist?: { item:string; ok:boolean }[] }
  ```
- **Guardrails:**
  - No price, campaign or ad writes (level 0/1).
  - Never trade refunds or gifts for reviews.
  - Data source = backend exports via X-08 recipes (`tts.sc.*`, `tts.ads.*`), run just before each scheduled run (v0.2).

### TTS-02 `tts_gmvmax_analyzer_skill`
- **Purpose:** GMV Max creative and campaign analysis → P0/P1 action table (GMVM Gemini prompt, rebuilt as code + LLM).
- **Inputs:**
  ```ts
  { store_id: string; creative_export: ArtifactRef /*tts_gmvmax_creative_rows*/; campaign_rows?: ArtifactRef; window_days: 7|14; roi_target: number }
  ```
- **Logic:**
  - **Code:**
    - Baseline medians.
    - Quadrant split on cost × ROI, using the median or the target as the axis.
    - Funnel per video (impressions → 2s → 6s → CTR → CVR).
    - Correlation of 2s rate with ROI.
    - Creator ROI ranking (avg ROI, and volume driven by low price).
    - Title keyword n-grams of winners.
    - Creative age vs lifecycle (5–10 days).
    - Weekly new-original count vs 3–7.
  - **LLM:** diagnoses bleeders (high CTR + low CVR means mismatch; low CTR + high CVR means a weak opening), then writes actions:
    - Push winners.
    - Kill bleeders.
    - Duplicate potentials to a test campaign.
    - Remix brief for declining creatives.
    - If the campaign isn't spending: add 3–5 videos, then loosen ROI by 0.5, then check the budget.
- **Output:**
  ```ts
  { baseline: Record<string,number>; quadrants: { winners:string[]; bleeders:string[]; potentials:string[]; others:string[] };
    funnel_issues: { video_id:string; issue:"opening"|"relevance"|"pdp"|"price"; evidence:any }[]; corr_2s_roi: number;
    creators: { creator:string; avg_roi:number; gmv:number; note:string }[]; winning_keywords: string[];
    creative_cadence: { new_originals_7d:number; target:[3,7]; replace_list:{video_id:string; reason:"ctr<1%"|"cpm>30"|"aged"}[] };
    actions: (ProposedAction & { priority:"P0"|"P1" })[]; remix_briefs: { video_id:string; keep_segments:string[]; cut_segments:string[]; new_hook_idea:string }[] }
  ```
- **Guardrails:**
  - At most 2 parameter changes per campaign per day.
  - ROI is labelled "includes organic + affiliate; not profit".
- **Open:**
  - OQ-T1: compensation rule validity.
  - OQ-T3: should the CPM>30 threshold be in USD?

### TTS-03 `tts_ad_noconv_diagnoser_skill`
- **Purpose:** Run the A3.3 tree on ad-level data, plus the GMV Max variant.
- **Inputs:**
  ```ts
  { store_id: string; ad_rows: ArtifactRef /*tts_ad_rows, destination clicks*/; audience_reach?: ArtifactRef; target_persona?: string; ctr_flag?: number }
  ```
- **Logic:**
  - A code node walks the tree per ad: sample guard → audience → CTR → click→PDP → PDP→checkout → checkout→purchase.
  - It emits `branch_path`.
  - The LLM writes a single-variable fix proposal and a test card for each ad.
- **Output:**
  ```ts
  { per_ad: { ad_id:string; branch_path:string[]; verdict:"insufficient_sample"|"audience"|"hook"|"selling_point_late"|"link"|"pdp_doubt"|"checkout_friction"|"ok"; metrics:{ctr:number; click_to_order:number; roas:number}; fix:{ change:string; keep_fixed:string[] }; test_card: ExperimentCard }[] }
  ```
- **Acceptance:** one fixture per leaf of the tree produces the expected verdict.

### TTS-04 `tts_creator_crm_skill`
- **Purpose:** Creator (affiliate) pipeline: discovery, scoring, tiering, CRM status, outreach drafts and follow-ups, performance attribution.
- **Sources:** TT12 #9, TTC creator CRM, A3.5.
- **Inputs:**
  ```ts
  { store_id: string; mode: "discover"|"score"|"followup"|"report"; product_ids?: string[]; seeds?: { hashtags?:string[]; competitor_creators?:string[]; categories?:string[] }; crm?: ArtifactRef /*tts_creator_rows*/ }
  ```
- **Scoring** (6 dimensions, `[INF]` weights, OQ-T4):

  | Dimension | Default weight |
  |---|---|
  | Category fit | 25% |
  | Audience geo/age fit | 15% |
  | Sales history (GMV, AOV) | 25% |
  | Content quality and hook rate | 15% |
  | Reliability (on-time posting) | 10% |
  | Ad-authorization willingness | 10% |

  **Tiers:** amplify ≥80, stable 65–79, long-tail test 50–64, observe <50.
- **Output:**
  ```ts
  { creators: { creator_id:string; handle:string; score:number; tier:"amplify"|"stable"|"longtail_test"|"observe"; fit_products:string[]; policy:{ sample:boolean; commission_pct:number; followup_days:number } }[];
    crm_updates: { creator_id:string; status:"invited"|"replied"|"confirmed"|"sample_sent"|"received"|"published"|"authorized"|"selling"|"lost"; next_step:string; next_date:string }[];
    outreach_drafts: { creator_id:string; channel:string; message:string }[];   // human sends
    funnel: Record<string, number>; performance: { creator_id:string; orders:number; gmv:number; videos:number }[] }
  ```
- **Guardrails:**
  - Messages, commission terms and sample approvals are always human actions.
  - Before reusing any creator video, its authorization must be confirmed (ACA / Video Code).

### TTS-05 `tts_product_test_skill`
- **Purpose:** Selection scoring + a fully costed test card + a verdict after the test window (TT12 #11, TTC).
- **Inputs:**
  ```ts
  { mode: "screen"|"create_card"|"evaluate"; candidates?: { name:string; cost:number; price:number; weight_g:number; category:string; evidence_urls?:string[] }[]; card_id?: string; results?: ArtifactRef }
  ```
- **Logic:**
  - Screen: qualification, logistics and quality fit, plus the 5-dimension score (market size, growth, competition, content suitability, fulfillment risk), plus the BF extras (gift-ability, price sensitivity, bundling, seasonality, return risk) when relevant.
  - Unit contribution comes from X-03.
  - The test card fields follow A3.1 #11.
  - Evaluate: scale / observe / stop, against the card's own conditions.
- **Output:**
  ```ts
  { screened?: { name:string; pass:boolean; score:number; reasons:string[] }[]; card?: ExperimentCard & { sku:string; audience:string; scene:string; spend_cap:number; acceptable_loss:number; metrics_required:string[] }; verdict?: { result:"scale"|"observe"|"stop"; evidence:any; missing?:string[] } }
  ```

---

## C6. DTC / Reddit / Google / Meta skills

### DTC-01 `dtc_cro_audit_skill`
- **Inputs:**
  ```ts
  { url: string; traffic_source?: "meta"|"google"|"reddit"|"tiktok"|"email"; ad_angle?: string; device: "mobile"|"desktop" }
  ```
- **Tools:** `x_browser_extract` (DOM + screenshots, above-the-fold), PageSpeed Insights API, `ec_text_metrics`.
- **Logic:**
  - Message-match score between the ad angle and the first screen.
  - Reddit 5-point check (A4.1).
  - FAB, trust and social-proof presence.
  - Price, shipping and returns visibility.
  - Mobile CTA, speed (LCP, CLS, INP) and image weight.
- **Output:**
  ```ts
  { scores: { message_match:number; five_point:number[]; trust:number; speed:{ lcp_ms:number; cls:number; inp_ms:number; score:number } }; issues: { area:string; issue:string; fix:string; impact:"H"|"M"|"L" }[]; ab_test_ideas: { hypothesis:string; variant:string; metric:string }[] }
  ```

### DTC-02 `dtc_funnel_diagnosis_skill`
- **Inputs:**
  ```ts
  { store_id: string; window_days: number; ga4: ArtifactRef /*dtc_ga4_funnel*/; shopify_orders?: ArtifactRef; by: ("source_medium"|"device"|"landing_page"|"country")[] }
  ```
- **Logic:**
  - Stage rates per segment: sessions → view_item → ATC → begin_checkout → purchase.
  - Compare each against store benchmarks and `[INF]` defaults.
  - Classify the root cause as traffic (intent mismatch), ads (creative promise) or site (UX, price, trust, checkout).
- **Output:**
  ```ts
  { stages: { segment:string; rates:Record<string,number>; worst_drop:string }[]; causes: { segment:string; class:"traffic"|"ads"|"site"; evidence:any }[]; levers: { lever:"AOV"|"CVR"|"LTV"|"CAC"; action:string; expected_effect:string }[]; decisions: DecisionRecord[] }
  ```

### DTC-03 `dtc_google_ads_skill` (expanded v0.4: the main paid channel for the Shopify stores)
- **Purpose:** Plan, launch and optimize Google Ads for each Shopify store: Shopping/PMax on the Merchant Center feed, plus Search. Tracking and feed health are hard prerequisites.
- **Sources:** GMETA (Search 3 series, PMax 4 tiers, GSC loop, "protect quality, then scale"); A10 (mostly `[INF]`).
- **Triggers:**
  - `shopify_google_daily`: light pass for anomalies, stop-loss and obvious negatives.
  - `shopify_google_weekly`: full optimize.
  - On demand: readiness / plan / launch_pack.
- **Inputs:**
  ```ts
  { store_id: string; mode: "readiness"|"plan"|"launch_pack"|"optimize_daily"|"optimize_weekly"|"diagnose";
    budget_daily: number; target?: { roas?: number; cpa?: number };      // default: break-even ROAS from X-03 × 1.2
    brand_terms: string[]; competitor_terms?: string[]; hero_product_ids?: string[]; window_days?: 7|14|30 }
  ```
- **Data (X-08 recipes):** `gads.campaigns_report`, `gads.search_terms_report`, `gads.shopping_products_report`, `gads.conversions_summary`, `gads.change_history`, `gads.auto_apply_status`, `gmc.diagnostics`, `ga4.funnel_export`, `gsc.performance_export`, `shopify.products_export`.
- **Vars:** `thresholds.gads`, `store_profile.targets`, `approval_policy`, `policy_pack` (Google Ads + Shopping).
- **Tools:** `ec_table_query`, `ec_metrics_calc`, `ec_rules_eval(ruleset="gads_v1")`, `ec_ngram_rootwords`, `ec_bulk_file_build(google_ads)`, `x_unit_economics`, `x_compliance_gate`.
- **Readiness gate** (mode `readiness`, and re-checked before every plan or launch):
  - **Tracking:** DTC-10 verdict is `pass`.
  - **Feed:** DTC-09 shows ≥80% of active products approved and no account-level issue.
  - **Site:** DTC-01 policy pages are present.
  - **Settings:** auto-apply recommendations are off.
  - If any check fails: `status:"needs_input"`, `readiness.blockers[]`, followups to DTC-10 / 09 / 01, and **no campaigns are proposed**.
- **Logic by mode:**
  - **plan:** pick the budget tier (A10 step 4) and build the structure:
    - Campaign names follow `GADS-<store>-<PMAX|SHOP|SRCH>-<tier/series>-<goal>`.
    - Listing groups split by `custom_label_0` (from DTC-09).
    - Search ad groups by product type.
    - An initial shared negative list `[INF]`: free, diy, used, repair, jobs, wholesale, template, pattern…, edited per catalog.
    - Never mix exploration with harvest.
  - **launch_pack:**
    - Full entity lists.
    - RSAs: up to 15 headlines (≤30 characters) and 4 descriptions (≤90), written by an LLM node and gated by X-02.
    - PMax asset-group text, plus the image count needed (→ X-06 followup).
    - Sitelinks, callouts and the bulk CSV.
  - **optimize_daily:**
    - Stop-loss: spend ≥ 3× target CPA with 0 conversions in 7 days → pause proposal.
    - Spend anomalies (`ec_baseline_compare`).
    - Negatives only for terms with cost ≥ 2× target CPA and 0 conversions.
  - **optimize_weekly:** all A10 step-6 rules:
    - Search-term negatives (exact/phrase, with LLM relevance for the grey zone).
    - Harvesting converting terms into BOF exact.
    - Product labels (hero/steady/zombie/new) → DTC-09 supplemental feed.
    - Bidding ladder transitions.
    - Budget steps.
    - The GSC loop: organic queries without paid coverage, and the brand-search share trend.
    - Nothing structural during the 7-day learning window.
  - **diagnose:** the A10 step-8 map, which separates ad problems from feed, site and price problems, and sends followups to DTC-09, DTC-01, DTC-11 and DTC-02.
- **Output:**
  ```ts
  { readiness?: { tracking:"pass"|"fail"; feed:"pass"|"fail"; site:"pass"|"fail"; auto_apply_off:boolean; blockers:string[] };
    tier?: "small"|"medium"|"large";
    structure?: { campaign:string; type:"pmax"|"shopping"|"search"; tier_or_series:string; budget_daily:number;
      bidding:{ strategy:"max_clicks"|"max_conversions"|"max_conv_value"|"troas"|"tcpa"; target?:number; cpc_cap?:number };
      listing_groups?: { by:"custom_label_0"|"product_type"|"item_id"; include:string[]; exclude:string[] }[];
      ad_groups?: { name:string; keywords:{ text:string; match:"exact"|"phrase"|"broad" }[]; rsa:{ headlines:string[]; descriptions:string[] } }[];
      asset_groups?: { name:string; final_url:string; headlines:string[]; long_headlines:string[]; descriptions:string[]; images_needed:number; audience_signals:string[] }[];
      negatives:string[] }[];
    optimize?: { kpis:{ spend:number; conv:number; conv_value:number; roas:number; breakeven_roas:number; cpa:number; ctr:number; cvr:number; search_is?:number; lost_is_budget?:number; lost_is_rank?:number };
      negatives_add:{ term:string; match:"exact"|"phrase"; level:"campaign"|"shared_list"; reason:string; cost:number }[];
      keywords_add:{ term:string; match:"exact"|"phrase"; campaign:string; evidence:any }[];
      product_labels:{ item_id:string; label:"hero"|"steady"|"zombie"|"new"; evidence:any }[];
      bidding_changes:{ campaign:string; from:any; to:any; reason:string }[];
      budget_changes:{ campaign:string; from:number; to:number; reason:string }[];
      in_learning:string[] };
    decisions: DecisionRecord[]; actions: ProposedAction[]; bulk_file?: ArtifactRef; followups: FollowupRequest[] }
  ```
- **Execution:**
  - Level 1 drafts. Changes are applied only through the `gads.bulk_upload` write recipe after approval (B7).
  - The first delegation candidate is `negate_keyword` only.
  - Label changes go through DTC-09's supplemental feed.
- **Guardrails:**
  - Never touch billing, payments or account settings.
  - Never accept Google recommendations or turn on auto-apply.
  - Budget changes are capped by `approval_policy`.
  - Structural changes are blocked inside the learning window, stop-loss excepted.
  - Ad text claims must exist in `ProductFacts`.
  - No trademark terms the store doesn't own in ad text.
- **Acceptance:**
  - On fixtures, readiness fails when the purchase conversion is missing or duplicated.
  - Each A10 rule produces the expected action.
  - The bulk CSV previews cleanly in the Google Ads UI upload (manual check).
  - No action is proposed for a campaign that is still in learning, except stop-loss.
- **Open:** OQ-D2 (confirm the A10 numbers), OQ-D4 (account state), OQ-D5 (Google profile), OQ-G22 (budgets).

### DTC-04 `dtc_meta_ads_skill`
- **Inputs:**
  ```ts
  { store_id: string; meta_rows: ArtifactRef; target_cpa: number; breakeven_roas: number; mode: "creative_race"|"scale"|"retarget_check" }
  ```
- **Logic:**
  - ABO race verdicts per ad: kill / keep / graduate, using `thresholds.dtc_meta` (OQ-D1).
  - Graduate winners to CBO/ASC.
  - Scale +20–30% every 48–72h on stable winners.
  - Partnership Ads candidates come from creator content, with the license check.
  - DPA prerequisites check.
- **Output:**
  ```ts
  { ads: { ad_id:string; verdict:"kill"|"keep"|"graduate"|"insufficient"; metrics:{cpm:number; ctr:number; atc_rate:number; cvr:number; cpa:number; roas:number}; reason:string }[]; scale_plan: { campaign:string; budget_before:number; budget_after:number; when:string }[]; creative_requests: FollowupRequest[] /*→ X-07/X-06*/; actions: ProposedAction[] }
  ```

### DTC-05 `dtc_reddit_research_skill`
- **Sources:** RDT (all scoring and research steps).
- **Inputs:**
  ```ts
  { product: string; category: string; keywords: { product:string[]; use_case:string[]; problem:string[]; purchase:string[]; competitor:string[] }; markets?: string[] }
  ```
- **Tools:** `x_browser_extract` with extractors `reddit.search`, `reddit.sub_rules`, `reddit.top_30d` (v0.2 browser-first); Google `site:reddit.com` queries; `x_voc_miner`.
- **Logic:**
  - Product-fit score (0–10).
  - Discover subreddits across the 6 layers.
  - Community score (5 × 1–5, minimum 15), keeping 5–8.
  - Rules library: post types, links, flair, brand posts, giveaways, AMA policy.
  - VOC table.
- **Output:**
  ```ts
  { product_fit: { scores:Record<"demand"|"research"|"evidence"|"differentiation"|"capacity",0|1|2>; total:number; verdict:"priority"|"test"|"fix_first" };
    subreddits: { name:string; layer:string; members:number; activity_30d:number; score:{ relevance:number; activity:number; tolerance:number; intent:number; sustainable:number; total:number }; keep:boolean; rules:{ links:string; flair_required:boolean; self_promo:string; ama:string; notes:string } }[];
    voc: { sub:string; link:string; quote:string; stage:"discover"|"compare"|"decide"|"use"; evidence:string; objection?:string; action:{ type:"product"|"content"|"ad"|"service"; owner_role:string } }[];
    recurring_questions: string[] }
  ```

### DTC-06 `dtc_reddit_engage_skill`
- **Purpose:** The daily 30-minute routine, done as drafts (A4.4).
- **Inputs:**
  ```ts
  { subreddits: string[]; watch_words: string[]; max_age_h: 24; disclosure_line: string; max_drafts: number /*default 5*/ ; mode: "reply_scan"|"post_draft"|"ama_prep" }
  ```
- **Logic:**
  - **reply_scan:** find threads under 24h old that match the watch words, rank them by intent, and filter to questions the team can answer with real facts from `product_facts` or the knowledge base. Draft a 3-part reply: answer → evidence → limits → disclosure, with no link unless the rules allow it.
  - **post_draft:** use one of the 6 templates plus a title formula, then a rules check against the subreddit.
  - **ama_prep:** a modmail request draft plus 20 Q&As.
  - Everything passes through `x_compliance_gate(content_type="reddit_*")`.
- **Output:**
  ```ts
  { threads: { url:string; sub:string; age_h:number; intent:"high"|"med"|"low"; question:string }[]; drafts: { thread_url?:string; type:"comment"|"post"|"modmail"|"ama"; text:string; rule_checks:{rule:string; ok:boolean}[]; utm_link?:string }[]; log: { topic:string; outcome?:string }[] }
  ```
- **Guardrails:**
  - Never post automatically.
  - Never vote.
  - Never use multiple accounts.
  - Disclosure is always included.
  - The subreddit's rules check must pass before a draft is shown.

### DTC-07 `dtc_seo_backlink_skill`
- **Inputs:**
  ```ts
  { our_domain: string; competitor_domains: string[] /*3–5*/; tool: "ahrefs"|"semrush"; mode: "backlink_gap"|"geo_content_plan"; questions_ref?: string /*from DTC-05 / X-04*/ }
  ```
- **Logic:**
  - **backlink_gap:** export backlinks through X-08 (A4.3 click paths) or the API. Filter to dofollow, then sort by DR or Authority Score and traffic. Classify each as guest post / review / gift guide / resource / directory / forum, then compute the link gap and build the outreach list.
  - **geo_content_plan:** turn questions and quotes into comparison pages, buying guides, FAQs and seasonal pages, each with schema markup suggestions.
- **Output:**
  ```ts
  { gap?: { referring_domain:string; dr:number; type:string; links_to:string[]; we_have:boolean; outreach_angle:string }[]; content_plan?: { page_type:"comparison"|"guide"|"faq"|"seasonal"; title:string; target_queries:string[]; evidence_sources:string[]; schema:string }[] }
  ```
- **Open:** OQ-D3. Which do you subscribe to: Ahrefs or Semrush? (Data comes via browser export recipes, v0.2.)

### DTC-08 `dtc_social_calendar_skill`
- **Inputs:**
  ```ts
  { brand: string; channels: ("ig"|"tiktok"|"youtube"|"facebook"|"pinterest"|"email")[]; horizon_weeks: 4|12; peak_event?: "bfcm"|"prime"|"christmas"|string; budget_model: "founder"|"inhouse_creator"|"retainer" }
  ```
- **Logic:**
  - Content mix is 90% evergreen pillars (founder story / education / real experience) and 10% trends.
  - Hero–Hub–Help cadence.
  - The 12-week peak flow (T-12 → tail).
  - KOL briefs and the Partnership Ads checklist (license scope, term, edit rights, disclosure).
- **Output:**
  ```ts
  { calendar: { date:string; channel:string; pillar:string; format:string; hook:string; goal:string; cta:string }[]; kol_briefs: { tier:"micro"|"mid"|"macro"; objective:string; brief_md:string }[]; partnership_ads_checklist: string[]; libraries_to_update: string[] }
  ```

### DTC-09 `dtc_merchant_feed_skill` (new v0.4)
- **Purpose:** Keep the Google Merchant Center feed approved and competitive, since it is the raw material for Shopping and PMax (A10 steps 2 and 7).
- **Inputs:**
  ```ts
  { store_id: string; mode: "diagnose"|"optimize_titles"|"labels"|"policy_check"; product_ids?: string[];
    labels_from?: string /*DTC-03 optimize result id*/ }
  ```
- **Data:** `gmc.diagnostics`, `gmc.products_export`, the price-competitiveness view if available, `shopify.products_export`, `site.policy_pages`.
- **Logic:**
  - **diagnose / policy_check:**
    - *Account-level* issues are `immediate`, each with fix steps: misrepresentation, "website needs improvement", unverified business info, missing return/shipping policy, checkout problems.
    - *Item-level* disapprovals go to a fix list marked auto-fixable or human: identifiers, image, price/availability mismatch, landing page, shipping, category.
  - **optimize_titles:**
    - Formula by category `[INF]`: brand + product type + key attributes + model, with the important words in the first ~70 characters (limit 150).
    - Also sets `product_type`, `google_product_category`, highlights/details, and a primary-image check (no text or watermark).
  - **labels:**
    - `custom_label_0` = performance (hero/steady/zombie/new, from DTC-03).
    - `_1` = margin band (X-03), `_2` = price band, `_3` = seasonality, `_4` = free.
  - **delivery:** a supplemental feed file, applied by the `gmc.supplemental_feed_upload` write recipe (level 2). Fixes that belong in Shopify go to DTC-11.
- **Output:**
  ```ts
  { approval_rate:number; account_issues:{ issue:string; severity:"immediate"|"same_day"; fix_steps:string[]; owner:"user"|"agent" }[];
    item_issues:{ item_id:string; issue:string; fix:string; auto_fixable:boolean }[];
    title_rewrites:{ item_id:string; before:string; after:string; rationale:string }[];
    labels:{ item_id:string; custom_label_0?:string; custom_label_1?:string; custom_label_2?:string; custom_label_3?:string }[];
    supplemental_feed?: ArtifactRef; actions: ProposedAction[] }
  ```
- **Guardrails:**
  - Titles must match landing-page facts and `ProductFacts`.
  - The X-02 Google Shopping pack applies: no promo text, no ALL CAPS, no unsupported claims.
  - Business-identity fixes are user actions.
- **Acceptance:** on a fixture feed, every missing identifier and policy page is flagged, and rewritten titles stay within limits and pass X-02.

### DTC-10 `dtc_tracking_audit_skill` (new v0.4)
- **Purpose:** Verify measurement before spending (A10 step 1). Bidding on broken conversions burns budget.
- **Inputs:**
  ```ts
  { store_id: string; checks: ("gads_conversions"|"ga4_events"|"meta_pixel"|"shopify_customer_events"|"consent"|"reconcile")[]; window_days?: 14 }
  ```
- **Data:**
  - `gads.conversions_summary`: status, primary vs secondary, source, counting, value.
  - GA4 events/realtime.
  - `shopify.customer_events`: installed pixels and apps.
  - A storefront T2 extractor reading gtag/dataLayer *presence only* (read-only, no fetch).
  - Reconciliation of Shopify orders vs Google Ads conversions vs GA4 purchases over the window.
- **Rules `[INF]`:**
  - **Fail** if there is no primary purchase conversion, the value isn't tracked, there are two primary purchase actions (double counting), or the conversion status is inactive or "no recent conversions" while orders exist.
  - **Warn** if the reconciliation gap is > 25% or consent mode is missing for EU/UK traffic.
- **Output:**
  ```ts
  { verdict:"pass"|"warn"|"fail"; findings:{ check:string; status:"pass"|"warn"|"fail"; detail:string; fix:string; owner:"user"|"agent" }[];
    primary_conversion?: { name:string; source:"google_youtube_app"|"ga4_import"|"gtag"|"other"; counting:"every"|"one"; value_tracking:boolean };
    reconcile?: { shopify_orders:number; gads_conversions:number; ga4_purchases:number; gap_pct:number } }
  ```
- **Guardrails:**
  - Never edits tags, pixels, apps or Google Ads goals; fixes are user actions or a separately approved task.
  - Never places test orders. The user can place one, and the skill then re-checks.

### DTC-11 `shopify_product_optimizer_skill` (new v0.4)
- **Purpose:** Shopify product content that converts and matches both the feed (DTC-09) and the ad promises (DTC-03): title, FAB description, SEO title/meta, alt text, FAQ, collections.
- **Inputs:**
  ```ts
  { store_id: string; product_ids: string[] | "all"; mode: "audit"|"rewrite";
    keywords?: { term:string; source:"gsc"|"gads_search_terms"; clicks:number; conv?:number }[]; insight_ref?: string /*X-04*/ }
  ```
- **Data:** `shopify.products_export`, `shopify.pdp_snapshot`, `gsc.performance_export`, `gads.search_terms_report`.
- **Output:**
  ```ts
  { audit:{ product_id:string; score:number; issues:string[] }[];
    rewrites:{ product_id:string; handle:string; title:string; body_html:string; seo_title:string /*≤60*/; seo_description:string /*≤155*/; image_alts:string[]; faq:{q:string; a:string}[] }[];
    import_csv?: ArtifactRef /*Handle + changed columns only*/; actions: ProposedAction[] }
  ```
- **Execution:** the `shopify.products_csv_import` write recipe (level 2).
- **Guardrails:**
  - X-02 `dtc_page` pack.
  - Claims come only from `ProductFacts`.
  - Never changes price, inventory, variants or status.
  - Keeps handles unchanged, to protect URLs and the feed.
- **Acceptance:** the import CSV contains only changed columns, and a dry-run diff against the export matches the rewrites.

---

## C7. Walmart skill

### WMT-01 `wmt_migration_ops_skill`
- **Inputs:**
  ```ts
  { mode: "screen"|"price_plan"|"wfs_model"|"report_diagnosis"; amazon_skus?: string[]; walmart_data?: ArtifactRef; reports?: { item_health?:ArtifactRef; item?:ArtifactRef; keyword?:ArtifactRef; placement?:ArtifactRef } }
  ```
- **Logic:**
  - **screen:** re-check demand, competition, price room, WFS fees and margin. Score each SKU and recommend.
  - **price_plan:** daily, promo and was-price calendar, avoiding last-minute changes.
  - **wfs_model:** fees, first batch, peak safety stock.
  - **report_diagnosis:** locate whether the failure is CTR, CVR or ROAS; check incremental vs cannibalized traffic.
- **Output:**
  ```ts
  { screen?: { sku:string; fit_score:number; verdict:"migrate"|"wait"|"no"; reasons:string[]; unit:{ net_margin:number } }[]; price_plan?: { sku:string; daily:number; promo:{start:string; end:string; price:number}[]; was_price:number }[]; wfs?: { sku:string; fees:Record<string,number>; first_batch:number; safety_stock:number }[]; diagnosis?: DecisionRecord[] }
  ```
- **Data (v0.2):** `wmt.sc.reports` recipes.
- **Open:** OQ-W1. Walmart thresholds are needed before building this skill. P5.

---

## C8. eBay skills (new v0.4; playbook A11, `[INF]`)

### EBY-01 `ebay_listing_optimizer_skill`
- **Purpose:** Improve Best Match visibility and conversion of active eBay listings.
- **Inputs:**
  ```ts
  { store_id: string; listing_ids: string[] | "all_active"; mode: "audit"|"rewrite"|"price_check" }
  ```
- **Data:** `ebay.sh_listings_export`, `ebay.traffic_report` (impressions, CTR, views, sales conversion), `ebay.terapeak_sold` (sold comps), the item page extractor.
- **Rules (A11):**
  - Title ≤80 characters.
  - Missing required/recommended item specifics are flagged.
  - Fewer than 8 photos is flagged.
  - Handling time > 2 days is flagged.
  - Returns < 30 days is flagged.
  - Best Offer off is flagged.
  - Price > Terapeak median +15% with low sell-through is flagged.
  - Funnel buckets: 0 impressions / low CTR / views without sales.
- **Output:**
  ```ts
  { audit:{ listing_id:string; score:number; bucket:"no_impressions"|"low_ctr"|"no_sales"|"ok"; issues:string[]; traffic:{ impr:number; ctr:number; views:number; conv:number } }[];
    rewrites:{ listing_id:string; title:string; item_specifics:Record<string,string>; description_html?:string; photo_tasks:string[] }[];
    price_suggestions:{ listing_id:string; current:number; comps_median:number; sell_through:number; suggested:number; reason:string }[];
    bulk_file?: ArtifactRef; actions: ProposedAction[] }
  ```
- **Execution:** the `ebay.sh_bulk_upload` write recipe (level 2). Price changes are `price_change` actions, which are never delegated.
- **Guardrails:**
  - `<EBAY_PROFILE>` no-touch rule (B8.3): run only within sanctioned sessions, with low page budgets.
  - The X-02 eBay pack: VeRO brand terms, keyword spam, off-platform contact.
- **Acceptance:** on a fixture export, every rule bucket is produced, and the bulk file only changes the selected fields.

### EBY-02 `ebay_promoted_listings_skill`
- **Purpose:** Manage Promoted Listings General (ad rate) and Priority (CPC) within margin.
- **Inputs:**
  ```ts
  { store_id: string; mode: "plan"|"optimize"; max_ad_rate_pct?: number; priority_budget_daily?: number }
  ```
- **Data:** `ebay.pl_reports` (listing-level impressions, clicks, sales, ad fees), suggested/trending rates, X-03 margins.
- **Rules (A11):**
  - Ad rate ≤ gross margin − target net margin.
  - Start near the trending rate.
  - Lower the rate on listings whose sales are mostly organic (dependency check).
  - Priority campaigns only for the top 10–20% of items; pause keywords with ≥30 clicks and 0 sales.
- **Output:**
  ```ts
  { general:{ listing_id:string; current_rate:number; new_rate:number; reason:string }[];
    priority?:{ campaigns:any[]; negatives:string[]; bid_changes:any[] };
    kpis:{ ad_fees:number; ad_sales:number; roas:number; organic_share:number }; actions: ProposedAction[]; bulk_file?: ArtifactRef }
  ```
- **Guardrails:** rate and budget changes are level 2, capped by margin.

### EBY-03 `ebay_seller_standards_skill`
- **Purpose:** Get the account from Below Standard back to Above Standard / Top Rated. This is a live need: TDR 25%, out-of-stock cancellations, and a lost INR case.
- **Inputs:**
  ```ts
  { store_id: string; ex04_report: string /*EX-04 result id*/; window: "current"|"projected" }
  ```
- **Data:** `ebay.performance` (seller level, transaction defect rate, late shipment rate, cases closed without seller resolution, tracking on time, evaluation date), the orders list, `ebay.sh_listings_export` (quantities).
- **Logic:**
  - Break defects down by cause.
  - Project the next evaluation, and compute the defect-free transactions needed to get under the threshold (deterministic tool).
  - Map each root cause to a fix:
    - Stock accuracy / end dead listings.
    - Realistic handling time.
    - Same-day tracking upload.
    - Reply within 24h (X-13).
    - Resolve before a case opens.
- **Output:**
  ```ts
  { status:{ level:string; tdr:number; late_rate:number; cases_wo_resolution:number; eval_date:string };
    defect_breakdown:{ cause:string; count:number; examples:string[] }[]; needed_clean_txns?: number;
    plan:{ action:string; owner:"user"|"agent"; due:string }[]; inventory_fixes:{ listing_id:string; issue:"oversell_risk"|"dead_listing"; fix:string }[];
    followups: FollowupRequest[] /*X-13 drafts, EBY-01*/ }
  ```
- **Guardrails:** cancellations, refunds and returns are the user's decisions; the agent only drafts.

## C9. Etsy skills (new v0.4; playbook A12, `[INF]`)

### ETS-01 `etsy_listing_seo_skill`
- **Purpose:** Etsy search visibility and conversion.
- **Inputs:**
  ```ts
  { store_id: string; listing_ids: string[] | "all_active"; mode: "audit"|"rewrite" }
  ```
- **Data:** `etsy.listings_export`, `etsy.stats` (visits, views, favorites, orders, conversion, search terms), `etsy.search_visibility`, the listing page extractor.
- **Rules (A12):**
  - Title ≤140 characters with the key phrase first.
  - Exactly 13 tags, each ≤20 characters, multi-word, no duplicate of category/attribute words.
  - All attributes filled.
  - ≥5 photos (+ video).
  - Free US shipping threshold ($35) respected.
  - Processing time realistic.
  - Stats search terms feed the tags.
- **Output:**
  ```ts
  { audit:{ listing_id:string; score:number; issues:string[]; stats:{ visits:number; conv:number } }[];
    rewrites:{ listing_id:string; title:string; tags:string[] /*13*/; attributes:Record<string,string>; description_opening:string; photo_tasks:string[] }[];
    actions: ProposedAction[] }
  ```
- **Execution:** the `etsy.listing_edit` write recipe, one listing at a time (level 2, serialized, low rate), or the user applies the edits.
- **Guardrails:**
  - No trademarked terms.
  - No keyword stuffing.
  - The `<ETSY_PROFILE>` no-touch rule (B8.3).

### ETS-02 `etsy_ads_skill`
- **Purpose:** Etsy Ads on/off per listing, budget, and Offsite Ads economics.
- **Inputs:**
  ```ts
  { store_id: string; mode: "plan"|"optimize"; daily_budget: number }
  ```
- **Data:** `etsy.ads_report` (per-listing views, clicks, orders, revenue, spend), the Offsite Ads status, X-03 margins.
- **Rules (A12):**
  - Start with the best organic converters.
  - Judge after ≥14 days.
  - Turn off at ≥40 clicks with 0 orders.
  - Keep ROAS ≥ break-even.
  - Add the Offsite Ads fee (12–15%) to unit economics.
- **Output:**
  ```ts
  { listings:{ listing_id:string; ads:"on"|"off"; reason:string; metrics:any }[]; budget:{ current:number; proposed:number }; offsite_ads_note:string; actions: ProposedAction[] }
  ```
- **Guardrails:** budget changes are level 2.

---

# PART D: Manager skill (orchestration)

## D1. Role & responsibilities
`mgr_ecom_manager_skill` runs on a dedicated agent, **ecom-manager**.

**(v0.5)** It is first of all a **chat agent** (D9). Its standing goal is the user's contribution profit within the user's constraints (B9.5), pursued through the learning loop (B9.6, D10). The orchestration duties below run underneath the chat. It does not do analysis itself. It:

1. **Plans.** Turns a trigger into a run of a **Playbook**, or into an ad-hoc plan when a human gives a free-text command.
2. **Dispatches.** Sends TaskEnvelopes to role agents that host the needed skill (agent discovery by skill), respecting dependencies and concurrency.
3. **Waits and collects.** Uses `pend_event_node` on agent replies, with timeouts and retries.
4. **Verifies.** Checks every SkillResult before it is used (D5).
5. **Routes decisions.**
   - `actions_proposed` go to the approval gate (X-09).
   - `followups` become new dispatches, subject to the policy.
   - `anomalies` of class `immediate` are notified at once.
6. **Executes approved actions.** It dispatches execution tasks (bulk-file upload by the browser-operator, or an API call) only for level-2 approved actions. Then it logs the outcome and schedules the review date as an ExperimentCard.
7. **Reports.** Calls X-10 for digests.
8. **Learns and scores.** MGR-02 evaluates decisions after their review dates. MGR-03 builds monthly agent scorecards.

## D2. Triggers

| Trigger | Source | Example |
|---|---|---|
| `schedule` | eCan task schedules (one per playbook) | `amz_daily_ads` 08:30 store-local |
| `event.file` | new file in `inbox/<store>/` | ingest → route by report_type |
| `event.alert` | AMZ-10 / TTS-01 immediate anomaly | hijacker → notify + ticket |
| `event.approval` | approval-portal webhook `approval.decided` (from the email/SMS link) | execute approved actions |
| `event.input` | portal webhook `input.submitted` (logged in / OTP / form / patch review) | resume the paused run |
| `event.timer` | `add_timer` / `ec_experiment(due)` | evaluate an experiment |
| `human` | chat command | "帮我优化 B0XXXX 的 listing" / "run weekly report for store US-1" |

## D3. Playbook definition (declarative DAG)
Playbooks are data files (`playbooks/*.json` in the KB), so new routines need no new skill. The Manager interprets them.

**Format (v0.9, OQ-G12): JSON is the source of truth.**
- Playbooks are executed by the Manager, so they must validate against the `Playbook` schema, diff cleanly in `ec_change`, and roll back exactly. JSON does that.
- Each playbook has a **generated Markdown view** (`playbooks/<id>.md`: purpose, schedule, steps, gates, last change) for reading. The view is regenerated on every change and never edited by hand.
- Sellers change playbooks by asking the Manager in chat ("run the ads check at 9am instead", "skip TikTok on weekends"). The Manager edits the JSON and submits a ChangeProposal (B9). No GUI form in v1.
- Prose knowledge (the Part A playbook guidance, prompt fragments, platform-pack notes) stays in Markdown, as eCan prompts already are (`format: "md"`).

```ts
type Playbook = {
  id: string; title: string; version: string;
  scope: { platform: string; store_ids: string[] | "all" };
  schedule?: { cron: string; tz: "store" | string };
  inputs_template?: Record<string, any>;           // supports {{date}}, {{store_id}}, {{week}} templating
  steps: PlaybookStep[];
  on_failure: "continue" | "abort" | "notify";
  digest?: { period: "daily_am"|"daily_pm"|"weekly"|"monthly"; audience: string };
  approval_level_max: 0|1|2|3;
  budget?: { max_llm_cost_usd: number; max_browser_steps: number };
};
type PlaybookStep = {
  id: string; skill: string; inputs: Record<string, any>;   // may reference outputs: "$steps.ingest.result.tables[0].artifact"
  depends_on?: string[]; when?: string;                      // condition expr over prior results, e.g. "$steps.diag.result.anomalies.length > 0"
  foreach?: string;                                          // fan-out expr, e.g. "$store.hero_asins"
  parallel_max?: number; timeout_min?: number; retries?: number; optional?: boolean;
};
```

**Initial playbooks:**

| Playbook | Steps (→ = depends on) | Cadence |
|---|---|---|
| `growth_weekly_review` | X-14 (all stores) → the Manager updates `plan_30d` steps and review dates → X-10 weekly digest | Mon 08:00 |
| `shopify_google_daily` | session checks (Google + Shopify profiles) → X-08 Google Ads + Shopify reports → X-01 → DTC-03 `optimize_daily` → X-09 → X-10 | daily 08:00 |
| `shopify_google_weekly` | DTC-10 spot check → DTC-09 diagnose + labels → DTC-03 `optimize_weekly` → DTC-02 funnel → DTC-11 (bottom products) → X-09 → X-10 | Tue 09:00 |
| `messages_sla` | EX-01…04 messages → X-13 drafts → email the drafts, and SMS if any message is >12h old | 09:00 and 17:00 |
| `marketplace_listing_sprint` | for each store: AMZ-02/03, EBY-01, ETS-01 on the bottom-traffic listings → X-02 → X-09 → write recipes | biweekly / on demand |
| `stores_daily_check` | EX-01 … EX-04 (one per store, parallel by profile) → adapters (B8.5) → AMZ-11 followups (drafts) → X-10 end-of-day digest (email; SMS only for immediate red flags) | daily, per the existing schedules |
| `browser_registry_health` | X-08 dry-run (session check + asserts) for each ★ recipe → X-12 on failure → `ec_input_request(login)` for logged-out profiles | daily 06:30 (before the morning playbooks) |
| `amz_daily_ads` | X-08 `amz.ads.report_request` (requested the previous evening) + `amz.sc.business_report` → X-01 ingest → AMZ-08 daily diagnosis → AMZ-05 (7d) → X-09 approvals → X-10 digest | daily 08:30 |
| `amz_weekly_ops` | X-01 → AMZ-09 weekly → AMZ-06 placement/budget → AMZ-05 (30d, root words) → X-05 competitors → X-04 reviews → MGR-02 evaluations → X-10 weekly digest | Mon 09:00 |
| `amz_monthly_strategy` | AMZ-07 dependency → AMZ-08 deep (stage/role per SKU) → AMZ-06 dayparting → X-03 cash plan refresh → MGR-03 scorecards | 1st Mon |
| `amz_listing_refresh` | X-04 → AMZ-03 (foreach ASIN in scope) → X-09 (listing_update) | on demand / quarterly |
| `amz_patrol` | AMZ-10 (hero ASINs) → when alerts: ec_notify + ticket | every 3h |
| `amz_new_product` | AMZ-01 evaluate → X-03 → X-11 GTM → AMZ-02 create → X-06 visuals → AMZ-04 ads plan | on demand |
| `tts_daily` | X-01 → TTS-01(am) … TTS-01(midday) … TTS-01(pm) → X-10 | 09:00 / 13:00 / 17:00 |
| `tts_weekly_creative` | TTS-02 → X-07 (remix briefs) → TTS-04 followups → X-10 | Mon |
| `dtc_weekly_growth` | DTC-02 → DTC-04 → DTC-03 optimize → DTC-01 (top landing pages) → X-10 | Mon |
| `reddit_daily` | DTC-06 reply_scan → notify drafts | daily 10:00 |
| `reddit_monthly` | DTC-05 refresh → DTC-07 geo plan | monthly |
| `peak_season` | X-11/DTC-08 12-week plan; weekly checkpoints | event |

## D4. Manager skill flow (Flowgram sheets)

```
main:
 start
  → code:load_context        (trigger, playbook, store_profile, approval_policy, open runs)
  → mcp:ec_session_check     (each profile the playbook needs; blocked → ec_input_request email+SMS → pend until resumed / skip store)
  → llm:plan                 (ONLY for human free-text: map request → playbook or ad-hoc steps using {{skills_schema}};
                              output Plan JSON; ambiguity → needs_input)
  → code:build_run           (resolve templating, foreach fan-out, topo-sort; create Run record)
  → loop (while run not complete)
      → code:ready_steps     (deps satisfied, concurrency, change-throttle P4)
      → mcp:ec_task_dispatch (parallel per ready step)   [multi_tool_calls: parallel]
      → pend_event_node      (wait any reply | timeout tick)
      → sheet-call verify    (D5) → condition pass?
            no  → retry (≤retries, with error context) | mark failed | escalate
            yes → code:merge_result
      → code:route           (immediate anomalies → ec_notify;
                              actions_proposed → queue for approval batch;
                              followups → policy check → append steps)
  → sheet-call approvals     (X-09 with batched actions, if any and level≥2 allowed)
  → sheet-call execute       (dispatch execution tasks for approved actions; log; create ExperimentCards)
  → sheet-call digest        (X-10)
  → code:close_run           (persist Run, costs, all_done=true)
 end
```

**Run record (persisted):**
```ts
type Run = { run_id: string; playbook_id?: string; trigger: string; started_at: string; ended_at?: string;
  steps: { step_id: string; task_id: string; agent_id: string; skill: string; status: "pending"|"dispatched"|"done"|"failed"|"skipped"; attempts: number; result_ref?: string; verify?: VerifyReport }[];
  approvals: string[]; executed_actions: string[]; cost: { llm_usd: number; browser_steps: number }; status: "running"|"done"|"partial"|"failed" };
```

**Manager LLM `plan` node:**
- **Inputs:** human text, `{{skills_schema}}`, the playbook list and the store list.
- **Output:**
  ```ts
  { intent: string; playbook_id?: string; ad_hoc_steps?: PlaybookStep[]; store_ids: string[]; questions?: string[] }
  ```
- **Rules:**
  - Prefer an existing playbook.
  - Never invent skills.
  - If a required input is missing (store, ASIN), ask: return `needs_input` with `questions`.
  - Never raise `approval_level_max` above the store policy.

## D5. Verification (the Manager's QA gate)
`verify` runs on every SkillResult. Checks 1–6 are deterministic. Check 7 is an LLM spot-check.

| # | Check | Fail → |
|---|---|---|
| 1 | Envelope valid: `ec_schemas_get(SkillResult)` + the skill's result schema | retry with the validation errors |
| 2 | `status` consistent (`needs_input` → route the question to a human) | escalate |
| 3 | **Evidence integrity:** every `DecisionRecord.evidence.value` re-queried against the referenced table/artifact (sampled ≤ 20) | reject; log a "hallucinated number" against the agent's score |
| 4 | **Policy:** each `ProposedAction.required_level` ≤ the envelope max; caps (bid %, budget %, actions per day); entity changed in the last 72h (P4); brand-term protection | strip the offending actions, warn |
| 5 | **Compliance:** customer-facing text in the result carries a passing `x_compliance_gate` verdict | re-dispatch to X-02 |
| 6 | **Red list:** a keyword scan for A9 tactics in the drafts and recommendations | reject + alert |
| 7 | **Sanity (LLM, cheap model):** "Does the summary contradict the result data? Are the recommendations consistent with the stated lifecycle stage?" | warn, or request a re-run |

```ts
type VerifyReport = { passed: boolean; checks: { id: number; ok: boolean; detail?: string }[]; stripped_actions?: string[] };
```

## D6. Agent scorecards (MGR-03) and the decision feedback loop (MGR-02)

### MGR-02 `mgr_experiment_evaluator_skill`
- **Inputs:**
  ```ts
  { due_before: string; store_ids?: string[] }
  ```
- **Logic:**
  - Pull the ExperimentCards that are due and the DecisionRecords with `acceptance.review_at` ≤ now.
  - Re-query the metrics over the same window definition (P5).
  - Verdict: keep / rollback / extend / inconclusive.
  - If rollback, create a rollback ProposedAction (level 2).
- **Output:**
  ```ts
  { evaluated: { id:string; kind:"experiment"|"decision"; verdict:string; before:Record<string,number>; after:Record<string,number>; met_acceptance:boolean; rollback_action_id?:string }[] }
  ```

### MGR-04 `mgr_experiment_designer_skill` (new v0.5)
- **Purpose:** Turn diagnoses, anomalies, learnings and user requests into ranked hypotheses and concrete experiment designs for operator agents (B9.6, B9.8).
- **Trigger:** weekly after X-14 / X-16, when a chat request implies a test ("try lower prices on eBay"), or when a learning-transfer candidate appears.
- **Inputs:**
  ```ts
  { goal_ids: string[]; sources: { diagnosis_ids?: string[]; anomaly_ids?: string[]; learning_ids?: string[]; user_requests?: string[] }; max_new: number /*default 3*/ }
  ```
- **Tools:** `ec_learning(query)`, `ec_kb_resolve` (immutable core and constraints), `ec_experiment_design`, `ec_experiment(op:"create")`, `ec_table_query`.
- **Flow:**
  1. `llm:hypothesize` writes hypotheses with an expected effect and scope.
  2. `code:ice_score` × goal gap.
  3. `code:budget_and_lock_check` enforces the exploration share, concurrency and unit locks.
  4. `mcp:ec_experiment_design` (method chosen from the pack's `experiment_methods`).
  5. `llm:write_card` produces the card, success criteria and stop rules in plain language.
  6. Designs that change spend or listings go to X-09 for approval.
- **Output:**
  ```ts
  { hypotheses: Hypothesis[]; designs: ExperimentDesign[]; rejected: { hypothesis_id:string; reason:"budget"|"lock"|"core"|"low_ice"|"insufficient_traffic" }[] }
  ```
- **Guardrails:**
  - Never designs an experiment that touches the immutable core or A9 tactics.
  - Every design has guardrail metrics, a budget cap and a maximum duration.
  - Price experiments are `price_change` actions, so every arm needs user approval (never delegated).

### MGR-05 `mgr_change_manager_skill` (new v0.5)
- **Purpose:** How the agent system improves itself and its operators safely. Learnings and repeated human edits or rejections become `ChangeProposal`s, which go through the evaluation stages before promotion (B9.7).
- **Trigger:**
  - New validated learnings (from MGR-02).
  - MGR-03 scorecard findings, e.g. "human edit rate on Etsy titles is 60%".
  - X-12 recipe proposals.
  - A user request in chat ("stop suggesting X").
- **Inputs:**
  ```ts
  { source: { learning_ids?: string[]; scorecard_id?: string; user_instruction_id?: string; x12_proposal_id?: string } }
  ```
- **Tools:** `ec_change`, `ec_eval_suite_run`, `ec_skill_lint`, `ec_kb_resolve`, `x_approval_gate`.
- **Flow:**
  1. `llm:draft_change` writes the smallest diff: a threshold value, a prompt fragment, a schedule, a pack version.
  2. `code:core_check`: anything touching the immutable core is rejected.
  3. Offline eval (`ec_eval_suite_run`) → shadow (N runs) → canary, each as the change kind requires.
  4. X-09 approval, unless a tuning grant covers it.
  5. Promote, and set the rollback trigger.
  6. Monitor; on a trigger, roll back and notify.
- **Output:**
  ```ts
  { proposal: ChangeProposal }
  ```
- **Guardrails:**
  - Each change carries its learning evidence.
  - At most 1 active change per target at a time, and changes don't overlap a running experiment on the same unit.
  - The Manager's own core rules are never editable.
  - Every promotion or rollback appears in the chat and the digest.

### MGR-03 `mgr_agent_scorecard_skill` (maps A7 HR KPIs to agents)

| Dimension | Metric | Target `[INF]` |
|---|---|---|
| Throughput | tasks done / dispatched; on-time % (vs timeout) | ≥ 95% on time (A7 design team) |
| Quality | verify pass on first attempt %; evidence-integrity failures; compliance first-pass %; human edit rate on drafts | ≥ 90%; 0; ≥ 85%; trending ↓ |
| Acceptance | approved / proposed actions %; rejected-with-reason clusters | ≥ 70% |
| Outcome | % of decisions meeting acceptance at review; KPI movement attributable (ACOS, CVR, CTR) | ≥ 60% |
| Cost | LLM $ per task; browser steps per task | budget per playbook |
| Stability | output variance on rerun fixtures (PL principle) | structural diff = 0 |

- **Output:** a monthly scorecard per agent and per skill, plus the top 3 prompt or threshold tuning suggestions. Tuning suggestions are human-applied: thresholds and prompts are versioned and never auto-edited.

## D7. Concurrency, cost, safety

- **Concurrency:**
  - At most N parallel tasks per agent (default 2).
  - Browser agents are limited to 1 per profile, and each profile is pinned to one store.
- **Budgets:**
  - Per-playbook LLM $ and browser-step caps. The Manager aborts remaining optional steps when a cap is hit.
  - Model routing (v0.8): Manager steps use tier `manager` (sol). Operator steps use tier `web` (luna) for verify, map_headers, relevance, diagnosis and copy. Tasks the Manager marks `mode: "explore"` may escalate once to `explore` (terra) within the caps in B3.7.
- **Idempotency:**
  - `task_id` is deterministic for scheduled runs (`playbook:store:date:step`).
  - Re-delivery is ignored.
- **Acquisition windows (v0.2):**
  - Async reports are requested in the evening run and downloaded in the morning run.
  - Recipes for one site are serialized per profile.
  - A playbook whose data is missing marks dependent steps `skipped(data_unavailable)` instead of running on stale data.
- **Kill switch:** the store-level flag `automation_paused=true` stops all dispatches except `ingest`, `patrol` and `digest`.
- **Audit:** every dispatch, result, approval, execution and rollback goes to `ec_decision_log`, and can be queried by object (e.g. "everything that touched campaign X in October").

## D8. Role agents (hosts) and skill assignment

| Agent | Skills hosted | Model role | Notes |
|---|---|---|---|
| `ecom-manager` | MGR-01, MGR-02, MGR-03, X-09, X-10 | analysis + cheap | single instance |
| `data-analyst` | X-01, X-03, X-04, X-14, AMZ-07, AMZ-08, AMZ-09, TTS-03, DTC-01, DTC-02, DTC-07, DTC-10 | analysis | |
| `ads-optimizer` | DTC-03, DTC-04, AMZ-04, AMZ-05, AMZ-06, EBY-02, ETS-02, TTS-02 | analysis | DTC-03 first (v0.4) |
| `listing-writer` | DTC-09, DTC-11, AMZ-02, AMZ-03, EBY-01, ETS-01 | writing | multilingual |
| `creative-studio` | X-06, X-07 | writing + vision | |
| `compliance-officer` | X-02, AMZ-11, EBY-03 | analysis (cheap for lint) | |
| `browser-operator` | X-08, X-12, AMZ-03b, AMZ-10, X-05 | vision-capable (T3 only) | one per browser profile/store; T1/T2 need no LLM |
| `store-ops` | AMZ-01, X-11, TTS-01, TTS-05, WMT-01 | analysis | |
| `community-manager` | X-13, DTC-05, DTC-06, DTC-08, TTS-04 | writing | drafts only |

## D9. The Manager as a chat agent (v0.5)

**Channel:**
- The eCan chat with the `ecom-manager` agent: the GUI chat, and `send_chat` for programmatic use.
- Long-running work continues asynchronously. The Manager posts progress and results back into the same chat thread.
- Email and SMS stay for approvals, digests and urgent alerts (B7).
- **v0.6 (OQ-G25):** eCan chat at launch. **WhatsApp and WeChat** come later through eCan's existing channel bridges. The chat layer is channel-agnostic, so adding a channel means adding an adapter, with no change to the Manager:

```ts
type ChatMessage = { message_id: string; tenant_id: string; thread_id: string;
  channel: "ecan" | "whatsapp" | "wechat" | "email_reply"; channel_user_id: string; verified_identity: boolean;
  direction: "in" | "out"; text: string; attachments?: ArtifactRef[];
  card?: { kind: "approval" | "question" | "brief"; payload: any };   // rendered natively per channel (buttons on eCan; numbered replies on WhatsApp/WeChat)
  created_at: string };
```

**Per-turn loop** (one Flowgram sheet, `chat_turn`):

```
start (user message in state.attributes.current_invocation_input)
 → code:load_context     (active goals, user instructions, open runs/approvals, last N turns + thread summary, store list)
 → llm:understand        (intent + entities + missing info; output ChatIntent JSON)
 → condition by intent:
     ask_status / ask_why  → mcp:ec_table_query / ec_ledger / ec_decision_log / ec_learning → llm:answer_with_evidence
     request_work          → llm:plan (map to playbook / capability skill / experiment; ask if ambiguous) → dispatch (D4 loop, async)
     set_goal / constraint → draft Goal change (incl. exploration share, max experiments, budgets) → confirm in chat → ec_kb_put
     teach                 → draft UserInstruction → confirm ("Got it: never use 'eco-friendly' for store X — save?") → ec_kb_put → MGR-05 (prompt/threshold impact)
     approve / reject      → low/medium risk: confirm in chat and record via X-09 (v0.6, OQ-G26); high risk: send the portal link (+PIN)
     onboard / add_store   → X-15 interview mode
     smalltalk / unclear   → brief answer + clarifying question
 → llm:reply             (short, the user's language, numbers only from tool results, links to reports)
 → code:update_memory    (thread summary, extracted facts → pending confirmations)
 → end
```

```ts
type ChatIntent = { intent: "ask_status"|"ask_why"|"request_work"|"set_goal"|"set_constraint"|"teach"|"approve"|"reject"|"onboard"|"configure"|"smalltalk"|"unclear";
  entities: { store_ids?: string[]; platform?: string; skus?: string[]; metric?: string; period?: string; amount?: number };
  missing: string[]; confidence: number };

type UserInstruction = { id: string; text: string; normalized: { kind: "rule"|"prohibition"|"preference"|"fact"|"priority"; key?: string; value?: any };
  scope: { store_ids?: string[]; platform?: string; category?: string; sku?: string };
  source_turn: string; confirmed: boolean; created_at: string; expires_at?: string; status: "active"|"retired" };
```

**Manager chat prompt** (sections per B3.8):
- **goals:** "You are the user's e-commerce operations manager. Your goal is to grow contribution profit across their stores within their constraints, by understanding what they need, running and improving the operator agents, and being honest about results."
- **guidelines:**
  - Ask before assuming. Interview for missing context: goals, budgets, margins, priorities.
  - Prefer existing playbooks and capabilities.
  - Propose experiments when unsure.
  - Summarize first; give details on request.
  - Report failures plainly ("CHECK DID NOT COMPLETE").
- **rules:**
  - Numbers come only from tool results, and are cited.
  - Never claim an action was done unless the decision log shows it executed.
  - Never act outside the approval levels, and never touch the immutable core.
  - Spending, price changes, messages, appeals and listing pushes always go through approvals.
  - Teachings are confirmed before they are saved.
  - Store-specific data never goes into skill files.
- **examples:** a status question, a request that becomes a playbook, a teaching confirmation, a refusal of an A9 tactic with a compliant alternative.

**Tools exposed to the chat LLM:** a curated subset, not all ~130 MCP tools, to keep tool selection reliable.
- **Read:** `ec_table_query`, `ec_ledger(query)`, `ec_decision_log(query)`, `ec_learning(query)`, `ec_experiment(status)`, `ec_kb_get`.
- **Write:** `ec_kb_put` (goals and user instructions only, after confirmation).
- **Work and approvals:** `ec_task_dispatch` / run playbook, `ec_approval_request` status.
- **Self-adjustment:** `mgr_change_manager` and `mgr_experiment_designer` as sub-skills.

**Proactive messages** from the Manager into the chat:
- The morning brief (ledger vs goal, immediate issues, approvals waiting).
- Questions it is blocked on, e.g. "I need the COGS for these 12 products to judge Google Ads ROAS."
- Experiment results and the new learnings.
- Proposed changes awaiting approval.
- Things only you can do: sign-ins, certifications, policy pages.

**Memory:**
- A rolling thread summary plus the last N turns.
- Durable facts go to the KB only as confirmed `UserInstruction`s or `Goal`s. The Manager never silently "remembers" something that changes behaviour.

**Acceptance (chat):**
- "How did Etsy do last week?" returns ledger numbers that match `ec_ledger`.
- "Run Google Ads optimization for store X" starts `shopify_google_weekly` and later posts the digest into the same thread.
- "Never use the word cheap" creates a confirmed UserInstruction, and X-02 enforces it on the next draft.
- "Buy some reviews" is refused, with a compliant alternative.

## D10. The Manager's learning duties (v0.5)

| Cadence | Duty | Skills |
|---|---|---|
| Daily | Update the ledger vs goal; immediate anomalies; experiment stop-rule checks | X-16, AMZ-08/TTS-01/DTC-03 daily, MGR-02 (stop rules) |
| Weekly | Re-diagnose (X-14) → new hypotheses and designs within the exploration budget (MGR-04) → evaluate finished experiments (MGR-02) → ChangeProposals (MGR-05) → weekly digest, plus a chat summary of what was learned | X-14, MGR-04, MGR-02, MGR-05, X-10 |
| Monthly | Scorecards (MGR-03) → prompt/threshold proposals; learning-transfer proposals; onboarding refresh; goal review with the user in chat | MGR-03, MGR-05, X-15 |

**Success metrics for the Manager itself:**
- Contribution profit vs goal, the trend that matters.
- Experiments completed per month.
- Share of validated vs refuted hypotheses: calibration, not just wins.
- Promoted changes with 0 rollbacks.
- Fewer human edits per draft over time.
- Fewer open data gaps, including COGS coverage ≥ 80%.
- AI cost (tokens + browser runs) as a share of contribution, trending down (v0.6).

---

# PART E: Roadmap, open questions, review log

## E1. Build order & exit criteria

**Blocking dependencies before P0 can finish (v0.3, from the <BUILD_HOST> handoff).** These are server items, not skill work:
1. The eCanAI LLM proxy returns empty `choices` (item 6). Every LLM and browser step fails until it is fixed, or until a fallback provider is configured.
2. `requestReportUploadUrl` for report S3 upload (item 3). Not blocking: reports stay local until then.
3. The intl API key (items 4 and 7). Without it, runs longer than the ~1h Cognito token fail with 401.
4. The intl `onA2AMessage` subscription (item 5). A2A dispatch and the approval decision push need it; polling is the fallback.
5. The new approval/input API + page + SES/SNS setup (B7).

| Phase | Goal | Build | Exit criteria |
|---|---|---|---|
| **P0 Foundation** (≈2–3 wks) | Plumbing everything else needs | B3 schemas + `ec_schemas_get`; L1 tools (report/table/metrics/rules/compliance/unit-economics/KB/decision log/notify/approval/input/delegate/dispatch/session/recipe/JS/download/registry); approval portal on eCan cloud + SES/SNS (B7, B7.1); X-01, X-02, X-03, X-08, X-09, X-10, **X-15 onboarding, X-16 profit ledger (incl. AI cost), MGR-01 chat agent (D9, eCan chat channel, in-chat approval cards)**; tenant model + isolation (B9.10); `ec_kb_resolve` layering (B9.3) and `ec_skill_lint`; EX-01…06 adapters + `stores_daily_check`; session checks for all profiles | A dummy playbook dispatches → verifies → digests end to end; SMS approval round-trips in < 1 min; all six existing skills run under the Manager, with the OpenAI fallback active while the eCanAI gateway is down; onboarding produces KB records for every existing store through a chat interview; the ledger shows daily contribution per store; the D9 chat acceptance cases pass |
| **P1 Shopify + Google Ads** (≈3–4 wks; the user's priority) | Get the Shopify stores selling through Google | X-14, X-13, DTC-10, DTC-09, DTC-11, DTC-01, DTC-02, DTC-03 (as `cap_*` skills + google/shopify packs); MGR-02, MGR-04, MGR-05 (offline eval + approval); ★G recipes + the `gads.bulk_upload` / `gmc.supplemental_feed_upload` / `shopify.products_csv_import` write recipes; playbooks `shopify_google_daily/weekly`, `growth_weekly_review`, `messages_sla` | Both stores: tracking `pass`, feed approval ≥ 90%, policy pages complete; campaigns launched within budget; 4 weekly optimize cycles with ≥ 70% of proposals approved; ROAS vs break-even reported weekly; X-14 ranks every store's constraint; ≥2 Manager-designed Google Ads experiments run, evaluated and stored as Learnings; ≥1 ChangeProposal promoted through offline eval |
| **P2 Marketplace basics** | Fix health, listings and responsiveness on Amazon, eBay, Etsy, TikTok | X-17 (generic daily check, shadowed against EX-01…04 then replacing them), MGR-05 shadow/canary stages, AMZ-11, EBY-03, AMZ-02, AMZ-03 (simulated), X-04 (on EX-05), EBY-01, ETS-01, TTS-01, X-12, MGR-02; `marketplace_listing_sprint` | eBay on a recovery trajectory before the next evaluation; Etsy response rate ≥ 95%; Amazon account issues each have a draft fix/POA for the user; top 20 listings per store audited and rewritten, with approved ones applied |
| **P3 Marketplace ads + creative** | Paid traffic where listings are ready | AMZ-08, AMZ-05, AMZ-06, AMZ-04, EBY-02, ETS-02, TTS-02, TTS-03, X-06, X-07 | Ads ROAS ≥ break-even per platform after learning; a weekly approved creative output |
| **P4 Research & expansion** | New products and channels | AMZ-01 (on EX-06), TTS-05, TTS-04, X-05, X-11, AMZ-10, DTC-04, DTC-05, DTC-06, DTC-07, DTC-08 | First new-product memo → GTM → launch for one SKU; Meta and Reddit tests within budget |
| **P5 Scale & autonomy** | Less manual approval, more coverage | AMZ-07, AMZ-09, MGR-03, WMT-01, delegation-grant pilots (AMZ-03b dropped: OQ-G5 simulated only) | Scorecards live; a first delegation grant (negatives) with 0 rollbacks over 30 days |

**Where the build happens (OQ-G21):** on <BUILD_HOST>, branch `us_ec_skills`, once this doc is final. The B8.3 conventions apply.

### E1.1 Build-start checklist (v1.0)
Work top to bottom. Each step has a check that must pass before the next step starts.

**Step 0: before any skill work**
| # | Item | Done when |
|---|---|---|
| 0.1 | Rotate the OpenAI key found hardcoded in `my_skills/my_test_llm_tools_skill/...json` (B1), and store the new key in eCan's key store as `secret:openai` | Old key revoked; no key string in any skill JSON (`ec_skill_lint` clean) |
| 0.2 | Confirm the model ids `gpt-6.1-sol`, `gpt-6-luna` and `gpt-6.1-terra` on the eCanAI proxy and direct OpenAI, and check luna image input (OQ-G6c) | One test call per id per provider returns valid JSON; vision role mapped |
| 0.3 | eCanAI proxy empty-`choices` fix, or OpenAI fallback wired (E1 blocker 1) | An LLM node and a browser step both complete end to end |
| 0.4 | Intl API key so runs survive the ~1h Cognito token (blocker 3) | A 2h run finishes without 401 |
| 0.5 | Decide where this spec lives on <BUILD_HOST>. **Do not commit it as-is**: B8 tables name real stores and agent ids (B8.3 rule 6). Either keep it outside the repo or commit a copy with B8 store/agent names redacted | Spec readable by the build terminal; no account specifics in git |
| 0.6 | Re-read the no-touch profile rules (B8.3): never save, reset, import or modify store browser profiles or their cookies | Acknowledged in the build session's memory |

**Step 1: P0 foundation, in this order** (each item lists the spec section it implements)
| # | Build | Spec | Done when |
|---|---|---|---|
| 1.1 | `ec_schemas` registry with the B3 envelopes and shared shapes (TaskEnvelope with `mode`, SkillResult with model metrics, StoreProfile with `languages` + `legal_entity_id`, Tenant) | B3.2, B3.3, B9.10 | Schemas load; sample envelopes validate |
| 1.2 | `ec_store` (SQLite `ec_data.db` + Parquet + embedded DuckDB) with `ec_kb_*`, `ec_table_query`, `ec_kb_export/import`, `ec_store_snapshot` | B9.10 storage, B5 | Round-trip a KB record; SQL over a Parquet table joined to COGS; snapshot + restore on a scratch folder |
| 1.3 | `model_policy` resolution, escalation and fallback in the LLM/browser node wrappers | B3.7 | Forced invalid JSON on an `explore` task escalates once to terra; a `run` task does not; usage lands in SkillResult metrics |
| 1.4 | L1 deterministic tools: report detect/normalize, metrics, rules, unit economics, decision log, notify | B5 | Fixture reports normalize; rules produce the expected decisions |
| 1.5 | Browser acquisition: session, recipe runner, JS extractor runner (no `fetch`), registry, download | B6 | A ★ recipe and a T2 extractor run on one store profile read-only; T3 fallback returns `blocked.layout_changed` on a broken selector |
| 1.6 | EX-01…06 adapters into the `StoreDailyCheck` shape | B8 | Each existing daily check returns a valid SkillResult |
| 1.7 | Approval/input portal on eCan cloud + SES/SNS + `ec_delegate_approve` | B7, B7.1 | Email + SMS link approve and reject round-trip; an expired link is refused; PIN never appears in logs |
| 1.8 | X-01, X-02, X-03, X-08, X-09, X-10 | C | Each passes its spec's acceptance line |
| 1.9 | MGR-01 chat Manager on sol: chat turn, in-chat approval cards, playbook interpreter (JSON + generated md view) | D9, D3 | "Run today's check for all stores" in eCan chat produces a digest and one approval card |
| 1.10 | X-15 onboarding (asks the runtime OQs, sets store languages, entity, `cloud_data`, `buyer_reply_policy`) and X-16 profit ledger incl. AI cost | X-15, X-16 | A new store onboards from chat; the ledger shows AI cost per store pro rata |

**Step 2: P1 (Shopify + Google Ads)**, as in the E1 table. Start with DTC-10 (tracking audit), because every later Google decision depends on conversion data being right.

**Change control after the freeze:**
- Design changes go in as v1.x rows in E4, with IDs kept stable.
- Questions found while building are logged as `OQ-I<n>` (implementation) in E2, with the skill ID and the decision taken, so this doc stays the record.

## E2. Global open questions (please answer or comment inline)

**v0.5:** questions tagged **(runtime)** no longer block the spec. The Manager asks them in chat during onboarding (X-15), and the answers are stored as Goals, UserInstructions or KB records: OQ-G22, G23, D4, D5, T5, E2, ET2 and G7 (categories).

| ID | Question | Why it matters / my default |
|---|---|---|
| ~~OQ-G1~~ | **RESOLVED v1.0:** role agents shared across stores; browser-operator instances per store/profile | — |
| ~~OQ-G2~~ | **RESOLVED v0.2:** all data comes through the browser (recipes, JS extractors, LLM fallback). See B6. **Follow-up:** which paid data tools do you hold (SellerSprite, Sorftime, Xiyou, Keepa, Helium 10, FastMoss, Kalodata, Ahrefs, Semrush)? This decides which optional recipes get built | — |
| ~~OQ-G3~~ | **Answered v0.3:** level 3 = delegated approval through a PIN-file grant the user creates (B7.1) | Suggested first grant: `negate_keyword` for search terms with ≥40 clicks and 0 orders, ≤20 per day, one store, 14 days |
| ~~OQ-G4~~ | **RESOLVED v0.2:** email + SMS carrying a link to the approval URL. See B7 | — |
| ~~OQ-G5~~ | **RESOLVED v1.0:** simulated only. No live Rufus automation; AMZ-03b not built | — |
| ~~OQ-G6~~ | **RESOLVED v0.4:** primary is the eCanAI proxy with `gpt-6-luna`; the fallback is **OpenAI** (B3.7) | — |
| ~~OQ-G6b~~ | **RESOLVED v0.8:** Manager → `gpt-6.1-sol`; general web interaction → `gpt-6-luna`; exploratory work may escalate to `gpt-6.1-terra` (B3.7). The OpenAI key must still live in eCan's key store, and the old hardcoded key must be rotated (B1) | — |
| OQ-G6c | Confirm the exact model id strings on the eCanAI proxy and on the direct OpenAI provider, and whether `gpt-6-luna` accepts images (the `vision` role). Default: ids as written; if luna has no vision, `vision` maps to `explore` | Implementation check, not a design choice |
| OQ-G7 | Which stores, marketplaces and categories are in scope for the MVP? | **Partly answered (B8):** Amazon US (1 seller store + 1 shopper research profile), Shopify ×2, Etsy ×1, eBay ×1, TikTok Shop (v0.4: active, no profile registered yet). Still open: product categories (needed for `policy_pack`) |
| ~~OQ-G8~~ | **RESOLVED v0.9:** depends on the language the user selects for the store: `StoreProfile.languages.owner` for owner-facing text, `.customer` for buyer-facing text; replies match the buyer's language | — |
| ~~OQ-G25~~ | **RESOLVED v0.6:** eCan chat now. WhatsApp + WeChat later through channel adapters (`ChatMessage`, D9) | — |
| ~~OQ-G26~~ | **RESOLVED v0.6:** yes for low/medium risk; high risk via portal + PIN | — |
| ~~OQ-G27~~ | **RESOLVED v0.6:** starts at 20% and 2 per store; the owner changes them in chat (B9.8) | — |
| ~~OQ-G28~~ | **RESOLVED v0.6:** no tuning grant at launch | — |
| ~~OQ-G29~~ | **RESOLVED v0.6:** that definition, with AI cost as its own line; COGS comes from the store owner (B9.10) | — |
| ~~OQ-G30~~ | **RESOLVED v0.7:** off | — |
| ~~OQ-G31~~ | **RESOLVED v0.7:** pro rata by gross sales | — |
| ~~OQ-G32~~ | **RESOLVED v0.7:** single owner in v1 | — |
| ~~OQ-G33~~ | **RESOLVED v0.7:** local-first; the cloud holds approvals/input, delivery, and opt-in report upload only (B9.10) | — |
| OQ-G9 | Definitions behind the HR KPIs (design CTR ≥0.2%, "video view rate") if they are to be reused for agent scorecards | Otherwise MGR-03 uses only the D6 metrics |
| ~~OQ-G10~~ | **RESOLVED v0.9:** both. Local SQLite `ec_data.db` (records) + Parquet/DuckDB (report tables) is the source of truth; optional cloud `backup` (encrypted snapshot) or `sync` (summary mirror) per tenant (B9.10) | — |
| ~~OQ-G11~~ | **RESOLVED v0.9:** not for the reference deployment (one entity); other sellers may have several, so stores carry `legal_entity_id` (B9.10) | — |
| ~~OQ-G12~~ | **RESOLVED v0.9:** JSON source of truth + generated Markdown view; edits via Manager chat → ChangeProposal; no GUI form in v1 (D3) | — |
| ~~OQ-G13~~ | **RESOLVED v0.3:** eCan cloud (B7) | — |
| ~~OQ-G14~~ | **RESOLVED v0.3:** AWS SES + AWS SNS (B7). Setup: verify the SES domain and leave the sandbox; register an SNS origination identity for US SMS | — |
| ~~OQ-G15~~ | **RESOLVED v0.3:** no. DOM and the page's own exports only (B6.2) | — |
| ~~OQ-G16~~ | **RESOLVED v0.3:** the approver is the user only. Delegation works through a user-granted PIN file (B7.1) | — |
| ~~OQ-G17~~ | **RESOLVED v0.3:** existing skills on <BUILD_HOST> are surveyed and adopted (B8). Build priority is in B6.3. Seller Central runs in English | — |
| OQ-G18 | **DEFERRED v1.0 (owner):** the B7.1 never-delegated list (held buyer replies, Reddit/creator DMs, post_publish, appeal_submit, price_change, refunds/returns/compensation/case responses, high-risk actions, no-touch profiles, platform-mandated personal actions) ships as the default. The owner edits it later in config; agents cannot change it | Not blocking |
| ~~OQ-G19~~ | **RESOLVED v0.4:** all five platforms are active but selling poorly, so the roadmap is growth-first (E1) | — |
| ~~OQ-G20~~ | **RESOLVED v0.4:** yes. EBY-01…03, ETS-01…02 (C8, C9) | — |
| ~~OQ-G21~~ | **RESOLVED v0.4:** build on <BUILD_HOST> once the doc is final | — |
| OQ-G22 | **Monthly ad budget per store/platform**, and whether break-even data is available (COGS, shipping, fees per SKU) | Sets the Google Ads tier (A10), the caps, and break-even ROAS. Without COGS, X-03 uses a margin estimate you provide |
| OQ-G23 | **What each store sells:** categories, SKU count, price band, fulfillment (own stock / dropship / POD / FBA) | Seeds `policy_pack`, feed category mapping, listing rules and benchmarks |
| ~~OQ-G24~~ | **RESOLVED v0.9:** the agent sends replies itself; it holds only replies it is not confident about, or money-in-dispute replies not clearly covered by policy (X-13 `BuyerReplyPolicy`) | — |
| OQ-D4 | **Google Ads / Merchant Center state per Shopify store:** account exists? linked to Merchant Center? Google & YouTube app installed? any suspension or disapprovals? conversion tracking set up? | Decides whether P1 starts with readiness fixes or with campaign planning |
| OQ-D5 | **Google browser profile(s):** which Google account(s) own Ads, Merchant Center, GA4 and GSC for each store? One profile per store, or one shared? | New profiles must be created and signed in by you (B8.3 rules) |
| OQ-T5 | **TikTok Shop:** region, seller center URL, and a signed-in profile to register | TTS-01 needs it in P2 |
| OQ-E2 | **eBay:** store subscription level (Terapeak access) and whether Promoted Listings has been used | EBY-01/02 data |
| OQ-ET2 | **Etsy:** is Offsite Ads on, and is the shop over the $10k/yr mandatory threshold? | ETS-02 economics |
| OQ-I1 | **Implementation (B9.10 storage, E1.1 1.2):** DuckDB and pyarrow are not in the app's environment. **Decision:** `ec_store` uses SQLite only (`ec_data.db` per tenant) for both KB records and report tables, behind the same interface; Parquet/DuckDB can replace the table half later without changing callers | Built 2026-11-09 |
| OQ-I2 | **Implementation (B5.2 `ec_rules_eval`):** rule tables are JSON data (`rulesets/gads_v1.json`, `tracking_v1`, `feed_v1`, `readiness_v1`) run by a sandboxed expression evaluator; thresholds are `t.<name>` resolved through `ec_kb_resolve`. **Decision:** audits (DTC-10/09, the DTC-03 readiness gate) are rulesets over facts that code computes, so only arithmetic is code | Built 2026-11-09 |
| OQ-I3 | **Implementation (B7, D9):** existing MCP tools already cover delivery and dispatch (`send_email`, `send_sms`, `send_chat`, `launch_agent_task`, `run_skill_for_store`, `schedule_agent_task`, `get_task_progress`, `find_skill`). **Decision (owner, 2026-11-09):** the Manager and approvals are a skill + prompt over those tools; in-chat approval (`ec_actions op=decide`, quoting the owner's words, high risk refused) comes first, the signed-link portal later | Built 2026-11-09 |
| OQ-I4 | **Implementation (B5.2):** the first tools are grouped by operation instead of one tool per row of B5.2: `ec_kb` (get/list/put/resolve/thresholds), `ec_report_ingest` (detect + normalize + store), `ec_table_query`, `ec_unit_economics`, `ec_rules_eval`, `ec_actions`, `ec_bulk_file_build`, `ec_schemas_get` | Built 2026-11-09 |

**Platform-specific open questions (also referenced inline):**
- **Amazon:**
  - OQ-A1: description length unit (characters or words).
  - OQ-A2: "affordable" in titles.
  - OQ-A3: high/low ACOS and contribution definitions.
  - OQ-A4: legacy campaign names that don't follow B3.6.
  - OQ-A5: selection weights.
  - OQ-A6: DeepL for localization.
  - OQ-A7: Rufus question allocation.
  - OQ-A8: launch budget split by layer.
  - OQ-A9: negation level.
  - OQ-A10: dayparting execution tool.
  - OQ-A11: Xiyou access.
  - OQ-A12: SKU tier definitions.
- **TikTok Shop:**
  - OQ-T1: GMV Max compensation rule.
  - ~~OQ-T2~~: resolved v0.2 (browser exports).
  - OQ-T3: CPM currency.
  - OQ-T4: creator scoring weights.
- **DTC:**
  - OQ-D1: Meta thresholds.
  - OQ-D2: Google Ads API.
  - OQ-D3: Ahrefs/Semrush.
- **Cross-platform:**
  - OQ-X1: export variants.
  - OQ-X2: policy-pack scope.
  - OQ-X3: fee tables.
  - OQ-X4: review source.
  - OQ-X5: competitor data source.
  - OQ-X6: browser profiles.
  - ~~OQ-X7~~: resolved v0.2 (browser).
  - OQ-X8: GTM targets.
- **Creative:**
  - OQ-C1: image-generation provider.
  - OQ-C2: Photoshop automation.
- **Walmart:**
  - OQ-W1: Walmart thresholds and API.

## E3. Known risks

1. **Course-outline sources.** Most DTC, Meta, Google and Walmart rules are `[INF]` defaults. Plan a calibration month in which recommendations are compared against operator judgment before they are trusted.
2. **Browser fragility.** With browser-only data (v0.2) this is now the top operational risk. Seller Central, Ads, TikTok and Rufus UIs change often. Mitigations:
   - A versioned registry, with `assert` steps in every recipe.
   - The daily `browser_registry_health` dry run.
   - T3 fallback plus X-12 patch proposals.
   - Failures return `blocked.layout_changed`, never a guessed result.
   - Session expiry and 2FA need a human (`ec_input_request`), so expect occasional morning taps on the phone.
3. **Attribution mismatch.** Amazon (7/14-day windows), TikTok (GMV Max includes organic) and Meta (view-through) are never summed. Each digest section labels its attribution basis.
4. **Over-automation.** The corpus brochures promise "fully automatic tuning". This design deliberately keeps a human in the loop until scorecards justify more autonomy.
5. **Server and gateway dependencies (v0.3).** The current skills cannot run while the eCanAI proxy returns empty answers. The approval push needs intl subscriptions that don't exist yet. Configure a fallback LLM provider and the polling fallback early.
6. **Stale reference data.** The keyword data is from 2019 and the fee and FX data from 2017. Skills must not use them except as schema examples.

## E4. Review log

| Round | Date | Reviewer feedback | Changes |
|---|---|---|---|
| v0.1 | 2026-11-09 | — (initial draft) | — |
| v0.2 | 2026-11-09 | OQ-G4: approvals by email + SMS with a link to an approval URL. OQ-G2: data comes in through the browser; some acquisition can be tools that run JS | New B6 (browser acquisition: T1 recipes / T2 JS extractors / T3 agent fallback, registry shapes, initial catalog of about 30 recipes, sessions and safety) and B7 (approval and input portal, ApprovalRequest/InputRequest shapes, security). New tools: `ec_input_request`, `ec_session_check`, `ec_browser_recipe_run`, `ec_js_extract`, `ec_download_watch`, `ec_registry`. Rewrote X-08 and X-09, updated X-10, added X-12 (recipe maintainer). StoreProfile now has notify email/SMS and per-site browser profiles. Swapped API mentions in AMZ-01/10, X-04/05, TTS-01, DTC-03/05/07 and WMT-01 for recipes. Added the `browser_registry_health` playbook and session checks in the Manager flow. Updated the P0 exit criteria. New OQ-G13–G17 |
| v0.3 | 2026-11-09 | OQ-G13: eCan cloud. OQ-G14: SES + SNS. OQ-G15: no fetch. OQ-G16: the user approves, or delegates by letting the Manager read a PIN file. OQ-G17: existing skills on <BUILD_HOST> (shared `.claude` and `eCan.ai`) | Added B8, a survey of the 6 built skills, report code, profiles and conventions, with the EX-01…06 adapters and the `StoreDailyCheck` mapping. Added B7.1 delegated approval (`DelegationGrant`, `ec_delegate_approve`, never-delegated list). B3.4 level 3 is now delegation, and platform-mandated personal actions are never automated. B6 now forbids fetch, adds Shopify/Etsy/eBay extractors and a build priority. AMZ-11 moved to P1, and the ads skills depend on OQ-G19. E1 now lists the blocking server dependencies. Added eBay/Etsy to the enums and the `stores_daily_check` playbook. New OQ-G18–G21 |
| v0.4 | 2026-11-09 | Add a Google Ads skill: Shopify sales depend on Google Ads. OQ-G20 yes. OQ-G21 yes, build on <BUILD_HOST> once the doc is final. OQ-G6: fallback is OpenAI. OQ-G19: all five platforms are active but selling poorly | Expanded DTC-03 (readiness gate, tiers, bidding ladder, daily/weekly rules, launch pack). New DTC-09 (Merchant Center feed), DTC-10 (tracking audit), DTC-11 (Shopify product optimizer). New EBY-01/02/03 and ETS-01/02. New X-13 (buyer messages) and X-14 (growth diagnosis). New playbooks A10 (Shopify + Google), A11 (eBay), A12 (Etsy), all marked `[INF]`. New canonical tables and recipes for Google/GMC/Shopify/eBay/Etsy, plus write recipes. Growth-first roadmap; C1 rebuilt (51 skills). New playbooks: growth weekly, Shopify-Google daily/weekly, messages SLA, listing sprint. OpenAI fallback in B3.7. New OQ-G6b, G22–G24, D4, D5, T5, E2, ET2 |
| v0.5 | 2026-11-09 | Design skills to be shop- and product-agnostic, able to explore, learn and self-correct toward making money. The Manager designs experiments for operator agents, adjusts itself and others, and is a chat agent that finds out what the user needs and acts on it | Added B9: agnostic rules, capability skills + platform packs (56 behaviours → about 24 capability skills), knowledge layering with an immutable core, onboarding, the Goal + profit ledger objective, the learning loop (Hypothesis / ExperimentDesign / Learning), the self-adjustment pipeline (ChangeProposal: offline eval → shadow → canary → approval → auto-rollback), the exploration budget, and new tools. New X-15 onboarding, X-16 profit ledger, X-17 generic daily check, MGR-04 experiment designer, MGR-05 change manager; MGR-02 moved to P1. Added D9 (chat agent: per-turn loop, ChatIntent, UserInstruction, prompt, curated tools, proactive messages, memory, acceptance) and D10 (learning duties). Payout recipes added for the ledger. Principles P13/P14. Runtime-tagged OQs. New OQ-G25–G29 |
| v0.6 | 2026-11-09 | G25: eCan chat now, WhatsApp/WeChat later. G26: yes. G27: start at 20% / 2, adjustable. G28: no to start. G29: yes, other includes token cost; product costs are filled in by the store owner, and this is a product for all sellers | Added B9.10 (multi-tenant design: Tenant shape, isolation, no owner-specific defaults, COGS input paths + coverage rule, AI cost as a business cost with allocation, onboarding for any seller, opt-in cross-seller learning). Ledger gets `ai_cost` + `cogs_coverage`. Goal constraints gain owner-adjustable exploration settings. In-chat approval cards for low/medium risk. Channel-agnostic `ChatMessage`. B8 relabelled as the reference deployment. New OQ-G30–G33 |
| v0.7 | 2026-11-09 | G30 off, G31 pro rata, G32 single owner, G33 local-first | Tenant shape fixed: single owner, cross-tenant learning off, `data_location: local_first`. Added the local vs cloud data split, offline behaviour, and backup via `ec_kb_export`/`ec_kb_import`. Pro-rata AI-cost allocation with a zero-sales floor. Layer-7 priors are shipped defaults only |
| v0.8 | 2026-11-09 | G6b: Manager uses 6.1 sol; general web interaction uses gpt-6-luna; exploratory work can escalate to gpt-6.1 terra | B3.7 model tiers (`manager` / `web` / `explore`) and the `ModelPolicy` shape. Defined exploratory mode, escalation triggers, caps and the once-only rule, OpenAI fallback with the same model id, and escalation logging and costing. D10 learns from escalations. Updated B4, B8.3, the D-section routing line and OQ-G6b; new OQ-G6c (id strings and luna vision check) |
| v0.9 | 2026-11-09 | G8: depends on the user's language selection on the store. G10: recommend; both local and cloud. G11: not separate entities here, but other customers may be. G12: your call. G24: no per-message approval; only for replies the agent isn't confident about, or money in a dispute it isn't sure of | `StoreProfile.languages` + `legal_entity_id`; Tenant `cloud_data` + `legal_entities`; storage engines (SQLite `ec_data.db` + Parquet/DuckDB, `ec_store` interface, backup/sync modes, `ec_store_snapshot`, `ec_cloud_mirror`); legal-entity rules; JSON playbooks + generated md view; X-13 auto-send policy (`BuyerReplyPolicy`, verifier confidence, hold rules, money action separate, caps and audit); B3.4 and B7.1 updated; OQ-G18 text updated |
| v1.0 | 2026-11-09 | G1: default yes. G5: simulated only. G18: I'll edit this later | **Frozen for build.** OQ-G1 and OQ-G5 resolved (AMZ-03b and live Rufus not built); OQ-G18 deferred to the owner, the default list ships and only the owner can change it. Added E1.1 build-start checklist (step 0 prerequisites, ordered P0 build with done-when checks, change control). Fixed E3 numbering |
| v1.1 | | | |
