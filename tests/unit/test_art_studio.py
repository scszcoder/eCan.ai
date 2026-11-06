import os

from PIL import Image

from agent.ec_skills import art_studio as art

CAPS = {"qwen-image": {"endpoints": ["images"], "reference_images": False},
        "wan2.5-i2i-preview": {"endpoints": ["images"], "reference_images": True, "max_reference_images": 3},
        "seedream-5.0-lite": {"endpoints": ["images"], "reference_images": True, "max_reference_images": 14},
        "qwen3-vl-plus": {"endpoints": ["chat"]}}


def test_only_models_that_keep_the_real_product_are_picked():
    assert art.pick_model(CAPS) == "seedream-5.0-lite"
    assert art.pick_model(CAPS, "wan2.5-i2i-preview") == "wan2.5-i2i-preview"
    try:
        art.pick_model(CAPS, "qwen-image")
        assert False
    except ValueError:
        pass


def _photo(path, size=(600, 400), color=(250, 250, 250)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path)


def test_square_pads_without_cropping_and_grows_to_800(tmp_path):
    p = str(tmp_path / "a.jpg")
    _photo(p, (600, 400))
    out = art.square(p)
    with Image.open(out) as im:
        assert im.size == (800, 800) and out.endswith(".png") and not os.path.exists(p)


class FakeClient:
    def __init__(self, tmp):
        self.tmp, self.calls = tmp, []

    def get_model_capabilities(self):
        return CAPS

    def upload_file(self, path):
        return "https://proxy/media-input/" + os.path.basename(path)

    def generate_images(self, model, prompt, timeout_s=None, **kw):
        self.calls.append((model, prompt, kw["reference_images"]))
        return [{"url": "https://proxy/media-output/x.png"}]

    def download(self, url, dest_dir, filename=None):
        path = os.path.join(dest_dir, filename)
        _photo(path, (1024, 1024))
        return path


def test_a_set_is_five_pictures_per_product_from_its_own_photos_and_notes(tmp_path):
    _photo(str(tmp_path / "输入" / "睡衣A" / "1.jpg"))
    _photo(str(tmp_path / "输入" / "睡衣A" / "2.png"))
    (tmp_path / "输入" / "睡衣A" / "说明.txt").write_text("三层夹棉；加厚保暖", encoding="utf-8")
    c = FakeClient(tmp_path)
    out = art.run("set", str(tmp_path), client=c)
    assert len(out["files"]) == 5 and not out["errors"]
    assert all(m == "seedream-5.0-lite" and refs == ["https://proxy/media-input/1.jpg", "https://proxy/media-input/2.png"]
               for m, _, refs in c.calls)
    assert "三层夹棉" in c.calls[1][1] and "人工检查" in out["summary"]
    assert os.path.isfile(os.path.join(str(tmp_path), "结果", "睡衣A", "主图套图_卖点_2.png"))


def test_no_products_yet_says_where_to_put_photos(tmp_path):
    out = art.run("main", str(tmp_path), client=FakeClient(tmp_path))
    assert "没有商品文件夹" in out["summary"] and out["files"] == []
