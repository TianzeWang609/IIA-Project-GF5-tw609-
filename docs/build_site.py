#!/usr/bin/env python3
"""Generate the GF5 static website from Markdown sources.

The Markdown files are the source of truth. Generated HTML files should not be
edited by hand; rerun this script after editing Markdown.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT.parent / "site"
SITE_TITLE = "GF5: Animating 3D Characters"
GITHUB_REPOSITORY_URL = "https://github.com/CambridgeCVCourses/IIA-Project-GF5"


@dataclass(frozen=True)
class Page:
    source: str
    output: str
    nav_label: str
    eyebrow: str


PAGES = [
    Page("project_overview.md", "index.html", "Overview", "Parts 1 and 2 release"),
    Page("setup.md", "setup.html", "Setup", "Before coding"),
    Page("part1.md", "part1.html", "Part 1", "Part 1"),
    Page("part2.md", "part2.html", "Part 2", "Part 2"),
    Page("interim.md", "interim.html", "Interim", "Checkpoint"),
    Page("part3_placeholder.md", "part3.html", "Part 3", "Coming later"),
]

SOURCE_TO_OUTPUT = {page.source: page.output for page in PAGES}


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    ident: str


@dataclass(frozen=True)
class RenderedDocument:
    body: str
    title: str
    headings: tuple[Heading, ...]


def strip_inline_markdown(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_]{1,2}([^*_]+)[*_]{1,2}", r"\1", text)
    return text


def slugify(text: str, used: dict[str, int]) -> str:
    base = strip_inline_markdown(text).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not base:
        base = "section"
    count = used.get(base, 0)
    used[base] = count + 1
    return base if count == 0 else f"{base}-{count + 1}"


def rewrite_href(href: str) -> str:
    if re.match(r"^[a-z]+:", href) or href.startswith("#"):
        return href
    path, fragment = (href.split("#", 1) + [""])[:2] if "#" in href else (href, "")
    output = SOURCE_TO_OUTPUT.get(path, path)
    if output.endswith(".md"):
        output = output[:-3] + ".html"
    return f"{output}#{fragment}" if fragment else output


def format_plain(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    return text


def format_inline(text: str) -> str:
    parts = re.split(r"(`[^`]*`)", text)
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue

        pos = 0
        for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", part):
            rendered.append(format_plain(part[pos : match.start()]))
            label = format_plain(match.group(1))
            href = html.escape(rewrite_href(match.group(2)), quote=True)
            rendered.append(f'<a href="{href}">{label}</a>')
            pos = match.end()
        rendered.append(format_plain(part[pos:]))
    return "".join(rendered)


class MarkdownRenderer:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.out: list[str] = []
        self.heading_ids: dict[str, int] = {}
        self.paragraph: list[str] = []
        self.list_type: str | None = None
        self.list_items: list[str] = []
        self.list_start = 1
        self.in_code = False
        self.code_info = ""
        self.code_lines: list[str] = []
        self.title = ""
        self.headings: list[Heading] = []
        self.current_heading_id = ""

    def render(self, text: str) -> RenderedDocument:
        self.lines = text.splitlines()
        for line in self.lines:
            self.handle_line(line)
        self.close_all()
        return RenderedDocument("\n".join(self.out), self.title, tuple(self.headings))

    def handle_line(self, line: str) -> None:
        fence = re.match(r"^```(.*)$", line)
        if fence:
            if self.in_code:
                self.close_code()
            else:
                self.close_blocks()
                self.in_code = True
                self.code_info = fence.group(1).strip()
                self.code_lines = []
            return

        if self.in_code:
            self.code_lines.append(line)
            return

        if not line.strip():
            self.close_blocks()
            return

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            self.close_blocks()
            level = len(heading.group(1))
            text = heading.group(2)
            if level == 1 and not self.title:
                self.title = strip_inline_markdown(text)
                return
            ident = slugify(text, self.heading_ids)
            self.current_heading_id = ident
            if level in {2, 3}:
                self.headings.append(Heading(level, strip_inline_markdown(text), ident))
            self.out.append(f'<h{level} id="{ident}">{format_inline(text)}</h{level}>')
            return

        item = re.match(r"^\s*([-*])\s+(.+)$", line)
        numbered = re.match(r"^\s*(\d+)\.\s+(.+)$", line)
        if item or numbered:
            kind = "ul" if item else "ol"
            content = item.group(2) if item else numbered.group(2)
            start = int(numbered.group(1)) if numbered else None
            self.add_list_item(kind, content, start)
            return

        if self.list_type and re.match(r"^\s{2,}\S", line):
            self.list_items[-1] += " " + line.strip()
            return

        self.close_list()
        self.paragraph.append(line.strip())

    def add_list_item(self, kind: str, content: str, start: int | None = None) -> None:
        self.close_paragraph()
        if self.list_type and self.list_type != kind:
            self.close_list()
        if not self.list_type:
            self.list_start = start or 1
        self.list_type = kind
        self.list_items.append(content.strip())

    def close_code(self) -> None:
        language = ""
        if self.code_info:
            language = f' class="language-{html.escape(self.code_info, quote=True)}"'
        code = html.escape("\n".join(self.code_lines))
        self.out.append(f"<pre><code{language}>{code}</code></pre>")
        self.in_code = False
        self.code_info = ""
        self.code_lines = []

    def close_paragraph(self) -> None:
        if self.paragraph:
            text = " ".join(self.paragraph)
            self.out.append(f"<p>{format_inline(text)}</p>")
            self.paragraph = []

    def close_list(self) -> None:
        if self.list_type:
            list_class = ""
            checklist_sections = {
                "learning-goals",
                "part-1-output",
                "part-2-output",
                "what-to-submit",
                "required-figures-and-media",
                "what-to-do-now",
            }
            if self.list_type == "ul" and self.current_heading_id in checklist_sections:
                list_class = ' class="checklist"'

            if self.list_type == "ol" and self.list_start != 1:
                self.out.append(f'<ol start="{self.list_start}"{list_class}>')
            else:
                self.out.append(f"<{self.list_type}{list_class}>")
            for item in self.list_items:
                self.out.append(f"  <li>{format_inline(item)}</li>")
            self.out.append(f"</{self.list_type}>")
            self.list_type = None
            self.list_items = []
            self.list_start = 1

    def close_blocks(self) -> None:
        self.close_paragraph()
        self.close_list()

    def close_all(self) -> None:
        if self.in_code:
            self.close_code()
        self.close_blocks()


def render_nav(current: Page) -> str:
    items: list[tuple[str, str, bool]] = []
    for page in PAGES:
        items.append((page.nav_label, page.output, page == current))

    links = []
    for label, href, active in items:
        aria = ' aria-current="page"' if active else ""
        links.append(f'          <a href="{href}"{aria}>{html.escape(label)}</a>')
    return "\n".join(links)


def render_release_summary() -> str:
    return """      <section class="release-strip" aria-label="Release summary">
        <div class="metric">
          <strong>Part 1</strong>
          <span>Forward kinematics and a saved custom motion.</span>
        </div>
        <div class="metric">
          <strong>Part 2</strong>
          <span>Skinning weights, one-hot binding, and LBS comparison.</span>
        </div>
        <div class="metric">
          <strong>Interim</strong>
          <span>Code, videos, figures, and the report checkpoint.</span>
        </div>
        <div class="metric">
          <strong>Part 3</strong>
          <span>Public placeholder kept ready for the later brief.</span>
        </div>
      </section>
