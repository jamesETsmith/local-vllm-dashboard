from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from re import DOTALL, sub

from markdown import markdown

DOC_PATH = Path(__file__).parents[2] / "docs" / "USING_THE_DASHBOARD.md"


@lru_cache
def usage_markdown() -> str:
    return DOC_PATH.read_text()


def usage_text(base_url: str) -> str:
    document = usage_markdown().replace("{base_url}", base_url.rstrip("/"))
    return sub(r"<!--.*?-->", "", document, flags=DOTALL).rstrip() + "\n"


class HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.headings: list[tuple[int, str, str]] = []
        self.level: int | None = None
        self.heading_id = ""
        self.text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h2", "h3"}:
            self.level = int(tag[1])
            self.heading_id = dict(attrs).get("id") or ""
            self.text = ""

    def handle_data(self, data: str) -> None:
        if self.level is not None:
            self.text += data

    def handle_endtag(self, tag: str) -> None:
        if self.level is not None and tag == f"h{self.level}":
            self.headings.append((self.level, self.heading_id, self.text.strip()))
            self.level = None


def usage_html(base_url: str) -> tuple[str, tuple[tuple[int, str, str], ...]]:
    rendered = markdown(
        usage_text(base_url),
        extensions=("fenced_code", "tables", "toc"),
        output_format="html",
    )
    parser = HeadingParser()
    parser.feed(rendered)
    return rendered, tuple(parser.headings)
