# NYT Cooking MCP

[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub-EA4AAA?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/bramboe?frequency=one-time) [![Sponsor bunq.me](https://img.shields.io/badge/Sponsor-bunq.me-2E9AD0)](https://bunq.me/bramboe)

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant
(Claude, etc.) **search New York Times Cooking, fetch full recipes, and browse
your saved recipe box.**

NYT Cooking has no official public API, so this reads the same JSON endpoints
the website itself uses. The recipe paywall is enforced client-side, so
**searching and reading full recipes needs no login at all** — only your
personal *saved recipe box* requires a session cookie.

## Tools

| Tool | Auth needed | Description |
| --- | --- | --- |
| `search_recipes(query)` | no | Search recipes by natural-language query. |
| `get_recipe(recipe_id)` | no | Full recipe: ingredients, steps, time, rating. |
| `list_saved_recipes(page, per_page)` | yes | Your saved recipe box. |
| `login(nyt_s_cookie, user_id)` | — | Store credentials server-side and verify them. |
| `logout()` | — | Delete the stored credentials. |
| `auth_status()` | — | Check whether credentials are configured. |

## Install & run

Requires Python 3.10+. With [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/bramboe/nyt-cooking-mcp
cd nyt-cooking-mcp
uv run nyt-cooking-mcp                                   # stdio (default)
uv run nyt-cooking-mcp --transport streamable-http --port 3001
```

Or with pipx / pip:

```bash
pipx install git+https://github.com/bramboe/nyt-cooking-mcp
nyt-cooking-mcp
```

## Use with Claude Desktop / Claude Code

Add to your MCP config (`claude_desktop_config.json`, or via `claude mcp add`):

```json
{
  "mcpServers": {
    "nyt-cooking": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/nyt-cooking-mcp", "nyt-cooking-mcp"]
    }
  }
}
```

Then ask: *"search NYT Cooking for marry me chicken"* or *"get NYT recipe 1024503"*.

## Saved recipes (optional login)

`list_saved_recipes` is the only tool that needs your account. NYT Cooking has
no OAuth, so credentials are harvested once from your logged-in browser and
persisted server-side (like a session token). Call the **`login`** tool with:

1. **`nyt_s_cookie`** — value of the `NYT-S` cookie on `cooking.nytimes.com`
   (DevTools → Application → Cookies).
2. **`user_id`** — the `regi_id` value inside the `regi_cookie`.

`login` verifies the cookie with a live request and writes it to the
credentials file (`--credentials-file`, default
`~/.config/nyt-cooking-mcp/credentials.json`). Environment variables
`NYT_S_COOKIE` / `NYT_USER_ID` override the stored file. The `NYT-S` cookie is
long-lived; when calls start returning `auth_required`, run `login` again.

## Self-hosting as an always-on service

Run it as a `systemd` service over streamable-HTTP so it is always available:

```ini
# /etc/systemd/system/nyt-cooking-mcp.service
[Unit]
Description=NYT Cooking MCP Server
After=network.target

[Service]
User=nyt-cooking
ExecStart=/opt/nyt-cooking-mcp/.venv/bin/nyt-cooking-mcp \
    --transport streamable-http --host 0.0.0.0 --port 3001 \
    --credentials-file /var/lib/nyt-cooking-mcp/credentials.json
# Permit LAN access while keeping DNS-rebinding protection on (localhost always allowed):
Environment=NYT_MCP_ALLOWED_HOSTS=your.server.ip:*
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

The HTTP endpoint is then `http://your.server:3001/mcp`. Put a reverse proxy
(TLS) and an auth token in front before exposing it beyond your trusted network.

## Disclaimer

For personal use. This is an unofficial tool not affiliated with The New York
Times; respect NYT Cooking's Terms of Service and use your own account.

## License

MIT — see [LICENSE](LICENSE).
