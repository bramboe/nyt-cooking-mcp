"""Parse NYT Cooking page data from __NEXT_DATA__ JSON."""

from __future__ import annotations

import json
import re
from typing import Any


class ParseError(Exception):
    """Raised when page parsing fails."""

    pass


def _extract_text_from_doc(doc: Any) -> list[str]:
    """Recursively extract text nodes from a nested document structure."""
    texts = []
    if isinstance(doc, dict):
        if doc.get("type") == "text" and "text" in doc:
            return [doc["text"]]
        for v in doc.values():
            texts.extend(_extract_text_from_doc(v))
    elif isinstance(doc, list):
        for item in doc:
            texts.extend(_extract_text_from_doc(item))
    return texts


def _parse_ingredients(ingredients_data: dict) -> list[str]:
    """Parse ingredients from the nested document format."""
    doc = ingredients_data.get("doc", {})
    return _extract_text_from_doc(doc)


def _parse_steps(preparation_data: dict) -> list[str]:
    """Parse preparation steps from the nested document format."""
    doc = preparation_data.get("doc", {})
    steps = []
    content = doc.get("content", [])
    for item in content:
        if item.get("type") == "step":
            step_texts = _extract_text_from_doc(item)
            steps.append("".join(step_texts).strip())
    return steps


def _parse_time(time_data: dict) -> dict[str, str | None]:
    """Parse time information."""
    return {
        "total": time_data.get("readyIn"),
        "prep": _format_iso_duration(time_data.get("prepTime")),
        "cook": _format_iso_duration(time_data.get("cookTime")),
    }


def _format_iso_duration(iso_duration: str | None) -> str | None:
    """Convert ISO 8601 duration to human-readable format."""
    if not iso_duration:
        return None
    # Parse PT0H30M format
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso_duration)
    if not match:
        return iso_duration
    hours, minutes = match.groups()
    parts = []
    if hours and int(hours) > 0:
        parts.append(f"{int(hours)} hr")
    if minutes and int(minutes) > 0:
        parts.append(f"{int(minutes)} min")
    return " ".join(parts) if parts else None


def _parse_servings(yield_data: dict) -> str | None:
    """Parse servings information."""
    servings_list = yield_data.get("servings", [])
    if not servings_list:
        return None
    serving = servings_list[0]
    count = serving.get("count")
    unit = serving.get("unit", "servings")
    if count:
        return f"{count} {unit}"
    return None


def _get_author(bylines: list) -> str | None:
    """Extract author name from bylines."""
    if not bylines:
        return None
    return bylines[0].get("displayName")


def _parse_description(headnote: Any) -> str:
    """Parse description/headnote which may be string or nested doc."""
    if isinstance(headnote, str):
        return headnote
    if isinstance(headnote, dict):
        # Extract text from nested doc structure
        texts = _extract_text_from_doc(headnote)
        return " ".join(texts).strip()
    return ""


def extract_next_data(html: str) -> dict[str, Any]:
    """Extract __NEXT_DATA__ JSON from an NYT Cooking page.

    Args:
        html: The full HTML content of the page.

    Returns:
        The parsed JSON data from the __NEXT_DATA__ script tag.

    Raises:
        ParseError: If the __NEXT_DATA__ script tag is not found or invalid.
    """
    pattern = r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>'
    match = re.search(pattern, html, re.DOTALL)

    if not match:
        raise ParseError("__NEXT_DATA__ script tag not found")

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise ParseError(f"Invalid JSON in __NEXT_DATA__: {e}")


def _parse_legacy_ingredients(ingredients_data: list) -> list[str]:
    """Parse ingredients from legacy recipe format (list of groups)."""
    result = []
    for group in ingredients_data:
        for ing in group.get("ingredients", []):
            text = ing.get("text", "")
            quantity = ing.get("quantity", "")
            if quantity and text:
                result.append(f"{quantity} {text}")
            elif text:
                result.append(text)
    return result


def _parse_legacy_steps(steps_data: list) -> list[str]:
    """Parse steps from legacy recipe format (list of groups)."""
    result = []
    for group in steps_data:
        for step in group.get("steps", []):
            if isinstance(step, str):
                result.append(step)
            elif isinstance(step, dict):
                # Try common field names for step text
                text = (
                    step.get("description")
                    or step.get("text")
                    or step.get("step")
                    or ""
                )
                if text:
                    result.append(text)
    return result


