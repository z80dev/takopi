from __future__ import annotations

import re
from typing import Any

from markdown_it import MarkdownIt
from sulguk import transform_html


def render_markdown(md: str) -> tuple[str, list[dict[str, Any]]]:
    html = MarkdownIt("commonmark", {"html": False}).render(md or "")
    rendered = transform_html(html)

    text = re.sub("(?m)^(\\s*)\u2022", r"\1-", rendered.text)

    # FIX: Telegram requires MessageEntity.language (if present) to be a String.
    entities: list[dict[str, Any]] = []
    for e in rendered.entities:
        d = dict(e)
        if "language" in d and not isinstance(d["language"], str):
            d.pop("language", None)
        entities.append(d)
    return text, entities
