"""The Jinja environment for every generated page and feed, with the filters the templates use."""

import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from markupsafe import Markup

from .dates import parse_iso

TEMPLATES = Path(__file__).parent / "templates"

_md = MarkdownIt("commonmark").enable("table")


def markdown(text: str | None) -> Markup:
    """Markdown from the spec's own descriptions (trusted content)."""
    return Markup(_md.render(text)) if text else Markup("")


def compact(n: int) -> str:
    """12345678 -> "12.3M", like Intl's compact notation."""
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n / size >= 0.99995:
            return f"{n / size:.1f}".removesuffix(".0") + suffix
    return str(n)


def grouped(n: int) -> str:
    return f"{n:,}"


def format_timestamp(iso: str | None) -> str:
    """ "2026-10-24T13:11:46.000Z" -> "24 Oct 2026, 13:11 UTC" """
    when = parse_iso(iso)
    if not when:
        return "never"
    utc = when.astimezone(datetime.UTC)
    return f"{utc.day} {utc:%b %Y, %H:%M} UTC"


# Autoescaping covers .html and .xml, so values are escaped wherever they are interpolated.
env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
env.filters.update(markdown=markdown, compact=compact, grouped=grouped, timestamp=format_timestamp)
