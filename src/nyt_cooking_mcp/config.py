"""Credential resolution and persistence for the NYT Cooking MCP server.

Credentials are resolved in this order:
1. Environment variables NYT_S_COOKIE / NYT_USER_ID.
2. A persisted credentials file (written by the `login` tool), AH-style.
   Path: NYT_CREDENTIALS_FILE env var, or a per-process override set via
   set_credentials_file(), or ~/.config/nyt-cooking-mcp/credentials.json.
3. The legacy config file written by the `nytc` CLI at
   ~/.config/nytc/config.json ({"cookie": ..., "user_id": ...}).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Optional per-process override (set from the CLI --credentials-file flag).
_credentials_file_override: Path | None = None


def set_credentials_file(path: str | os.PathLike[str]) -> None:
    """Override the credentials file location for this process."""
    global _credentials_file_override
    _credentials_file_override = Path(path)


def credentials_path() -> Path:
    """Resolve where persisted credentials live."""
    if _credentials_file_override is not None:
        return _credentials_file_override
    env = os.environ.get("NYT_CREDENTIALS_FILE")
    if env:
        return Path(env)
    return Path.home() / ".config" / "nyt-cooking-mcp" / "credentials.json"


def _legacy_nytc_path() -> Path:
    return Path.home() / ".config" / "nytc" / "config.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def load_credentials() -> dict[str, Any]:
    """Load persisted credentials ({"cookie": ..., "user_id": ...})."""
    data = _read_json(credentials_path())
    if data:
        return data
    return _read_json(_legacy_nytc_path())


def save_credentials(cookie: str, user_id: str | None) -> Path:
    """Persist credentials to the credentials file with 0600 perms."""
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"cookie": cookie}
    if user_id:
        payload["user_id"] = user_id
    path.write_text(json.dumps(payload, indent=2))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def clear_credentials() -> bool:
    """Remove the persisted credentials file. Returns True if one existed."""
    path = credentials_path()
    if path.exists():
        path.unlink()
        return True
    return False


def get_cookie() -> str | None:
    """Return the NYT-S cookie value, or None if not configured."""
    return os.environ.get("NYT_S_COOKIE") or load_credentials().get("cookie")


def get_user_id() -> str | None:
    """Return the NYT user id (regi_id), or None if not configured."""
    return os.environ.get("NYT_USER_ID") or load_credentials().get("user_id")
