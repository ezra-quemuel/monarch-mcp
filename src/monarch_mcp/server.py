"""MCP server for Monarch Money.

Exposes Monarch Money financial data (accounts, transactions, budgets,
categories) as tools for Claude and other MCP clients.

Requires MONARCH_EMAIL and MONARCH_PASSWORD environment variables.
Optionally set MONARCH_MFA_SECRET for accounts with MFA enabled.
"""

import json
import os
from datetime import date
from functools import wraps
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from monarchmoney import MonarchMoney

# Patch the broken domain in the monarchmoney library.
# Monarch rebranded from monarchmoney.com to monarch.com, but the library
# hasn't been updated yet.
if hasattr(MonarchMoney, "BASE_URL") and "monarchmoney.com" in MonarchMoney.BASE_URL:
    MonarchMoney.BASE_URL = MonarchMoney.BASE_URL.replace(
        "api.monarchmoney.com", "api.monarch.com"
    )

mcp = FastMCP("monarch-money")

# Cached authenticated client
_client: Optional[MonarchMoney] = None


async def _login() -> MonarchMoney:
    """Create and authenticate a new Monarch Money client."""
    email = os.environ.get("MONARCH_EMAIL")
    password = os.environ.get("MONARCH_PASSWORD")
    mfa_secret = os.environ.get("MONARCH_MFA_SECRET")

    if not email or not password:
        raise ValueError(
            "MONARCH_EMAIL and MONARCH_PASSWORD environment variables are required"
        )

    mm = MonarchMoney()
    await mm.login(
        email=email,
        password=password,
        use_saved_session=True,
        save_session=True,
        mfa_secret_key=mfa_secret,
    )
    return mm


async def get_client() -> MonarchMoney:
    """Lazy-initialize and cache the authenticated Monarch Money client."""
    global _client
    if _client is not None:
        return _client
    _client = await _login()
    return _client


async def invalidate_client() -> None:
    """Clear the cached client so the next call re-authenticates."""
    global _client
    _client = None


def auto_retry_on_401(fn: Callable) -> Callable:
    """Decorator that retries a tool function once on 401 Unauthorized."""

    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            if "401" in str(e) or "Unauthorized" in str(e):
                await invalidate_client()
                return await fn(*args, **kwargs)
            raise

    return wrapper


def _slim_account(acct: dict, verbosity: str) -> dict:
    """Reduce account data based on verbosity level.

    Args:
        acct: Raw account dict from the Monarch API (may be nested in node).
        verbosity: "ultra-light", "light", or "standard".
    """
    node = acct if "id" in acct else acct.get("node", acct)

    if verbosity == "ultra-light":
        return {
            "id": node.get("id"),
            "name": node.get("displayName") or node.get("name"),
            "balance": node.get("currentBalance") or node.get("displayBalance"),
            "type": (
                node.get("type", {}).get("display")
                if isinstance(node.get("type"), dict)
                else node.get("type")
            ),
        }

    if verbosity == "light":
        return {
            "id": node.get("id"),
            "name": node.get("displayName") or node.get("name"),
            "balance": node.get("currentBalance") or node.get("displayBalance"),
            "type": (
                node.get("type", {}).get("display")
                if isinstance(node.get("type"), dict)
                else node.get("type")
            ),
            "subtype": (
                node.get("subtype", {}).get("display")
                if isinstance(node.get("subtype"), dict)
                else node.get("subtype")
            ),
            "institution": (
                node.get("credential", {}).get("institution", {}).get("name")
                if isinstance(node.get("credential"), dict)
                else None
            ),
            "includeInNetWorth": node.get("includeInNetWorth"),
        }

    return node  # standard: return everything


def _slim_transaction(txn: dict, verbosity: str) -> dict:
    """Reduce transaction data based on verbosity level.

    Args:
        txn: Raw transaction dict from the Monarch API (may be nested in node).
        verbosity: "ultra-light", "light", or "standard".
    """
    node = txn if "id" in txn else txn.get("node", txn)

    if verbosity == "ultra-light":
        return {
            "id": node.get("id"),
            "date": node.get("date"),
            "amount": node.get("amount"),
            "merchant": (
                node.get("merchant", {}).get("name")
                if isinstance(node.get("merchant"), dict)
                else node.get("merchant")
            ),
        }

    if verbosity == "light":
        return {
            "id": node.get("id"),
            "date": node.get("date"),
            "amount": node.get("amount"),
            "merchant": (
                node.get("merchant", {}).get("name")
                if isinstance(node.get("merchant"), dict)
                else node.get("merchant")
            ),
            "category": (
                node.get("category", {}).get("name")
                if isinstance(node.get("category"), dict)
                else node.get("category")
            ),
            "account": (
                node.get("account", {}).get("displayName")
                if isinstance(node.get("account"), dict)
                else node.get("account")
            ),
            "notes": node.get("notes"),
        }

    return node  # standard: return everything


