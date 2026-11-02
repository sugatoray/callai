"""Bundle the Markdown docs into one self-contained HTML page with tabs, a page list and an outline.

Usage: python3 docs/site/build_docs_html.py docs/callai --out build/docs.html [--ref BRANCH]

Tabs follow the landing page's `### Section` groups and the pages linked under each. Every page's
Markdown and every SVG in images/ are embedded as JSON; the page renders them in the browser with
marked and highlight.js, loaded from cdnjs. Links to files outside the docs point at GitHub on --ref.
"""

import argparse
import base64
import json
import re
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = "https://github.com/sugatoray/callai"
DOCS_IN_REPO = "docs/callai/"
TAB_LABELS = {"Help": "FAQ", "How-to guides": "Guides"}


def page_id(rel: str) -> str:
    """Give a page its URL-hash id: README.md -> home, guides/README.md -> guides, a/b.md -> a-b.

    Args:
        rel: the page's path relative to the docs folder.

    Returns:
        The id, using only letters, digits, hyphens and underscores.
    """
    if rel == "README.md":
        return "home"
    rel = rel[: -len(".md")]
    return rel[: -len("/README")] if rel.endswith("/README") else rel.replace("/", "-")


def collect(docs: Path) -> tuple[list[dict], list[dict]]:
    """Read the tabs and pages, in reading order, from README.md's `### Section` lists.

    Args:
        docs: the docs folder.

    Returns:
        (tabs, pages): each tab lists its page paths; each page carries its id, title, tab and Markdown.

    Raises:
        SystemExit: a page in the folder isn't linked from any section, so it would be unreachable.
    """
    tabs = [{"id": "home", "label": "Home", "pages": ["README.md"]}]
    current = None
    for line in (docs / "README.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            label = TAB_LABELS.get(line[4:].strip(), line[4:].strip())
            current = {"id": re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-"), "label": label, "pages": []}
            tabs.append(current)
        elif current and (m := re.match(r"- \[[^\]]+\]\(([^)#]+\.md)\)", line)):
            current["pages"].append(m.group(1))

    pages = []
    for tab in tabs:
        for rel in tab["pages"]:
            md = (docs / rel).read_text(encoding="utf-8")
            title = re.search(r"^# (.+)$", md, re.M)
            pages.append(
                {"id": page_id(rel), "path": rel, "title": title.group(1) if title else rel, "tab": tab["id"], "md": md}
            )

    unlisted = sorted({p.relative_to(docs).as_posix() for p in docs.rglob("*.md")} - {p["path"] for p in pages})
    if unlisted:
        raise SystemExit(f"pages not linked from a section of README.md: {', '.join(unlisted)}")
    return tabs, pages


def version() -> str:
    """Return callai's version, read from pyproject.toml (the single source of truth).

    Returns:
        The version string, e.g. "0.7.0".
    """
    pyproject = HERE.parents[1] / "pyproject.toml"
    return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]


def build(docs: Path, ref: str) -> tuple[str, int]:
    """Fill the template with the docs' pages, images and version.

    Args:
        docs: the docs folder.
        ref: the git branch or tag that links to files outside the docs point at.

    Returns:
        (the page's HTML, the number of pages bundled).
    """
    tabs, pages = collect(docs)
    images = {
        f"images/{p.name}": "data:image/svg+xml;base64," + base64.b64encode(p.read_bytes()).decode()
        for p in sorted((docs / "images").glob("*.svg"))
    }
    data = {
        "tabs": tabs,
        "pages": pages,
        "images": images,
        "repoBase": f"{REPO}/blob/{ref}/{DOCS_IN_REPO}",
        "treeBase": f"{REPO}/tree/{ref}/{DOCS_IN_REPO}",
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")  # never close the <script> early
    template = (HERE / "template.html").read_text(encoding="utf-8")
    html = template.replace("{{VERSION}}", version()).replace("/*__DOCS_DATA__*/null", blob)
    return html, len(pages)


def main(argv: list[str] | None = None) -> None:
    """Build the page and write it to --out.

    Args:
        argv: command-line arguments; defaults to sys.argv[1:].
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("docs", type=Path, help="the docs folder (holds README.md)")
    parser.add_argument("--out", type=Path, required=True, help="the HTML file to write")
    parser.add_argument("--ref", default="main", help="git branch or tag for links to GitHub (default: main)")
    args = parser.parse_args(argv)
    html, count = build(args.docs, args.ref)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out} ({count} pages, {len(html) // 1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
