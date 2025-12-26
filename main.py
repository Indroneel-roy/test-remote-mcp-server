from fastmcp import FastMCP
import os
import aiosqlite
import json
import tempfile

# ============================================================
# ENVIRONMENT-SAFE PATHS
# ============================================================

IS_CLOUD = os.getenv("FASTMCP_CLOUD", "") or os.getenv("MCP_CLOUD", "")

if IS_CLOUD:
    DB_DIR = tempfile.gettempdir()
else:
    DB_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(DB_DIR, "expenses.db")

mcp = FastMCP("ExpenseTracker")

# ============================================================
# DEFAULT CATEGORIES (in-memory, no file dependency)
# ============================================================

DEFAULT_CATEGORIES = {
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

# ============================================================
# DATABASE INIT (ASYNC - lazy initialization)
# ============================================================

_db_initialized = False

async def ensure_db():
    """Lazy async database initialization."""
    global _db_initialized
    if _db_initialized:
        return
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Don't use WAL in cloud/tmp - it can cause issues
            if not IS_CLOUD:
                await db.execute("PRAGMA journal_mode=WAL;")
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    note TEXT DEFAULT ''
                )
            """)
            await db.commit()
        
        _db_initialized = True
        
    except Exception as e:
        raise RuntimeError(f"Database initialization failed: {e}")

# ============================================================
# MCP TOOLS
# ============================================================

@mcp.tool()
async def add_expense(date: str, amount: float, category: str, subcategory: str = "", note: str = ""):
    """Add a new expense.
    
    Args:
        date: Date in YYYY-MM-DD format
        amount: Expense amount
        category: Expense category
        subcategory: Optional subcategory
        note: Optional note
    """
    try:
        await ensure_db()
        
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
                "message": f"Expense added: ${amount} for {category}"
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
async def list_expenses(start_date: str, end_date: str):
    """List expenses in date range.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    try:
        await ensure_db()
        
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
            expenses = [dict(zip(cols, r)) for r in rows]
            
            return {
                "status": "success",
                "count": len(expenses),
                "expenses": expenses
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
async def summarize_expenses(start_date: str, end_date: str, category: str = None):
    """Summarize expenses by category.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        category: Optional category filter
    """
    try:
        await ensure_db()
        
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
            summary = [dict(zip(cols, r)) for r in rows]
            
            total = sum(row['total'] for row in summary)
            
            return {
                "status": "success",
                "summary": summary,
                "total": total,
                "period": f"{start_date} to {end_date}"
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
async def delete_expense(expense_id: int):
    """Delete an expense by ID.
    
    Args:
        expense_id: The ID of the expense to delete
    """
    try:
        await ensure_db()
        
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            await db.commit()
            
            if cur.rowcount == 0:
                return {"status": "error", "message": f"Expense {expense_id} not found"}
            
            return {
                "status": "success",
                "message": f"Expense {expense_id} deleted"
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

# ============================================================
# MCP RESOURCE
# ============================================================

@mcp.resource("expense:///categories")
def get_categories() -> str:
    """Get available expense categories."""
    # In cloud, we can't read from filesystem, so return default
    # In local, try to read from file, fallback to default
    
    if not IS_CLOUD:
        categories_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "categories.json"
        )
        try:
            if os.path.exists(categories_file):
                with open(categories_file, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass
    
    return json.dumps(DEFAULT_CATEGORIES, indent=2)

# ============================================================
# SERVER
# ============================================================

if __name__ == "__main__":
    import sys
    
    # Determine transport based on how it's run
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        # fastmcp dev mode - uses stdio
        mcp.run()
    else:
        # HTTP mode for cloud or direct execution
        mcp.run(transport="http", host="0.0.0.0", port=8000)