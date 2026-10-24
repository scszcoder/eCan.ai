"""Store 主图 (2026-10-23): the 抖店 product list's main pictures reach the
matching knowledge-base products (by 商品ID listing, else exact title)."""
import io
import struct
import zlib

from knowledge.ks import product_images as pi, store_images


def _png():
    raw = b"".join(b"\x00" + bytes((9, 9, 200)) * 2 for _ in range(2))
    ck = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + ck(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + ck(b"IDAT", zlib.compress(raw)) + ck(b"IEND", b""))


def test_store_products_attach_or_are_added(svc, tmp_path, monkeypatch):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    monkeypatch.setattr(pi, "images_dir", lambda: str(imgs))
    monkeypatch.setattr(pi, "_ask_vision", lambda path: "蓝色儿童短袖T恤")

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(pi.urllib.request, "urlopen", lambda req, timeout=0: Resp(_png()))
    st = svc.save_store({"name": "小铺抖音店", "platform": "douyin", "ecan_store_id": "douyin-小铺"})
    svc.save_product({"code": "A", "title": "童装T恤", "attributes": {"材质": "商家写的"},
                      "listings": [{"store_id": st["id"], "platform_item_id": "3826"}]})
    svc.save_product({"code": "B", "title": "男童短裤"})
    svc.save_product({"code": "A336", "title": "旧标题"})
    img = "https://p9-aio.ecombdimg.com/obj/{}.png"
    stats = store_images.attach(svc, [
        {"id": "3826", "title": "店里改过的标题", "image": img.format("a"), "store_id": "douyin-小铺",
         "attributes": {"材质": "店里的"}},
        {"id": "9999", "title": "男童短裤", "image": img.format("b"), "store_id": "douyin-小铺"},
        {"id": "5555", "title": "新标题", "image": img.format("c"), "store_id": "douyin-小铺",
         "attributes": {"货号": "A336"}},
        {"id": "7777", "title": "店里新款卫衣", "image": img.format("d"), "store_id": "douyin-小铺",
         "platform": "douyin", "attributes": {"领型": "圆领", "货号": "W-1"},
         "variants": [{"颜色": "灰", "尺码": "S"}, {"颜色": "灰", "尺码": "S"}, {"颜色": "黑", "尺码": "M"}]}])
    assert stats["matched"] == 3 and stats["added"] == 1, stats
    prods = {p["code"]: p for p in svc.store.list_products(svc.tenant_id(), limit=10)["items"]}
    a = prods["A"]
    assert a["images"][0]["desc"] == "蓝色儿童短袖T恤" and a["images"][0]["from"] == "store"
    assert a["title"] == "童装T恤" and a["attributes"] == {"材质": "商家写的"}   # merchant's text kept
    assert prods["A336"]["title"] == "旧标题"                                    # matched by 货号
    assert svc.store.resolve_item(svc.tenant_id(), "9999") == prods["B"]["id"]  # listing added
    w = prods["W-1"]
    assert w["source"] == "store" and w["title"] == "店里新款卫衣" and w["attributes"]["领型"] == "圆领"
    assert len(w["variants"]) == 2 and w["images"][0]["file"]
    assert svc.store.resolve_item(svc.tenant_id(), "7777") == w["id"]
    again = store_images.attach(svc, [{"id": "3826", "title": "x", "image": img.format("a"), "store_id": "douyin-小铺"}])
    assert again["pictures"] == 0 and again["added"] == 0       # already there: nothing re-done


def test_a_photo_description_finds_the_product_by_its_appearance(svc, tmp_path, monkeypatch):
    # The answering model describes the buyer's photo in its rag_query; the
    # products' picture descriptions (外观) are what that query meets.
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    monkeypatch.setattr(pi, "images_dir", lambda: str(imgs))
    looks = {"S1": "藏青色条纹海魂衫，船领长袖，胸前小锚刺绣", "S2": "粉色碎花连衣裙，泡泡袖，收腰"}
    for i, (code, title) in enumerate((("S1", "法式上衣A款"), ("S2", "夏季新款B款"))):
        f = tmp_path / f"{code}.png"
        f.write_bytes(_png() + bytes([i]))            # two different pictures
        images = pi.prepare([str(f)])
        pi.describe(images, ask=lambda path, c=code: looks[c])
        svc.save_product({"code": code, "title": title, "images": images})
    res = svc.search("顾客发来图片：粉色碎花裙子 泡泡袖 有同款吗")
    assert res["candidates"][0]["code"] == "S2", res["candidates"]


