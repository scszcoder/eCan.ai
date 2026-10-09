"""Shared e-commerce fixture for Knowledge Service tests.

Merchant A ("优衣小铺") has two stores selling the same T-shirt under different
platform item ids, a merchant-wide returns policy, and one store that
overrides it. It also sells two near-identical shirts (cotton vs linen) — the
e-commerce version of the sister-datasheet trap. Merchant B is a separate
tenant whose data must never appear in A's answers.
"""
import pytest

from knowledge.ks.embedding import HashingEmbedder
from knowledge.ks.service import KnowledgeService


@pytest.fixture
def svc(tmp_path):
    return KnowledgeService(f"sqlite:///{(tmp_path / 'ks.db').as_posix()}", embedder=HashingEmbedder(), owner="tester")


@pytest.fixture
def shop(svc):
    tid = svc.tenant_id()
    tmall = svc.save_store({"name": "优衣小铺天猫店", "platform": "tmall"})
    douyin = svc.save_store({"name": "优衣小铺抖音店", "platform": "douyin"})
    cotton = svc.save_product({
        "code": "TS-001", "title": "男士纯棉圆领短袖T恤", "category": "男装/T恤",
        "attributes": {"材质": "100%棉", "厚薄": "常规", "产地": "广东"},
        "variants": [{"颜色": "白", "尺码": "M"}, {"颜色": "黑", "尺码": "L"}],
        "size_chart": {"headers": ["尺码", "身高", "胸围"], "rows": [["M", "165-170", "100"], ["L", "170-175", "106"]]},
        "selling_points": ["精梳棉透气", "不易变形"],
        "care": "30度以下水温机洗，不可漂白",
        "faq": [{"q": "会缩水吗", "a": "首次洗涤可能轻微缩水约1-2%，建议冷水洗"}],
        "listings": [{"store_id": tmall["id"], "platform_item_id": "6600001"},
                     {"store_id": douyin["id"], "platform_item_id": "3500009"}],
    })
    linen = svc.save_product({
        "code": "TS-002", "title": "男士亚麻圆领短袖T恤", "category": "男装/T恤",
        "attributes": {"材质": "55%亚麻 45%棉", "厚薄": "薄款"},
        "faq": [{"q": "会缩水吗", "a": "亚麻面料缩水约3-5%，请手洗"}],
        "listings": [{"store_id": tmall["id"], "platform_item_id": "6600002"}],
    })
    svc.save_policy("returns", "支持七天无理由退货，商品需保持吊牌完好，退货运费由买家承担。")
    svc.save_policy("returns", "抖音店支持七天无理由退货，赠送运费险，退货运费由运费险承担。", store_id=douyin["id"])
    svc.save_policy("shipping", "下单后48小时内从广州发货，默认中通快递，偏远地区不包邮。")

    other = svc.store.ensure_tenant("别家店", tenant_id="tn_other")
    svc.store.ensure_kb(other["id"], "别家商品", kind="catalog")
    other_store = svc.save_store({"name": "别家旗舰店"}, tenant_id=other["id"])
    svc.save_product({
        "code": "X-1", "title": "男士纯棉圆领短袖T恤 竞品", "attributes": {"材质": "80%棉 20%涤纶"},
        "faq": [{"q": "会缩水吗", "a": "别家答案：不会缩水"}],
        "listings": [{"store_id": other_store["id"], "platform_item_id": "6600001"}],
    }, tenant_id=other["id"])
    svc.save_policy("returns", "别家规则：不支持退货", tenant_id=other["id"])
    return {"tid": tid, "tmall": tmall, "douyin": douyin, "cotton": cotton, "linen": linen,
            "other_tid": other["id"], "other_store": other_store}
