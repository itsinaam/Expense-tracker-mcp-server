# Expense Tracker MCP Server

A local Model Context Protocol (MCP) server for recording expenses, reviewing spending, and managing monthly category budgets. It uses SQLite for storage and FastMCP for the HTTP transport.

## Features

- Create, list, inspect, update, and delete expense records.
- Filter expenses by inclusive date range and category.
- Summarize expenses by category over a date range or calendar month.
- Create, list, and delete monthly category budgets.
- Compare budget limits with actual spending, remaining amounts, and percentage used.
- Read the configured category list through the `expense:///categories` MCP resource.

## Requirements

- Python 3.10 or newer
- Packages in `requirements.txt`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

The server listens on `http://127.0.0.1:8000/mcp`. Keep it bound to localhost unless you configure an authenticated, protected deployment environment; this server does not provide application-level authentication.

For VS Code, add the following server entry to `.vscode/mcp.json` while the server is running:

```json
{
  "servers": {
    "expense-tracker": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

To select a persistent database location, set `EXPENSE_DB_PATH` before starting the server:

```powershell
$env:EXPENSE_DB_PATH = "$HOME\expense-tracker\expenses.db"
python main.py
```

If `EXPENSE_DB_PATH` is not set, the database is stored as `expenses.db` in the operating system's temporary directory. Temporary directories may be cleared by the OS, so configure a persistent path for important data. Existing installations using the default path continue using that same database.

## MCP tools

| Tool | Purpose | Important arguments |
| --- | --- | --- |
| `add_expense` | Add an expense | `date` (`YYYY-MM-DD`), positive `amount`, `category`; optional `subcategory`, `note` |
| `list_expenses` | List recent expenses, newest first | Optional `start_date`, `end_date`, `category`; `limit` (1-500, default 100) |
| `get_expense` | Look up one expense | `expense_id` |
| `update_expense` | Change one or more expense fields | `expense_id` and any of `date`, `amount`, `category`, `subcategory`, `note` |
| `delete_expense` | Delete one expense | `expense_id` |
| `summarize` | Group totals and counts by category | Required inclusive `start_date`, `end_date`; optional `category` |
| `monthly_summary` | Group totals and counts by category for a month | `month` (`YYYY-MM`) |
| `set_budget` | Create or replace a category budget | `month` (`YYYY-MM`), `category`, positive `amount` |
| `list_budgets` | List budgets | Optional `month` (`YYYY-MM`) |
| `delete_budget` | Remove a category budget | `month` (`YYYY-MM`), `category` |
| `budget_status` | Compare budgets with recorded spending | `month` (`YYYY-MM`) |

Dates are interpreted as ISO calendar dates, and date-range endpoints are inclusive. Monetary values are stored as SQLite `REAL` numbers. Categories are user-defined strings; `categories.json` provides the recommended categories and subcategories.

## Validation and errors

Amounts and budgets must be finite numbers greater than zero. Dates and months must use `YYYY-MM-DD` and `YYYY-MM`; a range's start must not be after its end. Invalid input is reported as a tool error. Lookup and deletion tools report `not_found` when the requested record does not exist.

## Development

Run the focused tests with:

```powershell
python -m unittest discover -s tests -v
```

