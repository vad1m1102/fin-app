import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "finance.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db():
    with get_connection() as conn:
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drafts (
                draft_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                type TEXT,
                created_at REAL NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state_data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.commit()


def add_transaction(user_id: int, amount: float, tx_type: str, category: str, description: Optional[str] = None) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
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
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM custom_categories
            WHERE user_id = ? AND type = ?
            ORDER BY id ASC
        """, (user_id, tx_type))
        custom = [row[0] for row in cursor.fetchall()]
    return defaults + custom


def get_custom_categories(user_id: int, tx_type: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
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
    with get_connection() as conn:
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
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM custom_categories WHERE id = ? AND user_id = ?", (cat_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_transaction(user_id: int, tx_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (tx_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_last_transaction(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
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
    with get_connection() as conn:
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
    with get_connection() as conn:
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

    with get_connection() as conn:
        cursor = conn.cursor()

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

        cursor.execute("""
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE user_id = ? AND type = 'expense' AND created_at >= ?
            GROUP BY category
            ORDER BY total DESC
        """, (user_id, start_str))
        expense_categories = cursor.fetchall()

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


def save_draft(draft_id: str, user_id: int, amount: float, description: str, tx_type: Optional[str] = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO drafts (draft_id, user_id, amount, description, type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (draft_id, user_id, amount, description, tx_type, time.time()))
        conn.commit()


def update_draft_type(draft_id: str, tx_type: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE drafts SET type = ? WHERE draft_id = ?", (tx_type, draft_id))
        conn.commit()


def get_draft(draft_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_draft(draft_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM drafts WHERE draft_id = ?", (draft_id,))
        conn.commit()


def cleanup_expired_drafts():
    limit = time.time() - 1800  # 30 хвилин
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM drafts WHERE created_at < ?", (limit,))
        cursor.execute("DELETE FROM user_states WHERE updated_at < ?", (limit,))
        conn.commit()


def set_user_state(user_id: int, state_data: Dict[str, Any]):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_states (user_id, state_data, updated_at)
            VALUES (?, ?, ?)
        """, (user_id, json.dumps(state_data, ensure_ascii=False), time.time()))
        conn.commit()


def get_user_state(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT state_data FROM user_states WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except Exception:
                return None
        return None


def clear_user_state(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
        conn.commit()