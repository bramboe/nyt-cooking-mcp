"""MCP server exposing NYT Cooking search, recipe retrieval and saved recipes."""

from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from nyt_cooking_mcp.client import (
    AuthError,
    CookingClient,
    NetworkError,
    NotFoundError,
)
from nyt_cooking_mcp.config import (
    clear_credentials,
    credentials_path,
    get_cookie,
    get_user_id,
    save_credentials,
    set_credentials_file,
)
from nyt_cooking_mcp import extract
from nyt_cooking_mcp.extract import ParseError

mcp = FastMCP("nyt-cooking")


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": code, "message": message}


@mcp.tool()
def search_recipes(query: str) -> dict[str, Any]:
    """Search NYT Cooking for recipes matching a natural-language query.

    Args:
        query: Search terms, e.g. "chicken parmesan" or "vegetarian chili".

    Returns a list of results with id, name, url and author. Use the id with
    get_recipe to fetch full ingredients and steps.
    """
    try:
        client = CookingClient()
        return extract.search(client.search_page(query))
    except AuthError as e:
        return _error("auth_required", str(e))
    except NetworkError as e:
        return _error("network_error", str(e))
    except ParseError as e:
        return _error("parse_error", str(e))


@mcp.tool()
def get_recipe(recipe_id: str) -> dict[str, Any]:
    """Fetch full details for a single NYT Cooking recipe by its numeric id.

    Args:
        recipe_id: The recipe id, e.g. "1019049" (from a search result or URL).

    Returns name, author, time, servings, rating, description, ingredients
    and step-by-step instructions.
    """
    try:
        client = CookingClient()
        return extract.recipe(client.recipe_json(recipe_id))
    except AuthError as e:
        return _error("auth_required", str(e))
    except NotFoundError as e:
        return _error("not_found", str(e))
    except NetworkError as e:
        return _error("network_error", str(e))
    except ParseError as e:
        return _error("parse_error", str(e))


@mcp.tool()
def list_saved_recipes(page: int = 1, per_page: int = 48) -> dict[str, Any]:
    """List recipes saved in the user's NYT Cooking recipe box.

    Requires a configured user id and a valid session cookie (see `login`).

    Args:
        page: 1-indexed page number.
        per_page: Number of results per page (default 48).
    """
    try:
        client = CookingClient()
        return extract.recipe_box(client.recipe_box(page=page, per_page=per_page))
    except AuthError as e:
        return _error("auth_required", str(e))
    except NetworkError as e:
        return _error("network_error", str(e))
    except ParseError as e:
        return _error("parse_error", str(e))


@mcp.tool()
def login(nyt_s_cookie: str, user_id: str = "") -> dict[str, Any]:
    """Store your NYT Cooking credentials so the server stays logged in.

    NYT Cooking has no OAuth, so credentials are harvested once from your
    logged-in browser and persisted server-side (like a session token):
      - nyt_s_cookie: value of the `NYT-S` cookie on cooking.nytimes.com
        (DevTools -> Application -> Cookies).
      - user_id: the `regi_id` value inside the `regi_cookie` (needed only
        for list_saved_recipes).

    The credentials are written to the server's credentials file and verified
    with a live request before returning.
    """
    if not nyt_s_cookie.strip():
        return _error("invalid_input", "nyt_s_cookie must not be empty.")

    path = save_credentials(nyt_s_cookie.strip(), user_id.strip() or None)

    # Verify the cookie with a lightweight live request.
    try:
        client = CookingClient(cookie=nyt_s_cookie.strip())
        client.search_page("salt")
        verified = True
        detail = "Cookie verified against cooking.nytimes.com."
    except AuthError:
        verified = False
        detail = "Saved, but the cookie was rejected (401/403). It may be wrong or expired."
    except (NetworkError, ParseError) as e:
        verified = False
        detail = f"Saved, but verification request did not complete: {e}"

    return {
        "ok": True,
        "verified": verified,
        "credentials_file": str(path),
        "user_id_stored": bool(user_id.strip()),
        "detail": detail,
    }


@mcp.tool()
def logout() -> dict[str, Any]:
    """Delete the stored NYT Cooking credentials from the server."""
    existed = clear_credentials()
    return {"ok": True, "removed": existed, "credentials_file": str(credentials_path())}


@mcp.tool()
def auth_status() -> dict[str, Any]:
    """Report whether NYT credentials (session cookie and user id) are configured.

    Does not reveal the values. Useful for diagnosing auth_required errors.
    """
    return {
        "cookie_configured": bool(get_cookie()),
        "user_id_configured": bool(get_user_id()),
        "credentials_file": str(credentials_path()),
        "hint": (
            "Use the `login` tool with your NYT-S cookie (and regi_id user id). "
            "Env vars NYT_S_COOKIE / NYT_USER_ID override the stored file."
        ),
    }


def main() -> None:
    """Run the MCP server. Supports stdio, sse and streamable-http transports."""
    parser = argparse.ArgumentParser(description="NYT Cooking MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.environ.get("NYT_MCP_TRANSPORT", "stdio"),
        help="Transport mode (default: stdio).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("NYT_MCP_PORT", "3001")),
        help="Port for http/sse transports (default: 3001).",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("NYT_MCP_HOST", "0.0.0.0"),
        help="Bind host for http/sse transports (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--credentials-file",
        default=os.environ.get("NYT_CREDENTIALS_FILE"),
        help="Path to the persisted credentials file.",
    )
    args = parser.parse_args()

    if args.credentials_file:
        set_credentials_file(args.credentials_file)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        from mcp.server.transport_security import TransportSecuritySettings

        mcp.settings.host = args.host
        mcp.settings.port = args.port

        # DNS-rebinding protection. By default only localhost is allowed; set
        # NYT_MCP_ALLOWED_HOSTS (comma-separated, e.g. "your.server.ip:*")
        # to permit LAN access while keeping the protection enabled.
        extra = [
            h.strip()
            for h in os.environ.get("NYT_MCP_ALLOWED_HOSTS", "").split(",")
            if h.strip()
        ]
        hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*", *extra]
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=hosts,
        )
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
