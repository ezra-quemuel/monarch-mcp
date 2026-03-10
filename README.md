# Monarch Money MCP Server

An MCP server that exposes Monarch Money financial data to Claude Code and other MCP clients.

## Tools

| Tool | Description |
|------|-------------|
| `get_accounts` | List financial accounts (verbosity: ultra-light, light, standard) |
| `get_transactions` | Query transactions with filters (limit, date range, search, verbosity) |
| `get_budgets` | Get budget data for a date range (verbosity) |
| `list_categories` | List all transaction categories with IDs |
| `set_budget` | Set a budget amount for a category |

## Setup

### 1. Install

```bash
cd ~/Projects/monarch-mcp
pip install -e .
```

Or with uv:

```bash
cd ~/Projects/monarch-mcp
uv pip install -e .
```

### 2. Configure environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MONARCH_EMAIL` | Yes | Your Monarch Money email |
| `MONARCH_PASSWORD` | Yes | Your Monarch Money password |
| `MONARCH_MFA_SECRET` | No | TOTP secret for MFA (base32 string from authenticator setup) |

### 3. Add to Claude Code

Add to `~/.claude/claude_desktop_config.json` or your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "monarch-money": {
      "command": "python",
      "args": ["-m", "monarch_mcp.server"],
      "cwd": "/Users/ezra/Projects/monarch-mcp/src",
      "env": {
        "MONARCH_EMAIL": "your-email@example.com",
        "MONARCH_PASSWORD": "your-password",
        "MONARCH_MFA_SECRET": "your-totp-secret"
      }
    }
  }
}
```

Or if installed as a package:

```json
{
  "mcpServers": {
    "monarch-money": {
      "command": "monarch-mcp",
      "env": {
        "MONARCH_EMAIL": "your-email@example.com",
        "MONARCH_PASSWORD": "your-password"
      }
    }
  }
}
```

## Verbosity Levels

- **ultra-light** — Minimal fields (id, name/merchant, amount/balance)
- **light** — Key fields including category, account, institution (default)
- **standard** — Full response from Monarch Money API

## License

MIT
