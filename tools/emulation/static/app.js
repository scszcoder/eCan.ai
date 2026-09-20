/*
 * Feige (飞鸽) emulation — front-end only.
 *
 * The DOM shape below intentionally matches the real Feige page so that the
 * browser-automation node's event-monitor + MCP tool selectors work unchanged:
 *
 *   chat list (2026-06-02 Feige redesign — old hashed classes RETIRED):
 *     .scroller > .scroller_content > .list_items   new scroll/list container
 *                                        (monitor cdpFilterExpr root = .list_items;
 *                                         #chantListScrollArea kept as outer scroller
 *                                         for the emulation's own scroll handling)
 *     [data-qa-id="qa-conversation-chat-item"]   each chat row (STABLE — kept)
 *     .conversationCard-ePRNJi            chat card
 *     .nameLine-Q8PQwE  (title attr)      customer name wrapper
 *     [class*="NameContent"]              customer name text (newNameContent-*)
 *     [class*="msgContent"]               last message
 *     [class*="timerParticular"]          timestamp / wait-timer
 *     [class*="badge-count"] (auxo <sup>) unread badge
 *     [class*="newAvatar"] img            avatar
 *     [class*="userLabel"] span           inline tags (e.g. 重复来访)
 *   (was: #chantListScrollArea / .MP1bk.../.Jv6Ft.../.lF_M7Qi.../.CEnLM8.../.rxAva.../.obeJr...)
 *
 *   chat thread:
 *     [data-qa-id="qa-message-warpper"]   each message wrapper  (note: typo in real DOM)
 *     .tC9ap6QtAyeCD0jfuMns               wrapper inner
 *     .iD7SHBvMhm4OhfCsBGr1               bubble; adds .messageIsMe (agent) or .messageNotMe (customer)
 *     .O4UWWFoQxgMq4AWHMq25               message timestamp
 *     .BqNO6cexAGBsZgUmEzIE               system notification (e.g. 会话关闭)
 *     .e0Bi5IauHWvUG8773oi9               system assign ("客服…接入")
 *     .rcHPT4n3TlQD0Nu4sSiv               time-only divider inside a system wrapper
 *
 *   compose:
 *     textarea[data-qa-id="qa-send-message-textarea"]
 *     [data-qa-id="qa-send-message-button"]
 */

