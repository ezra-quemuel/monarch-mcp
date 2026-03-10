"""MCP server for Monarch Money."""

import json
import os
from datetime import date
from typing import Optional

from mcp.server.fastmcp import FastMCP
from monarchmoney import MonarchMoney

# Patch the broken domain in the monarchmoney library
# (Monarch rebranded from monarchmoney.com to monarch.com)
if hasattr(MonarchMoney, "BASE_URL") and "monarchmoney.com" in MonarchMoney.BASE_URL:
    MonarchMoney.BASE_URL = MonarchMoney.BASE_URL.replace("api.monarchmoney.com", "api.monarch.com")

mcp = FastMCP("monarch-money")

# Cached authenticated client
_client: Optional[MonarchMoney] = None


async def get_client() -> MonarchMoney:
    """Lazy-initialize and cache the authenticated Monarch Money client."""
    global _client
    if _client is not None:
        return _client

    email = os.environ.get("MONARCH_EMAIL")
    password = os.environ.get("MONARCH_PASSWORD")
    mfa_secret = os.environ.get("MONARCH_MFA_SECRET")

    if not email or not password:
        raise ValueError("MONARCH_EMAIL and MONARCH_PASSWORD environment variables are required")

    mm = MonarchMoney()
    await mm.login(
        email=email,
        password=password,
        use_saved_session=True,
        save_session=True,
        mfa_secret_key=mfa_secret,
    )
    _client = mm
    return _client


def _slim_account(acct: dict, verbosity: str) -> dict:
    """Reduce account data based on verbosity level."""
    node = acct if "id" in acct else acct.get("node", acct)

    if verbosity == "ultra-light":
        return {
            "id": node.get("id"),
            "name": node.get("displayName") or node.get("name"),
            "balance": node.get("currentBalance") or node.get("displayBalance"),
            "type": node.get("type", {}).get("display") if isinstance(node.get("type"), dict) else node.get("type"),
        }

    if verbosity == "light":
        return {
            "id": node.get("id"),
            "name": node.get("displayName") or node.get("name"),
            "balance": node.get("currentBalance") or node.get("displayBalance"),
            "type": node.get("type", {}).get("display") if isinstance(node.get("type"), dict) else node.get("type"),
            "subtype": node.get("subtype", {}).get("display") if isinstance(node.get("subtype"), dict) else node.get("subtype"),
            "institution": node.get("credential", {}).get("institution", {}).get("name") if isinstance(node.get("credential"), dict) else None,
            "includeInNetWorth": node.get("includeInNetWorth"),
        }

    return node  # standard: return everything


def _slim_transaction(txn: dict, verbosity: str) -> dict:
    """Reduce transaction data based on verbosity level."""
    node = txn if "id" in txn else txn.get("node", txn)

    if verbosity == "ultra-light":
        return {
            "id": node.get("id"),
            "date": node.get("date"),
            "amount": node.get("amount"),
            "merchant": node.get("merchant", {}).get("name") if isinstance(node.get("merchant"), dict) else node.get("merchant"),
        }

    if verbosity == "light":
        return {
            "id": node.get("id"),
            "date": node.get("date"),
            "amount": node.get("amount"),
            "merchant": node.get("merchant", {}).get("name") if isinstance(node.get("merchant"), dict) else node.get("merchant"),
            "category": node.get("category", {}).get("name") if isinstance(node.get("category"), dict) else node.get("category"),
            "account": node.get("account", {}).get("displayName") if isinstance(node.get("account"), dict) else node.get("account"),
            "notes": node.get("notes"),
        }

    return node


def _slim_budget(item: dict, verbosity: str) -> dict:
    """Reduce budget item based on verbosity level."""
    if verbosity == "ultra-light":
        cat = item.get("category", {})
        return {
            "categoryId": cat.get("id") if isinstance(cat, dict) else None,
            "category": cat.get("name") if isinstance(cat, dict) else cat,
            "budgeted": item.get("budgetAmount") or item.get("plannedCashFlowAmount"),
            "actual": item.get("actualAmount") or item.get("actualCashFlowAmount"),
        }

    if verbosity == "light":
        cat = item.get("category", {})
        return {
            "categoryId": cat.get("id") if isinstance(cat, dict) else None,
            "category": cat.get("name") if isinstance(cat, dict) else cat,
            "budgeted": item.get("budgetAmount") or item.get("plannedCashFlowAmount"),
            "actual": item.get("actualAmount") or item.get("actualCashFlowAmount"),
            "remaining": item.get("remainingAmount"),
            "rolloverAmount": item.get("rolloverAmount"),
        }

    return item


