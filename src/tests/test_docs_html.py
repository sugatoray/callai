"""The single-page HTML docs bundle (make docs.html) must carry every page and diagram."""

import base64
import importlib.util
import json
import re
from pathlib import Path

import callai

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "docs" / "site"
DOCS = ROOT / "docs" / "callai"


def _builder():
    spec = importlib.util.spec_from_file_location("build_docs_html", SITE / "build_docs_html.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _data(html):
    match = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    assert match, "docs data not embedded"
    return json.loads(match.group(1).replace("<\\/", "</"))


def test_bundle_holds_every_page_and_image(tmp_path):
    out = tmp_path / "docs.html"
    _builder().main([str(DOCS), "--out", str(out), "--ref", "some-branch"])
    html = out.read_text(encoding="utf-8")
    data = _data(html)

    pages = {p["path"] for p in data["pages"]}
    assert pages == {str(p.relative_to(DOCS)) for p in DOCS.rglob("*.md")}
    svgs = {f"images/{p.name}" for p in DOCS.glob("images/*.svg")}
    assert set(data["images"]) == svgs | {"images/banner_2x.png"}
    assert [t["id"] for t in data["tabs"]][0] == "home"
    assert {"tutorial", "guides", "concepts", "reference", "faq"} <= {t["id"] for t in data["tabs"]}
    assert data["repoBase"].startswith("https://github.com/sugatoray/callai/blob/some-branch/")


def test_version_and_placeholders_are_filled(tmp_path):
    out = tmp_path / "docs.html"
    _builder().main([str(DOCS), "--out", str(out)])
    html = out.read_text(encoding="utf-8")
    assert f"v{callai.__version__}" in html
    assert "{{" not in html and "/*__DOCS_DATA__*/" not in html
    assert html.count("<script") == html.count("</script>")


def test_unlisted_page_is_an_error(tmp_path):
    docs = tmp_path / "docs"
    (docs / "images").mkdir(parents=True)
    (docs / "README.md").write_text("# Lib\n\nIntro.\n\n### Guides\n\n- [A](a.md): a\n")
    (docs / "a.md").write_text("# A\n")
    (docs / "orphan.md").write_text("# Orphan\n")
    try:
        _builder().main([str(docs), "--out", str(tmp_path / "o.html")])
    except SystemExit as exc:
        assert "orphan.md" in str(exc)
    else:
        raise AssertionError("expected an error for a page missing from README.md")


BANNER = ROOT / "docs" / "assets" / "images" / "banner_2x.png"


def test_landing_page_starts_with_the_banner(tmp_path):
    out = tmp_path / "docs.html"
    _builder().main([str(DOCS), "--out", str(out)])
    data = _data(out.read_text(encoding="utf-8"))
    home = next(p for p in data["pages"] if p["id"] == "home")
    first = home["md"].splitlines()[0]
    assert re.fullmatch(r"!\[[^\]]+\]\(images/banner_2x\.png\)", first)
    assert home["title"] == "callai"  # the page title still comes from the first heading
    uri = data["images"]["images/banner_2x.png"]
    assert uri.startswith("data:image/png;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == BANNER.read_bytes()
    others = [p for p in data["pages"] if p["id"] != "home"]
    assert not any("banner_2x.png" in p["md"] for p in others)


def test_no_banner_option(tmp_path):
    out = tmp_path / "docs.html"
    _builder().main([str(DOCS), "--out", str(out), "--no-banner"])
    data = _data(out.read_text(encoding="utf-8"))
    assert "images/banner_2x.png" not in data["images"]
    assert not next(p for p in data["pages"] if p["id"] == "home")["md"].startswith("![")


def test_custom_and_missing_banner(tmp_path):
    custom = tmp_path / "my_banner.png"
    custom.write_bytes(b"\x89PNG fake")
    out = tmp_path / "docs.html"
    _builder().main([str(DOCS), "--out", str(out), "--banner", str(custom)])
    data = _data(out.read_text(encoding="utf-8"))
    assert "images/my_banner.png" in data["images"]
    try:
        _builder().main([str(DOCS), "--out", str(out), "--banner", str(tmp_path / "missing.png")])
    except SystemExit as exc:
        assert "missing.png" in str(exc)
    else:
        raise AssertionError("expected an error for a missing banner")
