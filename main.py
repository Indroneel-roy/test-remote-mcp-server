from fastmcp import FastMCP
import os
import aiosqlite
import sqlite3
import json
import tempfile

# ============================================================
# ENVIRONMENT-SAFE PATHS
# ============================================================

IS_CLOUD = os.getenv("FASTMCP_CLOUD", "") or os.getenv("MCP_CLOUD", "")

if IS_CLOUD:
    # FastMCP Cloud → only /tmp is writable
    DB_DIR = tempfile.gettempdir()
else:
    # Local dev → project directory
    DB_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(DB_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "categories.json")

print(f"📂 Database path: {DB_PATH}")
print(f"☁️ Running in cloud: {bool(IS_CLOUD)}")

mcp = FastMCP("ExpenseTracker")

# ============================================================
# DATABASE INIT (SYNC)
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
            conn.commit()

        print("✅ Database initialized")

    except Exception as e:
        print(f"❌ DB init failed: {e}")
        raise

init_db()

# ============================================================
# MCP TOOLS
# ============================================================

@mcp.tool()
async def add_expense(date, amount, category, subcategory="", note=""):
    """Add a new expense."""
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
                "id": cur.lastrowid
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
async def list_expenses(start_date, end_date):
    """List expenses in date range."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC
                """,
                (start_date, end_date)
            )
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
async def summarize(start_date, end_date, category=None):
    """Summarize expenses."""
    try:
        query = """
            SELECT category, SUM(amount) AS total, COUNT(*) AS count
            FROM expenses
            WHERE date BETWEEN ? AND ?
        """
        params = [start_date, end_date]

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " GROUP BY category ORDER BY total DESC"

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(query, params)
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    except Exception as e:
        return {"status": "error", "message": str(e)}

# ============================================================
# MCP RESOURCE
# ============================================================

@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    default = {
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
        return json.dumps(default, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})

# ============================================================
# SERVER
# ============================================================

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