def test_both_platform_lists_are_read_until_nothing_new(monkeypatch):
    import asyncio
    from agent.ec_skills.browser_use_extension import store_page
    from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import ws_observer
    monkeypatch.setattr(store_page, "store_tabs", lambda p: [{"profile": "p", "ws": "ws://x"}])
    pages = {"douyin": 0, "pdd": 0}

    async def fake_eval(ws, js):
        if "getMallChatGoodsList" in js:
            pages["pdd"] += 1
            assert '"4486121917"' in js                     # a buyer this app answered
            return {"ok": True, "items": [{"id": "5377", "title": "睡衣", "image": "https://img.pddpic.com/a"}]}
        pages["douyin"] += 1                                  # `page` is ignored: same list every time
        return {"code": 0, "items": [{"id": "3826", "title": "童装", "image": "https://p9-aio.ecombdimg.com/a"}]}
    monkeypatch.setattr(store_page, "evaluate", fake_eval)
    monkeypatch.setattr(ws_observer, "_ECHOES", {"4486121917": []})
    assert [i["id"] for i in asyncio.run(store_images.douyin_products())] == ["3826"]
    assert [i["id"] for i in asyncio.run(store_images.pdd_products())] == ["5377"]
    assert pages == {"douyin": 2, "pdd": 2}
    monkeypatch.setattr(ws_observer, "_ECHOES", {})
    assert asyncio.run(store_images.pdd_products()) == []  # no buyer yet: nothing asked


def test_a_reply_syncs_at_most_every_12_hours(monkeypatch):
    calls = []
    monkeypatch.setattr(store_images, "sync_in_background", lambda svc=None: calls.append(1))
    monkeypatch.setattr(store_images, "_last_sync", 0.0)
    for _ in range(3):
        store_images.maybe_sync()
    assert calls == [1]


def test_a_buyer_photo_is_described_and_searched_by_appearance(svc, tmp_path, monkeypatch):
    # 2026-10-23: rag_query adds what the buyer's picture shows, in the same words
    # the product pictures were described with, so "这个有吗" + photo finds the item.
    import base64
    import json
    from knowledge.ks import agent_bridge
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    monkeypatch.setattr(pi, "images_dir", lambda: str(imgs))
    asked = []
    monkeypatch.setattr(pi, "_ask_vision", lambda data: asked.append(1) or "粉色碎花连衣裙，泡泡袖，收腰")
    photo = _png() + b"buyer"
    state = {"input": json.dumps({"latest_message": "这个有吗", "latest_message_attachments": [
        {"kind": "image", "data_uri": "data:image/png;base64," + base64.b64encode(photo).decode()}]})}
    scope = agent_bridge.scope_from_state(state)
    assert scope["image_desc"].startswith("粉色碎花")
    agent_bridge.scope_from_state(state)
    assert len(asked) == 1                                 # same picture: described once
    looks = {"S1": "藏青色条纹海魂衫，船领长袖", "S2": "粉色碎花连衣裙，泡泡袖，收腰"}
    for i, (code, title) in enumerate((("S1", "法式上衣A款"), ("S2", "夏季新款B款"))):
        f = tmp_path / f"{code}.png"
        f.write_bytes(_png() + bytes([i]))
        images = pi.prepare([str(f)])
        pi.describe(images, ask=lambda path, c=code: looks[c])
        svc.save_product({"code": code, "title": title, "images": images})
    seen = {}
    real_search = svc.search
    monkeypatch.setattr(svc, "search", lambda q, **k: seen.setdefault("q", q) and real_search(q, **k))
    import knowledge.ks.service as ks_service
    monkeypatch.setattr(ks_service, "get_service", lambda mw=None: svc)
    monkeypatch.setattr(agent_bridge, "enabled", lambda: True)
    agent_bridge.try_product_answer(None, {"query": "这个有吗", "workspace": "", "_ks_scope": scope})
    assert "粉色碎花连衣裙" in seen["q"]
    assert real_search(seen["q"])["candidates"][0]["code"] == "S2"