"""


def render_actions(page: Page) -> str:
    if page.output == "index.html":
        github_href = html.escape(GITHUB_REPOSITORY_URL, quote=True)
        return f"""          <div class="actions">
            <a class="button primary" href="{github_href}" target="_blank" rel="noreferrer">GitHub codebase</a>
            <a class="button" href="setup.html">Start setup</a>
          </div>
"""
    index = PAGES.index(page)
    actions: list[str] = []
    if index > 0:
        previous = PAGES[index - 1]
        actions.append(
            f'<a class="button" href="{html.escape(previous.output, quote=True)}">'
            f'Previous: {html.escape(previous.nav_label)}</a>'
        )
    if index < len(PAGES) - 1:
        next_page = PAGES[index + 1]
        actions.append(
            f'<a class="button primary" href="{html.escape(next_page.output, quote=True)}">'
            f'Next: {html.escape(next_page.nav_label)}</a>'
        )
    if not actions:
        actions.append('<a class="button" href="index.html">Back to overview</a>')
    return "          <div class=\"actions\">\n            " + "\n            ".join(actions) + "\n          </div>\n"


def render_hero(page: Page, doc: RenderedDocument) -> str:
    title = html.escape(doc.title or page.nav_label)
    eyebrow = html.escape(page.eyebrow)
    actions = render_actions(page)
    if page.output == "index.html":
        return f"""      <section class="release-band">
        <div>
          <p class="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p class="lede">The Markdown handouts are the source of truth; this page is generated from them for the student-facing release.</p>
{actions}        </div>
        <figure class="visual-panel" aria-label="Animation viewer preview">
          <img src="assets/gf5-rig-preview.svg" alt="Diagram of the GF5 viewer showing a block character, skeleton, skinning weights, and a timeline.">
        </figure>
      </section>
