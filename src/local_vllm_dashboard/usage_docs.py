from functools import lru_cache
from pathlib import Path

from markdown import markdown

DOC_PATH = Path(__file__).parents[2] / "docs" / "USING_THE_DASHBOARD.md"


@lru_cache
def usage_markdown() -> str:
    return DOC_PATH.read_text()


def usage_text(base_url: str) -> str:
    return usage_markdown().replace("{base_url}", base_url.rstrip("/"))


def usage_html(base_url: str) -> str:
    return markdown(
        usage_text(base_url),
        extensions=("fenced_code", "tables"),
        output_format="html",
    )