def test_app_embeddings_go_in_batches_of_at_most_10():
    from knowledge.ks.embedding import LangChainEmbedder
    sizes = []

    class Emb:
        def embed_documents(self, texts):
            sizes.append(len(texts))
            return [[1.0, 0.0] for _ in texts]
    LangChainEmbedder(Emb(), "eCanAI", "text-embedding-v4").embed([f"t{i}" for i in range(23)])
    assert sizes == [10, 10, 3]


def test_one_failing_product_does_not_stop_the_others(svc, monkeypatch):
    calls = []
    real = svc.save_product

    def save(data, **k):
        calls.append(data["code"])
        if data["code"] == "bad":
            raise RuntimeError("batch size is invalid")
        return real(data, **k)
    monkeypatch.setattr(svc, "save_product", save)
    stats = store_images.attach(svc, [{"id": "1", "title": "坏的", "attributes": {"货号": "bad"}},
                                      {"id": "2", "title": "好的", "attributes": {"货号": "good"}}])
    assert stats["failed"] == 1 and stats["added"] == 1 and calls == ["bad", "good"]


def test_the_buyer_photo_is_found_in_the_multimodal_message_too(tmp_path, monkeypatch):
    import base64
    from langchain_core.messages import HumanMessage
    from knowledge.ks import agent_bridge
    monkeypatch.setattr(pi, "images_dir", lambda: str(tmp_path))
    monkeypatch.setattr(pi, "_ask_vision", lambda data: "蓝色牛仔短裤，卡通贴布")
    uri = "data:image/jpeg;base64," + base64.b64encode(_png() + b"m").decode()
    state = {"input": "这个有吗", "messages": ["agent", HumanMessage(content=[
        {"type": "text", "text": "这个有吗"}, {"type": "image_url", "image_url": {"url": uri}}])]}
    assert agent_bridge.scope_from_state(state)["image_desc"] == "蓝色牛仔短裤，卡通贴布"
    assert "image_desc" not in agent_bridge.scope_from_state({"input": "你好", "messages": []})


def test_a_whole_turn_as_the_query_searches_the_buyers_words_and_picture(svc, tmp_path, monkeypatch):
    # 2026-10-23 KEN: the skill's auto-selected rag_query passed the whole
    # hand-off JSON (155,912 chars with the photo's base64) as the query.
    import base64
    import json
    from knowledge.ks import agent_bridge
    import knowledge.ks.service as ks_service
    monkeypatch.setattr(pi, "images_dir", lambda: str(tmp_path))
    monkeypatch.setattr(pi, "_ask_vision", lambda data: "粉色碎花连衣裙，泡泡袖")
    monkeypatch.setattr(ks_service, "get_service", lambda mw=None: svc)
    monkeypatch.setattr(agent_bridge, "enabled", lambda: True)
    svc.save_product({"code": "S2", "title": "夏季新款B款"})
    seen = {}
    real = svc.search
    monkeypatch.setattr(svc, "search", lambda q, **k: seen.setdefault("q", q) and real(q, **k))
    turn = {"customer_id": "c1", "latest_message": "这个有吗", "latest_message_attachments": [
        {"kind": "image", "data_uri": "data:image/png;base64," + base64.b64encode(_png() + b"q").decode()}]}
    agent_bridge.try_product_answer(None, {"query": json.dumps(turn, ensure_ascii=False), "workspace": "",
                                           "_ks_scope": {"store_id": ""}})
    assert seen["q"].startswith("这个有吗") and "粉色碎花连衣裙" in seen["q"] and "base64" not in seen["q"]