def _extract_items(data: dict, key: str) -> list:
    """Extract list items from GraphQL-style response (handles edges/node pattern)."""
    obj = data.get(key, data)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        edges = obj.get("edges")
        if edges:
            return [e.get("node", e) for e in edges]
        results = obj.get("results") or obj.get("allTransactions", {}).get("results", [])
        if results:
            return results
    return [obj] if obj else []


@mcp.tool()
async def get_accounts(verbosity: str = "light") -> str:
    """Get all financial accounts from Monarch Money.

    Args:
        verbosity: Detail level — "ultra-light", "light", or "standard"
    """
    mm = await get_client()
    data = await mm.get_accounts()
    accounts = _extract_items(data, "accounts")
    slimmed = [_slim_account(a, verbosity) for a in accounts]
    return json.dumps(slimmed, indent=2, default=str)


@mcp.tool()
async def get_transactions(
    limit: int = 50,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: str = "",
    verbosity: str = "light",
) -> str:
    """Get transactions from Monarch Money.

    Args:
        limit: Max number of transactions to return (default 50)
        start_date: Filter start date (YYYY-MM-DD)
        end_date: Filter end date (YYYY-MM-DD)
        search: Search term to filter transactions
        verbosity: Detail level — "ultra-light", "light", or "standard"
    """
    mm = await get_client()
    data = await mm.get_transactions(
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        search=search,
    )
    transactions = _extract_items(data, "allTransactions")
    slimmed = [_slim_transaction(t, verbosity) for t in transactions]
    return json.dumps(slimmed, indent=2, default=str)


@mcp.tool()
async def get_budgets(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    verbosity: str = "light",
) -> str:
    """Get budget data from Monarch Money.

    Args:
        start_date: Budget period start (YYYY-MM-DD). Defaults to current month.
        end_date: Budget period end (YYYY-MM-DD). Defaults to current month.
        verbosity: Detail level — "ultra-light", "light", or "standard"
    """
    mm = await get_client()
    today = date.today()
    sd = start_date or today.replace(day=1).isoformat()
    ed = end_date or today.isoformat()
    data = await mm.get_budgets(start_date=sd, end_date=ed, use_legacy_goals=False, use_v2_goals=False)

    # Build category ID -> name lookup from categoryGroups
    category_map: dict[str, str] = {}
    for group in data.get("categoryGroups", []):
        for cat in group.get("categories", []):
            category_map[cat["id"]] = cat["name"]

    # Extract per-category budget data
    budget_data = data.get("budgetData", {})
    monthly_by_category = budget_data.get("monthlyAmountsByCategory", [])

    items = []
    for entry in monthly_by_category:
        cat_id = entry.get("category", {}).get("id")
        cat_name = category_map.get(cat_id, f"Category {cat_id}")
        monthly = entry.get("monthlyAmounts", [{}])[0] if entry.get("monthlyAmounts") else {}
        budgeted = monthly.get("plannedCashFlowAmount") or 0
        actual = monthly.get("actualAmount") or 0
        remaining = monthly.get("remainingAmount") or 0
        if budgeted != 0 or actual != 0:
            items.append({
                "categoryId": cat_id,
                "category": cat_name,
                "budgeted": budgeted,
                "actual": actual,
                "remaining": remaining,
            })

    return json.dumps(items, indent=2, default=str)


@mcp.tool()
async def list_categories() -> str:
    """List all transaction categories from Monarch Money."""
    mm = await get_client()
    data = await mm.get_transaction_categories()
    categories = _extract_items(data, "categories")
    result = [{"id": c.get("id"), "name": c.get("name"), "group": c.get("group", {}).get("name") if isinstance(c.get("group"), dict) else c.get("group")} for c in categories]
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def set_budget(
    category_id: str,
    amount: float,
    start_date: Optional[str] = None,
    apply_to_future: bool = False,
) -> str:
    """Set a budget amount for a category in Monarch Money.

    Args:
        category_id: The category ID to set the budget for
        amount: Monthly budget amount
        start_date: Budget start date (YYYY-MM-DD). Defaults to first of current month.
        apply_to_future: Apply this budget to all future months
    """
    mm = await get_client()
    today = date.today()
    sd = start_date or today.replace(day=1).isoformat()
    result = await mm.set_budget_amount(
        amount=amount,
        category_id=category_id,
        start_date=sd,
        apply_to_future=apply_to_future,
    )
    return json.dumps(result, indent=2, default=str)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
