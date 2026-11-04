"""The single-page HTML docs bundle (make docs.html) must carry every page and diagram."""

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
    assert set(data["images"]) == {f"images/{p.name}" for p in DOCS.glob("images/*.svg")}
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


BANNER = ROOT / "src" / "tools" / "banner" / "callai-banner.html"


def _build(tmp_path, *args):
    out = tmp_path / "docs.html"
    _builder().main([str(DOCS), "--out", str(out), *args])
    html = out.read_text(encoding="utf-8")
    return html, _data(html)


def test_landing_page_banner_is_the_static_banner_html(tmp_path):
    html, data = _build(tmp_path)
    banner = data["banner"]
    assert banner.lstrip().startswith('<div id="banner">')
    assert f"v{callai.__version__}" in banner
    for name in ("claude-code", "codex", "opencode", "pi", "hermes", "grok"):
        assert f'<span class="pill">{name}</span>' in banner
    # no editing features
    assert "data-edit" not in banner and "contenteditable" not in banner and 'id="pills"' not in banner
    # its wordmark must not become a page heading (outline, anchors)
    assert "<h1" not in banner and '<div class="name">' in banner
    # its CSS comes along, without the editor's rules
    assert "#banner .terminal" in html and "#banner.editing" not in html and "html.bare" not in html
    # the Markdown is untouched and no image is embedded for it
    home = next(p for p in data["pages"] if p["id"] == "home")
    assert home["md"] == (DOCS / "README.md").read_text(encoding="utf-8")
    assert not any(k.endswith(".png") for k in data["images"])


def test_no_banner_option(tmp_path):
    html, data = _build(tmp_path, "--no-banner")
    assert data["banner"] is None
    assert "#banner .terminal" not in html and "/*__BANNER_CSS__*/" not in html


def test_banner_without_markers_or_missing_is_an_error(tmp_path):
    plain = tmp_path / "plain.html"
    plain.write_text("<html><body><div id='banner'></div></body></html>")
    for path, message in ((plain, "banner:html:start"), (tmp_path / "missing.html", "missing.html")):
        try:
            _build(tmp_path, "--banner", str(path))
        except SystemExit as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"expected an error for {path}")


def test_header_links_to_the_repo_without_a_branch(tmp_path):
    html, _ = _build(tmp_path, "--ref", "some-branch")
    header = html[html.index('<header class="top">') : html.index("</header>")]
    links = re.findall(r'<a class="icon-btn gh-btn" href="([^"]+)"[^>]*>', header)
    assert links == ["https://github.com/sugatoray/callai"]
    tag = re.search(r'<a class="icon-btn gh-btn"[^>]*>', header).group(0)
    assert 'aria-label="callai on GitHub"' in tag and 'target="_blank"' in tag and 'rel="noopener"' in tag
    assert "some-branch" not in header
    # it sits right before the light/dark toggle
    assert header.index("gh-btn") < header.index('id="theme-btn"')
    assert '</a>\n    <button class="icon-btn theme-btn"' in header


def test_search_box_has_a_magnifying_glass_and_keeps_its_label(tmp_path):
    html, _ = _build(tmp_path)
    search = html[html.index('<label class="search"') : html.index("</label>", html.index('<label class="search"'))]
    assert 'class="search-icon"' in search and 'aria-hidden="true"' in search
    assert 'placeholder="Search the docs"' in search and 'aria-label="Search the docs"' in search
    # phones hide the placeholder text, leaving the icon
    assert re.search(r"@media \(max-width: 560px\) \{[^@]*\.search input::placeholder \{ color: transparent; \}", html)