def test_an_export_updates_the_store_added_product_and_keeps_its_picture(svc, tmp_path, monkeypatch):
    # The store sync added the item (code = 货号) before the 抖店 export arrived
    # (code = 商家编码): one product, the export's facts, the store's picture.
    import csv
    monkeypatch.setattr(pi, "images_dir", lambda: str(tmp_path / "imgs"))
    (tmp_path / "imgs").mkdir()
    monkeypatch.setattr(pi, "_ask_vision", lambda path: "蓝色牛仔短裤")

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(pi.urllib.request, "urlopen", lambda req, timeout=0: Resp(_png()))
    st = svc.save_store({"name": "小店一号", "platform": "douyin", "ecan_store_id": "douyin-小店一号"})
    store_images.attach(svc, [{"id": "3826", "title": "女童牛仔短裤", "image": "https://p9-aio.ecombdimg.com/a.png",
                               "store_id": "douyin-小店一号", "attributes": {"货号": "K078"}}])
    f = tmp_path / "export.csv"
    with open(f, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["商品ID", "商品名称", "商家编码", "一级类目", "二级类目"])
        w.writerow(["3826", "女童牛仔短裤", "01448143f0b0", "服装", "童装"])
    job = svc.import_catalog(str(f), {"商品ID": "platform_item_id", "商品名称": "title", "商家编码": "code",
                                      "一级类目": "category", "二级类目": "category_level"},
                             default_store_id=st["id"], run_inline=True)
    assert svc.get_job(job["id"])["status"] == "succeeded"
    items = svc.store.list_products(svc.tenant_id(), limit=10)["items"]
    assert len(items) == 1
    p = items[0]
    assert p["code"] == "01448143f0b0" and p["category"] == "服装/童装"
    assert p["images"] and p["images"][0]["desc"] == "蓝色牛仔短裤"


def test_a_clear_picture_match_answers_with_that_products_facts(svc, tmp_path, monkeypatch):
    import base64
    import json
    from knowledge.ks import agent_bridge
    monkeypatch.setattr(agent_bridge, "PICTURE_MATCH_MIN", 0.0)   # test embedder scores run low
    import knowledge.ks.service as ks_service
    monkeypatch.setattr(pi, "images_dir", lambda: str(tmp_path))
    monkeypatch.setattr(ks_service, "get_service", lambda mw=None: svc)
    monkeypatch.setattr(agent_bridge, "enabled", lambda: True)
    looks = {"S1": "藏青色条纹海魂衫，船领长袖", "S2": "粉色碎花连衣裙，泡泡袖，收腰"}
    for i, (code, title) in enumerate((("S1", "法式上衣A款"), ("S2", "夏季新款B款"))):
        f = tmp_path / f"{code}.png"
        f.write_bytes(_png() + bytes([i]))
        images = pi.prepare([str(f)])
        pi.describe(images, ask=lambda path, c=code: looks[c])
        svc.save_product({"code": code, "title": title, "images": images,
                          "attributes": {"可选尺码": "S、M、L"} if code == "S2" else {}})
    monkeypatch.setattr(pi, "_ask_vision", lambda data: "粉色碎花连衣裙，泡泡袖")
    turn = {"latest_message": "这个有吗", "latest_message_attachments": [
        {"kind": "image", "data_uri": "data:image/png;base64," + base64.b64encode(_png() + b"buyer").decode()}]}
    out = agent_bridge.try_product_answer(None, {"query": json.dumps(turn, ensure_ascii=False), "workspace": "",
                                                 "_ks_scope": {"store_id": ""}})
    text = out["data"]["response"]
    assert text.startswith("[图片匹配] 顾客图片最像本店的「夏季新款B款」") and "S、M、L" in text


def test_an_app_spawned_cli_uses_the_accounts_knowledge_folder(tmp_path, monkeypatch):
    # Fast Deploy's CLI wrote the auto-apply flag to ~/.ecan while the app reads
    # the account folder (2026-10-23 KEN).
    import knowledge.ks.service as ks_service
    from config.app_info import app_info
    import app_context
    monkeypatch.setattr(app_context.AppContext, "get_main_window", staticmethod(lambda: None))
    monkeypatch.setattr(app_info, "appdata_path", str(tmp_path), raising=False)
    monkeypatch.setenv("ECAN_LOG_USER", "1050588178_qq_com")
    assert ks_service._ks_folder() == str(tmp_path / "1050588178_qq_com" / "knowledge_service")
    monkeypatch.delenv("ECAN_LOG_USER")
    assert ks_service._ks_folder().endswith(".ecan" + __import__("os").sep + "knowledge_service")


