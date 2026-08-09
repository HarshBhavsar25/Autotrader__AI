import sqlite3
import json
import os
from datetime import datetime, date
from typing import Dict, List, Optional, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "autotrader.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Table for recording individual executed trades
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        entry_price REAL NOT NULL,
        exit_price REAL,
        position_size_inr REAL NOT NULL,
        position_size_usdt REAL NOT NULL,
        leverage INTEGER NOT NULL,
        raw_pnl_inr REAL,
        net_pnl_inr REAL,
        fees_inr REAL,
        confidence_score REAL NOT NULL,
        entry_time TEXT NOT NULL,
        exit_time TEXT,
        status TEXT NOT NULL, -- OPEN, CLOSED_TP, CLOSED_SL, CLOSED_TRAILING, CLOSED_EARLY
        exit_reason TEXT,
        max_profit_reached_inr REAL DEFAULT 0.0,
        breakeven_triggered INTEGER DEFAULT 0,
        metrics_json TEXT
    );
    """)

    # Table for daily performance summary reports
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_date TEXT UNIQUE NOT NULL,
        starting_balance_inr REAL NOT NULL,
        ending_balance_inr REAL NOT NULL,
        gross_pnl_inr REAL NOT NULL,
        net_pnl_inr REAL NOT NULL,
        total_fees_inr REAL NOT NULL,
        total_trades INTEGER NOT NULL,
        winning_trades INTEGER NOT NULL,
        losing_trades INTEGER NOT NULL,
        transferred_to_spot_inr REAL DEFAULT 0.0,
        target_achieved INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # Table for tracking wallet profit transfers (Futures to Spot)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wallet_transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        transfer_date TEXT NOT NULL,
        amount_inr REAL NOT NULL,
        amount_usdt REAL NOT NULL,
        source_wallet TEXT NOT NULL,
        target_wallet TEXT NOT NULL,
        status TEXT NOT NULL, -- SUCCESS, FAILED, SIMULATED
        transaction_id TEXT,
        details TEXT
    );
    """)

    # Table for audit logs & event streams
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        level TEXT NOT NULL,
        category TEXT NOT NULL,
        message TEXT NOT NULL,
        data_json TEXT
    );
    """)

    conn.commit()
    conn.close()

class DatabaseManager:
    def __init__(self):
        init_db()

    def record_trade_entry(self, symbol: str, side: str, entry_price: float, size_inr: float,
                           size_usdt: float, leverage: int, confidence_score: float,
                           metrics_json: Dict[str, Any]) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO trades (symbol, side, entry_price, position_size_inr, position_size_usdt,
                                leverage, confidence_score, entry_time, status, metrics_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (symbol, side, entry_price, size_inr, size_usdt, leverage, confidence_score, now_str, json.dumps(metrics_json)))
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return trade_id

    def update_trade_exit(self, trade_id: int, exit_price: float, raw_pnl_inr: float,
                          net_pnl_inr: float, fees_inr: float, status: str, exit_reason: str,
                          max_profit_reached: float = 0.0, breakeven_triggered: bool = False):
        conn = get_db_connection()
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()
        cursor.execute("""
            UPDATE trades
            SET exit_price = ?, raw_pnl_inr = ?, net_pnl_inr = ?, fees_inr = ?,
                status = ?, exit_reason = ?, exit_time = ?,
                max_profit_reached_inr = ?, breakeven_triggered = ?
            WHERE id = ?
        """, (exit_price, raw_pnl_inr, net_pnl_inr, fees_inr, status, exit_reason,
              now_str, max_profit_reached, 1 if breakeven_triggered else 0, trade_id))
        conn.commit()
        conn.close()

    def get_recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def record_transfer(self, amount_inr: float, amount_usdt: float, status: str,
                        tx_id: str = "", details: str = "") -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute("""
            INSERT INTO wallet_transfers (timestamp, transfer_date, amount_inr, amount_usdt,
                                          source_wallet, target_wallet, status, transaction_id, details)
            VALUES (?, ?, ?, ?, 'FUTURES', 'SPOT', ?, ?, ?)
        """, (now.isoformat(), now.strftime("%Y-%m-%d"), amount_inr, amount_usdt, status, tx_id, details))
        transfer_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return transfer_id

    def get_transfers(self, limit: int = 30) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wallet_transfers ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def record_daily_report(self, report_date: str, starting_bal: float, ending_bal: float,
                            gross_pnl: float, net_pnl: float, total_fees: float,
                            total_trades: int, winning_trades: int, losing_trades: int,
                            transferred: float, target_achieved: bool):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO daily_reports (report_date, starting_balance_inr, ending_balance_inr,
                                                 gross_pnl_inr, net_pnl_inr, total_fees_inr,
                                                 total_trades, winning_trades, losing_trades,
                                                 transferred_to_spot_inr, target_achieved, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (report_date, starting_bal, ending_bal, gross_pnl, net_pnl, total_fees,
              total_trades, winning_trades, losing_trades, transferred,
              1 if target_achieved else 0, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_daily_reports(self, limit: int = 30) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_reports ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def log_event(self, level: str, category: str, message: str, data: Optional[Dict[str, Any]] = None):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO system_logs (timestamp, level, category, message, data_json)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), level, category, message, json.dumps(data or {})))
        conn.commit()
        conn.close()

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

db_manager = DatabaseManager()
