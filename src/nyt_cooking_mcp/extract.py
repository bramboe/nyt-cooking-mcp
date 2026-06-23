"""Turn NYT Cooking API payloads and pages into plain output dicts.

Recipe details come from the site's JSON recipe endpoint, which carries the
full ingredient and instruction list independently of the client-side
paywall. Search results are read from the recipe cards in the search page
markup, and the recipe box is read from its JSON API response.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any

SITE = "https://cooking.nytimes.com"


class ParseError(Exception):
    """Raised when a page or payload cannot be turned into output."""


_RECIPE_HREF = re.compile(r'href="([^"]*?/recipes/(\d+)-[^"]*)"')
_CARD_ALT = re.compile(
    r'<img[^>]*\balt="([^"]+)"[^>]*\bclass="cardimage_image', re.IGNORECASE
)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def _absolute(url: str) -> str:
    """Return an absolute https URL for a protocol-relative/relative path."""
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{SITE}{url}"
    return url


def _plain_text(value: Any) -> str:
    """Strip HTML tags and entities, collapsing whitespace."""
    if not isinstance(value, str):
        return ""
    return _SPACES.sub(" ", unescape(_TAGS.sub(" ", value))).strip()


def _time_display(value: Any) -> str | None:
    """Pull the human label out of a {"display": ..., "minutes": ...} time."""
    if isinstance(value, dict):
        label = value.get("display")
        return label if isinstance(label, str) and label else None
    if isinstance(value, str) and value:
        return value
    return None


def _ingredients(parts: Any) -> list[str]:
    """Flatten the grouped ``parts`` structure into ingredient lines."""
    lines: list[str] = []
    if not isinstance(parts, list):
        return lines
    for group in parts:
        for item in group.get("ingredients", []) if isinstance(group, dict) else []:
            if not isinstance(item, dict):
                continue
            quantity = (item.get("display_quantity") or "").strip()
            text = _plain_text(item.get("display_text", ""))
            line = f"{quantity} {text}".strip()
            if line:
                lines.append(line)
    return lines


def _steps(directions: Any) -> list[str]:
    """Flatten the grouped ``directions`` structure into step descriptions."""
    steps: list[str] = []
    if not isinstance(directions, list):
        return steps
    for group in directions:
        for step in group.get("steps", []) if isinstance(group, dict) else []:
            if not isinstance(step, dict):
                continue
            text = _plain_text(step.get("description", ""))
            if text:
                steps.append(text)
    return steps


def recipe(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a recipe dict from the JSON recipe endpoint payload."""
    if not isinstance(payload, dict) or "name" not in payload:
        raise ParseError("Unexpected recipe payload.")

    rating = payload.get("rating") or {}
    byline = payload.get("byline")
    topnote = payload.get("topnote") or {}

    return {
        "id": str(payload.get("id", "")),
        "name": _plain_text(payload.get("name", "")) or payload.get("name", ""),
        "url": _absolute(payload.get("url", "")),
        "author": byline.strip().title() if isinstance(byline, str) and byline else None,
        "time": {
            "total": _time_display(payload.get("cooking_time")),
            "prep": _time_display(payload.get("prep_time")),
            "cook": _time_display(payload.get("cook_time")),
        },
        "servings": payload.get("yield") or None,
        "rating": {
            "average": rating.get("value") if isinstance(rating, dict) else None,
            "count": rating.get("total") if isinstance(rating, dict) else None,
        },
        "description": _plain_text(topnote.get("content") if isinstance(topnote, dict) else topnote),
        "ingredients": _ingredients(payload.get("parts")),
        "steps": _steps(payload.get("directions")),
    }


def search(html: str) -> dict[str, Any]:
    """Build search results from the recipe cards in the search page markup."""
    hrefs = _RECIPE_HREF.findall(html)
    names = _CARD_ALT.findall(html)
    aligned = len(names) == len(hrefs)

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, (href, rid) in enumerate(hrefs):
        if rid in seen:
            continue
        seen.add(rid)
        clean = _absolute(href.split("?", 1)[0])
        if aligned:
            name = unescape(names[index])
        else:
            slug = re.sub(r"^.*?/recipes/\d+-", "", clean).replace("-", " ")
            name = slug.title()
        results.append({"id": rid, "name": name, "url": clean, "author": None})

    return {"results": results, "count": len(results)}


def recipe_box(payload: dict[str, Any]) -> dict[str, Any]:
    """Build saved-recipe results from the recipe box API response."""
    if not isinstance(payload, dict):
        raise ParseError("Unexpected recipe box response.")

    items = payload.get("collectables") or []
    results = [
        {
            "id": str(item.get("id", "")),
            "name": item.get("name", ""),
            "url": _absolute(item.get("url", "")),
            "author": item.get("byline"),
        }
        for item in items
        if isinstance(item, dict)
    ]

    return {
        "results": results,
        "count": len(results),
        "total": payload.get("collectables_count", len(results)),
    }
