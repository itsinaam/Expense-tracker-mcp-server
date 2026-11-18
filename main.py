import json
import math
import os
import sqlite3
import tempfile
import calendar
from datetime import date, datetime
from typing import Optional

import aiosqlite
from fastmcp import FastMCP


DB_PATH = os.path.expanduser(
    os.environ.get(
        "EXPENSE_DB_PATH",
        os.path.join(tempfile.gettempdir(), "expenses.db"),
    )
)
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP("ExpenseTracker")


def init_db() -> None:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                UNIQUE(month, category)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_expenses_date_category "
            "ON expenses(date, category)"
        )
        connection.commit()
    finally:
        connection.close()


def _validate_date(value: str, field_name: str) -> str:
    try:
        parsed_date = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a valid date in YYYY-MM-DD format.") from error
    if parsed_date.isoformat() != value:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format.")
    return value


def _validate_month(value: str) -> str:
    try:
        parsed_month = datetime.strptime(value, "%Y-%m")
    except (TypeError, ValueError) as error:
        raise ValueError("month must be a valid month in YYYY-MM format.") from error
    if parsed_month.strftime("%Y-%m") != value:
        raise ValueError("month must be in YYYY-MM format.")
    return value


def _month_last_date(month: str) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    last_day = calendar.monthrange(year, month_number)[1]
    return f"{month}-{last_day:02d}"


def _validate_amount(amount: float, field_name: str = "amount") -> float:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError(f"{field_name} must be a number greater than zero.")
    try:
        numeric_amount = float(amount)
    except OverflowError as error:
        raise ValueError(f"{field_name} must be a finite number greater than zero.") from error
    if not math.isfinite(numeric_amount) or numeric_amount <= 0:
        raise ValueError(f"{field_name} must be a finite number greater than zero.")
    return numeric_amount


def _validate_category(category: str) -> str:
    if not isinstance(category, str) or not category.strip():
        raise ValueError("category must be a non-empty string.")
    return category.strip()


async def _fetch_dicts(cursor: aiosqlite.Cursor) -> list[dict]:
    try:
        columns = [column[0] for column in cursor.description or ()]
        return [dict(zip(columns, row)) for row in await cursor.fetchall()]
    finally:
        await cursor.close()


init_db()


@mcp.tool()
async def add_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = "",
) -> dict:
    """Add an expense using a date, positive amount, and category."""
    date = _validate_date(date, "date")
    amount = _validate_amount(amount)
    category = _validate_category(category)
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            """
            INSERT INTO expenses(date, amount, category, subcategory, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (date, amount, category, subcategory, note),
        )
        expense_id = cursor.lastrowid
        await cursor.close()
        await connection.commit()
        return {
            "status": "success",
            "id": expense_id,
            "message": "Expense added successfully.",
        }


@mcp.tool()
async def list_expenses(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """List expenses with optional inclusive date and category filters."""
    if start_date is not None:
        start_date = _validate_date(start_date, "start_date")
    if end_date is not None:
        end_date = _validate_date(end_date, "end_date")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must be earlier than or equal to end_date.")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("limit must be an integer between 1 and 500.")

    conditions = []
    parameters = []
    if start_date:
        conditions.append("date >= ?")
        parameters.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        parameters.append(end_date)
    if category is not None:
        conditions.append("category = ?")
        parameters.append(_validate_category(category))
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            f"""
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            {where_clause}
            ORDER BY date DESC, id DESC
            LIMIT ?
            """,
            (*parameters, limit),
        )
        return await _fetch_dicts(cursor)


@mcp.tool()
async def get_expense(expense_id: int) -> Optional[dict]:
    """Get one expense by its ID; returns null when it does not exist."""
    if not isinstance(expense_id, int) or isinstance(expense_id, bool) or expense_id <= 0:
        raise ValueError("expense_id must be a positive integer.")
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses WHERE id = ?
            """,
            (expense_id,),
        )
        rows = await _fetch_dicts(cursor)
        return rows[0] if rows else None


