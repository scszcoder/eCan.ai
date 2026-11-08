from agent.ec_skills import word_patrol as wp


def test_longer_words_win_and_each_word_is_reported_once():
    words = wp.word_list()
    hits = [w for w, _, _ in wp.find("全网第一 最新款 全网第一", words)]
    assert hits == ["全网第一", "最新"]


def test_store_list_adds_files_and_drops_words(tmp_path):
    (tmp_path / wp.OWN).write_text("# 我们的\n-最新\n慎用:羽绒\n竞品名A、竞品名B\n", encoding="utf-8")
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / wp.SHARED).write_text("极限词:宇宙第一\n", encoding="utf-8")
    words = wp.word_list(str(tmp_path), str(shared))
    assert "最新" not in words and words["羽绒"] == ("慎用", wp.CARE) and words["竞品名B"] == ("商家", wp.BAN)
    assert words["宇宙第一"][0] == "极限词"


def test_check_lists_title_and_spec_hits_banned_first():
    skus = [{"product_id": "1", "title": "男士衬衫 美白", "spec": {"颜色": "白色"}},
            {"product_id": "1", "title": "男士衬衫 美白", "spec": {"颜色": "顶级黑"}},
            {"product_id": "2", "title": "普通T恤", "spec": {}}]
    rows = wp.check(skus, wp.word_list())
    assert [(r["级别"], r["位置"], r["词"]) for r in rows] == [("禁用", "规格", "顶级"), ("慎用", "标题", "美白")]
    text = wp.summary(rows, 2, "店")
    assert "1 个有问题" in text and "禁用词 1 处" in text and "不会改店铺" in text
    assert "没发现违禁词" in wp.summary([], 2, "店")


def test_run_writes_the_excel_from_given_skus(tmp_path):
    out = wp.run_for_store("douyin-x", "douyin", str(tmp_path), skus=[{"product_id": "1", "title": "史上最低价"}])
    assert out["hits"] == 1 and out["path"].endswith(".xlsx")


def test_douyin_quality_rows_say_what_is_missing_lowest_score_first():
    from agent.ec_skills import store_quality as sq
    raw = [{"product_id": "1", "title": "A", "score": 94, "has_score": True, "level": "lv3", "base": 100,
            "miss": {"miss_white_bg_cnt": 1}},
           {"product_id": "2", "title": "B", "score": 70, "has_score": True, "level": "lv1", "base": 90,
            "miss": {"miss_pic_34_cnt": 3, "miss_main_video_cnt": 1, "miss_pic_11_cnt": 0}, "punished": True}]
    rows = sq.rows_of(raw)
    assert [r["商品ID"] for r in rows] == ["2", "1"]
    assert rows[0]["缺的素材"] == "3:4主图3张、主图视频" and rows[0]["要做的"].startswith("有处罚单")
    text = sq.summary(rows)
    assert "平均 82 分" in text and "低于 80 分的 1 个" in text and "白底图 1 个商品" in text