def _extract_items(data: dict, key: str) -> list:
    """Extract list items from a GraphQL-style response.

    Handles the edges/node pattern commonly used by the Monarch API.

    Args:
        data: Raw API response dict.
        key: Top-level key to extract from.
    """
    obj = data.get(key, data)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        edges = obj.get("edges")
        if edges:
            return [e.get("node", e) for e in edges]
        results = obj.get("results") or obj.get(
            "allTransactions", {}
        ).get("results", [])
        if results:
            return results
    return [obj] if obj else []


@mcp.tool()
@auto_retry_on_401
async def get_accounts(verbosity: str = "light") -> str:
    """Get all financial accounts from Monarch Money.

    Returns account balances, types, and institutions. Use this to see
    a summary of all linked accounts.

    Args:
        verbosity: Detail level - "ultra-light" (id/name/balance/type),
                   "light" (adds subtype/institution), or "standard" (full API response).
    """
    mm = await get_client()
    data = await mm.get_accounts()
    accounts = _extract_items(data, "accounts")
    slimmed = [_slim_account(a, verbosity) for a in accounts]
    return json.dumps(slimmed, indent=2, default=str)


@mcp.tool()
@auto_retry_on_401
async def get_transactions(
    limit: int = 50,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: str = "",
    verbosity: str = "light",
) -> str:
    """Get transactions from Monarch Money.

    Query recent transactions with optional filters for date range and
    search terms. Returns merchant, amount, category, and account info.

    Args:
        limit: Max number of transactions to return (default 50).
        start_date: Filter start date (YYYY-MM-DD).
        end_date: Filter end date (YYYY-MM-DD).
        search: Search term to filter transactions by merchant/description.
        verbosity: Detail level - "ultra-light", "light", or "standard".
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
@auto_retry_on_401
async def get_budgets(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Get budget data from Monarch Money.

    Returns per-category budget amounts, actual spending, and remaining
    amounts for the specified date range.

    Args:
        start_date: Budget period start (YYYY-MM-DD). Defaults to first of current month.
        end_date: Budget period end (YYYY-MM-DD). Defaults to today.
    """
    mm = await get_client()
    today = date.today()
    sd = start_date or today.replace(day=1).isoformat()
    ed = end_date or today.isoformat()
    data = await mm.get_budgets(
        start_date=sd,
        end_date=ed,
        use_legacy_goals=False,
        use_v2_goals=False,
    )

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
        monthly = (
            entry.get("monthlyAmounts", [{}])[0]
            if entry.get("monthlyAmounts")
            else {}
        )
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
@auto_retry_on_401
async def list_categories() -> str:
    """List all transaction categories from Monarch Money.

    Returns category IDs, names, and group names. Use this to find
    category IDs needed for set_budget or update_transaction.
    """
    mm = await get_client()
    data = await mm.get_transaction_categories()
    categories = _extract_items(data, "categories")
    result = [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "group": (
                c.get("group", {}).get("name")
                if isinstance(c.get("group"), dict)
                else c.get("group")
            ),
        }
        for c in categories
    ]
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
@auto_retry_on_401
async def set_budget(
    category_id: str,
    amount: float,
    start_date: Optional[str] = None,
    apply_to_future: bool = False,
) -> str:
    """Set a budget amount for a category in Monarch Money.

    Use list_categories to find the category ID first.

    Args:
        category_id: The category ID to set the budget for.
        amount: Monthly budget amount in dollars.
        start_date: Budget start date (YYYY-MM-DD). Defaults to first of current month.
        apply_to_future: Apply this budget to all future months.
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


@mcp.tool()
@auto_retry_on_401
async def update_transaction(
    transaction_id: str,
    category_id: Optional[str] = None,
    merchant_name: Optional[str] = None,
    amount: Optional[float] = None,
    date: Optional[str] = None,
    notes: Optional[str] = None,
    hide_from_reports: Optional[bool] = None,
    needs_review: Optional[bool] = None,
) -> str:
    """Update an existing transaction in Monarch Money.

    Only the fields you provide will be updated; others remain unchanged.

    Args:
        transaction_id: The transaction ID to update.
        category_id: New category ID (use list_categories to find IDs).
        merchant_name: New merchant name.
        amount: New amount in dollars.
        date: New date (YYYY-MM-DD).
        notes: New notes (empty string to clear).
        hide_from_reports: Hide this transaction from reports.
        needs_review: Mark as needs review.
    """
    mm = await get_client()
    kwargs: dict = {"transaction_id": transaction_id}
    if category_id is not None:
        kwargs["category_id"] = category_id
    if merchant_name is not None:
        kwargs["merchant_name"] = merchant_name
    if amount is not None:
        kwargs["amount"] = amount
    if date is not None:
        kwargs["date"] = date
    if notes is not None:
        kwargs["notes"] = notes
    if hide_from_reports is not None:
        kwargs["hide_from_reports"] = hide_from_reports
    if needs_review is not None:
        kwargs["needs_review"] = needs_review
    result = await mm.update_transaction(**kwargs)
    return json.dumps(result, indent=2, default=str)


def main():
    """Entry point for the monarch-mcp CLI command."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