@mcp.tool()
async def update_expense(
    expense_id: int,
    date: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    note: Optional[str] = None,
) -> dict:
    """Update supplied fields on an expense; omitted fields stay unchanged."""
    if not isinstance(expense_id, int) or isinstance(expense_id, bool) or expense_id <= 0:
        raise ValueError("expense_id must be a positive integer.")

    updates = {}
    if date is not None:
        updates["date"] = _validate_date(date, "date")
    if amount is not None:
        updates["amount"] = _validate_amount(amount)
    if category is not None:
        updates["category"] = _validate_category(category)
    if subcategory is not None:
        updates["subcategory"] = subcategory
    if note is not None:
        updates["note"] = note
    if not updates:
        raise ValueError("Provide at least one expense field to update.")

    assignments = ", ".join(f"{field} = ?" for field in updates)
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            f"UPDATE expenses SET {assignments} WHERE id = ?",
            (*updates.values(), expense_id),
        )
        rowcount = cursor.rowcount
        await cursor.close()
        if rowcount == 0:
            await connection.commit()
            return {"status": "not_found", "id": expense_id}
        cursor = await connection.execute(
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses WHERE id = ?
            """,
            (expense_id,),
        )
        rows = await _fetch_dicts(cursor)
        await connection.commit()
    expense = rows[0] if rows else None
    return {"status": "success", "expense": expense}


@mcp.tool()
async def delete_expense(expense_id: int) -> dict:
    """Delete an expense by its ID and report whether it existed."""
    if not isinstance(expense_id, int) or isinstance(expense_id, bool) or expense_id <= 0:
        raise ValueError("expense_id must be a positive integer.")
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        rowcount = cursor.rowcount
        await cursor.close()
        await connection.commit()
    if rowcount == 0:
        return {"status": "not_found", "id": expense_id}
    return {"status": "success", "id": expense_id, "deleted": True}


@mcp.tool()
async def summarize(start_date: str, end_date: str, category: Optional[str] = None) -> list[dict]:
    """Summarize expense totals and counts by category for an inclusive date range."""
    start_date = _validate_date(start_date, "start_date")
    end_date = _validate_date(end_date, "end_date")
    if start_date > end_date:
        raise ValueError("start_date must be earlier than or equal to end_date.")

    query = """
        SELECT category, SUM(amount) AS total_amount, COUNT(*) AS count
        FROM expenses
        WHERE date BETWEEN ? AND ?
    """
    parameters = [start_date, end_date]
    if category is not None:
        query += " AND category = ?"
        parameters.append(_validate_category(category))
    query += " GROUP BY category ORDER BY total_amount DESC"

    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(query, parameters)
        return await _fetch_dicts(cursor)


@mcp.tool()
async def monthly_summary(month: str) -> list[dict]:
    """Summarize expense totals and counts by category for a YYYY-MM month."""
    month = _validate_month(month)
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            """
            SELECT category, SUM(amount) AS total_amount, COUNT(*) AS count
            FROM expenses
            WHERE date >= ? AND date <= ?
            GROUP BY category
            ORDER BY total_amount DESC
            """,
            (f"{month}-01", _month_last_date(month)),
        )
        return await _fetch_dicts(cursor)


@mcp.tool()
async def set_budget(month: str, category: str, amount: float) -> dict:
    """Create or replace a monthly spending budget for one category."""
    month = _validate_month(month)
    category = _validate_category(category)
    amount = _validate_amount(amount, "amount")
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            """
            INSERT INTO budgets(month, category, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(month, category) DO UPDATE SET amount = excluded.amount
            """,
            (month, category, amount),
        )
        await cursor.close()
        await connection.commit()
    return {"status": "success", "month": month, "category": category, "amount": amount}


@mcp.tool()
async def list_budgets(month: Optional[str] = None) -> list[dict]:
    """List all budgets, optionally filtered to one YYYY-MM month."""
    query = "SELECT month, category, amount FROM budgets"
    parameters = ()
    if month is not None:
        month = _validate_month(month)
        query += " WHERE month = ?"
        parameters = (month,)
    query += " ORDER BY month DESC, category"
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(query, parameters)
        return await _fetch_dicts(cursor)


@mcp.tool()
async def delete_budget(month: str, category: str) -> dict:
    """Delete the budget for a category and month."""
    month = _validate_month(month)
    category = _validate_category(category)
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            "DELETE FROM budgets WHERE month = ? AND category = ?",
            (month, category),
        )
        rowcount = cursor.rowcount
        await cursor.close()
        await connection.commit()
    if rowcount == 0:
        return {"status": "not_found", "month": month, "category": category}
    return {"status": "success", "month": month, "category": category, "deleted": True}


@mcp.tool()
async def budget_status(month: str) -> list[dict]:
    """Compare each monthly category budget with actual spending."""
    month = _validate_month(month)
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            """
            SELECT budgets.category,
                   budgets.amount AS budget_amount,
                   COALESCE(SUM(expenses.amount), 0) AS spent_amount
            FROM budgets
            LEFT JOIN expenses
                ON expenses.category = budgets.category
                AND expenses.date >= ?
                AND expenses.date <= ?
            WHERE budgets.month = ?
            GROUP BY budgets.category, budgets.amount
            ORDER BY budgets.category
            """,
            (f"{month}-01", _month_last_date(month), month),
        )
        results = await _fetch_dicts(cursor)

    for result in results:
        result["remaining_amount"] = result["budget_amount"] - result["spent_amount"]
        result["percent_used"] = round(
            result["spent_amount"] / result["budget_amount"] * 100,
            2,
        )
    return results


@mcp.resource("expense:///categories", mime_type="application/json")
def categories() -> str:
    """Return configured expense categories as JSON."""
    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as category_file:
            return category_file.read()
    except FileNotFoundError:
        default_categories = {
            "categories": [
                "Food & Dining",
                "Transportation",
                "Shopping",
                "Entertainment",
                "Bills & Utilities",
                "Healthcare",
                "Travel",
                "Education",
                "Business",
                "Other",
            ]
        }
        return json.dumps(default_categories, indent=2)


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
