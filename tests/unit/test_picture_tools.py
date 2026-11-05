import os
import shutil

from PIL import Image

from agent.ec_skills import picture_tools as pt


def _pic(path, size=(400, 300), bg="white", box="red"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.new("RGB", size, bg)
    im.paste(Image.new("RGB", (100, 100), box), (150, 100))
    im.save(path)
    return path


def test_resize_pads_without_cropping_and_stamp_draws_a_badge(tmp_path):
    _pic(str(tmp_path / "输入" / "ECK1" / "a.png"))
    out = pt.run("resize", str(tmp_path))
    sizes = sorted(Image.open(f).size for f in out["files"])
    assert sizes == [(750, 1000), (800, 800)] and "做好 2 张" in out["summary"]
    big = Image.open([f for f in out["files"] if "1比1" in f][0])
    assert big.getpixel((400, 400)) == (255, 0, 0)          # the product is still there, centred
    out = pt.run("stamp", str(tmp_path), {"stamp_text": "限时直降"})
    im = Image.open(out["files"][0])
    assert im.getpixel((28, 28)) != (255, 255, 255)          # badge in the top-left corner


def test_cutout_makes_only_the_outer_white_transparent(tmp_path):
    src = _pic(str(tmp_path / "w.png"), size=(300, 300))
    im = Image.open(src)
    im.paste(Image.new("RGB", (100, 100), "red"), (150, 100))
    im.paste(Image.new("RGB", (20, 20), "white"), (190, 140))   # a white hole inside the red box
    im.save(src)
    got = Image.open(pt.transparent(src, str(tmp_path / "t.png")))
    assert got.getpixel((5, 5))[3] == 0 and got.getpixel((160, 110))[3] == 255 and got.getpixel((195, 145))[3] == 255


class FakeClient:
    def __init__(self, src):
        self.src, self.prompts = src, []

    def get_model_capabilities(self):
        return {"seedream-x": {"endpoints": ["images"], "reference_images": True}}

    def upload_file(self, path):
        return "ref://" + os.path.basename(path)

    def generate_images(self, model, prompt, timeout_s=None, reference_images=None):
        self.prompts.append((model, prompt, reference_images))
        return [{"url": "https://x/y.png"}]

    def download(self, url, dest_dir, filename):
        os.makedirs(dest_dir, exist_ok=True)
        return shutil.copy(self.src, os.path.join(dest_dir, filename))


def test_white_background_goes_through_the_image_model_with_the_picture_as_reference(tmp_path):
    _pic(str(tmp_path / "输入" / "a.jpg"))
    fake = FakeClient(_pic(str(tmp_path / "model_out.png")))
    out = pt.run("cutout", str(tmp_path), client=fake)
    assert fake.prompts[0][0] == "seedream-x" and fake.prompts[0][2] == ["ref://a.jpg"] and "纯白" in fake.prompts[0][1]
    got = Image.open(out["files"][0])
    assert got.mode == "RGBA" and got.size == (800, 800) and got.getpixel((2, 2))[3] == 0
    assert "检查商品细节" in out["summary"]


def test_empty_inbox_says_where_to_put_pictures(tmp_path):
    assert "里没有图片" in pt.run("white_bg", str(tmp_path))["summary"]