def test_a_turn_query_that_is_not_valid_json_still_yields_words_and_picture():
    import base64
    from knowledge.ks import agent_bridge
    b64 = base64.b64encode(_png() * 20).decode()
    broken = ('{"customer_id": "eval-1", "latest_message": "这个\\"有\\"吗", "latest_message_attachments": '
              '[{"kind": "image", "data_uri": "data:image/png;base64,' + b64 + '"}], "x": ')   # cut short
    text, uri = agent_bridge._unwrap_turn_query(broken)
    assert text == '这个"有"吗' and uri.startswith("data:image/png;base64,") and uri.endswith(b64[-20:])
    assert agent_bridge._unwrap_turn_query("纯棉吗") == ("纯棉吗", "")


def test_a_photo_with_no_clear_match_says_so_instead_of_naming_a_product(monkeypatch):
    from knowledge.ks import agent_bridge
    weak = {"context": "…", "confidence": 0.3, "should_answer": False,
            "candidates": [{"id": "p1", "title": "男童短袖球服套装", "score": 0.41}]}
    out = agent_bridge._focus_on_picture_match(None, "这个有吗", "", weak)
    assert out["context"].startswith("[图片匹配] 本店没有找到与顾客图片明显一致的商品")
    assert "男童短袖球服套装" not in out["context"]               # 0.41 is no look-alike
    assert out["should_answer"] and out["confidence"] >= 0.6
    close = {"context": "", "candidates": [{"id": "a", "title": "A", "score": 0.8}, {"id": "b", "title": "B", "score": 0.78}]}
    assert "没有找到" in agent_bridge._focus_on_picture_match(None, "q", "", close)["context"]


def test_a_stripped_query_gets_the_picture_the_answering_node_saw(monkeypatch):
    # 2026-10-24 KEN: the rag_query text was written from the turn with the
    # base64 stripped (and cut), so the search never had the photo.
    from agent.ec_skills import turn_pictures
    from knowledge.ks import agent_bridge
    uri = "data:image/jpeg;base64," + "A" * 400
    turn_pictures.remember("eval-ev123", uri)
    stripped = '{"customer_id": "eval-ev123", "customer_name": "测试买家", "latest_message": "这个有吗", "lat'
    assert agent_bridge._unwrap_turn_query(stripped) == ("这个有吗", uri)
    assert agent_bridge._unwrap_turn_query(stripped.replace("ev123", "ev999"))[1] == ""
    monkeypatch.setattr(turn_pictures.time, "time", lambda: 10 ** 10)          # long after
    assert turn_pictures.recent("eval-ev123") == ""


def test_the_answering_node_remembers_the_buyers_picture():
    import json
    from agent.ec_skills import turn_pictures
    from agent.ec_skills.llm_utils.llm_utils import prep_multi_modal_content
    uri = "data:image/png;base64," + "iVBORw0KGgo" * 40
    state = {"input": json.dumps({"customer_id": "buyer-7", "latest_message": "这个有吗",
                                  "latest_message_attachments": [{"kind": "image", "data_uri": uri}]})}
    prep_multi_modal_content(state, base_text="这个有吗")
    assert turn_pictures.recent("buyer-7") == uri


def test_a_photo_match_is_ranked_on_appearance_not_crowded_out_by_attributes(svc, tmp_path, monkeypatch):
    # 2026-10-24 KEN: ~12 attribute chunks per product filled the general
    # search's top 20, so the right product's picture never ranked.
    monkeypatch.setattr(pi, "images_dir", lambda: str(tmp_path))
    looks = {"B": "白色短袖T恤配黑色短裤，正面蓝色线条字母图案，圆领", "P": "粉色碎花连衣裙，泡泡袖"}
    for i, code in enumerate("BP" + "".join(f"X{n}" for n in range(8))):
        images = []
        if code in looks:
            f = tmp_path / f"{code}.png"
            f.write_bytes(_png() + bytes([i]))
            images = pi.prepare([str(f)])
            pi.describe(images, ask=lambda path, c=code: looks[c])
        attrs = {f"属性{n}": f"白色短袖T恤配黑色短裤 值{n}" for n in range(12)}   # look-alike attribute text
        svc.save_product({"code": code, "title": f"商品{code}", "images": images, "attributes": attrs})
    top = svc.picture_candidates("白色短袖T恤配黑色短裤，T恤胸前浅蓝线条图案，圆领")
    assert top[0]["code"] == "B" and all(c["code"] in ("B", "P") for c in top)