(() => {
  "use strict";

  // ────────────────────────────────── constants ──────────────────────────────
  const AVATAR = {
    A: "https://p3.douyinpic.com/aweme/100x100/aweme-avatar/mosaic-legacy_3791_5070639578.jpeg?from=4010531038",
    B: "/static/avatars/B.svg",
    C: "/static/avatars/C.svg",
    shop: "https://p3-pigeon-sign.ecombdimg.com/tos-cn-i-6vegkygxbk/fee5145c3d8f4d45aca50527339a0247~tplv-jxcbcipi3j-image-limit.image?lk3s=6c886902&x-expires=1780031606&x-signature=Meeqyo2zIRYLt7Ig98tNku57ph4%3D",
  };
  // Random customer prompts. Tuned to overlap the three KB docs ingested
  // into LightRAG (test_docs/products.md, logistics.md, policy.md) so the
  // RAG-gated chatbot has a fighting chance of producing a confidently
  // grounded answer. A few generic greetings/chitchat lines are kept so
  // we still exercise the "no-RAG-needed" path of the skill.
  const QUESTION_POOL = [
    // —— greetings / chitchat (bot should NOT call RAG) ————————————
    "你好在吗？",
    "在吗在吗？",
    "能不能便宜点？",
    "有优惠券吗？",
    "有实物图吗？",
    // —— 尺码 / 商品 (products.md) ————————————————————————————
    "男装L码的胸围是多少？",
    "男装XL码适合多高？",
    "女装M码适合多高的人？",
    "女装L码胸围范围？",
    "男士32码裤子腰围多少厘米？",
    "女士牛仔裤27码腰围是多少？",
    "童装120码适合几岁的小孩？",
    "童装150码身高多少？",
    "男鞋42码脚长多少？",
    "男鞋42码对应美国码是多少？",
    "女鞋38码脚长是多少？",
    "婴儿66码是多大月龄？",
    "弹力面料应该怎么选码？",
    "胸围怎么量？",
    "腰围怎么测量？",
    // —— 物流 / 配送 (logistics.md) ————————————————————————————
    "包邮门槛是多少？",
    "新疆发货要加多少运费？",
    "港澳台运费怎么算？",
    "你们默认走什么快递？",
    "顺丰特快国内多久能到？",
    "DHL寄到欧洲多久能到？",
    "现货商品多久发货？",
    "几点之前下单能当天发货？",
    "双11大促发货要多久？",
    "国际EMS到北美几天？",
    "偏远地区用什么快递？",
    "丢件了怎么处理？",
    "国际订单清关延误怎么办？",
    // —— 售后 / 退换 (policy.md) ————————————————————————————
    "几天内可以无理由退货？",
    "质量问题可以退多久？",
    "买了一年了出质量问题还能保修吗？",
    "退款一般几天到账？",
    "生鲜出问题多久内联系客服？",
    "客服几点上班？",
    "定制商品可以退吗？",
    "怎么申请售后？",
    "签收后发现破损怎么办？",
    "拆封过的化妆品能退吗？",
  ];

  // ─── image-test pools (drives the three "图文模式" buttons) ─────────────
  // Two flavours of sample image, both served by the emulation server
  // itself (no external network dependency):
  //   * /sample0.png             — a real PNG captured from the live
  //                                Feige site (dropped beside server.py
  //                                by the operator).  This is the most
  //                                authentic end-to-end test case.
  //   * /sample-product/1..3.png — programmatically-generated two-tone
  //                                PNGs (red / blue / green) kept around
  //                                for click-to-click visual variety.
  // `sample0.png` is listed twice so, on average, ~half of test clicks
  // use the real photo and the other half rotate through the synthetic
  // colours — catching both authentic and edge-case payloads.
  // Debug override: pin every image-test click to the real captured photo
  // so the multimodal pipeline is exercised against an authentic payload
  // every single time.  Restore the multi-entry pool (with the synthetic
  // /sample-product/{1,2,3}.png variants) once the end-to-end path is
  // verified — the variety catches edge cases the real photo can't.
  const SAMPLE_IMAGE_URLS = [
    "/sample0.png",
  ];
  // Single-shot prompts (used by mode 1 + 2: one self-contained text
  // sibling alongside the image).
  const IMG_TEXT_FULL_POOL = [
    "我想要这款，多少钱？",
    "请问这件还有库存吗？",
    "这个款式有别的颜色吗？",
    "这款适合多大孩子穿？",
    "这件能今天发货吗？",
  ];
  // Two-part prompts for mode 3 — split at a natural mid-sentence break
  // so the prefix is meaningless without the suffix (and the image in
  // between).  This is the regression-test ammunition for the
  // "interleaved attachments" edge case: the dispatch trigger fires on
  // the LAST text bubble, but the image lives in the bubble before it.
  const IMG_TEXT_SPLIT_POOL = [
    ["我想要", "这款，多少钱？"],
    ["请问这件", "还有库存吗？"],
    ["这个", "有别的颜色吗？"],
    ["这款适合", "多大的小孩穿？"],
  ];

  // ─── product-card-test pool (drives the "商品卡片" buttons) ─────────────
  // When a customer pastes a Douyin product URL in real Feige, the
  // platform replaces the URL with a "来自电商小助手的推荐" card.  The
  // scraper (dom_assets.FEIGE_LATEST_CUSTOMER_BUBBLE_JS, _cardData)
  // detects these bubbles by the ``.chatd-card`` element and the
  // ``data-id="..._template"`` marker, then extracts title / price /
  // image / coupons / shipping into a structured ``product_cards``
  // field and synthesises a text-only ``[商品卡片] <title> ￥<price>``
  // representation for the downstream text-driven Q&A pipeline.
  // This pool is the corresponding test fixture set — each entry is
  // injected as a real card-shaped DOM via customerSendProductCard().
  // Reuses the /sample-product/{1,2,3}.png endpoints served by
  // server.py for the thumbnail.
  const SAMPLE_PRODUCT_CARDS = [
    {
      title: "男童短袖球服套装运动服女童青少年速干衣透气短裤中大童童装休闲",
      price_inter: "59",
      price_decimal: ".90",
      image_url: "/sample-product/1.png",
      coupons: ["满50减10"],
      shipping: "现在付款，明天发货",
    },
    {
      title: "女童加绒套装2025新款中大童帅气儿童冬装加厚洋气女孩牛仔两件套",
      price_inter: "89",
      price_decimal: ".00",
      image_url: "/sample-product/2.png",
      coupons: ["满100减20"],
      shipping: "现货发出",
    },
    {
      title: "NASA2025秋季中大童儿童装T恤卡通战斗机印花纯棉假两件长袖上衣",
      price_inter: "45",
      price_decimal: ".50",
      image_url: "/sample-product/3.png",
      coupons: [],
      shipping: "今日付款今日发货",
    },
  ];
  // Question texts to pair with a card (modes 1/2/3 below).
  const PRODUCT_CARD_TEXT_FULL_POOL = [
    "这款商品尺码准吗",
    "这件能今天发货吗",
    "我家小孩穿能合身吗",
    "材质透气吗",
    "现在下单还有优惠吗",
  ];
  // Split prompts for mode 3 (text → card → text), mirrors
  // IMG_TEXT_SPLIT_POOL — the dispatch trigger fires on the LAST text
  // bubble, but the card lives in the bubble before it.  Tests whether
  // the multi-bubble burst walk-back correctly captures the card.
  const PRODUCT_CARD_TEXT_SPLIT_POOL = [
    ["我看上了", "这款，能再便宜点吗"],
    ["这件", "适合8岁小朋友穿吗"],
    ["这款", "几天能到货"],
    ["这个", "尺码偏大还是偏小"],
  ];
  const GREETING_REPLY = "亲亲，在哒~很高兴为您服务，请问有什么可以帮您？";
  const HUMAN_WELCOME = "您好，现在是人工客服为您服务。为了更高效地帮您解决问题，我先查阅一下您和智能客服的对话记录，请您稍等片刻～";
  const SHOP_NAME = "钛斯特的小店";
  const HISTORICAL_CUSTOMER_MESSAGES = [
    "这件还有黑色吗？",
    "我平时穿M码，这款怎么选？",
    "麻烦帮我看下物流。",
    "今天下单什么时候发？",
    "收到后不合适可以换吗？",
    "这款面料会缩水吗？",
    "能不能发顺丰？",
    "尺码偏大还是偏小？",
  ];
  const HISTORICAL_AGENT_MESSAGES = [
    "亲，这款目前还有库存的。",
    "建议您按平时尺码选择，喜欢宽松可以大一码。",
    "我这边帮您核实一下物流进度。",
    "现货商品一般会尽快安排发出。",
    "不影响二次销售的情况下可以按售后流程处理。",
    "不同批次会有轻微差异，以实物为准哦。",
    "默认快递会根据仓库和地址自动匹配。",
    "您也可以把身高体重发我，我帮您参考。",
  ];
  const HISTORICAL_SYSTEM_MESSAGES = [
    "客服钛斯特的小店接入",
    "系统提醒：该订单存在售后记录",
    "平台提醒：请及时回复消费者消息",
    "昨天 15:36",
    "当前会话已长时间未回复，若后续仍未回复，平台可能主动介入处理。",
  ];
  const OVERDUE_MS = 3 * 60 * 1000;

  // ────────────────────────────────── state ──────────────────────────────────
  const customers = {
    A: newCustomer("A", "客户A", AVATAR.A),
    B: newCustomer("B", "客户B", AVATAR.B),
    C: newCustomer("C", "客户C", AVATAR.C),
  };

  // ─── Multi-tab state sync (2026-05-20) ──────────────────────────────────
  // Real Feige pushes state changes to all open tabs via WebSocket.  This
  // emulation is purely client-side so by default each browser tab gets an
  // independent in-memory state — breaks any test of eCan's multi-tab
  // typing/monitor split.
  //
  // We add a tiny cross-tab sync layer:
  //   * `localStorage[STORAGE_KEY]` holds the serialised `customers` dict
  //     (the only shared state — the rest is per-tab UI).
  //   * `BroadcastChannel(BC_NAME)` is the change-notification channel.
  //   * Mutations call `multiTabSync.scheduleSave()` (debounced ~50ms);
  //     other tabs receive the broadcast, reload from storage, re-render.
  //
  // What is shared:
  //   - `customers` dict (sidebar list, dialogs, lastMsg, unreadCount, …)
  // What stays per-tab (intentional, mirrors real Feige):
  //   - `state.activeCustomer` (which chat each tab is focused on)
  //   - `state.activeTab`, `settingsOpen`, `collapsedSections`, ...
  //   - `chaosConfig` (per-tab so we can A/B-test fault modes)
  const multiTabSync = (function () {
    const STORAGE_KEY = "feige_emu_state_v1";
    const BC_NAME = "feige_emu_v1";
    const SAVE_DEBOUNCE_MS = 50;
    const TAB_ID = Math.random().toString(36).slice(2, 8);

    let _bc = null;
    let _saveTimer = null;
    let _enabled = false;
    // Set to true while applying an incoming broadcast so the same change
    // doesn't echo back out via scheduleSave().
    let _applyingRemote = false;

    function _safeSerialise() {
      // Plain JSON of customers.  All fields are JSON-safe (no functions,
      // no Date objects — timestamps are stored as numbers).
      try {
        return JSON.stringify({
          v: 1,
          tab_id: TAB_ID,
          ts: Date.now(),
          customers: customers,
        });
      } catch (e) {
        flog("multitab.serialise_failed", { err: String(e) });
        return null;
      }
    }

    function _applyLoaded(parsed) {
      if (!parsed || typeof parsed.customers !== "object") return false;
      // ─── MERGE (not replace) — 2026-05-20 data-loss fix ────────────
      // The original code blew away the local customers dict and copied
      // the parsed snapshot wholesale.  Under concurrent multi-tab writes
      // (6 typing tabs each appending agent messages within 50ms of one
      // another) this is "last writer wins": tab A appends msg₁, tab B
      // appends msg₂, tab B's broadcast arrives at tab A first and wipes
      // msg₁ from tab A's local state — when tab A's own debounced save
      // fires the persisted state has msg₂ but lost msg₁.  Observed in
      // the 2026-05-20 20:30 flood: 9 of 20 customers had their real
      // reply silently dropped this way.
      //
      // Fix: merge per-message by id (pushMessage already assigns one
      // via uid()).  We never delete a local message — only adopt new
      // ones from the remote snapshot.  Convergent: any message written
      // by any tab eventually shows up in every tab.
      const remoteCusts = parsed.customers || {};
      for (const k in remoteCusts) {
        if (!Object.prototype.hasOwnProperty.call(remoteCusts, k)) continue;
        const remote = remoteCusts[k];
        const local = customers[k];
        if (!local) {
          customers[k] = remote;
          continue;
        }
        // Adopt scalar/header fields where remote is newer
        if (typeof remote.lastMsgAt === "number" &&
            (typeof local.lastMsgAt !== "number" || remote.lastMsgAt > local.lastMsgAt)) {
          local.lastMsg = remote.lastMsg;
          local.lastMsgAt = remote.lastMsgAt;
          local.lastMsgRole = remote.lastMsgRole;
        }
        if (typeof remote.unreadCount === "number" && remote.unreadCount > (local.unreadCount || 0)) {
          local.unreadCount = remote.unreadCount;
          local.firstUnreadAt = remote.firstUnreadAt;
        }
        if (typeof remote.seq === "number" && remote.seq > (local.seq || 0)) {
          local.seq = remote.seq;
        }
        // Merge dialogs by index, then messages by id within each
        const remoteDialogs = Array.isArray(remote.dialogs) ? remote.dialogs : [];
        if (!Array.isArray(local.dialogs)) local.dialogs = [];
        for (let di = 0; di < remoteDialogs.length; di++) {
          const rd = remoteDialogs[di];
          let ld = local.dialogs[di];
          if (!ld) {
            local.dialogs[di] = rd;
            continue;
          }
          if (!Array.isArray(ld.messages)) ld.messages = [];
          const localMsgIds = new Set();
          ld.messages.forEach(function(m){ if (m && m.id) localMsgIds.add(m.id); });
          const remoteMsgs = Array.isArray(rd.messages) ? rd.messages : [];
          for (let mi = 0; mi < remoteMsgs.length; mi++) {
            const rm = remoteMsgs[mi];
            if (!rm || !rm.id || localMsgIds.has(rm.id)) continue;
            ld.messages.push(rm);
          }
          // Re-sort by ts so render order is consistent across tabs
          ld.messages.sort(function(a, b){ return (a.ts || 0) - (b.ts || 0); });
        }
      }
      return true;
    }

    function loadFromStorage() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return false;
        const parsed = JSON.parse(raw);
        const ok = _applyLoaded(parsed);
        if (ok) {
          flog("multitab.loaded", {
            tab_id: TAB_ID,
            from_tab: parsed.tab_id,
            customer_count: Object.keys(customers).length,
            age_ms: Date.now() - (parsed.ts || 0),
          });
        }
        return ok;
      } catch (e) {
        flog("multitab.load_failed", { err: String(e) });
        return false;
      }
    }

    function _writeAndBroadcast(reason) {
      // 2026-05-20 read-modify-write fix:
      // The original code blindly serialised our local customers and
      // overwrote localStorage.  Under concurrent multi-tab writes that
      // overwrite loses peer tabs' updates whose broadcasts hadn't
      // reached us yet (BroadcastChannel ordering is not synchronous).
      // Symptoms in the 2026-05-20 22:36 flood: 客户15's real reply
      // was typed in a pool tab, broadcasted, but a later save from
      // another tab overwrote localStorage and the reply was lost.
      //
      // Fix: before writing, RE-LOAD the current localStorage and merge
      // it into our local customers via _applyLoaded (preserves
      // anything peers have written that we haven't seen yet).  Then
      // serialise + write.  This converges even when broadcasts arrive
      // late.
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          // _applyLoaded is the same merge function used by the
          // broadcast handler — preserves local messages, adopts any
          // peer messages we haven't seen yet.
          _applyLoaded(parsed);
        }
      } catch (e) {
        // non-fatal — if the load/merge fails we still write what we
        // have; that's the legacy behaviour.
        flog("multitab.preload_merge_failed", { err: String(e) });
      }
      const data = _safeSerialise();
      if (data == null) return;
      try {
        localStorage.setItem(STORAGE_KEY, data);
      } catch (e) {
        flog("multitab.write_failed", { err: String(e) });
        return;
      }
      try {
        if (_bc) {
          _bc.postMessage({ type: "state_changed", tab_id: TAB_ID, reason: reason });
        }
      } catch (e) {
        flog("multitab.broadcast_failed", { err: String(e) });
      }
    }

    function scheduleSave(reason) {
      if (!_enabled || _applyingRemote) return;
      if (_saveTimer) clearTimeout(_saveTimer);
      _saveTimer = setTimeout(() => {
        _saveTimer = null;
        _writeAndBroadcast(reason || "unspecified");
      }, SAVE_DEBOUNCE_MS);
    }

    function _onRemoteChange(ev) {
      if (!ev || !ev.data) return;
      if (ev.data.tab_id === TAB_ID) return; // ignore our own echo
      if (ev.data.type !== "state_changed") return;
      _applyingRemote = true;
      try {
        loadFromStorage();
        // Re-render — sidebar always; thread only if our active customer's
        // data may have changed.  Cheap to always re-render thread too.
        if (typeof renderChatList === "function") renderChatList();
        if (typeof renderThread === "function") renderThread();
        flog("multitab.applied_remote", {
          tab_id: TAB_ID,
          from_tab: ev.data.tab_id,
          reason: ev.data.reason || "",
        });
      } finally {
        _applyingRemote = false;
      }
    }

    function bootstrap() {
      _enabled = true;
      // 1. Adopt existing shared state if any tab wrote it first.
      const loaded = loadFromStorage();
      // 2. Subscribe to other tabs' changes.
      try {
        if (typeof BroadcastChannel === "function") {
          _bc = new BroadcastChannel(BC_NAME);
          _bc.onmessage = _onRemoteChange;
        } else {
          flog("multitab.no_broadcast_channel", { tab_id: TAB_ID });
        }
      } catch (e) {
        flog("multitab.bc_init_failed", { err: String(e) });
      }
      // 3. If we are the first tab (no storage), persist defaults so the
      //    next tab can pick them up.
      if (!loaded) {
        _writeAndBroadcast("first_tab_initial_state");
      }
      flog("multitab.bootstrap", {
        tab_id: TAB_ID,
        loaded_from_storage: loaded,
        customer_count: Object.keys(customers).length,
      });
    }

    return {
      TAB_ID,
      bootstrap,
      scheduleSave,
      loadFromStorage,
    };
  })();

  const STRESS_DEFAULT_COUNT = 20;
  const STRESS_MAX_COUNT = 200;
  const STRESS_AVATARS = [AVATAR.A, AVATAR.B, AVATAR.C];
  const DEFAULT_CHAOS_CONFIG = {
    enabled: true,
    preset: "realistic_site",
    probability: 0.55,
    send: { blockClickMs: 1200, delayAgentAppendMs: 1800, neverAppendAgent: false },
    renderer: { stallEnabled: true, blockMs: 450, intervalMs: 1800, autoStopAfterMs: 180000 },
    dom: {
      selectorDelayMs: 12, extraMessageRows: 240, systemRows: 12, churnEnabled: true, churnIntervalMs: 1000,
      // ── load-dependent scrape stall (2026-06-03, mt070 blackout repro) ──
      // The real detection blackout: each feige_scrape_bubble Runtime.evaluate
      // on the shared main tab takes 5-28s under 6-customer load because the
      // scrape JS walks an O(DOM) thread that GROWS over the test. That long
      // synchronous eval holds V8's single main thread, so the co-located
      // sidebar detection poll's concurrent Runtime.evaluate queues behind it
      // and times out (6s) → consecutive recycle spiral → 100-184s blind.
      //
      // We reproduce it by busy-waiting inside the patched querySelector(All)
      // ONLY for scrape-signature selectors (the ones the eCan scraper uses,
      // which run in the page main world via Runtime.evaluate). The wait scales
      // with accumulated conversation volume + concurrent active customers, so
      // it starts cheap and crosses the 6s detection-timeout cliff after the
      // threads have grown — mirroring "fine for 8 min, then slows". Disabled
      // by default (no-op) so existing scenarios are unaffected.
      scrapeStall: {
        enabled: false,
        baseMs: 120,       // fixed floor per scrape evaluate
        perMsgMs: 20,      // × total messages across active conversations
        perConvoMs: 500,   // × customers active in the last 120s
        capMs: 30000,      // hard ceiling (matches worst real 28s scrape)
      },
    },
    focus: {
      churnEnabled: true,
      switchIntervalMs: 1500,
      switchProbability: 0.18,
      rerenderDuringSend: true,
      removeComposeDuringSend: false,
      removeComposeMs: 1200,
    },
    harness: {
      fakeRuntimeDelayMs: 7000,
      fakeRuntimeNeverResolve: false,
      cdpUseDelayMs: 7000,
      cdpUseNeverRespond: false,
      cdpUseLateResponseMs: 7000,
    },
  };
  const CHAOS_PRESETS = {
    off: {},
    realistic_site: {
      enabled: true,
      probability: 0.55,
      send: { blockClickMs: 1200, delayAgentAppendMs: 1800 },
      renderer: { stallEnabled: true, blockMs: 450, intervalMs: 1800, autoStopAfterMs: 180000 },
      dom: { selectorDelayMs: 12, extraMessageRows: 240, systemRows: 12, churnEnabled: true, churnIntervalMs: 1000 },
      focus: { churnEnabled: true, switchIntervalMs: 1500, switchProbability: 0.18, rerenderDuringSend: true },
      harness: { fakeRuntimeDelayMs: 7000, cdpUseDelayMs: 7000, cdpUseLateResponseMs: 7000 },
    },
    runtime_timeout: { enabled: true, send: { blockClickMs: 8000 } },
    slow_dom: { enabled: true, dom: { selectorDelayMs: 30, extraMessageRows: 500, systemRows: 30 } },
    renderer_stall: { enabled: true, renderer: { stallEnabled: true, blockMs: 1200, intervalMs: 1500, autoStopAfterMs: 60000 } },
    // mt070 detection-blackout repro: load-dependent scrape stall, a modest
    // baseline DOM that grows per turn, light renderer churn. Pair with a
    // ramped 6-customer flood (joinSpreadSec + followUpRounds) so threads
    // grow past the detection-timeout cliff ~8 min in.
    detection_blackout: {
      enabled: true,
      probability: 1.0,
      renderer: { stallEnabled: false },
      dom: {
        selectorDelayMs: 0, extraMessageRows: 30, systemRows: 6,
        churnEnabled: true, churnIntervalMs: 1500,
        scrapeStall: { enabled: true, baseMs: 120, perMsgMs: 20, perConvoMs: 500, capMs: 30000 },
      },
      focus: { churnEnabled: true, switchIntervalMs: 1500, switchProbability: 0.25, rerenderDuringSend: true },
      send: { blockClickMs: 0, delayAgentAppendMs: 800 },
    },
    focus_churn: { enabled: true, focus: { churnEnabled: true, switchIntervalMs: 800, switchProbability: 0.4, rerenderDuringSend: true } },
    full_flood: {
      enabled: true,
      probability: 0.75,
      send: { blockClickMs: 1200, delayAgentAppendMs: 2500 },
      renderer: { stallEnabled: true, blockMs: 700, intervalMs: 1800, autoStopAfterMs: 60000 },
      dom: { selectorDelayMs: 20, extraMessageRows: 400, systemRows: 30, churnEnabled: true, churnIntervalMs: 700 },
      focus: { churnEnabled: true, switchIntervalMs: 900, switchProbability: 0.25, rerenderDuringSend: true },
    },
  };

  let state = {
    activeTab: "current",
    activeCustomer: null,       // customer id currently open in middle panel
    settingsOpen: false,
    collapsedSections: new Set(["recentSearch", "starred", "todayNoOrder", "todayUnpaid"]),
    clearedCurrent: false,      // after "清除当前会话" button
  };
  let chaosConfig = cloneChaosConfig(DEFAULT_CHAOS_CONFIG);
  let rendererStallTimer = null;
  let rendererAutoStopTimer = null;
  let focusChurnTimer = null;
  let domChurnTimer = null;
  let chaosSaveTimer = null;
  let lastSelectorDelayLogAt = 0;
  let lastScrapeStallLogAt = 0;
  // One scrape-stall charge per synchronous Runtime.evaluate (reset on the
  // microtask after the current sync turn) so a single scrape that fires
  // several querySelectorAll calls is charged once, not N times.
  let _scrapeChargedThisTick = false;
  let _scrapeLoadCache = { at: 0, msgs: 0, convos: 0 };
  // >0 while the emulation page is running its OWN synchronous render (which
  // also queries scrape-signature selectors to wire the sidebar). The eCan
  // scraper runs as a separate CDP Runtime.evaluate task and can never
  // interleave with a synchronous render, so this flag cleanly excludes the
  // page's own queries from the scrape stall — only eCan's scrape pays it.
  let _pageRenderDepth = 0;
  // True only while a harness metrics run is active (set from the ~1/s command
  // poll). The scrapeStall is gated on this so a leftover scrapeStall.enabled
  // config can NEVER busy-wait/freeze a normal manual session — the stall only
  // applies between run/start and run/stop.
  let _runActive = false;

  // Structured diagnostic logger.  Prefixes every line with [feige-emu]
  // and a millisecond timestamp so the eCan app's browser_console.log
  // tail can be correlated with the Python-side runlogs/eCan.log.
  // Call as `flog('event_name', { ...fields })`.  Fields are shown as
  // a compact JSON blob.
  function flog(event, fields) {
    var ts;
    try {
      var now = new Date();
      ts = now.toTimeString().slice(0, 8) + '.' + String(now.getMilliseconds()).padStart(3, '0');
      var payload = fields ? JSON.stringify(fields) : '';
      // eslint-disable-next-line no-console
      console.log('[feige-emu] ' + ts + ' ' + event + (payload ? ' ' + payload : ''));
    } catch (e) { /* ignore console failures */ }
    // Fire-and-forget mirror to the emulation server so the user can
    // see every button click / state transition in the terminal where
    // they launched `python server.py`.  The eCan app's
    // `browser_console.log` tail only watches `localhost:3000`, so
    // without this the emulation tab's console output is invisible to
    // the Python side.  keepalive:true lets the POST survive page
    // unload; failures are swallowed — this is pure diagnostics.
    try {
      var body = JSON.stringify({ ts: ts, event: event, fields: fields || null });
      fetch('/emu-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
        keepalive: true,
      }).catch(function () { /* ignore */ });
    } catch (e) { /* ignore */ }
  }

  // ─── flood-test metrics oracle (2026-06-02) ────────────────────────────
  // Fire-and-forget structured events to the emulation server, which is the
  // ground-truth observer of the flood test (it sends every query and
  // receives every reply). The server only records these while a "run" is
  // active (between /api/emulation/run/{start,stop}); outside a run they are
  // harmless 204s. Two event types:
  //   emetric("q_sent",    { cid, cust, text, ts })
  //   emetric("agent_msg", { cid, cust, text, is_placeholder, ts })
  function emetric(mtype, fields) {
    try {
      var body = JSON.stringify(Object.assign({ mtype: mtype }, fields || {}));
      fetch('/api/emulation/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
        keepalive: true,
      }).catch(function () { /* ignore */ });
    } catch (e) { /* ignore */ }
  }

  // The eCan agent's time-buying placeholder ("人工服务正在回复中…" and
  // variants). Anchored on stable substrings so wording tweaks don't break
  // metric classification.
  var PLACEHOLDER_MARKERS = ["正在回复", "人工服务正在", "稍等", "马上为您", "稍候", "正在为您"];
  function isPlaceholderText(text) {
    var t = String(text || "");
    for (var i = 0; i < PLACEHOLDER_MARKERS.length; i++) {
      if (t.indexOf(PLACEHOLDER_MARKERS[i]) !== -1) return true;
    }
    return false;
  }

  function cloneChaosConfig(obj) {
    return JSON.parse(JSON.stringify(obj || DEFAULT_CHAOS_CONFIG));
  }

  function mergeChaosConfig(base, incoming) {
    const out = cloneChaosConfig(base);
    if (!incoming || typeof incoming !== "object") return out;
    Object.keys(incoming).forEach((key) => {
      const val = incoming[key];
      if (val && typeof val === "object" && !Array.isArray(val) && out[key] && typeof out[key] === "object") {
        out[key] = mergeChaosConfig(out[key], val);
      } else {
        out[key] = val;
      }
    });
    return out;
  }

  function clampNumber(value, min, max, fallback) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  function chaosIsEnabled() {
    return !!(chaosConfig && chaosConfig.enabled);
  }

  function chaosHit() {
    if (!chaosIsEnabled()) return false;
    return Math.random() < clampNumber(chaosConfig.probability, 0, 1, 1);
  }

  function busyWait(ms) {
    const n = clampNumber(ms, 0, 30000, 0);
    if (n <= 0) return;
    const end = performance.now() + n;
    while (performance.now() < end) {}
  }

  // Build a lightweight snapshot of every customer's visibility state
  // so we can diff it around suspicious transitions (e.g. when the
  // 当前会话 tab suddenly empties mid-session).
  function customersSnapshot() {
    var out = {};
    for (var k in customers) {
      if (!Object.prototype.hasOwnProperty.call(customers, k)) continue;
      var c = customers[k];
      out[k] = {
        mode: c.mode,
        inCurrent: !!c.inCurrent,
        unread: c.unreadCount | 0,
        everChatted: !!c.everChatted,
        lastMsgRole: c.lastMsgRole,
        lastMsg: (c.lastMsg || '').slice(0, 40)
      };
    }
    return out;
  }

  function newCustomer(id, name, avatar) {
    return {
      id,
      name,
      avatar,
      // lifecycle
      mode: "auto",              // "auto" | "human" | "closed"
      inCurrent: false,          // true → appears in 当前会话 tab
      firstUnreadAt: null,       // ms timestamp of first unread customer msg
      unreadCount: 0,
      everChatted: false,
      // rendering
      tags: ["重复来访"],
      dialogs: [],               // [{ dateLabel, messages: [...] }]
      lastMsg: "",
      lastMsgAt: null,
      lastMsgRole: null,         // "customer" | "agent" | "smart_cs" | "system"
      // to make mutations observable, we use an incrementing seq
      seq: 0,
    };
  }

  // ────────────────────────────── helpers ──────────────────────────────
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function fmtTime(ts) {
    const d = new Date(ts);
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  }
  function fmtTimeShort(ts) {
    const d = new Date(ts);
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }
  function fmtDateLabel(ts) {
    const d = new Date(ts);
    return `${d.getMonth() + 1}月${d.getDate()}日 ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }
  function fmtDateOnly(ts) {
    const d = new Date(ts);
    return `${d.getMonth() + 1}月${d.getDate()}日`;
  }
  function uid() { return Math.random().toString(36).slice(2, 10) + Date.now().toString(36); }
  function pickRandom(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
  function randomInt(min, max) { return min + Math.floor(Math.random() * (max - min + 1)); }
  function shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }

  function stressCustomerId(n) {
    return "S" + String(n).padStart(3, "0");
  }

  function stressCustomerName(n) {
    return "客户" + String(n).padStart(2, "0");
  }

  function ensureStressCustomers(count) {
    const ids = [];
    let _added = 0;
    for (let i = 1; i <= count; i++) {
      const id = stressCustomerId(i);
      ids.push(id);
      if (!customers[id]) {
        customers[id] = newCustomer(
          id,
          stressCustomerName(i),
          STRESS_AVATARS[(i - 1) % STRESS_AVATARS.length],
        );
        _added++;
      }
    }
    // 2026-05-20 multi-tab sync: broadcast new customer roster to other tabs.
    if (_added > 0) {
      multiTabSync.scheduleSave("ensureStressCustomers:+" + _added);
    }
    return ids;
  }

  function getStressCount() {
    const el = $("#stressCountInput");
    const raw = el ? parseInt(el.value, 10) : STRESS_DEFAULT_COUNT;
    const count = Number.isFinite(raw) ? raw : STRESS_DEFAULT_COUNT;
    const clamped = Math.max(1, Math.min(STRESS_MAX_COUNT, count));
    if (el && String(clamped) !== el.value) el.value = String(clamped);
    return clamped;
  }

  // ─── 并发消息 multimodal mix (2026-05-24 mt038) ──────────────────────
  // Replaces the legacy "图文 N 人 (checkbox + count)" controls with two
  // percentage knobs (图文 % + 卡片 %) sampled per customer.  Defaults
  // 20/20 (= 20% image, 20% card, 60% plain text), so a 20-customer
  // flood reliably hits "[商品]" / "[图片]" sidebar previews — that's
  // the only way to exercise mt038A/B locally.
  //
  // Backwards-compat: if the legacy stressImageCountInput holds a value
  // and the new stressImagePercentInput is at default 0, derive the
  // percentage from the legacy count so an operator who'd configured
  // the old controls doesn't silently lose their setting on reload.
  function _readPercent(elId, fallback) {
    const el = $(elId);
    const raw = el ? parseFloat(el.value) : fallback;
    const v = Number.isFinite(raw) ? raw : fallback;
    return Math.max(0, Math.min(100, v));
  }

  function getStressImagePercent() {
    return _readPercent("#stressImagePercentInput", 20);
  }

  function getStressCardPercent() {
    return _readPercent("#stressCardPercentInput", 20);
  }

  function normalizeChaosConfig(config) {
    const cfg = mergeChaosConfig(DEFAULT_CHAOS_CONFIG, config || {});
    cfg.enabled = !!cfg.enabled;
    cfg.preset = String(cfg.preset || "off");
    cfg.probability = clampNumber(cfg.probability, 0, 1, 1);
    cfg.send.blockClickMs = clampNumber(cfg.send.blockClickMs, 0, 20000, 0);
    cfg.send.delayAgentAppendMs = clampNumber(cfg.send.delayAgentAppendMs, 0, 20000, 0);
    cfg.send.neverAppendAgent = !!cfg.send.neverAppendAgent;
    cfg.renderer.stallEnabled = !!cfg.renderer.stallEnabled;
    cfg.renderer.blockMs = clampNumber(cfg.renderer.blockMs, 0, 5000, 0);
    cfg.renderer.intervalMs = clampNumber(cfg.renderer.intervalMs, 100, 10000, 1000);
    cfg.renderer.autoStopAfterMs = clampNumber(cfg.renderer.autoStopAfterMs, 1000, 300000, 60000);
    cfg.dom.selectorDelayMs = clampNumber(cfg.dom.selectorDelayMs, 0, 250, 0);
    cfg.dom.extraMessageRows = Math.floor(clampNumber(cfg.dom.extraMessageRows, 0, 2000, 0));
    cfg.dom.systemRows = Math.floor(clampNumber(cfg.dom.systemRows, 0, 200, 0));
    cfg.dom.churnEnabled = !!cfg.dom.churnEnabled;
    cfg.dom.churnIntervalMs = clampNumber(cfg.dom.churnIntervalMs, 100, 10000, 500);
    if (!cfg.dom.scrapeStall || typeof cfg.dom.scrapeStall !== "object") cfg.dom.scrapeStall = {};
    cfg.dom.scrapeStall.enabled = !!cfg.dom.scrapeStall.enabled;
    cfg.dom.scrapeStall.baseMs = clampNumber(cfg.dom.scrapeStall.baseMs, 0, 30000, 120);
    cfg.dom.scrapeStall.perMsgMs = clampNumber(cfg.dom.scrapeStall.perMsgMs, 0, 1000, 20);
    cfg.dom.scrapeStall.perConvoMs = clampNumber(cfg.dom.scrapeStall.perConvoMs, 0, 10000, 500);
    cfg.dom.scrapeStall.capMs = clampNumber(cfg.dom.scrapeStall.capMs, 0, 30000, 30000);
    cfg.focus.churnEnabled = !!cfg.focus.churnEnabled;
    cfg.focus.switchIntervalMs = clampNumber(cfg.focus.switchIntervalMs, 100, 10000, 1000);
    cfg.focus.switchProbability = clampNumber(cfg.focus.switchProbability, 0, 1, 0.2);
    cfg.focus.rerenderDuringSend = !!cfg.focus.rerenderDuringSend;
    cfg.focus.removeComposeDuringSend = !!cfg.focus.removeComposeDuringSend;
    cfg.focus.removeComposeMs = clampNumber(cfg.focus.removeComposeMs, 100, 10000, 1200);
    cfg.harness.fakeRuntimeDelayMs = clampNumber(cfg.harness.fakeRuntimeDelayMs, 0, 30000, 7000);
    cfg.harness.fakeRuntimeNeverResolve = !!cfg.harness.fakeRuntimeNeverResolve;
    cfg.harness.cdpUseDelayMs = clampNumber(cfg.harness.cdpUseDelayMs, 0, 30000, 7000);
    cfg.harness.cdpUseNeverRespond = !!cfg.harness.cdpUseNeverRespond;
    cfg.harness.cdpUseLateResponseMs = clampNumber(cfg.harness.cdpUseLateResponseMs, 0, 30000, 0);
    return cfg;
  }

  function chaosEl(id) {
    return $("#" + id);
  }

  function setChaosChecked(id, value) {
    const el = chaosEl(id);
    if (el) el.checked = !!value;
  }

  function setChaosValue(id, value) {
    const el = chaosEl(id);
    if (el) el.value = String(value);
  }

  function readChaosNumber(id, min, max, fallback) {
    const el = chaosEl(id);
    return clampNumber(el ? el.value : fallback, min, max, fallback);
  }

  function setChaosControlValues(config) {
    const cfg = normalizeChaosConfig(config);
    setChaosChecked("chaosEnabled", cfg.enabled);
    setChaosValue("chaosPreset", cfg.preset);
    setChaosValue("chaosProbability", Math.round(cfg.probability * 100));
    setChaosValue("chaosSendBlockMs", cfg.send.blockClickMs);
    setChaosValue("chaosSendDelayMs", cfg.send.delayAgentAppendMs);
    setChaosChecked("chaosSendNeverAppend", cfg.send.neverAppendAgent);
    setChaosChecked("chaosRendererEnabled", cfg.renderer.stallEnabled);
    setChaosValue("chaosRendererBlockMs", cfg.renderer.blockMs);
    setChaosValue("chaosRendererIntervalMs", cfg.renderer.intervalMs);
    setChaosValue("chaosRendererAutoStopMs", cfg.renderer.autoStopAfterMs);
    setChaosValue("chaosSelectorDelayMs", cfg.dom.selectorDelayMs);
    setChaosValue("chaosExtraRows", cfg.dom.extraMessageRows);
    setChaosValue("chaosSystemRows", cfg.dom.systemRows);
    setChaosChecked("chaosDomChurn", cfg.dom.churnEnabled);
    setChaosValue("chaosDomChurnMs", cfg.dom.churnIntervalMs);
    setChaosChecked("chaosFocusChurn", cfg.focus.churnEnabled);
    setChaosValue("chaosFocusSwitchMs", cfg.focus.switchIntervalMs);
    setChaosValue("chaosFocusProbability", Math.round(cfg.focus.switchProbability * 100));
    setChaosChecked("chaosRerenderDuringSend", cfg.focus.rerenderDuringSend);
    setChaosChecked("chaosRemoveCompose", cfg.focus.removeComposeDuringSend);
    setChaosValue("chaosRemoveComposeMs", cfg.focus.removeComposeMs);
    setChaosValue("chaosFakeDelayMs", cfg.harness.fakeRuntimeDelayMs);
    setChaosChecked("chaosFakeNever", cfg.harness.fakeRuntimeNeverResolve);
    setChaosValue("chaosCdpUseDelayMs", cfg.harness.cdpUseDelayMs);
    setChaosChecked("chaosCdpUseNever", cfg.harness.cdpUseNeverRespond);
    setChaosValue("chaosCdpUseLateMs", cfg.harness.cdpUseLateResponseMs);
  }

  function collectChaosConfigFromControls() {
    return normalizeChaosConfig({
      enabled: !!(chaosEl("chaosEnabled") && chaosEl("chaosEnabled").checked),
      preset: chaosEl("chaosPreset") ? chaosEl("chaosPreset").value : chaosConfig.preset,
      probability: readChaosNumber("chaosProbability", 0, 100, 100) / 100,
      send: {
        blockClickMs: readChaosNumber("chaosSendBlockMs", 0, 20000, 0),
        delayAgentAppendMs: readChaosNumber("chaosSendDelayMs", 0, 20000, 0),
        neverAppendAgent: !!(chaosEl("chaosSendNeverAppend") && chaosEl("chaosSendNeverAppend").checked),
      },
      renderer: {
        stallEnabled: !!(chaosEl("chaosRendererEnabled") && chaosEl("chaosRendererEnabled").checked),
        blockMs: readChaosNumber("chaosRendererBlockMs", 0, 5000, 0),
        intervalMs: readChaosNumber("chaosRendererIntervalMs", 100, 10000, 1000),
        autoStopAfterMs: readChaosNumber("chaosRendererAutoStopMs", 1000, 300000, 60000),
      },
      dom: {
        selectorDelayMs: readChaosNumber("chaosSelectorDelayMs", 0, 250, 0),
        extraMessageRows: readChaosNumber("chaosExtraRows", 0, 2000, 0),
        systemRows: readChaosNumber("chaosSystemRows", 0, 200, 0),
        churnEnabled: !!(chaosEl("chaosDomChurn") && chaosEl("chaosDomChurn").checked),
        churnIntervalMs: readChaosNumber("chaosDomChurnMs", 100, 10000, 500),
      },
      focus: {
        churnEnabled: !!(chaosEl("chaosFocusChurn") && chaosEl("chaosFocusChurn").checked),
        switchIntervalMs: readChaosNumber("chaosFocusSwitchMs", 100, 10000, 1000),
        switchProbability: readChaosNumber("chaosFocusProbability", 0, 100, 20) / 100,
        rerenderDuringSend: !!(chaosEl("chaosRerenderDuringSend") && chaosEl("chaosRerenderDuringSend").checked),
        removeComposeDuringSend: !!(chaosEl("chaosRemoveCompose") && chaosEl("chaosRemoveCompose").checked),
        removeComposeMs: readChaosNumber("chaosRemoveComposeMs", 100, 10000, 1200),
      },
      harness: {
        fakeRuntimeDelayMs: readChaosNumber("chaosFakeDelayMs", 0, 30000, 7000),
        fakeRuntimeNeverResolve: !!(chaosEl("chaosFakeNever") && chaosEl("chaosFakeNever").checked),
        cdpUseDelayMs: readChaosNumber("chaosCdpUseDelayMs", 0, 30000, 7000),
        cdpUseNeverRespond: !!(chaosEl("chaosCdpUseNever") && chaosEl("chaosCdpUseNever").checked),
        cdpUseLateResponseMs: readChaosNumber("chaosCdpUseLateMs", 0, 30000, 0),
      },
    });
  }

  async function loadChaosConfig() {
    try {
      const res = await fetch("/api/emulation/config", { cache: "no-store" });
      const data = await res.json();
      chaosConfig = normalizeChaosConfig(data && data.config);
      setChaosControlValues(chaosConfig);
      applyChaosRuntime();
      renderChatList();
      renderThread();
      flog("chaos.config.loaded", { config: chaosConfig });
    } catch (e) {
      flog("chaos.config.load_failed", { error: String(e && e.message || e) });
    }
  }

  async function saveChaosConfig(config) {
    chaosConfig = normalizeChaosConfig(config || chaosConfig);
    setChaosControlValues(chaosConfig);
    applyChaosRuntime();
    renderChatList();
    renderThread();
    const res = await fetch("/api/emulation/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chaosConfig),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "save failed");
    chaosConfig = normalizeChaosConfig(data.config);
    setChaosControlValues(chaosConfig);
    flog("chaos.config.saved", { config: chaosConfig });
    return chaosConfig;
  }

  function scheduleChaosSave() {
    clearTimeout(chaosSaveTimer);
    chaosSaveTimer = setTimeout(() => {
      saveChaosConfig(collectChaosConfigFromControls()).catch((e) => {
        flog("chaos.config.save_failed", { error: String(e && e.message || e) });
      });
    }, 350);
  }

  function applyChaosPreset(name) {
    const keepHarness = cloneChaosConfig(chaosConfig).harness;
    const next = mergeChaosConfig(DEFAULT_CHAOS_CONFIG, CHAOS_PRESETS[name] || {});
    next.preset = name;
    next.harness = keepHarness;
    chaosConfig = normalizeChaosConfig(next);
    setChaosControlValues(chaosConfig);
    saveChaosConfig(chaosConfig).catch((e) => flog("chaos.preset.save_failed", { error: String(e && e.message || e) }));
  }

  function setupChaosControls() {
    const panel = $("#chaosPanel");
    if (!panel) return;
    panel.querySelectorAll("input, select").forEach((el) => {
      el.addEventListener("change", () => {
        if (el.id === "chaosPreset") applyChaosPreset(el.value);
        else scheduleChaosSave();
      });
      el.addEventListener("input", () => {
        if (el.id !== "chaosPreset") scheduleChaosSave();
      });
    });
  }

  async function resetChaosConfig() {
    const res = await fetch("/api/emulation/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "reset failed");
    chaosConfig = normalizeChaosConfig(data.config);
    setChaosControlValues(chaosConfig);
    applyChaosRuntime();
    renderChatList();
    renderThread();
    flog("chaos.config.reset", {});
  }

  async function runChaosHarness(mode) {
    const out = $("#chaosHarnessOutput");
    if (out) out.textContent = "running " + mode + "...";
    await saveChaosConfig(collectChaosConfigFromControls());
    const res = await fetch("/api/emulation/run-harness", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    const data = await res.json();
    const text = JSON.stringify(data, null, 2);
    if (out) out.textContent = text;
    flog("chaos.harness.result", { mode, ok: !!data.ok, returncode: data.returncode });
  }

  function applyChaosRuntime() {
    if (rendererStallTimer) clearInterval(rendererStallTimer);
    if (rendererAutoStopTimer) clearTimeout(rendererAutoStopTimer);
    if (focusChurnTimer) clearInterval(focusChurnTimer);
    if (domChurnTimer) clearInterval(domChurnTimer);
    rendererStallTimer = null;
    rendererAutoStopTimer = null;
    focusChurnTimer = null;
    domChurnTimer = null;
    const cfg = normalizeChaosConfig(chaosConfig);
    if (!cfg.enabled) return;
    if (cfg.renderer.stallEnabled && cfg.renderer.blockMs > 0) {
      rendererStallTimer = setInterval(() => {
        if (!chaosIsEnabled() || !chaosConfig.renderer.stallEnabled) return;
        flog("chaos.renderer_stall.tick", { block_ms: chaosConfig.renderer.blockMs });
        busyWait(chaosConfig.renderer.blockMs);
      }, cfg.renderer.intervalMs);
      rendererAutoStopTimer = setTimeout(() => {
        chaosConfig.renderer.stallEnabled = false;
        setChaosControlValues(chaosConfig);
        saveChaosConfig(chaosConfig).catch(() => {});
        applyChaosRuntime();
        flog("chaos.renderer_stall.auto_stop", {});
      }, cfg.renderer.autoStopAfterMs);
    }
    if (cfg.focus.churnEnabled) {
      focusChurnTimer = setInterval(() => {
        if (!chaosIsEnabled() || !chaosConfig.focus.churnEnabled) return;
        if (Math.random() > clampNumber(chaosConfig.focus.switchProbability, 0, 1, 0.2)) return;
        const ids = Object.keys(customers).filter((id) => customers[id] && customers[id].everChatted);
        if (!ids.length) return;
        const cid = pickRandom(ids);
        focusCustomer(cid);
        renderChatList();
        renderThread();
        flog("chaos.focus_churn.switch", { cid });
      }, cfg.focus.switchIntervalMs);
    }
    if (cfg.dom.churnEnabled) {
      domChurnTimer = setInterval(() => {
        if (!chaosIsEnabled() || !chaosConfig.dom.churnEnabled) return;
        document.body.setAttribute("data-chaos-churn", String(Date.now()));
        renderChatList();
        renderThread();
        flog("chaos.dom_churn.render", { activeCustomer: state.activeCustomer });
      }, cfg.dom.churnIntervalMs);
    }
  }

  // ── mt070 detection-blackout: load-dependent scrape stall ──────────────
  // Selector substrings the eCan Feige scrapers use (sidebar detector +
  // per-customer bubble scrape). When a Runtime.evaluate in the page main
  // world queries one of these, we busy-wait proportional to current load —
  // modelling the real 5-28s scrape evals that blind the co-located monitor.
  // 2026-06-03: scope the heavy stall to THREAD/BUBBLE scrape selectors only.
  // The per-customer thread scrape is the O(DOM)-expensive one (5-28s in the
  // real trace); the 新消息 SIDEBAR scrape is cheap. The blackout is the heavy
  // thread scrape BLOCKING the co-located sidebar poll on a shared renderer —
  // so we must NOT also penalize the sidebar selectors, or the dedicated-tab
  // fix (which moves the poll to its own renderer) wouldn't be demonstrable:
  // the poll would still busy-wait on its own tab. Excluding the sidebar
  // selectors means a shared tab still blackouts (thread scrape blocks the
  // poll's eval on the same V8 thread) while a dedicated tab does not.
  const SCRAPE_SIGNATURE_SELECTORS = [
    "qa-message-warpper",          // thread bubble wrapper (the THREAD scrape)
    "messageNotMe", "messageIsMe", // bubble side classes
    "iD7SHBvMhm4OhfCsBGr1",        // text-bubble class
    "chatd-card",                  // product-card bubble
    // sidebar selectors (qa-conversation-chat-item, list_items) intentionally
    // EXCLUDED — the detection scrape is cheap; blocking is what blinds it.
  ];

  function _isScrapeSignature(selector) {
    const s = String(selector || "");
    for (let i = 0; i < SCRAPE_SIGNATURE_SELECTORS.length; i++) {
      if (s.indexOf(SCRAPE_SIGNATURE_SELECTORS[i]) !== -1) return true;
    }
    return false;
  }

  // Aggregate conversation load (cached ~500ms — it changes slowly and we
  // must not walk every customer on every querySelector call). msgs = total
  // messages across customers that have ever chatted (grows monotonically as
  // the test runs); convos = customers active within the last 120s (concurrency).
  function _scrapeLoadSnapshot() {
    const now = Date.now();
    if (now - _scrapeLoadCache.at < 500) return _scrapeLoadCache;
    let msgs = 0, convos = 0;
    for (const k in customers) {
      if (!Object.prototype.hasOwnProperty.call(customers, k)) continue;
      const c = customers[k];
      if (!c || !c.everChatted) continue;
      const dialogs = Array.isArray(c.dialogs) ? c.dialogs : [];
      for (let di = 0; di < dialogs.length; di++) {
        const ms = dialogs[di] && Array.isArray(dialogs[di].messages) ? dialogs[di].messages : null;
        if (ms) msgs += ms.length;
      }
      if (typeof c.lastMsgAt === "number" && now - c.lastMsgAt < 120000) convos++;
    }
    _scrapeLoadCache = { at: now, msgs: msgs, convos: convos };
    return _scrapeLoadCache;
  }

  function _scrapeStallMs() {
    const cfg = chaosConfig && chaosConfig.dom && chaosConfig.dom.scrapeStall;
    if (!cfg || !cfg.enabled || !chaosIsEnabled()) return 0;
    const snap = _scrapeLoadSnapshot();
    const cost = (cfg.baseMs || 0)
      + (cfg.perMsgMs || 0) * snap.msgs
      + (cfg.perConvoMs || 0) * snap.convos;
    return Math.max(0, Math.min(cfg.capMs || 30000, cost));
  }

  function maybeScrapeStall(selector) {
    if (!_runActive) return;                     // only during an active harness run
    const cfg = chaosConfig && chaosConfig.dom && chaosConfig.dom.scrapeStall;
    if (!cfg || !cfg.enabled || !chaosIsEnabled()) return;
    if (_pageRenderDepth > 0) return;            // skip the page's own renders
    if (_scrapeChargedThisTick) return;          // once per synchronous evaluate
    if (!_isScrapeSignature(selector)) return;
    _scrapeChargedThisTick = true;
    Promise.resolve().then(function () { _scrapeChargedThisTick = false; });
    const ms = _scrapeStallMs();
    if (ms <= 0) return;
    const wnow = Date.now();
    if (wnow - lastScrapeStallLogAt > 1000) {
      lastScrapeStallLogAt = wnow;
      const snap = _scrapeLoadSnapshot();
      flog("chaos.scrape_stall", {
        selector: String(selector).slice(0, 60),
        ms: Math.round(ms), msgs: snap.msgs, convos: snap.convos,
      });
    }
    busyWait(ms);
  }

  function installSelectorDelayPatch() {
    if (window.__feigeChaosSelectorPatch) return;
    window.__feigeChaosSelectorPatch = true;
    const docQuery = Document.prototype.querySelector;
    const docQueryAll = Document.prototype.querySelectorAll;
    const elQuery = Element.prototype.querySelector;
    const elQueryAll = Element.prototype.querySelectorAll;
    function maybeDelaySelector(selector) {
      const ms = chaosConfig && chaosConfig.dom ? chaosConfig.dom.selectorDelayMs : 0;
      if (!chaosHit() || ms <= 0) return;
      const now = Date.now();
      if (now - lastSelectorDelayLogAt > 1000) {
        lastSelectorDelayLogAt = now;
        flog("chaos.selector_delay", { selector: String(selector).slice(0, 120), ms });
      }
      busyWait(ms);
    }
    Document.prototype.querySelector = function(selector) {
      maybeDelaySelector(selector);
      maybeScrapeStall(selector);
      return docQuery.call(this, selector);
    };
    Document.prototype.querySelectorAll = function(selector) {
      maybeDelaySelector(selector);
      maybeScrapeStall(selector);
      return docQueryAll.call(this, selector);
    };
    Element.prototype.querySelector = function(selector) {
      maybeDelaySelector(selector);
      maybeScrapeStall(selector);
      return elQuery.call(this, selector);
    };
    Element.prototype.querySelectorAll = function(selector) {
      maybeDelaySelector(selector);
      maybeScrapeStall(selector);
      return elQueryAll.call(this, selector);
    };
  }

  // keep adding messages into the CURRENT dialog; start a new dialog when the
  // previous dialog has been closed (via timeoutClose) OR after 30-min idle.
  function currentDialog(c, nowTs) {
    if (c.dialogs.length === 0 || c.dialogs[c.dialogs.length - 1].closed) {
      const d = { dateLabel: fmtDateLabel(nowTs), messages: [], startAt: nowTs, closed: false };
      c.dialogs.push(d);
      return d;
    }
    return c.dialogs[c.dialogs.length - 1];
  }

  function touchSeq(c) {
    c.seq = (c.seq | 0) + 1;
    // 2026-05-20 multi-tab sync: signal other tabs that customer state changed.
    // Debounced so a burst of mutations within ~50ms collapses to one write.
    multiTabSync.scheduleSave("touchSeq:" + (c && c.id ? c.id : "?"));
  }

  // Message shape:
  //   { id, role, text, time, ts, read?, senderLabel?, systemKind?: 'assign'|'close'|'warn' }
  function pushMessage(c, msg) {
    const d = currentDialog(c, msg.ts);
    d.messages.push(msg);
    c.lastMsg = msg.systemKind ? msg.text : msg.text;
    c.lastMsgAt = msg.ts;
    c.lastMsgRole = msg.role;
    touchSeq(c);
  }

  // Mark all unread counters cleared for this customer (when agent opens thread).
  function clearUnread(c) {
    c.unreadCount = 0;
    c.firstUnreadAt = null;
  }

  // ────────────────────────────── rendering: chat list ─────────────────────
  const scrollRoot = $("#chantListScrollArea");
  const settingsRow = $("#settingsRow");
  const settingsPopup = $("#settingsPopup");

  let _prevSidebarKey = '';
  function renderChatList() {
    _pageRenderDepth++;
    try {
    const isCurrent = state.activeTab === "current";
    settingsRow.style.display = isCurrent ? "" : "none";
    if (!isCurrent) settingsPopup.classList.add("hidden");

    // mt067-emulation: new Feige nests the rows under .scroller_content >
    // .list_items inside the scroll container (the monitor's cdpFilterExpr
    // root is ".list_items").  #chantListScrollArea stays as the outer
    // scroller for the emulation's own scroll handling.
    //
    // 2026-06-03 FIX: wrapCurrentListHTML/renderRecentTabHTML ALREADY emit the
    // .scroller > .scroller_content > .list_items structure, so the previous
    // extra '<div class="scroller_content"><div class="list_items">' here
    // double-wrapped the current tab — producing TWO nested .list_items. The
    // monitor scrapes the FIRST .list_items (the empty outer wrapper) and saw
    // items=1 keys=['|'] while the real customer rows sat in the inner one →
    // detection silently never fired (every 2026-06-02 flood = answered=0).
    // Emit the tab HTML directly so there is exactly ONE .list_items holding
    // the rows.
    scrollRoot.innerHTML = (isCurrent ? renderCurrentTabHTML() : renderRecentTabHTML());

    // wire up click-to-open on every chat-item
    $$('[data-qa-id="qa-conversation-chat-item"]', scrollRoot).forEach(el => {
      el.addEventListener("click", () => {
        if (el.dataset.cid) openSession(el.dataset.cid);
      });
    });
    // wire up collapsible sections
    $$('.section .section-header', scrollRoot).forEach(el => {
      el.addEventListener("click", () => {
        const sec = el.parentElement;
        const key = sec.dataset.section;
        if (state.collapsedSections.has(key)) state.collapsedSections.delete(key);
        else state.collapsedSections.add(key);
        renderChatList();
      });
    });

    // tab count on 当前会话 tab button
    const curCount = activeHumanCustomers().length;
    $("#tabCountCurrent").textContent = curCount;

    // Log sidebar composition whenever it changes.  This is how we
    // catch "B and C disappeared" situations: every transition that
    // removes a customer from the visible sidebar will emit one log
    // line with before/after state.
    const rowNames = [];
    scrollRoot.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]').forEach(function(el){
      const nm = (el.querySelector('[class*="NameContent"]') || el.querySelector('.Jv6FtqUv5VoYARd2pp4y') || el).textContent || '';
      rowNames.push(nm.trim());
    });
    const key = state.activeTab + '|' + rowNames.join(',');
    if (key !== _prevSidebarKey) {
      flog('sidebar.render', { tab: state.activeTab, rows: rowNames, curCount, clearedCurrent: state.clearedCurrent, customers: customersSnapshot() });
      _prevSidebarKey = key;
    }
    } finally { _pageRenderDepth--; }
  }

  function activeHumanCustomers() {
    return Object.values(customers).filter(c => c.inCurrent && !state.clearedCurrent);
  }

  function setActiveTab(tabName) {
    state.activeTab = tabName;
    $$("#tabBar .tab").forEach(x => {
      const isActive = x.dataset.tab === tabName;
      x.classList.toggle("active", isActive);
      x.classList.toggle("auxo-tabs-tab-active", isActive);
      const tabBtn = x.querySelector('[role="tab"]');
      if (tabBtn) tabBtn.setAttribute("aria-selected", isActive ? "true" : "false");
    });
  }

  function renderCurrentTabHTML() {
    const actives = activeHumanCustomers();
    if (actives.length === 0) {
      return wrapCurrentListHTML(`<div class="empty-hint">暂无会话中用户</div>`);
    }
    const now = Date.now();
    const within3 = [], overdue = [];
    for (const c of actives) {
      const waitMs = c.firstUnreadAt == null ? 0 : now - c.firstUnreadAt;
      if (waitMs >= OVERDUE_MS) overdue.push(c); else within3.push(c);
    }
    // sort: longest waiting first
    within3.sort((a, b) => (a.firstUnreadAt || Infinity) - (b.firstUnreadAt || Infinity));
    overdue.sort((a, b) => (a.firstUnreadAt || Infinity) - (b.firstUnreadAt || Infinity));

    let html = "";
    if (within3.length) {
      html += sectionHTML("within3min", "3分钟内待回复", within3.length,
        within3.map(c => chatItemHTML(c, "within3")).join(""));
    }
    if (overdue.length) {
      html += sectionHTML("overdue", "已超时待回复", overdue.length,
        overdue.map(c => chatItemHTML(c, "overdue")).join(""));
    }
    return wrapCurrentListHTML(html);
  }

  function renderRecentTabHTML() {
    const all = Object.values(customers)
      .filter(c => c.everChatted)
      .sort((a, b) => (b.lastMsgAt || 0) - (a.lastMsgAt || 0));

    const sections = [
      { key: "sysNotif",    title: "系统通知",          count: null },
      { key: "recentSearch",title: "最近搜索",          count: "0" },
      { key: "starred",     title: "星标用户",          count: "0/200" },
      { key: "todayNoOrder",title: "今日咨询未下单",    count: "0" },
      { key: "todayUnpaid", title: "今日咨询下单未付款",count: "0" },
    ];
    const top = sections.map(s => {
      const col = state.collapsedSections.has(s.key) ? " collapsed" : "";
      const chev = state.collapsedSections.has(s.key) ? "▸" : "▾";
      const cnt = s.count == null ? "" : `<span class="count">${s.count}</span>`;
      const body = s.key === "sysNotif" ? systemConversationHTML() : "";
      return `<div class="section${col}" data-section="${s.key}">
        <div class="section-header RgIhlSdWdADEQLpUt24s B5ss9nLVPJ3ZQtM1a76y"><span class="section-name _HSer7gySgUfNV40_wif">${s.title}</span>${cnt}<span class="chevron auxo-sp-icon sp-icon-parcel">${chev}</span></div>
        <div class="section-body">${body}</div>
      </div>`;
    }).join("");

    const contactsCol = state.collapsedSections.has("recentContacts") ? " collapsed" : "";
    const contactsChev = state.collapsedSections.has("recentContacts") ? "▸" : "▾";
    const contactsBody = all.length === 0
      ? `<div class="empty-hint" style="position: static; transform: none; padding: 24px 0; text-align: center;">暂无联系人</div>`
      : all.map(c => chatItemHTML(c, "recent")).join("");

    return wrapRecentListHTML(top + `<div class="section${contactsCol}" data-section="recentContacts">
      <div class="section-header RgIhlSdWdADEQLpUt24s B5ss9nLVPJ3ZQtM1a76y"><span class="section-name _HSer7gySgUfNV40_wif">最近联系人</span><span class="chevron auxo-sp-icon sp-icon-parcel">${contactsChev}</span></div>
      <div class="section-body">${contactsBody}</div>
    </div>`);
  }

  function wrapCurrentListHTML(innerHTML) {
    return `<div class="pigeonChatNotScrollBox"><div style="height:100%;">
      <div class="scroller" style="position:relative;height:100%;width:100%;overflow:hidden overlay;transform:translateY(0px);contain:strict;">
        <div class="scroller_content">
          <div data-name="scroll_holder" style="height:1px;width:100%;position:absolute;transform:translate(0px, 1px);"></div>
          <div class="list_items">${innerHTML}</div>
        </div>
      </div>
    </div></div>`;
  }

  function wrapRecentListHTML(innerHTML) {
    return `<div class="pigeonChatScrollBox"><div>${innerHTML}</div></div>`;
  }

  function systemConversationHTML() {
    return `<div class="auxo-dropdown-trigger">
      <div data-btm-id="a9034.b39122.c2622.systemConv" data-kora="conversation" data-qa-id="qa-conversation-chat-item" class="conversationCard-ePRNJi newConversationCard-c5qnW3" data-cid="" data-system-row="1">
        <div class="avatarContainer-t7pXDD newAvatarContainer-zBZQl8"><img class="newAvatar-zHhRmT newFrameAvatar-FTwOpk" src="${escHtml(AVATAR.shop)}" alt="头像"></div>
        <div class="cardContent-t1Fuqy"><div class="nameLine-Q8PQwE" title="智能客服"><span class="newNameContent-DfqCyb newFrameNameContent-IViCcL">智能客服</span><div class="userLabelWrap-qkD0UF"><div class="userLabel-jVrDgb"><span>系统通知</span></div></div><div><div class="timerParticular-XjA0_t">${fmtDateOnly(Date.now())}</div></div></div>
        <div class="content-VWj6Mr newFrameContent-q7nkzA newContent-5YZgki"><div class="msgContent-JqEWJs"><span>挽单方案配置</span></div></div></div>
      </div>
    </div>`;
  }

  function sectionHTML(key, title, count, bodyHTML) {
    const col = state.collapsedSections.has(key) ? " collapsed" : "";
    const chev = state.collapsedSections.has(key) ? "▸" : "▾";
    return `<div class="section oswSnFXzSwn_l7DMyWnz${col}" data-section="${key}">
      <div class="section-header RgIhlSdWdADEQLpUt24s B5ss9nLVPJ3ZQtM1a76y"><span class="section-name">${title}</span><span class="count" id="count-${key}">(${count})</span><span class="chevron auxo-sp-icon sp-icon-parcel">${chev}</span></div>
      <div class="section-body">${bodyHTML || `<div style="padding:12px 14px; color:#aaa; font-size:12px;">无</div>`}</div>
    </div>`;
  }

  function chatItemHTML(c, mode) {
    // timestamp-field meaning: for 当前会话 show "等待 Xs/Xm Xs"; for 最近联系 show date.
    let tsText = "";
    let tsExtraCls = "";
    if (mode === "recent") {
      tsText = c.lastMsgAt ? fmtDateOnly(c.lastMsgAt) : "";
    } else {
      const waitMs = c.firstUnreadAt == null ? 0 : Math.max(0, Date.now() - c.firstUnreadAt);
      tsText = fmtWaitTime(waitMs);
      tsExtraCls = " ts-wait";
    }
    // mt067-emulation: new Feige unread badge = auxo <sup> with title; tags =
    // userLabel-* spans; active card = selectedNew-/selected- classes.
    const unreadNum = c.unreadCount > 0
      ? `<sup class="auxo-scroll-number auxo-badge-count auxo-badge-count-sm" title="${c.unreadCount}"><span class="auxo-scroll-number-only">${c.unreadCount}</span></sup>`
      : "";
    const tagHTML = c.tags.length
      ? `<div class="userLabelWrap-qkD0UF"><div class="userLabel-jVrDgb">${c.tags.map(t => `<span>${escHtml(t)}</span>`).join("")}</div></div>`
      : "";
    const active = state.activeCustomer === c.id ? " active" : "";
    const activeReal = active ? " selectedNew-WI_v9D selected-fTcLcH" : "";
    const btmScope = mode === "recent" ? "recent" : "current";
    // 2026-06-02 mt067-emulation: rendered to match Feige's redesigned
    // conversation card (live DOM captured 2026-06-02).  Old hashed classes
    // (.MP1bk.../.Jv6Ft.../.lF_M7Qi...) are GONE; the new design uses
    // semantic-prefix+hash classes (conversationCard-/nameLine-/
    // newNameContent-/msgContent-/timerParticular-) and keeps the stable
    // data-qa-id="qa-conversation-chat-item".  Mirrors the customer-pasted
    // card so the monitor's new cdpFilterExpr selectors ([class*=NameContent]
    // etc.) and the mt062-065 code fallbacks can be exercised locally.
    return `<div
        class="conversationCard-ePRNJi newConversationCard-c5qnW3 needReply-JehIyj${active}${activeReal}"
        data-btm-id="a9034.b39122.c2622.${btmScope}"
        data-kora="conversation"
        data-qa-id="qa-conversation-chat-item"
        data-cid="${c.id}"
        data-seq="${c.seq}">
      <div class="avatarContainer-t7pXDD newAvatarContainer-zBZQl8">
        <span class="auxo-badge auxo-badge-top-right">
          <img class="newAvatar-zHhRmT newFrameAvatar-FTwOpk zeVHjNO_lFGbJlreiSda" src="${escHtml(c.avatar)}" alt="头像">
          ${unreadNum}
        </span>
      </div>
      <div class="cardContent-t1Fuqy">
        <div class="nameLine-Q8PQwE" title="${escHtml(c.name)}">
          <span class="newNameContent-DfqCyb newFrameNameContent-IViCcL Jv6FtqUv5VoYARd2pp4y">${escHtml(c.name)}</span>
          ${tagHTML}
          <div><div class="timerParticular-XjA0_t CEnLM8MEGksTdgi_8Lqf${tsExtraCls}">${escHtml(tsText)}</div></div>
        </div>
        <div data-btm="d089038" class="content-VWj6Mr newFrameContent-q7nkzA newContent-5YZgki lF_M7QiFB0ukHWpMfQde">
          <div class="msgContent-JqEWJs"><span>${escHtml(c.lastMsg || "")}</span></div>
          <div class="cardIcon-Cgx51x"></div>
        </div>
      </div>
    </div>`;
  }

  function fmtWaitTime(ms) {
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return `${sec}s`;
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    // past 3 minutes: minute-only granularity (ticks once per minute)
    if (m >= 3) return `${m}m`;
    return `${m}m ${s}s`;
  }

  // ────────────────────────────── rendering: thread ──────────────────────────
  const threadEl = $("#thread");
  const threadEmpty = $("#threadEmpty");
  const threadScroll = $("#threadScroll");
  const midName = $("#midName");
  const midSub = $("#midSub");

  function renderThread() {
    const cid = state.activeCustomer;
    if (!cid || !customers[cid] || !customers[cid].everChatted) {
      threadEl.innerHTML = "";
      threadEl.dataset.cid = "";
      threadEmpty.classList.remove("hidden");
      midName.textContent = "请选择一个会话";
      midName.dataset.cid = "";
      midSub.textContent = "";
      return;
    }
    const c = customers[cid];
    // 2026-05-20: stamp the rendered customer's ID onto thread + header
    // DOM nodes so handleAgentSend can derive routing from what's
    // *visually rendered* instead of state.activeCustomer (which can
    // race with sidebar clicks under flood load).
    threadEl.dataset.cid = c.id;
    midName.dataset.cid = c.id;
    threadEmpty.classList.add("hidden");
    midName.textContent = c.name;
    midSub.textContent = c.mode === "human"
      ? "人工客服会话中"
      : c.mode === "closed" ? "会话已关闭" : "智能客服会话中";

    const parts = [];
    for (const d of c.dialogs) {
      parts.push(`<div class="date-separator">${escHtml(d.dateLabel)}</div>`);
      if (d === c.dialogs[c.dialogs.length - 1]) parts.push(chaosThreadRowsHTML(c, d.startAt || Date.now()));
      for (const m of d.messages) {
        parts.push(renderMessageHTML(c, m));
      }
    }
    threadEl.innerHTML = parts.join("");
    // scroll to bottom
    threadScroll.scrollTop = threadScroll.scrollHeight;
  }

  function chaosThreadRowsHTML(c, baseTs) {
    if (!chaosIsEnabled()) return "";
    const cfg = chaosConfig.dom || {};
    const rows = [];
    const systemRows = Math.floor(clampNumber(cfg.systemRows, 0, 200, 0));
    const extraRows = Math.floor(clampNumber(cfg.extraMessageRows, 0, 2000, 0));
    for (let i = 0; i < systemRows; i++) {
      rows.push(renderMessageHTML(c, {
        id: "chaos_sys_" + i,
        role: "system",
        systemKind: i % 3 ? "warn" : "assign",
        text: HISTORICAL_SYSTEM_MESSAGES[i % HISTORICAL_SYSTEM_MESSAGES.length],
        ts: baseTs - ((extraRows + systemRows - i) * 60000),
      }));
    }
    for (let i = 0; i < extraRows; i++) {
      const isAgent = i % 3 === 0;
      const msgTs = baseTs - ((extraRows - i) * 45000);
      rows.push(renderMessageHTML(c, {
        id: "chaos_extra_" + i,
        role: isAgent ? "agent" : "customer",
        text: isAgent
          ? HISTORICAL_AGENT_MESSAGES[i % HISTORICAL_AGENT_MESSAGES.length]
          : HISTORICAL_CUSTOMER_MESSAGES[i % HISTORICAL_CUSTOMER_MESSAGES.length],
        senderLabel: isAgent ? SHOP_NAME : "",
        ts: msgTs,
        time: fmtTime(msgTs),
        read: true,
      }));
    }
    return rows.join("");
  }

  function renderMessageHTML(c, m) {
    if (m.role === "system") {
      const kindCls = m.systemKind === "assign" ? "e0Bi5IauHWvUG8773oi9" : "BqNO6cexAGBsZgUmEzIE";
      return `<div data-qa-id="qa-message-warpper" data-qa-message-id="" class="msgItemWrap">
        <div data-id="${escHtml(m.id)}" class="tC9ap6QtAyeCD0jfuMns">
          <div class="rcHPT4n3TlQD0Nu4sSiv">${escHtml(fmtTimeShort(m.ts))}</div>
          <div class="${kindCls}"><span>${escHtml(m.text)}</span></div>
        </div>
      </div>`;
    }

    // customer or agent (incl. smart_cs) — a regular bubble.
    //
    // DOM shape intentionally matches real Feige production (see
    // customer_logs/dom3.txt for the source we reverse-engineered):
    //   row direction is encoded via inline `flex-direction` on the
    //   `Ie29C7uLyEjZzd8JeS8A` parent — NOT via a `.customer/.agent`
    //   class — and the bubble carries `messageIsMe` (my side) or
    //   `messageNotMe` (other side).  Everything else is obfuscated
    //   Feige class names; no human-readable classes are emitted
    //   because the production DOM has none, and any selector that
    //   relied on the friendly names would pass in emulation and
    //   break in production.
    const isAgent = m.role === "agent" || m.role === "smart_cs";
    const bubbleCls = isAgent ? "messageIsMe" : "messageNotMe";
    const avatar = isAgent ? AVATAR.shop : c.avatar;

    // image-kind bubble: customer-side image attachment.  Mirrors the
    // live Feige DOM exactly — see the user-supplied sample bubble:
    //   * NO .iD7SHBvMhm4OhfCsBGr1 element (so the text-bubble selector
    //     skips it cleanly)
    //   * <img alt="图片"> sits directly inside the row container
    //   * avatar <img class="Zq9KgucRnc7bRQfikvzQ" alt="头像"> remains
    //     a sibling of the bubble row, so the scraper's avatar-class
    //     filter does its job
    // product_card-kind bubble: customer-side card attachment.  DOM is
    // a minimal-but-realistic subset of the real Feige .chatd-card
    // structure — exposes exactly the selectors that the scraper's
    // _cardData() detector reads:
    //   * data-id ending in "_template"  (card-type marker)
    //   * .chatd-card / .chatd-card-main wrapper
    //   * First .pigeon-card-place-holder-text .content = header label
    //   * Second .pigeon-card-place-holder-text .content = product title
    //     (heuristic: title is the longest non-header placeholder)
    //   * .chatd-price-currency / .chatd-price-price-inter / -decimal
    //   * Inline background-image url() on the thumbnail div
    //   * <span>满N减N</span> for coupons
    //   * <span>现在付款，明天发货</span> for shipping
    //
    // Mirrors the customer-side DOM the operator pasted into the
    // 2026-05-17 chat — see dom_assets._cardData for the matching
    // selectors.
    // 2026-05-25 J14N9 wrap-1 shape: system "用户正在查看商品，来自电商
    // 小助手的推荐" marker.  Has data-id ending in "_template" but NO
    // Ie29C7uLyEjZzd8JeS8A row container — instead a
    // .pigeon-dynamic-card-system-container-new wrapper.  dom_assets's
    // _customerBubble(wrap) returns null on this shape (skip), and
    // source-guard's allCustomerBubbles also skips it (no row).  So
    // the wrap is invisible to BOTH scrapers but appears in the
    // sidebar as last_message="用户正在查看商品".  Live J14N9 trace
    // 12:35:31 — this event fired dom_observed without any actual
    // customer message and PreDispatch eventually dispatched on a
    // pre-existing product card (mt040A now defers this).
    if (m.kind === "system_browsing") {
      const sb = m.browsingData || {};
      return `<div data-qa-id="qa-message-warpper" data-qa-message-id="" class="msgItemWrap" style="align-self: stretch;">
        <div data-id="${escHtml(m.id)}" class="tC9ap6QtAyeCD0jfuMns">
          <div class="pigeon-dynamic-card-system-container-new">
            <div style="margin-top: 8px; margin-bottom: 16px;">
              <div style="position: relative; box-sizing: border-box; font-size: 12px; padding: 0px 12px; width: 100%; display: flex; flex-direction: column;">
                <div style="position: relative; box-sizing: border-box; font-size: 12px; padding: 8px 12px; background-color: rgb(255, 255, 255); width: 100%; border-radius: 8px; display: flex; flex-direction: column;">
                  <div class="pigeon-card-place-holder-text">
                    <div class="content max-line" style="font-size: 12px; color: rgb(137, 139, 143);">
                      <span>用户正在查看商品，来自电商小助手的推荐</span>
                    </div>
                  </div>
                  <div style="display: flex; flex-direction: row; margin-top: 4px;">
                    <div style="background-image: url('${escHtml(sb.image_url || '')}'); background-size: cover; width: 32px; height: 32px; border-radius: 4px; margin-right: 8px;"></div>
                    <div style="flex: 1 1 0px; display: flex; flex-direction: column; padding: 6px 8px 6px 0px;">
                      <div class="pigeon-card-place-holder-text">
                        <div class="content max-line" style="font-size: 14px; font-weight: 500; color: rgb(37, 41, 49);">
                          <span>${escHtml(sb.title || '')}</span>
                        </div>
                      </div>
                      <div style="display: flex; flex-direction: row; align-items: center; margin-top: 4px;">
                        <div class="chatd-price chatd-price--left chatd-price--highlight">
                          <div class="chatd-price-currency" style="font-size: 10px;">¥</div>
                          <div class="chatd-price-price">
                            <div class="chatd-text chatd-price-price-inter" style="font-size: 14px;">${escHtml(sb.price_inter || '')}</div>
                            <div class="chatd-text chatd-price-price-decimal" style="font-size: 10px;">${escHtml(sb.price_decimal || '')}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>`;
    }

    if (m.kind === "product_card") {
      const card = m.cardData || {};
      const rowStyleC = isAgent
        ? "flex-direction: row-reverse; margin-bottom: 0px;"
        : "flex-direction: row; margin-bottom: 0px;";
      const avatarStyleC = isAgent
        ? "margin-right: 16px; margin-left: 4px;"
        : "margin-right: 4px; margin-left: 16px;";
      const thumbStyle =
        "position: relative; box-sizing: border-box; margin: 0px 8px 0px 0px; " +
        "padding: 0px; background-image: url(\"" + escHtml(card.image_url || "") + "\"); " +
        "background-position: center center; background-size: cover; " +
        "width: 56px; height: 56px; border-radius: 4px;";
      const couponHTML = (card.coupons || []).map(function (c) {
        return '<span style="color: rgb(255, 64, 80); font-size: 12px;">' + escHtml(c) + '</span>';
      }).join("");
      const shippingHTML = card.shipping
        ? '<span>' + escHtml(card.shipping) + '</span>'
        : "";
      return (
        '<div data-qa-id="qa-message-warpper" data-qa-message-id="" class="msgItemWrap" style="align-self: stretch;">' +
          '<div data-id="' + escHtml(m.id) + '" class="tC9ap6QtAyeCD0jfuMns">' +
            '<div style="margin-top: 8px; margin-bottom: 8px;">' +
              '<div class="Ie29C7uLyEjZzd8JeS8A Gau7ODcdZ5yvIGvjSkxJ" style="' + rowStyleC + '">' +
                '<div class="xPPA9AYUzftDhhVtlENd Rovw4rA5pP7iHYJGNHMz" style="' + avatarStyleC + '">' +
                  '<img class="Zq9KgucRnc7bRQfikvzQ" src="' + escHtml(c.avatar) + '" alt="头像">' +
                '</div>' +
                '<div style="max-width: 70%; width: auto;">' +
                  '<div class="chatd-card chatd-card--platform-pc chatd-card--lg" style="flex-grow: 1;">' +
                    '<div class="chatd-card-main" platform="mobile" style="padding: 8px 12px;">' +
                      // Header label
                      '<div class="pigeon-card-place-holder-text">' +
                        '<div class="content max-line" style="font-size: 14px; font-weight: 500;">' +
                          '<span>来自电商小助手的推荐</span>' +
                        '</div>' +
                      '</div>' +
                      // Product row: thumbnail + title + price
                      '<div style="display: flex; flex-direction: row;">' +
                        '<div style="' + thumbStyle + '"></div>' +
                        '<div style="flex: 1 1 0px;">' +
                          // Product title
                          '<div class="pigeon-card-place-holder-text">' +
                            '<div class="content max-line" style="font-size: 14px; font-weight: 400;">' +
                              '<span>' + escHtml(card.title || "") + '</span>' +
                            '</div>' +
                          '</div>' +
                          // Price
                          '<div style="margin-top: 4px;">' +
                            '<div class="chatd-price chatd-price--left chatd-price--highlight">' +
                              '<div class="chatd-price-currency" style="font-size: 10px; color: rgb(255, 59, 82);">￥</div>' +
                              '<div class="chatd-price-price">' +
                                '<div class="chatd-text chatd-price-price-inter" style="font-size: 14px; color: rgb(255, 59, 82);">' +
                                  escHtml(card.price_inter || "") +
                                '</div>' +
                                '<div class="chatd-text chatd-price-price-decimal" style="font-size: 10px; color: rgb(255, 59, 82);">' +
                                  escHtml(card.price_decimal || "") +
                                '</div>' +
                              '</div>' +
                            '</div>' +
                          '</div>' +
                        '</div>' +
                      '</div>' +
                      // Coupons row
                      (couponHTML ? '<div style="margin-top: 6px;">' + couponHTML + '</div>' : "") +
                      // Shipping row
                      (shippingHTML ? '<div style="margin-top: 4px; font-size: 12px;">' + shippingHTML + '</div>' : "") +
                    '</div>' +
                  '</div>' +
                '</div>' +
              '</div>' +
              '<div class="Vry36sSLfjhqZr9MfWnO">' +
                '<div class="O4UWWFoQxgMq4AWHMq25"><div multiple-click-times="5">' + escHtml(fmtTime(m.ts)) + '</div></div>' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
    }

    if (m.kind === "image") {
      const rowStyleImg = isAgent
        ? "flex-direction: row-reverse; margin-bottom: 0px;"
        : "flex-direction: row; margin-bottom: 0px;";
      const avatarStyleImg = isAgent
        ? "margin-right: 16px; margin-left: 4px;"
        : "margin-right: 4px; margin-left: 16px;";
      const bubbleRowStyleImg = isAgent
        ? "position: relative; display: flex; flex-direction: row-reverse;"
        : "position: relative; display: flex; flex-direction: row;";
      // Mirror the inline sizing from the production sample so layout
      // doesn't shift between live & emulated DOMs.
      const imgStyle = "width: 138.547px; height: 300px; object-fit: cover; border-radius: 8px 8px 8px 2px;";
      return `<div data-qa-id="qa-message-warpper" data-qa-message-id="" class="msgItemWrap" style="align-self: stretch;">
        <div data-id="${escHtml(m.id)}" class="tC9ap6QtAyeCD0jfuMns">
          <div style="margin-bottom: 4px;">
            <div class="Ie29C7uLyEjZzd8JeS8A Gau7ODcdZ5yvIGvjSkxJ" style="${rowStyleImg}">
              <div class="xPPA9AYUzftDhhVtlENd Rovw4rA5pP7iHYJGNHMz" style="${avatarStyleImg}">
                <img class="Zq9KgucRnc7bRQfikvzQ" src="${escHtml(avatar)}" alt="头像">
              </div>
              <div style="max-width: 70%; width: auto;">
                <div style="${bubbleRowStyleImg}">
                  <img src="${escHtml(m.imageUrl)}" alt="图片" class="auxo-dropdown-trigger WOUA1PDG10lEGvmqa_W3" style="${imgStyle}">
                  <div class="BPCj8gJpe3remPV_wWAv"></div>
                  <div class="Vry36sSLfjhqZr9MfWnO">
                    <div class="O4UWWFoQxgMq4AWHMq25 EjjnvGPGLbGHAIVS9HZf"><div multiple-click-times="5">${escHtml(fmtTime(m.ts))}</div></div>
                    <div class="n8Q1ZZgm6vKkQE4v_774"></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>`;
    }

    const rowStyle = isAgent
      ? "flex-direction: row-reverse; margin-bottom: 0px;"
      : "flex-direction: row; margin-bottom: 0px;";
    const avatarStyle = isAgent
      ? "margin-right: 16px; margin-left: 4px;"
      : "margin-right: 4px; margin-left: 16px;";
    const bubbleRowStyle = isAgent
      ? "position: relative; display: flex; flex-direction: row-reverse;"
      : "position: relative; display: flex; flex-direction: row;";
    const bubbleColorStyle = isAgent
      ? "background-color: rgb(225, 239, 255); color: rgb(37, 41, 49); border-radius: 8px;"
      : "background-color: rgb(255, 255, 255); color: rgb(18, 20, 26); border-radius: 8px;";
    const senderLabelStyle = isAgent
      ? "flex-direction: row-reverse; margin-bottom: 0px;"
      : "flex-direction: row; margin-bottom: 0px;";

    const senderLabel = m.senderLabel
      ? `<div class="gow1kLMbwl371067rDpR" style="${senderLabelStyle}"><div style="margin-bottom: 6px; display: flex;">${escHtml(m.senderLabel)}</div></div>`
      : "";
    // Real Feige DOM: read mark is an inner span with data-qa-id inside
    // the `n8Q1ZZgm6vKkQE4v_774` wrapper.  Unread agent messages leave
    // the wrapper empty.  Customer-side messages omit the wrapper too.
    const readStatus = isAgent
      ? (m.read
          ? `<div class="n8Q1ZZgm6vKkQE4v_774"><span data-qa-id="qa-message-read-mark" class="J6h_lAGn79Q9xo5UzUHw">已读</span></div>`
          : `<div class="n8Q1ZZgm6vKkQE4v_774"></div>`)
      : "";
    const preStyle = "font-size: inherit; line-height: inherit; white-space: pre-wrap; margin: 0px; font-family: inherit;";

    // 2026-05-25 J14N9-shape: real Feige's customer text bubble has
    // EXTRA structure that the emulator was missing — see the live DOM
    // snapshot the operator captured from J14N9's chat:
    //   * outer .auxo-dropdown-trigger.leaveMessageWrapper.UvgX3P3fvcbG2HuKQesN
    //     wraps the Ie29C7uLyEjZzd8JeS8A row
    //   * bubble class list includes ``leaveMessage`` (so
    //     ``iD7SHBvMhm4OhfCsBGr1 leaveMessage messageNotMe``)
    //   * the avatar img is OMITTED when the bubble immediately follows
    //     the same customer's prior bubble (consecutive-message
    //     collapse).  We always include it for simplicity since the
    //     scraper's avatar filter handles both cases.
    // Agent-side bubbles in real Feige do NOT have leaveMessage — only
    // customer-side messageNotMe bubbles do.  Gate the extra classes on
    // !isAgent so the emulator's bot replies still look agent-shaped.
    const leaveMessageBubbleCls = isAgent ? bubbleCls : `leaveMessage ${bubbleCls}`;
    const leaveMessageRowWrapOpen = isAgent
      ? ""
      : `<div class="auxo-dropdown-trigger leaveMessageWrapper UvgX3P3fvcbG2HuKQesN" style="margin-bottom: 0px;">`;
    const leaveMessageRowWrapClose = isAgent ? "" : `</div>`;
    return `<div data-qa-id="qa-message-warpper" data-qa-message-id="" class="msgItemWrap" style="align-self: stretch;">
      <div data-id="${escHtml(m.id)}" class="tC9ap6QtAyeCD0jfuMns">
        ${leaveMessageRowWrapOpen}
        <div class="Ie29C7uLyEjZzd8JeS8A Gau7ODcdZ5yvIGvjSkxJ" style="${rowStyle}">
          <div class="xPPA9AYUzftDhhVtlENd Rovw4rA5pP7iHYJGNHMz" style="${avatarStyle}">
            <img class="Zq9KgucRnc7bRQfikvzQ" src="${escHtml(avatar)}" alt="头像">
          </div>
          <div style="max-width: 70%; width: auto;">
            ${senderLabel}
            <div style="${bubbleRowStyle}">
              <div class="iD7SHBvMhm4OhfCsBGr1 ${leaveMessageBubbleCls}" style="${bubbleColorStyle}"><pre style="${preStyle}"><span>${escHtml(m.text)}</span></pre></div>
              <div class="BPCj8gJpe3remPV_wWAv"></div>
              <div class="Vry36sSLfjhqZr9MfWnO">
                <div class="O4UWWFoQxgMq4AWHMq25 EjjnvGPGLbGHAIVS9HZf">${escHtml(fmtTime(m.ts))}</div>
                ${readStatus}
              </div>
            </div>
          </div>
        </div>
        ${leaveMessageRowWrapClose}
      </div>
    </div>`;
  }

  // ─────────────────────────── test-panel actions ────────────────────────────
  function openSession(cid) {
    if (!customers[cid]) return;
    state.activeCustomer = cid;
    const c = customers[cid];
    if (c.unreadCount > 0) {
      clearUnread(c);
      // also mark all agent messages as 已读 once the session is re-opened
      for (const d of c.dialogs) {
        for (const m of d.messages) {
          if (m.role === "agent" || m.role === "smart_cs") m.read = true;
        }
      }
      touchSeq(c);
    }
    renderChatList();
    renderThread();
  }

  // focus the middle panel on a customer without clearing their unread counter
  // (unread only clears when the human agent clicks the chat-item themselves)
  function focusCustomer(cid) {
    if (!customers[cid]) return;
    state.activeCustomer = cid;
  }

  function customerSendMessage(cid, text) {
    const c = customers[cid];
    const ts = Date.now();
    const prevMode = c.mode;
    const prevInCurrent = c.inCurrent;
    c.everChatted = true;
    if (c.firstUnreadAt == null) c.firstUnreadAt = ts;
    c.unreadCount += 1;
    // any new customer activity surfaces them in 当前会话 (keeps mode unchanged)
    c.inCurrent = true;
    if (c.mode === "closed") c.mode = "auto";
    state.clearedCurrent = false;
    setActiveTab("current");
    flog('customerSendMessage', { cid, text, prevMode, newMode: c.mode, prevInCurrent, newInCurrent: true, unread: c.unreadCount });

    pushMessage(c, {
      id: uid(),
      role: "customer",
      text,
      ts,
      time: fmtTime(ts),
    });
    emetric("q_sent", { cid, cust: c.name, text, ts });
    focusCustomer(cid);
    flashFooter(`${c.name} 发消息：${text}`);

    // trigger the default 智能客服 greeting the first time the dialog starts
    // while the customer is still in auto mode. If the dialog was previously
    // handed to a human and then returned to auto via 平台介入, the warn handler
    // sets d.allowBotRegreet so smart_cs greets once more.
    if (c.mode === "auto") {
      const d = c.dialogs[c.dialogs.length - 1];
      const hasBotReply = d.messages.some(m => m.role === "smart_cs");
      const canGreet = !hasBotReply || d.allowBotRegreet === true;
      if (canGreet) {
        const delay = 500 + Math.floor(Math.random() * 1500);
        setTimeout(() => {
          const botTs = Date.now();
          pushMessage(c, {
            id: uid(),
            role: "smart_cs",
            text: GREETING_REPLY,
            ts: botTs,
            time: fmtTime(botTs),
            senderLabel: "智能客服",
            read: true,
          });
          d.allowBotRegreet = false;
          renderChatList();
          if (state.activeCustomer === cid) renderThread();
        }, delay);
      }
    }
    renderChatList();
    if (state.activeCustomer === cid) renderThread();
  }

  // Customer sends a single IMAGE bubble (no text).  Same lifecycle
  // book-keeping as customerSendMessage — counts as unread, surfaces in
  // 当前会话, kicks the smart_cs greeter on first contact — but the
  // bubble itself is image-only (`kind: "image"`, `text: ""`).  The
  // upstream scraper now handles image-only bubbles end-to-end (Step 1
  // of the multimodal pipeline).
  function customerSendImage(cid, imageUrl) {
    const c = customers[cid];
    const ts = Date.now();
    const prevMode = c.mode;
    c.everChatted = true;
    if (c.firstUnreadAt == null) c.firstUnreadAt = ts;
    c.unreadCount += 1;
    c.inCurrent = true;
    if (c.mode === "closed") c.mode = "auto";
    state.clearedCurrent = false;
    setActiveTab("current");
    flog('customerSendImage', { cid, imageUrl, prevMode, newMode: c.mode, unread: c.unreadCount });

    pushMessage(c, {
      id: uid(),
      role: "customer",
      kind: "image",
      imageUrl,
      text: "",  // image-only bubble; scraper produces text="" + attachments=[{...}]
      ts,
      time: fmtTime(ts),
    });
    // image-only bubble does NOT trigger the smart-cs greeter — feels
    // unnatural to greet a bare image, and the live system also waits
    // for the text follow-up.  When this bubble is part of a 图文模式
    // sequence the accompanying text bubble will trigger greeting if
    // appropriate (and only once, due to hasBotReply guard).
    focusCustomer(cid);
    flashFooter(`${c.name} 发图片`);
    renderChatList();
    if (state.activeCustomer === cid) renderThread();
  }

  // ─── product-card bubble (mirrors customerSendImage for shape) ────────
  // Injects a customer-side bubble carrying the structured fields the
  // real Feige "来自电商小助手的推荐" widget exposes — the renderer
  // builds the .chatd-card DOM and the scraper's _cardData detector
  // fires off the data-id="..._template" + .chatd-card markers.
  // Like image bubbles, the data-id carries a `_template` suffix so
  // the scraper recognises the bubble type.  text="" because cards
  // have no .iD7SHBvMhm4OhfCsBGr1 text container — the scraper
  // synthesises the textual representation from product_cards[*]
  // after detection.
  function customerSendProductCard(cid, cardData) {
    const c = customers[cid];
    const ts = Date.now();
    const prevMode = c.mode;
    c.everChatted = true;
    if (c.firstUnreadAt == null) c.firstUnreadAt = ts;
    c.unreadCount += 1;
    c.inCurrent = true;
    if (c.mode === "closed") c.mode = "auto";
    state.clearedCurrent = false;
    setActiveTab("current");
    flog('customerSendProductCard', {
      cid,
      title: (cardData.title || '').slice(0, 30),
      price: (cardData.price_inter || '') + (cardData.price_decimal || ''),
      image_url: cardData.image_url,
      prevMode,
      newMode: c.mode,
      unread: c.unreadCount,
    });

    pushMessage(c, {
      id: uid() + "_template",  // _template suffix is the scraper's card-type marker
      role: "customer",
      kind: "product_card",
      cardData: cardData,
      text: "",  // card has no text bubble; scraper produces product_cards[*]
      ts,
      time: fmtTime(ts),
    });
    // Like image-only bubbles, card-only bubbles don't trigger the
    // smart-cs greeter — the accompanying text bubble (when paired)
    // will, and the hasBotReply guard prevents double-greeting.
    focusCustomer(cid);
    flashFooter(`${c.name} 发商品卡片`);
    renderChatList();
    if (state.activeCustomer === cid) renderThread();
  }

  // ─── 三种"图文模式"的发送序列 ─────────────────────────────────────────
  //
  // These three handlers stress-test different temporal orderings of the
  // (text, image) pair the customer can send.  Each fires multiple
  // bubbles asynchronously; the upstream front-desk dispatch will fire
  // after each new-bubble event the monitor catches, so the multimodal
  // pipeline must correctly thread the image through regardless of
  // which bubble is "latest" at dispatch time.
  //
  //   Mode 1 (文→图):     text  → 1s → image
  //   Mode 2 (图→文):     image → 1s → text
  //   Mode 3 (文→图→文):  prefix-text → 1s → image → 1s → suffix-text
  //
  // Mode 3 is the harshest test: when the dispatch picks up the LAST
  // bubble, that bubble is text — so the multimodal pipeline must look
  // back through the chat-thread context to surface the image attached
  // to the *previous* customer bubble.  If your pipeline drops the
  // image in mode 3, you'll see a hallucinated reply with no image
  // grounding even though modes 1+2 work.

  // 2026-05-24 mt038: bare image, no text bubble.  Reproduces the
  // "[图片]" sidebar preview exactly — the trigger pattern that
  // mt038B's defer-on-attachment-marker code path needs to fire.
  // Distinct from customerSendImageText1/2/3, which always send at
  // least one text bubble alongside the image.
  function customerSendImageOnly(cid) {
    const imageUrl = pickRandom(SAMPLE_IMAGE_URLS);
    flog('customerSendImageOnly', { cid, imageUrl });
    customerSendImage(cid, imageUrl);
  }

  // ─── mt048C/D test: customer-pastes-URL scenarios ──────────────────
  // Fixed real Amazon URL (beach sandals product detail page).  Once
  // mt048D wires the browser-fetch route, eCan should open this URL in
  // a new tab and answer the customer's question from the fetched DOM
  // content.  For mt048C (detection only), the _ecan_url_* flags
  // should appear on the item right after PreDispatch enrich.
  const URL_SAMPLE_AMAZON_BEACH_SANDALS =
    "https://www.amazon.com/KuaiLu-Support-Comfortable-Walking-Sandals/" +
    "dp/B0C5ZRQS2X/ref=sr_1_7?crid=CUJPO2MJI1A2&dib=eyJ2IjoiMSJ9.-dPmHmpxzOQJoL_a4ibO8q" +
    "cts--_dViPAV0YBkOEA4qyh2KFXTBouSAsn0_vIb5blID5T87RNyFVrmlBMw9NuZT6SDbZFqPSqZPpzwHJRp" +
    "8Jwazk1ia_GZufCWkNpkQdYm-_JA4PF05p7X15SQ-kssm9O8BGooXXl6a5w66smiEOaebblWzaj4FtL8uiqZ" +
    "tCoG6j6LOtAz7Gbf-GBBrAkFiBrkJC6Oa_B8614tFoKN2P9Xl_FVAFHRsDhdEmdejBaeBXZSYRYYQLYFmWEA" +
    "EP4GxMQ7E8R4pede23-5A_AEY.dI7irOPsbpG7fw3Sc477w1L_lm_qi-Rrc2kiNb4QfY8&dib_tag=se&" +
    "keywords=beach%2Bsandals&qid=1779821100&sprefix=beach%2Bsan%27de%27l%27s%2Caps%2C229" +
    "&sr=8-7&th=1&psc=1";

  // Customer-question variants that embed the URL.  Topic = beach
  // sandals (KuaiLu) so eCan's bot can be evaluated on its ability to
  // extract product details + answer the question from the fetched
  // page (mt048D future work).
  const URL_QUESTION_TEMPLATES = [
    "你看下这款 {URL} 适合脚宽的人穿吗？",
    "{URL} 这款沙滩鞋海边玩水会不会容易坏？防水吗？",
    "请问 {URL} 现在有现货吗？最快几天能到？",
    "{URL} 这双有什么颜色和码数可选？我穿42码合适吗？",
    "{URL} 这款是男士的还是女士的？尺码偏大还是偏小？",
  ];

  function _fmtUrlQuestion(template) {
    return template.replace("{URL}", URL_SAMPLE_AMAZON_BEACH_SANDALS);
  }

  // Single bubble: text + URL mixed.  The most common shape — customer
  // types a question and pastes the URL in the same message.
  function customerSendUrlQuestion(cid) {
    const template = pickRandom(URL_QUESTION_TEMPLATES);
    const text = _fmtUrlQuestion(template);
    flog('customerSendUrlQuestion', {
      cid,
      template: template.slice(0, 60),
      url_host: "amazon.com",
      // mt048C/D test marker — eCan-side analysis can correlate.
      mt048c_test: true,
    });
    customerSendMessage(cid, text);
  }

  // Single bubble: URL only, no surrounding text.  Tests detection of
  // a bare URL bubble (worst case for URL extraction since there's no
  // accompanying question context).
  function customerSendUrlOnly(cid) {
    flog('customerSendUrlOnly', {
      cid,
      url_host: "amazon.com",
      mt048c_test: true,
    });
    customerSendMessage(cid, URL_SAMPLE_AMAZON_BEACH_SANDALS);
  }

  // Two-bubble burst: URL first, follow-up question 1-2s later.  Tests
  // the burst-rebuild path (mt041B) carrying the URL through to the
  // dispatched payload.
  function customerSendUrlThenText(cid) {
    flog('customerSendUrlThenText.start', { cid, mt048c_test: true });
    customerSendMessage(cid, URL_SAMPLE_AMAZON_BEACH_SANDALS);
    const delay = 800 + Math.floor(Math.random() * 1500);
    setTimeout(() => {
      const followUps = [
        "这款怎么样？质量好吗",
        "你们家有类似的款吗？",
        "海边穿合适吗",
        "尺码偏大还是偏小？",
      ];
      const text = pickRandom(followUps);
      flog('customerSendUrlThenText.followup', { cid, text, delay_ms: delay });
      customerSendMessage(cid, text);
    }, delay);
  }

  // 2026-05-25 J14N9 wrap-1 repro: push a system "用户正在查看商品" marker
  // into the chat thread.  Sidebar's last_message becomes
  // "用户正在查看商品", the chat thread gets a wrap with no row
  // container (so scrapers skip it).  This is what real Feige emits
  // when the customer opens a product page in the same Feige tab —
  // triggers dom_observed but carries no actual customer message.
  // Live J14N9 trace 2026-05-25 12:35:31.
  function customerSendBrowsingMarker(cid, browsingData) {
    const c = customers[cid];
    const ts = Date.now();
    const data = browsingData || pickRandom(SAMPLE_PRODUCT_CARDS);
    c.everChatted = true;
    if (c.firstUnreadAt == null) c.firstUnreadAt = ts;
    c.unreadCount += 1;
    c.inCurrent = true;
    if (c.mode === "closed") c.mode = "auto";
    state.clearedCurrent = false;
    setActiveTab("current");
    flog('customerSendBrowsingMarker', {
      cid,
      title: (data.title || '').slice(0, 30),
    });
    pushMessage(c, {
      id: uid() + "_template",   // data-id ends in _template, matches J14N9 wrap1
      role: "customer",
      kind: "system_browsing",
      browsingData: data,
      text: "用户正在查看商品",   // becomes sidebar last_message
      ts,
      time: fmtTime(ts),
    });
    focusCustomer(cid);
    flashFooter(`${c.name} 用户正在查看商品`);
    renderChatList();
    if (state.activeCustomer === cid) renderThread();
  }

  // 2026-05-25 J14N9 full-scenario reproducer.
  //
  // Replays the exact 12:34-12:36 sequence from the live customer
  // trace where the bot ignored a real customer for 7+ minutes:
  //
  //   t+0     store_auto_greeting (system, fired by chat entry)
  //   t+2s    customer clicks 转人工
  //   t+85s   "用户正在查看商品" system marker (wrap1 shape)
  //   t+87s   customer pastes product card (wrap2 shape)
  //   t+100s  customer types text "夏天能不能便宜点" (wrap3 leaveMessage)
  //
  // We compress the timeline to 0/1.5/3/5/7s so the test completes
  // quickly.  Real-time spread isn't needed to reproduce the bug;
  // sequencing is.
  //
  // To repro the mt040A defer correctly: BEFORE clicking this button,
  // click "重置所有聊天记录" so the bot starts fresh.  Then watch the
  // log for `mt040A defer dispatch ... store_auto_greeting` and
  // `mt040A defer dispatch ... transfer_to_human_label` — both should
  // fire and the bot should NOT dispatch a hallucinated reply at the
  // card/text steps.
  function reproJ14N9Scenario(cid) {
    const c = customers[cid] || customers["B"];
    if (!c) {
      flashFooter("J14N9 重现失败：找不到客户");
      return;
    }
    const cidFinal = c.id;
    flog('reproJ14N9Scenario.start', { cid: cidFinal });
    flashFooter(`重现 J14N9 现场 (5 步)`);

    // Step 1 (t+0): store auto-greeting — already happens implicitly
    // when customer first interacts.  Skip; the test starts from the
    // greeting being implicit.

    // Step 2 (t+0): 转人工 request.
    customerRequestHuman(cidFinal);

    // Step 3 (t+1.5s): "用户正在查看商品" marker.
    setTimeout(() => {
      customerSendBrowsingMarker(cidFinal);
    }, 1500);

    // Step 4 (t+3s): product card (same NASA T-shirt as the original
    // trace — pick the 3rd entry which most closely matches in title).
    setTimeout(() => {
      const card = SAMPLE_PRODUCT_CARDS[2] || pickRandom(SAMPLE_PRODUCT_CARDS);
      customerSendProductCard(cidFinal, card);
    }, 3000);

    // Step 5 (t+5s): customer's text question.
    setTimeout(() => {
      customerSendMessage(cidFinal, "这款呢，夏天能不能便宜点");
      flog('reproJ14N9Scenario.done', { cid: cidFinal });
    }, 5000);

    // Step 6 (t+45s, optional): customer rephrases (gives the bot
    // another chance after mt017's 120s human-intervention TTL would
    // have expired in the original trace; we shorten to 45s).
    setTimeout(() => {
      customerSendMessage(cidFinal, "这款透气吗？现在是夏天 能不能便宜点");
      flog('reproJ14N9Scenario.rephrase', { cid: cidFinal });
    }, 45000);
  }

  // ─── mt017/18/21 repro: human-types-directly into Feige ────────────
  // Real-world trigger: a human customer-service staff member opens
  // the same chat in their Feige tab and types a reply directly,
  // bypassing the eCan bot.  eCan's mt017 detector scrapes the chat
  // thread, sees an agent bubble whose text isn't in the recent-
  // reply ledger, and marks the question as human-handled (the bot
  // aborts mid-flight if before the LLM call, or no-ops if after).
  //
  // We push role:"agent" with read:true (a real human reply is read
  // immediately on the staff side) so it lands in the chat thread
  // exactly the way the production scraper would see it.  No unread
  // bump — this is an outbound message, not a customer one.
  //
  // 2026-05-26 mt048B test support — TWO pools so the LLM judge in
  // eCan can be exercised:
  //   * RELEVANT — substantive answers that DO address typical questions
  //     (judge should return answered=True → bot reply dropped).
  //   * OFFTOPIC — acknowledgements, holding phrases, generic greetings
  //     that DON'T answer anything (judge should return answered=False
  //     → bot reply allowed through).
  // The original ``HUMAN_REPLY_POOL`` kept as alias for backwards compat
  // with any operator scripts that grep for the constant.
  const HUMAN_REPLY_RELEVANT_POOL = [
    "亲，这款现在没有库存了哦，建议您看看其他款。",
    "已为您申请补偿，请您耐心等待审核结果。",
    "好的，已为您备注，明天会发顺丰快递哦。",
    "这件商品支持7天无理由退换货哦，您放心购买。",
    "尺码偏小，建议您拍大一码哦。",
    "正常码，按平时穿就行。",
    "包邮的哦，新疆西藏除外。",
    "现在下单可享受满50减10优惠哦。",
  ];
  const HUMAN_REPLY_OFFTOPIC_POOL = [
    "在的，您说。",
    "您好，请稍等一下。",
    "这边帮您查询一下，请稍等。",
    "好的，您稍等。",
    "您好，这边人工客服为您服务。请问还有什么需要帮忙的吗？",
    "马上回复您。",
    "稍等一下哦~",
  ];
  // Backwards-compat alias.  Old code paths that pulled from the unified
  // pool now get a mix of both flavors.
  const HUMAN_REPLY_POOL = HUMAN_REPLY_RELEVANT_POOL.concat(HUMAN_REPLY_OFFTOPIC_POOL);

  function _pickHumanReplyText(flavor) {
    if (flavor === "relevant") return pickRandom(HUMAN_REPLY_RELEVANT_POOL);
    if (flavor === "offtopic") return pickRandom(HUMAN_REPLY_OFFTOPIC_POOL);
    return pickRandom(HUMAN_REPLY_POOL);
  }

  function customerSimulateHumanReply(cid, text, flavor) {
    const c = customers[cid];
    if (!c) return;
    const ts = Date.now();
    // ``flavor`` (mt048B): "relevant" | "offtopic" | undefined (random).
    const replyText = text || _pickHumanReplyText(flavor);
    const flavorLabel = flavor || "any";
    c.everChatted = true;
    c.inCurrent = true;
    if (c.mode === "closed") c.mode = "auto";
    state.clearedCurrent = false;
    setActiveTab("current");
    flog('customerSimulateHumanReply', {
      cid,
      text: replyText.slice(0, 40),
      mode: c.mode,
      flavor: flavorLabel,
      // mt048B: tag so eCan-side analysis can correlate emulator action
      // with judge decisions in the trace.
      mt048b_test: true,
    });
    pushMessage(c, {
      id: uid(),
      role: "agent",
      text: replyText,
      ts,
      time: fmtTime(ts),
      senderLabel: "人工客服",
      read: true,
    });
    focusCustomer(cid);
    flashFooter(`${c.name} ← 人工客服直接回复 (${flavorLabel})`);
    renderChatList();
    if (state.activeCustomer === cid) renderThread();
  }

  // ─── mt048B: race-mode human intervention during 并发消息 flood ─────
  // Fires the standard concurrent-messages flood and, for ``ratio``
  // fraction of the participating customers, also injects a human
  // bubble during the bot's response window so the runner.py drop
  // check + LLM judge get exercised under flood pressure.
  //
  // ``options.timing`` controls WHEN the human bubble lands:
  //   "before" — fires 500-2000 ms AFTER customer sends Q (likely
  //     before bot reply lands; tests the pre-send guard path).
  //   "after"  — fires 8000-12000 ms after Q (likely after bot reply
  //     has landed; tests that mt017 doesn't fire spurious drops).
  //   "race"   — random per-customer; useful for stress.
  // ``options.flavor`` is forwarded to customerSimulateHumanReply.
  function runConcurrentMessagesWithHumanIntervention(options) {
    options = options || {};
    const ratio = typeof options.ratio === "number"
      ? Math.max(0, Math.min(1, options.ratio))
      : 0.5;
    const timing = options.timing || "race";
    const flavor = options.flavor || "any";
    flog("mt048b.flood_with_intervention.start", { ratio, timing, flavor });
    flashFooter(`并发消息 + 人工干预 (ratio=${ratio}, timing=${timing}, flavor=${flavor})`);
    runConcurrentMessages();
    const cids = Object.keys(customers).filter((k) => customers[k].mode !== "closed");
    const picked = cids.filter(() => Math.random() < ratio);
    picked.forEach((cid) => {
      let delay = 0;
      if (timing === "before") {
        delay = 500 + Math.floor(Math.random() * 1500); // 0.5-2.0s
      } else if (timing === "after") {
        delay = 8000 + Math.floor(Math.random() * 4000); // 8-12s
      } else {
        // race: random
        delay = 500 + Math.floor(Math.random() * 11500); // 0.5-12s
      }
      setTimeout(() => {
        if (!customers[cid]) return;
        flog("mt048b.intervention.fire", { cid, delay_ms: delay, timing, flavor });
        customerSimulateHumanReply(cid, undefined, flavor);
      }, delay);
    });
    flog("mt048b.flood_with_intervention.scheduled", {
      picked_count: picked.length,
      total_active: cids.length,
    });
  }

  // ─── mt030 repro: historical-session bubble (stale Q+A pair) ─────────
  // Real-world trigger: after a process restart, the chat thread for a
  // customer still contains a previous-session Q (customer) followed by
  // an A (agent reply we already sent yesterday).  The sidebar may
  // still surface the old Q as the unread "preview" because the
  // customer hasn't dismissed the dialog.  Fresh eCan process has no
  // customer_last_dispatched_msg_id baseline for this customer, so the
  // legacy mt019 dedup doesn't fire — front-desk dispatches the old Q
  // as if new.  mt030's scrape-time agent.index > customer.index
  // guard is the stateless safety net that catches this; reproduce
  // it by injecting the stale Q+A pair with a small unread bump on
  // the sidebar so the customer appears in 当前会话.
  const HISTORICAL_QA_PAIRS = [
    { q: "你们默认走什么快递？", a: "您好，我们默认一般是走中通快递哦，部分地区走韵达。" },
    { q: "退货的运费谁出？", a: "亲，质量问题我们承担运费，无理由退货是您承担哦。" },
    { q: "这款会缩水吗？", a: "正常机洗或手洗都可以的，建议冷水洗，不会明显缩水哦。" },
  ];

  function customerInjectHistoricalSession(cid) {
    const c = customers[cid];
    const pair = pickRandom(HISTORICAL_QA_PAIRS);
    // Place both bubbles ~24h in the past so a human looking at the
    // thread can see they're old.  The eCan scraper doesn't read the
    // emulator-internal ts — it sees DOM order — so the index-test
    // (agent.index > customer.index) is what actually triggers mt030.
    const baseTs = Date.now() - 24 * 3600 * 1000;
    c.everChatted = true;
    c.inCurrent = true;
    if (c.mode === "closed") c.mode = "auto";
    state.clearedCurrent = false;
    setActiveTab("current");
    flog('customerInjectHistoricalSession', { cid, q: pair.q, a: pair.a.slice(0, 30) });
    // Stale customer Q
    pushMessage(c, {
      id: uid(),
      role: "customer",
      text: pair.q,
      ts: baseTs,
      time: fmtTime(baseTs),
      read: true,
    });
    // Stale agent A (we already replied yesterday)
    pushMessage(c, {
      id: uid(),
      role: "agent",
      text: pair.a,
      ts: baseTs + 30 * 1000,
      time: fmtTime(baseTs + 30 * 1000),
      senderLabel: "客服",
      read: true,
    });
    // Bump unread by 1 + set firstUnreadAt to NOW so the sidebar
    // surfaces this customer as actionable.  The sidebar preview
    // continues to show the stale Q (last_message) because no fresher
    // customer bubble exists — that's the exact misleading state
    // mt030 was built to handle.
    c.unreadCount = Math.max(c.unreadCount, 1);
    if (c.firstUnreadAt == null) c.firstUnreadAt = Date.now();
    c.lastMsg = pair.q;
    focusCustomer(cid);
    flashFooter(`${c.name} 历史会话注入 (Q+A 已存在)`);
    renderChatList();
    if (state.activeCustomer === cid) renderThread();
  }

  function customerSendImageText1(cid) {
    const text = pickRandom(IMG_TEXT_FULL_POOL);
    const imageUrl = pickRandom(SAMPLE_IMAGE_URLS);
    flog('customerSendImageText.start', { cid, mode: 1, text, imageUrl });
    customerSendMessage(cid, text);
    setTimeout(() => {
      customerSendImage(cid, imageUrl);
      flog('customerSendImageText.done', { cid, mode: 1 });
    }, 1000);
  }

  function customerSendImageText2(cid) {
    const text = pickRandom(IMG_TEXT_FULL_POOL);
    const imageUrl = pickRandom(SAMPLE_IMAGE_URLS);
    flog('customerSendImageText.start', { cid, mode: 2, text, imageUrl });
    customerSendImage(cid, imageUrl);
    setTimeout(() => {
      customerSendMessage(cid, text);
      flog('customerSendImageText.done', { cid, mode: 2 });
    }, 1000);
  }

  function customerSendImageText3(cid) {
    const [prefix, suffix] = pickRandom(IMG_TEXT_SPLIT_POOL);
    const imageUrl = pickRandom(SAMPLE_IMAGE_URLS);
    flog('customerSendImageText.start', { cid, mode: 3, prefix, suffix, imageUrl });
    customerSendMessage(cid, prefix);
    setTimeout(() => {
      customerSendImage(cid, imageUrl);
      setTimeout(() => {
        customerSendMessage(cid, suffix);
        flog('customerSendImageText.done', { cid, mode: 3 });
      }, 1000);
    }, 1000);
  }

  // ─── 商品卡片测试 — 四种模式 ───────────────────────────────────────────
  //   Mode 0 (card-only):  card alone, no text — bare product card
  //   Mode 1 (text→card):  customer typed a question, then card rendered
  //   Mode 2 (card→text):  card rendered, then text follow-up
  //   Mode 3 (text→card→text): prefix-text → card → suffix-text
  //
  // The realistic UX is mode 1 (customer pastes a Douyin product URL
  // AFTER typing a question) and mode 2 (URL first, then question).
  // Mode 3 stresses the multi-bubble burst walk-back: scraper must
  // capture both text fragments + card into the same Q&A turn.

  function customerSendProductCard0(cid) {
    const card = pickRandom(SAMPLE_PRODUCT_CARDS);
    flog('customerSendProductCard.start', { cid, mode: 0, title: card.title.slice(0, 20) });
    customerSendProductCard(cid, card);
    flog('customerSendProductCard.done', { cid, mode: 0 });
  }

  function customerSendProductCardText1(cid) {
    const text = pickRandom(PRODUCT_CARD_TEXT_FULL_POOL);
    const card = pickRandom(SAMPLE_PRODUCT_CARDS);
    flog('customerSendProductCard.start', { cid, mode: 1, text, title: card.title.slice(0, 20) });
    customerSendMessage(cid, text);
    setTimeout(() => {
      customerSendProductCard(cid, card);
      flog('customerSendProductCard.done', { cid, mode: 1 });
    }, 1000);
  }

  function customerSendProductCardText2(cid) {
    const text = pickRandom(PRODUCT_CARD_TEXT_FULL_POOL);
    const card = pickRandom(SAMPLE_PRODUCT_CARDS);
    flog('customerSendProductCard.start', { cid, mode: 2, text, title: card.title.slice(0, 20) });
    customerSendProductCard(cid, card);
    setTimeout(() => {
      customerSendMessage(cid, text);
      flog('customerSendProductCard.done', { cid, mode: 2 });
    }, 1000);
  }

  function customerSendProductCardText3(cid) {
    const [prefix, suffix] = pickRandom(PRODUCT_CARD_TEXT_SPLIT_POOL);
    const card = pickRandom(SAMPLE_PRODUCT_CARDS);
    flog('customerSendProductCard.start', { cid, mode: 3, prefix, suffix, title: card.title.slice(0, 20) });
    customerSendMessage(cid, prefix);
    setTimeout(() => {
      customerSendProductCard(cid, card);
      setTimeout(() => {
        customerSendMessage(cid, suffix);
        flog('customerSendProductCard.done', { cid, mode: 3 });
      }, 1000);
    }, 1000);
  }

  function customerRequestHuman(cid) {
    const c = customers[cid];
    const ts = Date.now();
    const prevMode = c.mode;
    c.everChatted = true;
    if (c.firstUnreadAt == null) c.firstUnreadAt = ts;
    c.unreadCount += 1;
    // surface immediately so the customer appears in 当前会话 on the first click
    c.inCurrent = true;
    state.clearedCurrent = false;
    setActiveTab("current");
    flog('customerRequestHuman', { cid, prevMode, willBecomeMode: 'human' });

    // customer msg: 转人工
    pushMessage(c, {
      id: uid(),
      role: "customer",
      text: "转人工",
      ts,
      time: fmtTime(ts),
    });
    focusCustomer(cid);
    flashFooter(`${c.name} 请求人工客服`);

    // system assign + welcome bubble
    setTimeout(() => {
      const ts1 = Date.now();
      pushMessage(c, {
        id: uid() + "_CsAssign_",
        role: "system",
        systemKind: "assign",
        text: `客服${SHOP_NAME}接入`,
        ts: ts1,
        time: fmtTime(ts1),
      });
      const ts2 = ts1 + 200;
      pushMessage(c, {
        id: uid() + "_Welcome_",
        role: "agent",
        text: HUMAN_WELCOME,
        senderLabel: "系统消息",
        ts: ts2,
        time: fmtTime(ts2),
        read: false,
      });
      c.mode = "human";
      renderChatList();
      if (state.activeCustomer === cid) renderThread();
    }, 200);

    renderChatList();
    if (state.activeCustomer === cid) renderThread();
  }

  function customerTimeoutClose(cid) {
    const c = customers[cid];
    if (!c.everChatted) {
      flashFooter(`${c.name} 尚无对话，无法关闭会话`);
      return;
    }
    const ts = Date.now();
    pushMessage(c, {
      id: uid() + "_CloseNoProcess_",
      role: "system",
      systemKind: "close",
      text: "用户超时未回复，系统关闭会话",
      ts,
      time: fmtTime(ts),
    });
    // wrap up the current dialog
    const d = c.dialogs[c.dialogs.length - 1];
    if (d) d.closed = true;
    c.mode = "closed";
    c.inCurrent = false;
    c.unreadCount = 0;
    c.firstUnreadAt = null;
    focusCustomer(cid);
    flashFooter(`${c.name} 超时 · 会话已关闭`);
    flog('customerTimeoutClose', { cid, mode: c.mode, inCurrent: c.inCurrent });

    renderChatList();
    if (state.activeCustomer === cid) renderThread();
  }

  function customerTimeoutWarn(cid) {
    const c = customers[cid];
    if (!c.everChatted) {
      flashFooter(`${c.name} 尚无对话，无法触发平台介入`);
      return;
    }
    const ts = Date.now();
    pushMessage(c, {
      id: uid() + "_PlatformWarn_",
      role: "system",
      systemKind: "warn",
      text: "当前会话已长时间未回复，若后续仍未回复，平台可能主动介入处理。",
      ts,
      time: fmtTime(ts),
    });
    // this clears 当前会话 and re-enters 智能客服 auto mode (per spec).
    // Flag the current dialog so smart_cs re-greets on the next customer msg
    // even though it has already greeted once.
    c.mode = "auto";
    c.inCurrent = false;
    c.unreadCount = 0;
    c.firstUnreadAt = null;
    const curDlg = c.dialogs[c.dialogs.length - 1];
    if (curDlg) curDlg.allowBotRegreet = true;
    focusCustomer(cid);
    flashFooter(`${c.name} 超时 · 平台介入提醒`);
    flog('customerTimeoutWarn', { cid, mode: c.mode, inCurrent: c.inCurrent });

    renderChatList();
    if (state.activeCustomer === cid) renderThread();
  }

  function clearCurrentSessions() {
    const before = customersSnapshot();
    state.clearedCurrent = true;
    for (const c of Object.values(customers)) {
      c.inCurrent = false;
      c.unreadCount = 0;
      c.firstUnreadAt = null;
    }
    flashFooter("已清除当前会话");
    flog('clearCurrentSessions', { before, after: customersSnapshot() });
    renderChatList();
  }

  // 2026-05-24 mt038F: deep reset of all chat threads.
  //
  // ``clearCurrentSessions`` only resets the sidebar (in-current /
  // unread flags) — each customer's ``dialogs[]`` is left intact so
  // the chat-thread DOM still carries every bubble ever pushed.  When
  // an operator runs ``并发消息`` multiple times in the same emulator
  // session, those accumulated bubbles include prior-flood
  // (customer Q + agent A) pairs.  eCan's PreDispatch enrich scrape
  // walks the thread and finds the prior pair as ``latest``, then
  // mt030's ``agent.idx > customer.idx → skip dispatch`` correctly
  // fires for what looks like an already-answered question — even
  // though the operator's NEW flood just enqueued a fresh question.
  //
  // Live trace 2026-05-24 14:21:54: mt030 skipped ALL 20 customers
  // at flood start because every chat thread still had the prior
  // flood's last reply at the tail; the new questions were behind
  // it in the sidebar but not yet promoted as the thread's latest
  // customer bubble.  Result: 3/20 customers (03/14/15) never
  // recovered and got only placeholders.
  //
  // This reset wipes ``dialogs[]`` so the next flood starts with
  // empty chat threads — matching the "first flood after reload"
  // baseline.  Customer list configuration (names, avatars, modes)
  // is preserved.
  function resetAllChatThreads() {
    const before = customersSnapshot();
    let dialogCount = 0;
    let messageCount = 0;
    for (const c of Object.values(customers)) {
      for (const d of c.dialogs) {
        messageCount += d.messages.length;
      }
      dialogCount += c.dialogs.length;
      // Wipe the dialog list — pushMessage creates a new empty dialog
      // lazily on the next customer message, so we don't need to seed
      // one here.
      c.dialogs = [];
      c.inCurrent = false;
      c.unreadCount = 0;
      c.firstUnreadAt = null;
      c.lastMsg = "";
      c.everChatted = false;
      // mode is intentionally preserved: operators may have set a
      // customer into "human" mode for a specific test scenario and
      // shouldn't lose it on reset.
    }
    state.clearedCurrent = true;
    flog('resetAllChatThreads', {
      cleared_customers: Object.keys(customers).length,
      cleared_dialogs: dialogCount,
      cleared_messages: messageCount,
      before,
      after: customersSnapshot(),
    });
    flashFooter(
      `重置所有聊天记录: ${Object.keys(customers).length}人 / ${dialogCount}会话 / ${messageCount}条消息`
    );
    renderChatList();
    renderThread();
  }

  function runConcurrentHumanTransfer() {
    const count = getStressCount();
    const ids = shuffle(ensureStressCustomers(count).slice());
    const startedAt = Date.now();
    flog('stress.concurrentHuman.start', { count, ids });
    flashFooter(`并发转人工：${count}人`);

    ids.forEach((cid) => {
      const firstDelayMs = randomInt(0, 1000);
      const transferDelayMs = randomInt(300, 1000);
      setTimeout(() => {
        customerSendMessage(cid, pickRandom(QUESTION_POOL));
        setTimeout(() => {
          customerRequestHuman(cid);
        }, transferDelayMs);
      }, firstDelayMs);
    });

    setTimeout(() => {
      flog('stress.concurrentHuman.scheduled', {
        count,
        elapsed_ms: Date.now() - startedAt,
        customers: customersSnapshot(),
      });
    }, 1100);
  }

  // 2026-05-24 mt038: weighted multimodal flood.
  //
  // Per-customer bucket draw using the 图文%/卡片% knobs:
  //   draw u ~ U(0,1):
  //     u <  imagePct                      → image bucket
  //     u <  imagePct + cardPct            → card bucket
  //     else                               → plain text bucket
  //
  // Within image bucket: uniform pick from [imageOnly, imageText1,
  // imageText2, imageText3].  Within card bucket: uniform pick from
  // [productCard0..3].  This guarantees every flood exercises bare
  // attachment markers ("[图片]"/"[商品]") AND interleaved-bubble
  // burst-walk-back paths, not just one or the other.
  const STRESS_IMAGE_MODES = [
    customerSendImageOnly,
    customerSendImageText1,
    customerSendImageText2,
    customerSendImageText3,
  ];
  const STRESS_CARD_MODES = [
    customerSendProductCard0,
    customerSendProductCardText1,
    customerSendProductCardText2,
    customerSendProductCardText3,
  ];

  function runConcurrentMessages() {
    const count = getStressCount();
    const ids = shuffle(ensureStressCustomers(count).slice());
    const imagePct = getStressImagePercent();
    const cardPct = getStressCardPercent();
    // Cap combined non-text at 100 — if operator over-allocates, keep
    // image as configured and shrink card to fit so the bucket order
    // (image takes precedence) is deterministic.
    const imagePctNorm = Math.min(100, imagePct);
    const cardPctNorm = Math.min(100 - imagePctNorm, cardPct);
    const imageThreshold = imagePctNorm / 100;
    const cardThreshold = (imagePctNorm + cardPctNorm) / 100;

    // Assign bucket per cid so the flog has a usable breakdown for
    // post-test analysis.
    const buckets = { text: [], image: [], card: [] };
    const planned = ids.map((cid) => {
      const u = Math.random();
      let bucket;
      if (u < imageThreshold) bucket = "image";
      else if (u < cardThreshold) bucket = "card";
      else bucket = "text";
      buckets[bucket].push(cid);
      return { cid, bucket };
    });

    const startedAt = Date.now();
    flog('stress.concurrentMessage.start', {
      count,
      imagePct: imagePctNorm,
      cardPct: cardPctNorm,
      textCount: buckets.text.length,
      imageCount: buckets.image.length,
      cardCount: buckets.card.length,
      ids,
    });
    flashFooter(
      `并发消息：${count}人 (文${buckets.text.length}/图${buckets.image.length}/卡${buckets.card.length})`
    );

    planned.forEach(({ cid, bucket }) => {
      setTimeout(() => {
        if (bucket === "image") {
          pickRandom(STRESS_IMAGE_MODES)(cid);
        } else if (bucket === "card") {
          pickRandom(STRESS_CARD_MODES)(cid);
        } else {
          customerSendMessage(cid, pickRandom(QUESTION_POOL));
        }
      }, randomInt(0, 1000));
    });

    setTimeout(() => {
      flog('stress.concurrentMessage.scheduled', {
        count,
        textCount: buckets.text.length,
        imageCount: buckets.image.length,
        cardCount: buckets.card.length,
        elapsed_ms: Date.now() - startedAt,
        customers: customersSnapshot(),
      });
    }, 1100);
  }

  // ─── harness-driven flood (2026-06-02) ─────────────────────────────────
  // Same spread as runConcurrentMessages but parameterised (no DOM reads),
  // so the round-controller can trigger a deterministic N-customer flood via
  // POST /api/emulation/flood. Defaults to text-only (imagePct=cardPct=0) so
  // the 4 metrics are computed over clean query/reply pairs.
  function runHarnessFlood(n, imagePct, cardPct, opts) {
    const count = Math.max(1, Math.min(STRESS_MAX_COUNT, parseInt(n, 10) || STRESS_DEFAULT_COUNT));
    imagePct = Math.max(0, Math.min(100, parseInt(imagePct, 10) || 0));
    cardPct = Math.max(0, Math.min(100 - imagePct, parseInt(cardPct, 10) || 0));
    // ── ramp options (2026-06-03, mt070 blackout repro) ──────────────────
    // joinSpreadSec  — stagger the N customers' FIRST message across this
    //                  window (so concurrency ramps up like the real test
    //                  where the 6th customer joined ~15 min in) instead of
    //                  all landing in the first second.
    // followUpRounds — after joining, each customer sends this many further
    //                  questions, one every followUpIntervalMs. Each turn
    //                  appends bubbles, so the thread DOM GROWS and the
    //                  load-dependent scrape stall climbs past the 6s
    //                  detection-timeout cliff — the "slows after 8 min".
    opts = opts || {};
    const joinSpreadMs = Math.max(0, Math.min(1800000, (parseInt(opts.joinSpreadSec, 10) || 0) * 1000));
    const followUpRounds = Math.max(0, Math.min(60, parseInt(opts.followUpRounds, 10) || 0));
    const followUpIntervalMs = Math.max(3000, Math.min(600000, parseInt(opts.followUpIntervalMs, 10) || 30000));
    const ids = shuffle(ensureStressCustomers(count).slice());
    const imageThreshold = imagePct / 100;
    const cardThreshold = (imagePct + cardPct) / 100;
    flog('harness.flood.start', {
      count, imagePct, cardPct,
      joinSpreadSec: Math.round(joinSpreadMs / 1000), followUpRounds, followUpIntervalMs,
    });
    flashFooter(`harness flood: ${count}人 (图${imagePct}% 卡${cardPct}% ` +
      `ramp${Math.round(joinSpreadMs / 1000)}s ×${followUpRounds})`);
    ids.forEach((cid, idx) => {
      const u = Math.random();
      let bucket = "text";
      if (u < imageThreshold) bucket = "image";
      else if (u < cardThreshold) bucket = "card";
      // Evenly stagger joins across joinSpreadMs (+ small jitter); falls back
      // to the legacy 0-1s burst when joinSpreadMs is 0.
      const joinAt = joinSpreadMs > 0
        ? Math.floor((idx + 1) / (ids.length + 1) * joinSpreadMs) + randomInt(0, 1000)
        : randomInt(0, 1000);
      setTimeout(() => {
        if (bucket === "image") pickRandom(STRESS_IMAGE_MODES)(cid);
        else if (bucket === "card") pickRandom(STRESS_CARD_MODES)(cid);
        else customerSendMessage(cid, pickRandom(QUESTION_POOL));
      }, joinAt);
      // Follow-ups begin one interval after this customer's own join, so the
      // per-customer cadence is independent of when they joined.
      for (let round = 1; round <= followUpRounds; round++) {
        setTimeout(() => {
          customerSendMessage(cid, pickRandom(FOLLOW_UP_POOL));
        }, joinAt + round * followUpIntervalMs + randomInt(0, 1500));
      }
    });
  }

  // Poll the server for harness commands (~1/s). The round-controller
  // queues a flood via POST /api/emulation/flood; we run it once here.
  function pollHarnessCommand() {
    fetch('/api/emulation/command', { cache: 'no-store' })
      .then((r) => r.json())
      .then((data) => {
        _runActive = !!(data && data.run_active);
        const cmd = data && data.command;
        if (cmd && cmd.cmd === 'flood') {
          runHarnessFlood(cmd.n, cmd.imagePct, cmd.cardPct, {
            joinSpreadSec: cmd.joinSpreadSec,
            followUpRounds: cmd.followUpRounds,
            followUpIntervalMs: cmd.followUpIntervalMs,
          });
        }
      })
      .catch(() => { /* ignore — server may not be up yet */ });
  }
  setInterval(pollHarnessCommand, 1000);

  // ─────────────────── real-site sim: LLM fault + follow-ups ────────────────
  //
  // These knobs write to emulation_config.json via /api/emulation/config; the
  // eCan app (when started with ECAN_EMULATION_TEST_FLAGS=1) reads that JSON
  // before every LLM call and synthesizes the configured fault. This lets us
  // reproduce the customer's billing-exhausted slowdown locally without
  // actually depleting an OpenAI key.

  // Follow-up product-detail questions — these are designed to require the
  // bot to remember the prior turn's RAG result. The customer's hypothesis
  // was that long conversations regressed in quality; this exercises that
  // path so we can see what the Q&A model actually has access to after
  // several turns.
  const FOLLOW_UP_POOL = [
    "那L码呢？",
    "M码呢？",
    "胸围呢？腰围呢？",
    "有红色的吗？",
    "有别的颜色吗？",
    "弹力面料的呢？",
    "如果偏胖建议怎么选？",
    "童装呢？童装的尺码表？",
    "有更详细的尺码表吗？",
    "刚才那个尺码是平铺测量吗？",
    "牛仔裤是高腰还是低腰？",
    "袖长大概是多少？",
    "肩宽是多少？",
    "面料含棉量呢？",
    "适合什么季节穿？",
  ];

  async function saveLlmFaultConfig() {
    const probability = Math.max(0, Math.min(100, Number($("#llmFault429Probability").value || 0)));
    const errorMode = $("#llmFaultErrorMode").value || "429";
    const payload = {
      llmFault: {
        inject429Probability: probability / 100,
        errorMode,
      },
    };
    const res = await fetch("/api/emulation/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "save failed");
    flog("llmFault.saved", payload.llmFault);
    flashFooter(`已保存 LLM 故障设定: ${probability}% ${errorMode}`);
    return data.config;
  }

  async function clearLlmFaultConfig() {
    $("#llmFault429Probability").value = 0;
    const payload = { llmFault: { inject429Probability: 0, errorMode: "429" } };
    const res = await fetch("/api/emulation/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "save failed");
    flog("llmFault.cleared", {});
    flashFooter("已关闭 LLM 故障注入");
    return data.config;
  }

  // ─── mt019/20 repro: RAG fault injection ─────────────────────────────
  // Mirrors the LLM-fault pattern.  Reads from emulation_config.json by
  // the eCan local_rag_mcp.rag_query() pre-check (under
  // ECAN_EMULATION_TEST_FLAGS=1) which sleeps or raises before the real
  // LightRAG call.  mt019 capped rag_query at 10s after a customer trace
  // where the MCP hung indefinitely; this lets us trigger that exact
  // failure mode without bringing down a real LightRAG server.
  //
  // Modes:
  //   "hang"  → sleep for ``hangSeconds`` (default 30s — well past mt019
  //              10s cap so we exercise the timeout branch)
  //   "error" → raise a generic ValueError immediately (exercises
  //              error-path fallbacks)
  async function saveRagFaultConfig() {
    const probability = Math.max(0, Math.min(100, Number($("#ragFaultProbability").value || 0)));
    const mode = $("#ragFaultMode").value || "hang";
    const hangSeconds = Math.max(0, Math.min(120, Number($("#ragFaultHangSeconds").value || 30)));
    const payload = {
      ragFault: {
        injectProbability: probability / 100,
        mode,
        hangSeconds,
      },
    };
    const res = await fetch("/api/emulation/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "save failed");
    flog("ragFault.saved", payload.ragFault);
    flashFooter(`已保存 RAG 故障设定: ${probability}% ${mode}${mode === "hang" ? " " + hangSeconds + "s" : ""}`);
    return data.config;
  }

  async function clearRagFaultConfig() {
    $("#ragFaultProbability").value = 0;
    const payload = { ragFault: { injectProbability: 0, mode: "hang", hangSeconds: 30 } };
    const res = await fetch("/api/emulation/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "save failed");
    flog("ragFault.cleared", {});
    flashFooter("已关闭 RAG 故障注入");
    return data.config;
  }

  let multiRoundState = { running: false, timers: [] };

  async function startMultiRoundChat() {
    if (multiRoundState.running) {
      flashFooter("多轮对话已在运行中，先点'停止'");
      return;
    }
    const rounds = Math.max(0, Math.min(10, Number($("#followUpRounds").value || 0)));
    const intervalMs = Math.max(5000, Number($("#followUpIntervalMs").value || 25000));
    if (rounds <= 0) {
      flashFooter("追问轮数为 0，请填一个 ≥ 1 的数字");
      return;
    }

    // Persist to emulation_config so the eCan app can also see the setting
    // if it wants to (currently only the front-end uses this; the JSON
    // record is for debugging/telemetry consistency).
    await fetch("/api/emulation/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ followUp: { rounds, intervalMs } }),
    });

    const count = getStressCount();
    const ids = shuffle(ensureStressCustomers(count).slice());
    flog("multiRound.start", { customers: count, rounds, intervalMs });
    flashFooter(`多轮对话: ${count}客户 × (1 + ${rounds}追问)`);
    multiRoundState.running = true;
    multiRoundState.timers = [];

    // Initial wave: each customer sends their first question with a small
    // random jitter so they don't all collide on the millisecond.
    ids.forEach((cid) => {
      const t0 = setTimeout(() => {
        customerSendMessage(cid, pickRandom(QUESTION_POOL));
      }, randomInt(0, 1000));
      multiRoundState.timers.push(t0);
    });

    // Follow-ups: every intervalMs, each customer sends another question.
    // We don't check whether the bot replied — real customers don't wait,
    // and this is the worst-case stress pattern.
    for (let round = 1; round <= rounds; round++) {
      ids.forEach((cid) => {
        const delay = round * intervalMs + randomInt(0, 2000);
        const t = setTimeout(() => {
          if (!multiRoundState.running) return;
          customerSendMessage(cid, pickRandom(FOLLOW_UP_POOL));
        }, delay);
        multiRoundState.timers.push(t);
      });
    }

    // Auto-clear the "running" flag after the last follow-up fires.
    const stopT = setTimeout(() => {
      multiRoundState.running = false;
      flog("multiRound.completed", { customers: count, rounds });
      flashFooter("多轮对话已结束");
    }, (rounds + 1) * intervalMs + 5000);
    multiRoundState.timers.push(stopT);
  }

  function stopMultiRoundChat() {
    if (!multiRoundState.running && multiRoundState.timers.length === 0) {
      flashFooter("多轮对话未运行");
      return;
    }
    multiRoundState.timers.forEach((t) => clearTimeout(t));
    multiRoundState.timers = [];
    multiRoundState.running = false;
    flog("multiRound.stopped", {});
    flashFooter("已停止多轮对话");
  }

  // ───────────────────────────── agent send flow ────────────────────────────
  // The agent calls feige_send_message which types into the textarea and clicks
  // the send button.  This handler appends the typed text as an agent bubble
  // into the currently-open customer's thread.
  function appendAgentMessage(c, text, ts) {
    pushMessage(c, {
      id: uid(),
      role: "agent",
      text,
      ts,
      time: fmtTime(ts),
      senderLabel: SHOP_NAME,
      read: false,
    });
    emetric("agent_msg", {
      cid: c.id, cust: c.name, text,
      is_placeholder: isPlaceholderText(text), ts,
    });
    clearUnread(c);
    renderChatList();
    renderThread();
    flashFooter(`已发送给 ${c.name}: ${text.slice(0, 30)}`);
  }

  function temporarilyRemoveCompose(ms) {
    const compose = $("#im-input-box");
    if (!compose || !compose.parentNode) return;
    const parent = compose.parentNode;
    const next = compose.nextSibling;
    parent.removeChild(compose);
    flog("chaos.compose.removed", { ms });
    setTimeout(() => {
      if (compose.parentNode) return;
      parent.insertBefore(compose, next);
      flog("chaos.compose.restored", {});
    }, ms);
  }

  function handleAgentSend() {
    const input = $("#composeInput");
    const raw = String(input.value || "").replace(/\r\n/g, "\n");
    const text = raw.trim();
    if (!text) {
      flog('agentSend.empty', {});
      return;
    }
    // 2026-05-20 routing fix: read cid from the RENDERED thread DOM
    // (stamped by renderThread), NOT from state.activeCustomer which
    // can race with sidebar clicks under flood load.  This guarantees
    // the message goes to whichever customer's chat is visually
    // displayed at click time — consistent with the user's intent and
    // with the bot's per-customer-chat verification (chatScopeOk).
    const renderedCid = (threadEl && threadEl.dataset && threadEl.dataset.cid) || "";
    const stateCid = state.activeCustomer || "";
    if (renderedCid && stateCid && renderedCid !== stateCid) {
      flog('agentSend.cidMismatch', {
        rendered: renderedCid, state: stateCid, text: text.slice(0, 60),
      });
    }
    // Prefer the rendered cid; fall back to state if DOM not yet stamped
    const cid = renderedCid || stateCid;
    if (!cid) {
      flashFooter("没有已打开的会话，无法发送");
      flog('agentSend.noActiveCustomer', { text: text.slice(0, 60) });
      return;
    }
    if (!customers[cid]) {
      flashFooter("未知会话: " + cid);
      flog('agentSend.unknownCid', { cid: cid, text: text.slice(0, 60) });
      return;
    }
    flog('agentSend', { cid, text: text.slice(0, 80), activeMode: customers[cid].mode });
    const c = customers[cid];
    const ts = Date.now();
    input.value = "";
    const hit = chaosHit();
    if (hit && chaosConfig.send.blockClickMs > 0) {
      flog("chaos.send.block_click", { cid, ms: chaosConfig.send.blockClickMs });
      busyWait(chaosConfig.send.blockClickMs);
    }
    if (hit && chaosConfig.focus.rerenderDuringSend) {
      renderChatList();
      renderThread();
      flog("chaos.send.rerender", { cid });
    }
    if (hit && chaosConfig.focus.removeComposeDuringSend) {
      temporarilyRemoveCompose(chaosConfig.focus.removeComposeMs);
    }
    if (hit && chaosConfig.send.neverAppendAgent) {
      renderChatList();
      renderThread();
      flashFooter(`chaos: 未追加客服消息 ${c.name}`);
      flog("chaos.send.never_append", { cid, text: text.slice(0, 80) });
      return;
    }
    if (hit && chaosConfig.send.delayAgentAppendMs > 0) {
      const delay = chaosConfig.send.delayAgentAppendMs;
      flog("chaos.send.delay_append", { cid, delay_ms: delay });
      setTimeout(() => {
        appendAgentMessage(c, text, ts);
        flog("chaos.send.delayed_append_done", { cid });
      }, delay);
      return;
    }
    appendAgentMessage(c, text, ts);
  }

  // ────────────────────────────── wiring ────────────────────────────────────
  function setupEvents() {
    // tabs
    $$("#tabBar .tab").forEach(el => {
      el.addEventListener("click", () => {
        setActiveTab(el.dataset.tab);
        renderChatList();
      });
    });

    // settings popup toggle
    settingsRow.addEventListener("click", () => {
      settingsPopup.classList.toggle("hidden");
    });
    document.addEventListener("click", (ev) => {
      if (settingsPopup.classList.contains("hidden")) return;
      if (ev.target === settingsRow || settingsRow.contains(ev.target)) return;
      if (ev.target === settingsPopup || settingsPopup.contains(ev.target)) return;
      settingsPopup.classList.add("hidden");
    });

    // test buttons (right panel)
    $$(".panel-right .test-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const act = btn.dataset.action;
        const cid = btn.dataset.cid;
        switch (act) {
          case "sendMsg":         customerSendMessage(cid, pickRandom(QUESTION_POOL)); break;
          case "requestHuman":    customerRequestHuman(cid); break;
          case "timeoutClose":    customerTimeoutClose(cid); break;
          case "timeoutWarn":     customerTimeoutWarn(cid); break;
          case "sendImageText1":  customerSendImageText1(cid); break;
          case "sendImageText2":  customerSendImageText2(cid); break;
          case "sendImageText3":  customerSendImageText3(cid); break;
          case "sendProductCard0":     customerSendProductCard0(cid); break;
          case "sendProductCardText1": customerSendProductCardText1(cid); break;
          case "sendProductCardText2": customerSendProductCardText2(cid); break;
          case "sendProductCardText3": customerSendProductCardText3(cid); break;
          case "sendImageOnly":   customerSendImageOnly(cid); break;
          case "humanReply":      customerSimulateHumanReply(cid); break;
          // mt048B test triggers — flavor-tagged human-intervention bubbles.
          case "humanReplyRelevant": customerSimulateHumanReply(cid, undefined, "relevant"); break;
          case "humanReplyOfftopic": customerSimulateHumanReply(cid, undefined, "offtopic"); break;
          // mt048B race-mode floods — fire ``并发消息`` AND inject human
          // bubbles for ~50% of customers at controlled timings.
          case "floodHumanBefore":   runConcurrentMessagesWithHumanIntervention({ timing: "before", flavor: "relevant", ratio: 0.5 }); break;
          case "floodHumanAfter":    runConcurrentMessagesWithHumanIntervention({ timing: "after",  flavor: "relevant", ratio: 0.5 }); break;
          case "floodHumanRace":     runConcurrentMessagesWithHumanIntervention({ timing: "race",   flavor: "any",      ratio: 0.5 }); break;
          // mt048C/D test triggers — customer-pastes-URL scenarios.
          case "sendUrlQuestion":    customerSendUrlQuestion(cid); break;
          case "sendUrlOnly":        customerSendUrlOnly(cid); break;
          case "sendUrlThenText":    customerSendUrlThenText(cid); break;
          case "injectHistorical": customerInjectHistoricalSession(cid); break;
          case "sendBrowsingMarker": customerSendBrowsingMarker(cid); break;
          case "reproJ14N9":      reproJ14N9Scenario(cid); break;
          case "stressHuman":     runConcurrentHumanTransfer(); break;
          case "stressMessage":   runConcurrentMessages(); break;
          case "saveLlmFault":    saveLlmFaultConfig().catch((e) => flog("llmFault.save_failed", { error: String(e && e.message || e) })); break;
          case "clearLlmFault":   clearLlmFaultConfig().catch((e) => flog("llmFault.clear_failed", { error: String(e && e.message || e) })); break;
          case "saveRagFault":    saveRagFaultConfig().catch((e) => flog("ragFault.save_failed", { error: String(e && e.message || e) })); break;
          case "clearRagFault":   clearRagFaultConfig().catch((e) => flog("ragFault.clear_failed", { error: String(e && e.message || e) })); break;
          case "runMultiRoundChat": startMultiRoundChat().catch((e) => flog("multiRound.start_failed", { error: String(e && e.message || e) })); break;
          case "stopMultiRoundChat": stopMultiRoundChat(); break;
          case "clearCurrent":    clearCurrentSessions(); break;
          case "resetAllThreads": resetAllChatThreads(); break;
          case "saveChaos":       saveChaosConfig(collectChaosConfigFromControls()).catch((e) => flog("chaos.manual_save_failed", { error: String(e && e.message || e) })); break;
          case "resetChaos":      resetChaosConfig().catch((e) => flog("chaos.reset_failed", { error: String(e && e.message || e) })); break;
          case "runFakeHarness":  runChaosHarness("fake-runtime").catch((e) => flog("chaos.harness.failed", { mode: "fake-runtime", error: String(e && e.message || e) })); break;
          case "runCdpUseHarness": runChaosHarness("cdp-use").catch((e) => flog("chaos.harness.failed", { mode: "cdp-use", error: String(e && e.message || e) })); break;
        }
      });
    });
    setupChaosControls();

    // send button + textarea
    const input = $("#composeInput");
    const sendBtn = $("#sendBtn");
    sendBtn.addEventListener("click", handleAgentSend);
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        handleAgentSend();
      }
    });
    // also support the 'input' event-based send via the send button node click
    sendBtn.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); handleAgentSend(); }
    });
  }

  // ──────────────────────────── periodic updates ────────────────────────────
  // The 等待 ticker updates every 1s within 3 min, then every 60s past 3 min.
  // We update just the .CEnLM8MEGksTdgi_8Lqf text — this is a mutation but it
  // does NOT change (customer_name, last_message) identity, so the monitor
  // won't emit false "added" events.
  function tickWaitTimers() {
    if (state.activeTab !== "current") return;
    const now = Date.now();
    for (const c of Object.values(customers)) {
      if (!c.inCurrent) continue;
      const waitMs = c.firstUnreadAt == null ? 0 : Math.max(0, now - c.firstUnreadAt);
      const items = scrollRoot.querySelectorAll(`.chat-item[data-cid="${c.id}"] .CEnLM8MEGksTdgi_8Lqf`);
      items.forEach(el => {
        el.textContent = fmtWaitTime(waitMs);
        el.classList.add("ts-wait");
      });

      // auto-promote: if now in overdue but still rendered inside within3min, re-render
      if (waitMs >= OVERDUE_MS && items.length) {
        const sec = items[0].closest('.section');
        if (sec && sec.dataset.section !== "overdue") {
          renderChatList();
          return;
        }
      }
    }
  }

  function flashFooter(msg) {
    const el = $("#rightFooter");
    el.textContent = msg;
    clearTimeout(flashFooter._t);
    flashFooter._t = setTimeout(() => { el.textContent = "emulation ready"; }, 3000);
  }

  // ─────────────────────────────── boot ─────────────────────────────────────
  function boot() {
    installSelectorDelayPatch();
    setupEvents();
    setChaosControlValues(chaosConfig);
    // 2026-05-20 multi-tab sync: must run BEFORE the first render so we
    // pick up any already-broadcast customer roster from earlier-opened
    // tabs.  Idempotent; safe to call on the first tab too (writes the
    // default A/B/C state to storage so a second tab can find it).
    multiTabSync.bootstrap();
    renderChatList();
    renderThread();
    setInterval(tickWaitTimers, 1000);
    loadChaosConfig();
    // quick hint in the status line
    flashFooter("点击右侧按钮模拟客户消息  [tab " + multiTabSync.TAB_ID + "]");
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
