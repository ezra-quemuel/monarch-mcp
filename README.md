# Monarch Money MCP Server

An [MCP](https://modelcontextprotocol.io/) server that connects Claude (and other MCP clients) to your [Monarch Money](https://www.monarchmoney.com/) financial data. Query accounts, transactions, and budgets, or update transactions and budget amounts — all through natural language.

## Features

| Tool | Description |
|------|-------------|
| `get_accounts` | List all linked financial accounts with balances and types |
| `get_transactions` | Query transactions with filters (limit, date range, search) |
| `get_budgets` | Get per-category budget vs. actual spending for a date range |
| `list_categories` | List all transaction categories with IDs and group names |
| `set_budget` | Set a monthly budget amount for a category |
| `update_transaction` | Update a transaction's category, merchant, notes, etc. |

Most read tools support a `verbosity` parameter (`ultra-light`, `light`, or `standard`) to control how much data is returned.

## Prerequisites

- Python 3.10+
- A [Monarch Money](https://www.monarchmoney.com/) account
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or [Claude Desktop](https://claude.ai/download) (or any MCP client)

## Installation

### From GitHub

```bash
pip install git+https://github.com/ezra-quemuel/monarch-mcp.git
```

### From source

```bash
git clone https://github.com/ezra-quemuel/monarch-mcp.git
cd monarch-mcp
pip install -e .
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MONARCH_EMAIL` | Yes | Your Monarch Money email |
| `MONARCH_PASSWORD` | Yes | Your Monarch Money password |
| `MONARCH_MFA_SECRET` | No | TOTP secret for MFA (base32 string from authenticator setup) |

### Claude Code

```bash
claude mcp add monarch-money \
  -e MONARCH_EMAIL=your-email@example.com \
  -e MONARCH_PASSWORD=your-password \
  -e MONARCH_MFA_SECRET=your-totp-secret \
  -- monarch-mcp
```

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "monarch-money": {
      "command": "monarch-mcp",
      "env": {
        "MONARCH_EMAIL": "your-email@example.com",
        "MONARCH_PASSWORD": "your-password",
        "MONARCH_MFA_SECRET": "your-totp-secret"
      }
    }
  }
}
```

If you installed from source with a virtual environment, use the full path to the `monarch-mcp` binary (e.g., `/path/to/monarch-mcp/.venv/bin/monarch-mcp`).

## Known Issues

### `gql` must be pinned to `<4.0`

The `monarchmoney` library depends on `gql`, but `gql` 4.0 changed the signature of `execute_async` in a breaking way. This project pins `gql<4.0` in its dependencies to avoid this.

### Domain rebrand (`monarchmoney.com` -> `monarch.com`)

Monarch rebranded their API domain from `api.monarchmoney.com` to `api.monarch.com`. The `monarchmoney` library hasn't been updated yet. This server patches `MonarchMoney.BASE_URL` at runtime to fix this automatically — no manual action needed.

### Budget goals fields

The `monarchmoney` library's GraphQL query for `get_budgets` references goals-related fields that no longer exist in the API schema. This server works around this by passing `use_legacy_goals=False, use_v2_goals=False`. If you still encounter errors, you may need to manually edit the installed `monarchmoney` library to remove the goals fields from the budget query. Look for the `get_budgets` query in `monarchmoney/__init__.py` or the relevant query file and remove the `goals { ... }` block.

## Contributing

Contributions are welcome! Please open an issue or pull request on [GitHub](https://github.com/ezra-quemuel/monarch-mcp).

## License

[MIT](LICENSE)
