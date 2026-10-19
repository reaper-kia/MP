"""Разбор HTML без привязки к площадке: текст без тегов, meta, текст статьи."""

import html
import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node

_BLOCK_BREAK = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6])\s*/?\s*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t ]+")
_NEWLINES = re.compile(r"\n{3,}")


def strip_html(value: str) -> str:
    """HTML-фрагмент → чистый текст: переносы на месте <br>/<p>, сущности раскрыты."""
    text = _BLOCK_BREAK.sub("\n", value)
    text = _TAGS.sub("", text)
    return normalize_text(html.unescape(text))


def normalize_text(value: str) -> str:
    lines = [_SPACES.sub(" ", line).strip() for line in value.replace("\r", "").split("\n")]
    return _NEWLINES.sub("\n\n", "\n".join(lines)).strip()


def node_text(node: Node | None) -> str:
    """Текст узла с переносами строк между блоками."""
    if node is None:
        return ""
    return strip_html(node.html or "")


def meta(tree: HTMLParser, name: str) -> str | None:
    """<meta property="og:title"> или <meta name="description"> → content."""
    for attr in ("property", "name", "itemprop"):
        node = tree.css_first(f'meta[{attr}="{name}"]')
        if node is not None:
            content = node.attributes.get("content")
            if content and content.strip():
                return html.unescape(content).strip()
    return None


ARTICLE_SELECTORS = (
    '[itemprop="articleBody"]',
    "article",
    ".article__text",
    ".article-text",
    ".news-text",
    ".text",
)


def article_text(document: str, min_length: int = 200) -> str:
    """Основной текст статьи новостного сайта: абзацы внутри articleBody / article.

    Не нашли достаточно текста — пустая строка (вызывающий возьмёт описание из RSS).
    """
    tree = HTMLParser(document)
    for selector in ARTICLE_SELECTORS:
        for node in tree.css(selector):
            paragraphs = [strip_html(p.html or "") for p in node.css("p")]
            text = "\n\n".join(p for p in paragraphs if p)
            if len(text) >= min_length:
                return text
    return ""