def test_a_no_match_names_only_real_look_alikes():
    from knowledge.ks import agent_bridge
    weak = {"context": "", "candidates": [{"id": "a", "title": "牛仔短裤", "score": 0.574},
                                         {"id": "b", "title": "弯刀裤", "score": 0.56}]}
    out = agent_bridge._focus_on_picture_match(None, "这个有吗", "", weak)
    assert "没有找到" in out["context"] and "牛仔短裤" not in out["context"]


def _two_lookalike_sets(svc, tmp_path, monkeypatch):
    monkeypatch.setattr(pi, "images_dir", lambda: str(tmp_path))
    ids = {}
    for i, (code, title) in enumerate((("A", "男童短袖球服套装"), ("B", "男童篮球服套装"), ("C", "女童假两件背心"))):
        f = tmp_path / f"{code}.png"
        f.write_bytes(_png() + bytes([i]))
        ids[code] = svc.save_product({"code": code, "title": title, "images": pi.prepare([str(f)])})["id"]
    weak = {"context": "", "candidates": [{"id": ids["A"], "title": "男童短袖球服套装", "score": 0.657},
                                          {"id": ids["C"], "title": "女童假两件背心", "score": 0.62},
                                          {"id": ids["B"], "title": "男童篮球服套装", "score": 0.597}]}
    uri = "data:image/png;base64," + __import__("base64").b64encode(_png() + b"buyer").decode()
    return weak, uri


def test_an_unclear_photo_match_is_settled_by_looking_at_the_pictures(svc, tmp_path, monkeypatch):
    # 2026-10-24 KEN: a mirrored photo of 男童篮球服套装 ranked 3rd on descriptions.
    from knowledge.ks import agent_bridge
    weak, uri = _two_lookalike_sets(svc, tmp_path, monkeypatch)
    seen = {}
    def ask(buyer, paths):
        seen["n"] = len(paths)
        return '好的 {"same": 3, "similar": [1]}'
    monkeypatch.setattr(pi, "_ask_compare", ask)
    out = agent_bridge._focus_on_picture_match(svc, "有没有类似的", "", weak, uri)
    assert seen["n"] == 3
    assert out["context"].startswith("[图片匹配] 顾客图片最像本店的「男童篮球服套装」")
    assert out["candidates"][0]["title"] == "男童篮球服套装"


def test_with_no_same_item_only_the_look_alikes_the_model_saw_are_named(svc, tmp_path, monkeypatch):
    from knowledge.ks import agent_bridge
    weak, uri = _two_lookalike_sets(svc, tmp_path, monkeypatch)
    monkeypatch.setattr(pi, "_ask_compare", lambda buyer, paths: '{"same": 0, "similar": [1, 3, 9]}')
    text = agent_bridge._focus_on_picture_match(svc, "有没有类似的", "", weak, uri)["context"]
    assert "没有找到" in text and "男童短袖球服套装、男童篮球服套装" in text
    assert "女童假两件背心" not in text                     # scored 0.62, but the model saw it is not alike


def test_when_the_pictures_cannot_be_compared_the_scores_decide(svc, tmp_path, monkeypatch):
    from knowledge.ks import agent_bridge
    weak, uri = _two_lookalike_sets(svc, tmp_path, monkeypatch)
    def down(buyer, paths):
        raise TimeoutError("proxy")
    monkeypatch.setattr(pi, "_ask_compare", down)
    text = agent_bridge._focus_on_picture_match(svc, "有没有类似的", "", weak, uri)["context"]
    assert "男童短袖球服套装、女童假两件背心" in text          # the old score-based look-alikes
