"""static_html: save a document's static HTML edition (ST: landing page + <stem>_asset/ pages and images)."""
import json
import urllib.error

from agent.ec_skills.chip_docs import static_html

LANDING = "https://www.st.com/resource/en/application_note/an1-usb-guide.html"
FINAL = "https://www.st.com/content/st_com/en/technical-documents/an1-usb-guide.html"
A = "https://www.st.com/content/st_com/en/technical-documents/an1-usb-guide_asset/"
SITE = {
    FINAL: b'<a href="#topic-intro">Intro</a> <img src="an1-usb-guide_asset/fig1.webp">'
           b'<a href="an1-usb-guide_asset/chunk-001-usb.html#topic-usb">USB</a>'
           b'<a href="/content/st_com/en.html">ST home</a> <script src="/etc/clientlibs/site.js"></script>',
    A + "chunk-001-usb.html": b'<img src="fig2.png"> <a href="chunk-002-power.html">Power</a> <a href="../an1-usb-guide.html">back</a>',
    A + "chunk-002-power.html": b'<img src="fig2.png" srcset="fig3.svg 2x">',
    A + "fig1.webp": b"w", A + "fig2.png": b"p", A + "fig3.svg": b"s",
}


def _fetch(fetched):
    def fetch(url):
        fetched.append(url)
        final = FINAL if url == LANDING else url
        return final, SITE[final]
    return fetch


def test_saves_landing_and_everything_under_its_asset_folder(tmp_path):
    fetched = []
    dest, files = static_html.save_edition(LANDING, tmp_path, fetch=_fetch(fetched))
    # saved under the short doc id with short names: ST's stems broke Windows' 260-character path limit
    assert dest == tmp_path / "an1"
    assert sorted(files) == ["asset/chunk-001-usb.html", "asset/chunk-002-power.html",
                             "asset/fig1.webp", "asset/fig2.png", "asset/fig3.svg", "index.html"]
    assert (dest / "asset" / "fig2.png").read_bytes() == b"p"
    assert b'src="asset/fig1.webp"' in (dest / "index.html").read_bytes()  # links rewritten to match
    assert b'href="../index.html"' in (dest / "asset" / "chunk-001-usb.html").read_bytes()
    assert len(fetched) == len(set(fetched)) == 6  # site pages and scripts outside the folder are not fetched
    assert json.loads((dest / static_html.DONE).read_text(encoding="utf-8"))["url"] == LANDING


def test_a_saved_edition_is_not_fetched_again(tmp_path):
    static_html.save_edition(LANDING, tmp_path, fetch=_fetch([]))
    fetched = []
    dest, files = static_html.save_edition(LANDING, tmp_path, fetch=_fetch(fetched))
    assert files == [] and fetched == [] and dest == tmp_path / "an1"


def test_a_failed_file_leaves_the_edition_unfinished(tmp_path):
    def fetch(url):
        if url.endswith("fig2.png"):
            raise OSError("HTTP Error 503")
        return _fetch([])(url)
    try:
        static_html.save_edition(LANDING, tmp_path, fetch=fetch)
    except OSError:
        pass
    assert not (tmp_path / "an1" / static_html.DONE).exists()


def test_a_link_to_a_missing_page_is_skipped(tmp_path):
    # 2026-10-16: AN4879 links AN4879_Introduction.html, which answers 404
    site = dict(SITE)
    site[A + "chunk-002-power.html"] += b'<a href="Intro.html">Intro</a>'

    def fetch(url):
        final = FINAL if url == LANDING else url
        if final not in site:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return final, site[final]
    dest, files = static_html.save_edition(LANDING, tmp_path, fetch=fetch)
    assert len(files) == 6
    assert json.loads((dest / static_html.DONE).read_text(encoding="utf-8"))["missing"] == ["asset/Intro.html"]
