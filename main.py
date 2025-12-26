from fastmcp import FastMCP
import os
import aiosqlite
import tempfile
import sqlite3
import json

# ============================================================
# Paths (PROJECT-LOCAL DATABASE — IMPORTANT FIX)
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(BASE_DIR, "categories.json")

print(f"📂 Database path: {DB_PATH}")

mcp = FastMCP("ExpenseTracker")

# ============================================================
# Database Initialization (SYNC — runs once)
# ============================================================

def init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    note TEXT DEFAULT ''
                )
            """)

            # Write test (verifies permissions)
            conn.execute(
                "INSERT OR IGNORE INTO expenses(date, amount, category) VALUES (?, ?, ?)",
                ("2000-01-01", 0, "test")
            )
            conn.execute("DELETE FROM expenses WHERE category = 'test'")
            conn.commit()

        print("✅ Database initialized successfully")

    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        raise


# Run initialization at import time
init_db()

# ============================================================
# MCP TOOLS
# ============================================================

@mcp.tool()
async def add_expense(date, amount, category, subcategory="", note=""):
    """
    Add a new expense entry to the database.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """
                INSERT INTO expenses (date, amount, category, subcategory, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (date, amount, category, subcategory, note)
            )
            await db.commit()

            return {
                "status": "success",
                "id": cur.lastrowid,
                "message": "Expense added successfully"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Database error: {str(e)}"
        }


@mcp.tool()
async def list_expenses(start_date, end_date):
    """
    List expenses between two dates (inclusive).
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
                """,
                (start_date, end_date)
            )

            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]

            return [dict(zip(cols, row)) for row in rows]

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error listing expenses: {str(e)}"
        }


@mcp.tool()
async def summarize(start_date, end_date, category=None):
    """
    Summarize expenses by category.
    """
    try:
        query = """
            SELECT category, SUM(amount) AS total_amount, COUNT(*) AS count
            FROM expenses
            WHERE date BETWEEN ? AND ?
        """
        params = [start_date, end_date]

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " GROUP BY category ORDER BY total_amount DESC"

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(query, params)
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]

            return [dict(zip(cols, row)) for row in rows]

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error summarizing expenses: {str(e)}"
        }

# ============================================================
# MCP RESOURCE
# ============================================================

@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    """
    Return expense categories.
    """
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
            "Other"
        ]
    }

    try:
        if os.path.exists(CATEGORIES_PATH):
            with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
                return f.read()
        return json.dumps(default_categories, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})

# ============================================================
# Server start
# ============================================================

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000
    )
