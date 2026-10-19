"""HTML публичных страниц OK → данные. Чистые функции, проверяются на сохранённых страницах
(tests/fixtures/ok/, сняты 2026-10-19 с группы «Новости Красноярска - НГС.НОВОСТИ»).

Разметка ленты топиков группы (`/group/{gid}/topics`):
  div.groups_post[data-l="topicId,{tid},…,groupId,{gid}"]   — один топик
    h3.feed_h_heading                                       — название группы
    div.feed_date                                           — «добавлена сегодня в 16:30»
    div.media-text_cnt_tx[data-tid]                         — текст (заголовок h2 + абзацы)
    li[data-widget-item-type=like|reshare] .widget_count, кнопка «Комментарии» .widget_count
  div.loader-container[data-url][data-last-element]         — подгрузка следующей страницы
Страница топика (`/group/{gid}/topic/{tid}`): link[rel=canonical], h1/p в .media-text_cnt_tx,
дата — <time> (сегодняшние — только «16:30», без дня).
"""

import re
from dataclasses import dataclass, replace
from datetime import datetime

from selectolax.lexbor import LexborHTMLParser, LexborNode

from collector_service.infra.ok.dates import parse_ok_date
from collector_service.infra.web.html import meta, node_text

OK_URL = "https://ok.ru"
_GROUP_CANONICAL = re.compile(r"^https://ok\.ru/group/(\d+)(?:/|$)")
_TOPIC_URL = re.compile(r"^https://(?:m\.)?ok\.ru/(?:group/(\d+)|[A-Za-z0-9_.-]+)/topic/(\d+)")
_DIGITS = re.compile(r"\d[\d\s ]*")


@dataclass(frozen=True, slots=True)
class OkGroup:
    gid: str
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class OkTopic:
    gid: str
    tid: str
    group_name: str
    text: str
    published_at: datetime | None
    likes: int | None
    reshares: int | None
    comments: int | None
    pinned: bool = False

    @property
    def url(self) -> str:
        return topic_url(self.gid, self.tid)


@dataclass(frozen=True, slots=True)
class FeedCursor:
    """Как запросить следующую страницу ленты: POST на url с номером страницы и курсором."""

    url: str
    page: int
    last_element: str


@dataclass(frozen=True, slots=True)
class TopicsPage:
    topics: list[OkTopic]
    cursor: FeedCursor | None


def topic_url(gid: str, tid: str) -> str:
    """Каноничная ссылка на пост (B1-04)."""
    return f"{OK_URL}/group/{gid}/topic/{tid}"


def group_url(gid: str) -> str:
    return f"{OK_URL}/group/{gid}"


def parse_group(document: str) -> OkGroup | None:
    tree = LexborHTMLParser(document)
    gid = _canonical_gid(tree)
    if gid is None:
        return None
    heading = tree.css_first("h1.group-name_h")
    name = node_text(heading) if heading else ""
    if not name:
        title = meta(tree, "og:title") or ""
        name = title.split(" | ")[0].strip()
    return OkGroup(gid=gid, name=name or f"group/{gid}", url=group_url(gid))


def parse_topics_page(document: str, now: datetime) -> TopicsPage:
    tree = LexborHTMLParser(document)
    pinned_ids = {
        _topic_id(node) for node in tree.css("#hook_Block_AltGroupPinnedTopics .groups_post")
    }
    topics: list[OkTopic] = []
    for node in tree.css("div.groups_post"):
        topic = _topic(node, now)
        if topic is None:
            continue
        if topic.tid in pinned_ids:
            topic = replace(topic, pinned=True)
        topics.append(topic)
    return TopicsPage(topics=topics, cursor=_cursor(tree))


def parse_topic_page(document: str, now: datetime) -> OkTopic | None:
    """Страница одного топика (открыть ссылку из поиска). Нет текста — None."""
    tree = LexborHTMLParser(document)
    canonical = tree.css_first('link[rel="canonical"]')
    href = (canonical.attributes.get("href") or "") if canonical else ""
    match = _TOPIC_URL.match(href)
    if not match or not match.group(1):
        return None
    gid, tid = match.group(1), match.group(2)
    text = "\n\n".join(
        t for t in (node_text(n) for n in tree.css(".mlr_cnt .media-text_cnt_tx")) if t
    )
    if not text:
        return None
    time_node = tree.css_first("group-author time") or tree.css_first("time")
    published = parse_ok_date(node_text(time_node), now) if time_node else None
    author = tree.css_first("group-author .group_author_group-author_name, group-author a")
    group_name = node_text(author) if author else ""
    if not group_name:
        title = meta(tree, "og:title") or ""
        group_name = title.rsplit(" в группе ", 1)[-1].split(" в ОК")[0].strip()
    return OkTopic(
        gid=gid,
        tid=tid,
        group_name=group_name or f"group/{gid}",
        text=text,
        published_at=published,
        likes=None,
        reshares=None,
        comments=None,
    )


def is_topic_url(url: str) -> bool:
    return _TOPIC_URL.match(url) is not None


# ---------- внутреннее ----------


def _topic(node: LexborNode, now: datetime) -> OkTopic | None:
    tid = _topic_id(node)
    gid = _data_l_value(node, "groupId")
    if not tid or not gid:
        return None
    text = "\n\n".join(t for t in (node_text(n) for n in node.css(".media-text_cnt_tx")) if t)
    heading = node.css_first("h3.feed_h_heading")
    date_node = node.css_first(".feed_date")
    return OkTopic(
        gid=gid,
        tid=tid,
        group_name=node_text(heading) if heading else "",
        text=text,
        published_at=parse_ok_date(node_text(date_node), now) if date_node else None,
        likes=_count(node, 'li[data-widget-item-type="like"] .widget_count'),
        reshares=_count(node, 'li[data-widget-item-type="reshare"] .widget_count'),
        comments=_comments(node),
    )


def _topic_id(node: LexborNode) -> str:
    return _data_l_value(node, "topicId")


def _data_l_value(node: LexborNode, key: str) -> str:
    """data-l="topicId,158870686352657,state,…,groupId,54787706781713" → значение по ключу."""
    parts = (node.attributes.get("data-l") or "").split(",")
    for i in range(0, len(parts) - 1, 2):
        if parts[i] == key and parts[i + 1].isdigit():
            return parts[i + 1]
    return ""


def _count(node: LexborNode, selector: str) -> int | None:
    found = node.css_first(selector)
    return _int(node_text(found)) if found is not None else None


def _comments(node: LexborNode) -> int | None:
    for button in node.css("button"):
        label = button.css_first(".widget_tx")
        if label is not None and node_text(label) == "Комментарии":
            return _count(button, ".widget_count")
    return None


def _int(text: str) -> int | None:
    match = _DIGITS.search(text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    return int(digits) if digits else None


def _cursor(tree: LexborHTMLParser) -> FeedCursor | None:
    loader = tree.css_first("div.loader-container[data-last-element]")
    if loader is None:
        return None
    url = loader.attributes.get("data-url") or ""
    last = loader.attributes.get("data-last-element") or ""
    page = loader.attributes.get("data-page") or "1"
    if not url or not last:
        return None
    return FeedCursor(
        url=OK_URL + url if url.startswith("/") else url, page=int(page), last_element=last
    )


def _canonical_gid(tree: LexborHTMLParser) -> str | None:
    canonical = tree.css_first('link[rel="canonical"]')
    href = (canonical.attributes.get("href") or "") if canonical else ""
    match = _GROUP_CANONICAL.match(href)
    return match.group(1) if match else None
