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


def test_store_pictures_attach_by_item_id_or_title(svc, tmp_path, monkeypatch):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    monkeypatch.setattr(pi, "images_dir", lambda: str(imgs))
    monkeypatch.setattr(pi, "_ask_vision", lambda path: "蓝色儿童短袖T恤")

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(pi.urllib.request, "urlopen", lambda req, timeout=0: Resp(_png()))
    st = svc.save_store({"name": "小铺抖音店", "platform": "douyin"})
    svc.save_product({"code": "A", "title": "童装T恤", "listings": [{"store_id": st["id"], "platform_item_id": "3826"}]})
    svc.save_product({"code": "B", "title": "男童短裤"})
    svc.save_product({"code": "C", "title": "没上架的"})
    stats = store_images.attach(svc, [
        {"id": "3826", "title": "店里改过的标题", "image": "https://p9-aio.ecombdimg.com/obj/a.png"},
        {"id": "9999", "title": "男童短裤", "image": "https://p9-aio.ecombdimg.com/obj/b.png"},
        {"id": "7777", "title": "别家的", "image": "https://p9-aio.ecombdimg.com/obj/c.png"}])
    assert stats["matched"] == 2 and stats["updated"] == 2
    prods = {p["code"]: p for p in svc.store.list_products(svc.tenant_id(), limit=10)["items"]}
    assert prods["A"]["images"][0]["desc"] == "蓝色儿童短袖T恤" and prods["A"]["images"][0]["from"] == "store"
    assert not prods["C"]["images"]
    again = store_images.attach(svc, [{"id": "3826", "title": "", "image": "https://p9-aio.ecombdimg.com/obj/a.png"}])
    assert again["updated"] == 0                         # already there: nothing re-done


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
