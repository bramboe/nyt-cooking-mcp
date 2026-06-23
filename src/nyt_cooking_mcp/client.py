"""HTTP access to the public NYT Cooking website.

NYT Cooking exposes no official API; this issues the same plain requests a
browser would. Recipe and search pages are public HTML; the recipe box is a
JSON endpoint that requires the signed-in ``NYT-S`` cookie.
"""

from __future__ import annotations

import requests

from nyt_cooking_mcp.config import get_cookie, get_user_id

SITE = "https://cooking.nytimes.com"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class CookingError(Exception):
    """Base error for NYT Cooking access."""


class AuthError(CookingError):
    """Credentials are missing or were rejected."""


class NotFoundError(CookingError):
    """The requested resource does not exist."""


class NetworkError(CookingError):
    """The request could not be completed."""


class CookingClient:
    """Thin wrapper around a ``requests`` session for cooking.nytimes.com."""

    def __init__(self, cookie: str | None = None, timeout: int = 30):
        self._timeout = timeout
        self._http = requests.Session()
        self._http.headers["User-Agent"] = _BROWSER_UA
        token = cookie if cookie is not None else get_cookie()
        if token:
            self._http.cookies.set("NYT-S", token, domain=".nytimes.com")

    def _get(self, url: str, **kwargs) -> requests.Response:
        try:
            response = self._http.get(url, timeout=self._timeout, **kwargs)
        except requests.RequestException as exc:
            raise NetworkError(str(exc)) from exc

        status = response.status_code
        if status in (401, 403):
            raise AuthError(
                "NYT Cooking rejected the request — not signed in, or the "
                "NYT-S cookie is missing or expired."
            )
        if status == 404:
            raise NotFoundError(f"Nothing found at {url}.")
        if not response.ok:
            raise NetworkError(f"NYT Cooking returned HTTP {status}.")
        return response

    # The site's JSON endpoints require this header to be served.
    _API_HEADERS = {"x-cooking-api": "cooking-frontend", "accept": "*/*"}

    def recipe_json(self, recipe_id: str) -> dict:
        """Return the full recipe payload from the JSON recipe endpoint."""
        response = self._get(
            f"{SITE}/api/v2/recipes/{recipe_id}", headers=self._API_HEADERS
        )
        return self._json(response, "Recipe")

    def search_page(self, query: str) -> str:
        """Return the HTML of a search results page."""
        return self._get(f"{SITE}/search", params={"q": query}).text

    def recipe_box(self, page: int = 1, per_page: int = 48) -> dict:
        """Return the JSON recipe box for the signed-in user."""
        user_id = get_user_id()
        if not user_id:
            raise AuthError(
                "No user id configured — run the login tool with your regi_id."
            )
        response = self._get(
            f"{SITE}/api/v2/users/{user_id}/search/recipe_box_search",
            params={"q": "", "page": page, "per_page": per_page},
            headers=self._API_HEADERS,
        )
        return self._json(response, "Recipe box")

    @staticmethod
    def _json(response: requests.Response, what: str) -> dict:
        try:
            return response.json()
        except ValueError as exc:
            raise NetworkError(f"{what} response was not valid JSON.") from exc
