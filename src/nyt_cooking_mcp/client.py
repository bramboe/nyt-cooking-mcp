"""HTTP client for NYT Cooking.

Adapted from https://github.com/atmz/nytccli (MIT). NYT Cooking has no
official public API, so this drives the website using the user's session
cookie, exactly as the browser does.
"""

from __future__ import annotations

import requests

from nyt_cooking_mcp.config import get_cookie, get_user_id


class NytcError(Exception):
    """Base exception for client errors."""


class AuthError(NytcError):
    """Raised when authentication fails or is missing."""


class NotFoundError(NytcError):
    """Raised when a resource is not found."""


class NetworkError(NytcError):
    """Raised when a network request fails."""


class NytcClient:
    """HTTP client for the NYT Cooking website."""

    BASE_URL = "https://cooking.nytimes.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def __init__(self, cookie: str | None = None):
        self.cookie = cookie or get_cookie()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        if self.cookie:
            self.session.cookies.set("NYT-S", self.cookie, domain=".nytimes.com")

    def fetch_page(self, url: str) -> str:
        """Fetch an HTML page from NYT Cooking."""
        if not url.startswith("http"):
            url = f"{self.BASE_URL}{url}"

        try:
            response = self.session.get(url, timeout=30)
        except requests.RequestException as e:
            raise NetworkError(f"Request failed: {e}")

        if response.status_code in (401, 403):
            raise AuthError(
                "Authentication required or session expired. Set NYT_S_COOKIE "
                "(and NYT_USER_ID) or run `nytc auth`."
            )
        if response.status_code == 404:
            raise NotFoundError(f"Page not found: {url}")
        if not response.ok:
            raise NetworkError(f"Request failed with status {response.status_code}")

        return response.text

    def get_recipe_url(self, recipe_id: str) -> str:
        return f"{self.BASE_URL}/recipes/{recipe_id}"

    def get_search_url(self, query: str) -> str:
        return f"{self.BASE_URL}/search?q={requests.utils.quote(query)}"

    def fetch_saved_recipes(self, page: int = 1, per_page: int = 48) -> dict:
        """Fetch saved recipes from the recipe box API."""
        user_id = get_user_id()
        if not user_id:
            raise AuthError(
                "User ID not configured. Set NYT_USER_ID or run `nytc auth`."
            )

        url = (
            f"{self.BASE_URL}/api/v2/users/{user_id}/search/recipe_box_search"
            f"?q=&per_page={per_page}&page={page}"
        )
        headers = {"x-cooking-api": "cooking-frontend", "accept": "*/*"}

        try:
            response = self.session.get(url, headers=headers, timeout=30)
        except requests.RequestException as e:
            raise NetworkError(f"Request failed: {e}")

        if response.status_code in (401, 403):
            raise AuthError(
                "Authentication failed. Your session may have expired. "
                "Update NYT_S_COOKIE or run `nytc auth`."
            )
        if not response.ok:
            raise NetworkError(f"Request failed with status {response.status_code}")

        return response.json()
