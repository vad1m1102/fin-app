import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

DB_NAME = "finance.db"


def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL,         -- 'expense' або 'income'
                category TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_created 
            ON transactions (user_id, created_at)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,         -- 'expense' або 'income'
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, type, name)
            )
        """)
        conn.commit()


def add_transaction(user_id: int, amount: float, tx_type: str, category: str, description: Optional[str] = None) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (user_id, amount, type, category, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, round(amount, 2), tx_type, category, description or "", now_str))
        conn.commit()
        return cursor.lastrowid


def get_user_categories(user_id: int, tx_type: str) -> List[str]:
    from keyboards import DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES
    defaults = DEFAULT_EXPENSE_CATEGORIES if tx_type == "expense" else DEFAULT_INCOME_CATEGORIES
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM custom_categories
            WHERE user_id = ? AND type = ?
            ORDER BY id ASC
        """, (user_id, tx_type))
        custom = [row[0] for row in cursor.fetchall()]
    return defaults + custom


def get_custom_categories(user_id: int, tx_type: Optional[str] = None) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if tx_type:
            cursor.execute("""
                SELECT id, name, type FROM custom_categories
                WHERE user_id = ? AND type = ?
                ORDER BY id ASC
            """, (user_id, tx_type))
        else:
            cursor.execute("""
                SELECT id, name, type FROM custom_categories
                WHERE user_id = ?
                ORDER BY type, id ASC
            """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]


def add_custom_category(user_id: int, tx_type: str, name: str) -> bool:
    clean_name = name.strip()
    if not clean_name:
        return False
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO custom_categories (user_id, type, name)
                VALUES (?, ?, ?)
            """, (user_id, tx_type, clean_name))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def delete_custom_category(user_id: int, cat_id: int) -> bool:
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM custom_categories WHERE id = ? AND user_id = ?", (cat_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_transaction(user_id: int, tx_id: int) -> bool:
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (tx_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_last_transaction(user_id: int) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM transactions 
            WHERE user_id = ? 
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        tx_data = dict(row)
        cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_data["id"],))
        conn.commit()
        return tx_data


def get_recent_transactions(user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, amount, type, category, description, created_at
            FROM transactions
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]


def get_all_transactions(user_id: int) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, created_at, type, category, amount, description
            FROM transactions
            WHERE user_id = ?
            ORDER BY created_at ASC
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_period_dates(period: str):
    now = datetime.now()
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        title = "Сьогодні"
    elif period == "week":
        # Початок поточного тижня (понеділок)
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        title = "Цього тижня"
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        title = "Цього місяця"
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        title = "Цього року"
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        title = "Цього місяця"

    start_str = start.strftime("%Y-%m-%d %H:%M:%S")
    return start_str, title


def get_stats(user_id: int, period: str) -> Dict[str, Any]:
    start_str, period_title = get_period_dates(period)

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # Загальні суми доходів та витрат
        cursor.execute("""
            SELECT type, COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ? AND created_at >= ?
            GROUP BY type
        """, (user_id, start_str))
        totals = dict(cursor.fetchall())
        income = totals.get("income", 0.0)
        expense = totals.get("expense", 0.0)
        balance = income - expense

        # Витрати за категоріями
        cursor.execute("""
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE user_id = ? AND type = 'expense' AND created_at >= ?
            GROUP BY category
            ORDER BY total DESC
        """, (user_id, start_str))
        expense_categories = cursor.fetchall()

        # Доходи за категоріями
        cursor.execute("""
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE user_id = ? AND type = 'income' AND created_at >= ?
            GROUP BY category
            ORDER BY total DESC
        """, (user_id, start_str))
        income_categories = cursor.fetchall()

        return {
            "period_title": period_title,
            "income": income,
            "expense": expense,
            "balance": balance,
            "expense_categories": expense_categories,
            "income_categories": income_categories
        }