"""
    return f"""      <section class="doc-hero">
        <div>
          <p class="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
{actions}        </div>
      </section>
"""


def render_toc(doc: RenderedDocument) -> str:
    headings = [heading for heading in doc.headings if heading.level == 2]
    if not headings:
        return ""
    links = "\n".join(
        f'            <a href="#{html.escape(heading.ident, quote=True)}">{html.escape(heading.title)}</a>'
        for heading in headings
    )
    return f"""        <aside class="doc-toc" aria-label="On this page">
          <strong>On this page</strong>
{links}
        </aside>
"""


def render_page(
    page: Page,
    *,
    source_base_url: str | None = None,
    source_relative_base: str = "",
) -> str:
    markdown = (ROOT / page.source).read_text(encoding="utf-8")
    doc = MarkdownRenderer().render(markdown)
    title = doc.title or page.nav_label
    html_title = SITE_TITLE if title == SITE_TITLE else f"{title} | {SITE_TITLE}"
    release_summary = render_release_summary() if page.output == "index.html" else ""
    toc = render_toc(doc)
    if source_base_url:
        source_href = f"{source_base_url.rstrip('/')}/{page.source}"
    elif source_relative_base and source_relative_base != ".":
        source_href = f"{source_relative_base.rstrip('/')}/{page.source}"
    else:
        source_href = page.source
    return f"""<!doctype html>
<!-- Generated from {page.source} by docs/build_site.py. Do not edit by hand. -->
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(html_title)}</title>
    <link rel="stylesheet" href="assets/site.css">
  </head>
  <body>
    <a class="skip-link" href="#main">Skip to content</a>
    <header class="site-header">
      <div class="nav-shell">
        <a class="brand" href="index.html" aria-label="GF5 home">
          <span class="brand-mark">GF5</span>
          <span>{html.escape(SITE_TITLE)}</span>
        </a>
        <nav class="nav-links" aria-label="Main navigation">
{render_nav(page)}
        </nav>
      </div>
    </header>

    <main id="main" class="page doc-page">
{render_hero(page, doc)}{release_summary}
      <div class="doc-shell">
{toc}        <article class="doc-content">
{indent(doc.body, 10)}
        </article>
      </div>
    </main>

    <footer class="footer">
      <div class="footer-inner">
        Generated from Markdown source: <a href="{html.escape(source_href, quote=True)}">{html.escape(page.source)}</a>.
      </div>
    </footer>
  </body>
</html>
"""


def indent(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in text.splitlines())


def build_site(output: Path, *, source_base_url: str | None = None) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    assets_output = output / "assets"
    if assets_output.exists():
        shutil.rmtree(assets_output)
    shutil.copytree(ROOT / "assets", assets_output)
    (output / ".nojekyll").write_text("", encoding="utf-8")
    source_relative_base = Path(os.path.relpath(ROOT, output)).as_posix()

    for page in PAGES:
        output_path = output / page.output
        output_path.write_text(
            render_page(
                page,
                source_base_url=source_base_url,
                source_relative_base=source_relative_base,
            ),
            encoding="utf-8",
        )
        display_path = output_path.relative_to(Path.cwd()) if output_path.is_relative_to(Path.cwd()) else output_path
        print(f"wrote {display_path} from {page.source}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory where generated site files should be written.",
    )
    parser.add_argument(
        "--source-base-url",
        default=None,
        help="Optional URL prefix for Markdown source links in generated footers.",
    )
    args = parser.parse_args()

    build_site(args.output.resolve(), source_base_url=args.source_base_url)


if __name__ == "__main__":
    main()