def parse_recipe(next_data: dict[str, Any]) -> dict[str, Any]:
    """Parse recipe data from __NEXT_DATA__ into our output schema.

    Handles both new (scoopRecipe) and legacy (recipe) formats.

    Args:
        next_data: The parsed __NEXT_DATA__ JSON.

    Returns:
        Recipe data in our output schema format.

    Raises:
        ParseError: If required recipe data is missing.
    """
    page_props = next_data.get("props", {}).get("pageProps", {})

    # Try new format first (scoopRecipe)
    if "scoopRecipe" in page_props:
        return _parse_scoop_recipe(page_props["scoopRecipe"])

    # Fall back to legacy format (recipe)
    if "recipe" in page_props:
        return _parse_legacy_recipe(page_props["recipe"])

    raise ParseError("Recipe data not found in page")


def _parse_scoop_recipe(scoop_recipe: dict) -> dict[str, Any]:
    """Parse new-style scoopRecipe format."""
    rating_data = scoop_recipe.get("rating", {})

    return {
        "id": str(scoop_recipe.get("externalId", "")),
        "name": scoop_recipe.get("title", ""),
        "url": scoop_recipe.get("url", ""),
        "author": _get_author(scoop_recipe.get("bylines", [])),
        "time": _parse_time(scoop_recipe.get("time", {})),
        "servings": _parse_servings(scoop_recipe.get("yield", {})),
        "rating": {
            "average": rating_data.get("roundedAverage"),
            "count": rating_data.get("count"),
        },
        "description": _parse_description(scoop_recipe.get("headnote", "")),
        "ingredients": _parse_ingredients(scoop_recipe.get("ingredients", {})),
        "steps": _parse_steps(scoop_recipe.get("preparation", {})),
    }


def _parse_legacy_recipe(recipe: dict) -> dict[str, Any]:
    """Parse legacy recipe format."""
    ratings = recipe.get("ratings", {})
    url = recipe.get("fullUrl") or recipe.get("url", "")
    if url and not url.startswith("http"):
        url = f"https://cooking.nytimes.com{url}"

    return {
        "id": str(recipe.get("id", "")),
        "name": recipe.get("title", ""),
        "url": url,
        "author": recipe.get("attribution") or None,
        "time": {
            "total": recipe.get("totalTime"),
            "prep": recipe.get("prepTime"),
            "cook": recipe.get("cookTime"),
        },
        "servings": recipe.get("recipeYield"),
        "rating": {
            "average": ratings.get("avgRating"),
            "count": ratings.get("numRatings"),
        },
        "description": recipe.get("topnote", ""),
        "ingredients": _parse_legacy_ingredients(recipe.get("ingredients", [])),
        "steps": _parse_legacy_steps(recipe.get("steps", [])),
    }


def _clean_search_url(url: str) -> str:
    """Clean search result URL by removing query params and adding domain."""
    # Remove query params (tracking info)
    clean_url = url.split("?")[0]
    # Add domain if relative URL
    if clean_url.startswith("/"):
        clean_url = f"https://cooking.nytimes.com{clean_url}"
    return clean_url


def parse_search_results(next_data: dict[str, Any]) -> dict[str, Any]:
    """Parse search results from __NEXT_DATA__ into our output schema.

    Args:
        next_data: The parsed __NEXT_DATA__ JSON.

    Returns:
        Search results in our output schema format.

    Raises:
        ParseError: If search results data is missing.
    """
    try:
        page_props = next_data["props"]["pageProps"]
        results = page_props["results"]
    except KeyError:
        raise ParseError("Search results not found in page")

    parsed_results = []
    for item in results:
        # Author is in contentAttribution.cardByline
        content_attr = item.get("contentAttribution", {})
        author = content_attr.get("cardByline") if content_attr else None

        parsed_results.append({
            "id": str(item.get("id", "")),
            "name": item.get("title", ""),
            "url": _clean_search_url(item.get("url", "")),
            "author": author,
        })

    return {
        "results": parsed_results,
        "count": len(parsed_results),
    }


def parse_saved_recipes(api_data: dict[str, Any]) -> dict[str, Any]:
    """Parse saved recipes from the recipe box API response.

    Args:
        api_data: The JSON response from the recipe box API.

    Returns:
        Saved recipes in our output schema format.

    Raises:
        ParseError: If the data format is unexpected.
    """
    try:
        collectables = api_data.get("collectables", [])
        total_count = api_data.get("collectables_count", len(collectables))
    except (KeyError, TypeError):
        raise ParseError("Unexpected format in saved recipes response")

    parsed_results = []
    for item in collectables:
        url = item.get("url", "")
        if url and not url.startswith("http"):
            url = f"https://cooking.nytimes.com{url}"

        parsed_results.append({
            "id": str(item.get("id", "")),
            "name": item.get("name", ""),
            "url": url,
            "author": item.get("byline"),
        })

    return {
        "results": parsed_results,
        "count": len(parsed_results),
        "total": total_count,
    }
