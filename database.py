"""
数据库模块 — 用户、订单、使用记录（SQLite）
"""

import sqlite3
import uuid
import secrets
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "data" / "ai_video_studio.db"


def _ensure_dir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db():
    """获取数据库连接（自动提交/回滚）"""
    _ensure_dir()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """初始化数据库表"""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                uid         TEXT UNIQUE NOT NULL,
                nickname    TEXT DEFAULT '',
                credits     INTEGER DEFAULT 0,
                plan        TEXT DEFAULT 'none',
                plan_expire TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no    TEXT UNIQUE NOT NULL,
                uid         TEXT NOT NULL,
                type        TEXT NOT NULL,
                amount      REAL NOT NULL,
                credits     INTEGER NOT NULL,
                plan        TEXT,
                status      TEXT DEFAULT 'pending',
                pay_channel TEXT,
                paid_at     TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (uid) REFERENCES users(uid)
            );

            CREATE TABLE IF NOT EXISTS usage_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                uid          TEXT NOT NULL,
                action       TEXT NOT NULL,
                order_no     TEXT,
                credits_used INTEGER DEFAULT 1,
                input_files  TEXT,
                output_file  TEXT,
                duration_ms  INTEGER,
                created_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS redeem_codes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT UNIQUE NOT NULL,
                credits     INTEGER NOT NULL,
                plan        TEXT,
                used_by     TEXT,
                used_at     TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_users_uid ON users(uid);
            CREATE INDEX IF NOT EXISTS idx_orders_uid ON orders(uid);
            CREATE INDEX IF NOT EXISTS idx_orders_no  ON orders(order_no);
            CREATE INDEX IF NOT EXISTS idx_usage_uid  ON usage_logs(uid);
            CREATE INDEX IF NOT EXISTS idx_redeem_code ON redeem_codes(code);
        """)


# ===== 用户操作 =====

def get_user(uid: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        return dict(row) if row else None


def create_user() -> dict:
    """注册新用户，赠送 3 次免费体验"""
    uid = "u_" + secrets.token_hex(8)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (uid, credits) VALUES (?, 3)",
            (uid,),
        )
    return get_user(uid)


def add_credits(uid: str, amount: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET credits=credits+?, updated_at=datetime('now') WHERE uid=?",
            (amount, uid),
        )


def use_credit(uid: str) -> bool:
    """扣 1 次，成功返回 True，余额不足返回 False"""
    with get_db() as conn:
        row = conn.execute("SELECT credits FROM users WHERE uid=?", (uid,)).fetchone()
        if not row or row["credits"] <= 0:
            return False
        conn.execute(
            "UPDATE users SET credits=credits-1, updated_at=datetime('now') WHERE uid=?",
            (uid,),
        )
        return True


# ===== 订单操作 =====

def create_order(uid: str, order_type: str, amount: float, credits: int, plan: str = None) -> dict:
    order_no = "ORD" + datetime.now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(4)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO orders (order_no, uid, type, amount, credits, plan) VALUES (?,?,?,?,?,?)",
            (order_no, uid, order_type, amount, credits, plan),
        )
    return get_order(order_no)


def get_order(order_no: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
        return dict(row) if row else None


# ===== 使用记录 =====

def log_usage(uid: str, action: str, credits_used: int = 1,
              input_files: str = "", output_file: str = "", duration_ms: int = 0):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO usage_logs (uid, action, credits_used, input_files, output_file, duration_ms) "
            "VALUES (?,?,?,?,?,?)",
            (uid, action, credits_used, input_files, output_file, duration_ms),
        )


def get_usage_logs(uid: str, limit: int = 20) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM usage_logs WHERE uid=? ORDER BY created_at DESC LIMIT ?",
            (uid, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ===== 兑换码 =====

def generate_redeem_codes(credits: int, count: int, plan: str = None) -> list:
    codes = []
    with get_db() as conn:
        for _ in range(count):
            code = "AV" + secrets.token_hex(5).upper()
            conn.execute(
                "INSERT INTO redeem_codes (code, credits, plan) VALUES (?,?,?)",
                (code, credits, plan),
            )
            codes.append(code)
    return codes


def redeem_code(code: str, uid: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM redeem_codes WHERE code=? AND used_by IS NULL", (code.upper().strip(),)
        ).fetchone()
        if not row:
            return {"success": False, "error": "兑换码无效或已使用"}

        conn.execute(
            "UPDATE redeem_codes SET used_by=?, used_at=datetime('now') WHERE code=?",
            (uid, row["code"]),
        )
        conn.execute(
            "UPDATE users SET credits=credits+?, updated_at=datetime('now') WHERE uid=?",
            (row["credits"], uid),
        )
        return {"success": True, "credits": row["credits"], "plan": row["plan"]}


def list_redeem_codes(only_unused: bool = True) -> list:
    with get_db() as conn:
        if only_unused:
            rows = conn.execute(
                "SELECT * FROM redeem_codes WHERE used_by IS NULL ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM redeem_codes ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]
