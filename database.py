import csv
import logging
import os
import tempfile
import time
from datetime import datetime
from typing import List

import aiosqlite
from aiogram import Bot

from config import (
    DB_PATH, ALLOWED_USER_FIELDS, ALERT_COOLDOWN_SEC,
    TRIAL_DAYS, REF_BONUS_DAYS, REF_DISCOUNT_PERCENT
)

logger = logging.getLogger("SpikePRO.DB")


def format_time_left(sub_end: float) -> str:
    rem = int(sub_end - time.time())
    if rem <= 0:
        return "❌ Истёк"
    days = rem // 86400
    hours = (rem % 86400) // 3600
    minutes = (rem % 3600) // 60
    if days > 0:
        return f"{days} дн. {hours} ч."
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    return f"{max(1, minutes)} мин."


def format_time_left_short(sub_end: float) -> str:
    rem = int(sub_end - time.time())
    if rem <= 0:
        return "Истёк"
    days = rem // 86400
    hours = (rem % 86400) // 3600
    minutes = (rem % 3600) // 60
    if days > 0:
        return f"{days}д {hours}ч"
    if hours > 0:
        return f"{hours}ч {minutes}м"
    return f"{max(1, minutes)}м"


async def init_db():
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                sub_end_timestamp REAL DEFAULT 0,
                min_volume_mult REAL DEFAULT 3.0,
                min_price_change REAL DEFAULT 1.5,
                min_oi_change REAL DEFAULT 1.2,
                referrer_id INTEGER DEFAULT NULL,
                alerts_enabled INTEGER DEFAULT 1,
                blacklist TEXT DEFAULT '',
                expiry_notified INTEGER DEFAULT 0,
                offer_accepted_at REAL DEFAULT 0
            )
        """)
        for col in [
            "min_oi_change REAL DEFAULT 1.2",
            "referrer_id INTEGER DEFAULT NULL",
            "alerts_enabled INTEGER DEFAULT 1",
            "blacklist TEXT DEFAULT ''",
            "expiry_notified INTEGER DEFAULT 0",
            "offer_accepted_at REAL DEFAULT 0"
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tokens_cache (
                contract_address TEXT PRIMARY KEY,
                detected_at TEXT,
                liquidity_usd REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS paid_invoices (
                invoice_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                paid_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS paid_fiat (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount_rub REAL,
                provider TEXT,
                paid_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS news_cache (
                news_id TEXT PRIMARY KEY,
                sent_at REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS signals_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                side TEXT,
                entry_price REAL,
                vol_ratio REAL,
                oi_change REAL,
                market_phase TEXT,
                created_at REAL,
                checked_15m INTEGER DEFAULT 0,
                max_profit_15m REAL DEFAULT 0.0,
                max_loss_15m REAL DEFAULT 0.0,
                checked_1h INTEGER DEFAULT 0,
                max_profit_1h REAL DEFAULT 0.0,
                result TEXT DEFAULT 'PENDING'
            )
        """)
        await db.commit()


async def get_bot_setting(key: str, default: str = "1") -> str:
    try:
        async with aiosqlite.connect(DB_PATH, timeout=30) as db:
            async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else default
    except Exception:
        return default


async def set_bot_setting(key: str, value: str):
    try:
        async with aiosqlite.connect(DB_PATH, timeout=30) as db:
            await db.execute(
                "INSERT INTO bot_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value)
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения настройки {key}: {e}")


async def log_signal_to_db(sig: dict, side: str, market_phase: str):
    try:
        now = time.time()
        async with aiosqlite.connect(DB_PATH, timeout=30) as db:
            async with db.execute(
                "SELECT 1 FROM signals_history WHERE symbol = ? AND created_at > ?",
                (sig['symbol'], now - ALERT_COOLDOWN_SEC)
            ) as cur:
                if await cur.fetchone():
                    return

            await db.execute("""
                INSERT INTO signals_history (
                    symbol, side, entry_price, vol_ratio, oi_change, market_phase, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                sig['symbol'], side, sig['price'], sig['vol_ratio'],
                sig['oi_change'], market_phase, now
            ))
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка логирования сигнала: {e}")


async def get_or_create_user(user_id: int, bot_instance: Bot = None, referrer_id: int = None) -> dict:
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                u = dict(row)
                if referrer_id and referrer_id != user_id and u.get('referrer_id') is None:
                    await db.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
                    await db.commit()
                    u['referrer_id'] = referrer_id
                return u

            bonus_time = (REF_BONUS_DAYS * 24 * 3600) if referrer_id and referrer_id != user_id else 0
            trial_end = time.time() + (TRIAL_DAYS * 24 * 3600) + bonus_time

            cursor = await db.execute(
                "INSERT OR IGNORE INTO users (user_id, sub_end_timestamp, min_volume_mult, min_price_change, min_oi_change, referrer_id, alerts_enabled, expiry_notified, offer_accepted_at) VALUES (?, ?, 3.0, 1.5, 1.2, ?, 1, 0, 0)",
                (user_id, trial_end, referrer_id)
            )
            await db.commit()

            if cursor.rowcount > 0:
                if referrer_id and referrer_id != user_id:
                    await add_subscription_time(referrer_id, REF_BONUS_DAYS)
                    if bot_instance:
                        try:
                            await bot_instance.send_message(
                                referrer_id,
                                f"🎉 <b>По вашей ссылке зарегистрировался пользователь!</b>\nВам начислено +{REF_BONUS_DAYS} дня PRO-доступа."
                            )
                        except Exception:
                            pass
                if bot_instance:
                    try:
                        total_days = TRIAL_DAYS + (REF_BONUS_DAYS if (referrer_id and referrer_id != user_id) else 0)
                        ref_text = f"\n🎁 <i>+{REF_BONUS_DAYS} дня бонуса + скидка {REF_DISCOUNT_PERCENT}% на продление подписки!</i>" if (referrer_id and referrer_id != user_id) else ""
                        await bot_instance.send_message(
                            user_id,
                            f"⚡️ <b>Вам открыт тестовый PRO-доступ на {total_days} дн.!</b>{ref_text}\nОцените работу фильтров и аналитики."
                        )
                    except Exception:
                        pass

            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor_new:
                return dict(await cursor_new.fetchone())


async def record_offer_acceptance(user_id: int):
    try:
        async with aiosqlite.connect(DB_PATH, timeout=30) as db:
            await db.execute(
                "UPDATE users SET offer_accepted_at = ? WHERE user_id = ? AND (offer_accepted_at IS NULL OR offer_accepted_at = 0)",
                (time.time(), user_id)
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка записи акцепта оферты для {user_id}: {e}")


async def update_user_setting(user_id: int, field: str, value: any):
    if field not in ALLOWED_USER_FIELDS:
        raise ValueError(f"Недопустимое поле БД: {field}")
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()


async def add_subscription_time(user_id: int, days: int):
    seconds_to_add = days * 24 * 3600
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, sub_end_timestamp, min_volume_mult, min_price_change, min_oi_change, alerts_enabled, expiry_notified, offer_accepted_at) VALUES (?, 0, 3.0, 1.5, 1.2, 1, 0, 0)",
            (user_id,)
        )
        async with db.execute("SELECT sub_end_timestamp FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            current_sub = row[0] if row else time.time()
        new_sub_end = max(time.time(), current_sub) + seconds_to_add
        await db.execute(
            "UPDATE users SET sub_end_timestamp = ?, expiry_notified = 0 WHERE user_id = ?",
            (new_sub_end, user_id)
        )
        await db.commit()


async def claim_fiat_and_add_sub(order_id: str, user_id: int, days: int, amount_rub: float, provider: str = "prodamus") -> bool:
    seconds_to_add = days * 24 * 3600
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        try:
            await db.execute("BEGIN IMMEDIATE;")
            cursor = await db.execute(
                "INSERT OR IGNORE INTO paid_fiat (order_id, user_id, amount_rub, provider, paid_at) VALUES (?, ?, ?, ?, ?)",
                (order_id, user_id, float(amount_rub), provider, datetime.now().isoformat())
            )
            if cursor.rowcount == 0:
                await db.rollback()
                return False

            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, sub_end_timestamp, min_volume_mult, min_price_change, min_oi_change, alerts_enabled, expiry_notified, offer_accepted_at) VALUES (?, 0, 3.0, 1.5, 1.2, 1, 0, ?)",
                (user_id, time.time())
            )
            async with db.execute("SELECT sub_end_timestamp FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                current_sub = row[0] if row else time.time()

            new_sub_end = max(time.time(), current_sub) + seconds_to_add
            await db.execute(
                "UPDATE users SET sub_end_timestamp = ?, expiry_notified = 0 WHERE user_id = ?",
                (new_sub_end, user_id)
            )
            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка подтверждения рублёвого платежа {order_id}: {e}")
            return False


async def claim_invoice_and_add_sub(invoice_id: int, user_id: int, days: int) -> bool:
    seconds_to_add = days * 24 * 3600
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        try:
            await db.execute("BEGIN IMMEDIATE;")
            cursor = await db.execute(
                "INSERT OR IGNORE INTO paid_invoices (invoice_id, user_id, paid_at) VALUES (?, ?, ?)",
                (invoice_id, user_id, datetime.now().isoformat())
            )
            if cursor.rowcount == 0:
                await db.rollback()
                return False

            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, sub_end_timestamp, min_volume_mult, min_price_change, min_oi_change, alerts_enabled, expiry_notified, offer_accepted_at) VALUES (?, 0, 3.0, 1.5, 1.2, 1, 0, 0)",
                (user_id,)
            )
            async with db.execute("SELECT sub_end_timestamp FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                current_sub = row[0] if row else time.time()

            new_sub_end = max(time.time(), current_sub) + seconds_to_add
            await db.execute(
                "UPDATE users SET sub_end_timestamp = ?, expiry_notified = 0 WHERE user_id = ?",
                (new_sub_end, user_id)
            )
            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка подтверждения инвойса CryptoBot: {e}")
            return False


async def get_active_subscribers() -> List[dict]:
    current_time = time.time()
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, min_volume_mult, min_price_change, min_oi_change, blacklist FROM users WHERE sub_end_timestamp > ? AND alerts_enabled = 1",
            (current_time,)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_referrals_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def is_token_processed(contract_address: str) -> bool:
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        async with db.execute("SELECT 1 FROM tokens_cache WHERE contract_address = ?", (contract_address,)) as cursor:
            return await cursor.fetchone() is not None


async def save_token(contract_address: str, liquidity: float):
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute(
            "INSERT OR IGNORE INTO tokens_cache (contract_address, detected_at, liquidity_usd) VALUES (?, ?, ?)",
            (contract_address, datetime.now().isoformat(), liquidity)
        )
        await db.commit()


async def cleanup_old_tokens():
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        threshold_time = datetime.fromtimestamp(time.time() - 48 * 3600).isoformat()
        await db.execute("DELETE FROM tokens_cache WHERE detected_at < ?", (threshold_time,))
        await db.commit()


async def get_all_users() -> List[int]:
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            return [r[0] for r in await cursor.fetchall()]


async def export_csv_files() -> tuple[str, str, int, int]:
    tmp_dir = tempfile.gettempdir()
    date_tag = datetime.now().strftime("%Y-%m-%d_%H-%M")
    users_csv = os.path.join(tmp_dir, f"users_{date_tag}.csv")
    signals_csv = os.path.join(tmp_dir, f"signals_{date_tag}.csv")

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY sub_end_timestamp DESC") as cur:
            users_rows = [dict(r) for r in await cur.fetchall()]
        async with db.execute("SELECT * FROM signals_history ORDER BY id DESC") as cur:
            signals_rows = [dict(r) for r in await cur.fetchall()]

    now_ts = time.time()
    with open(users_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "User_ID", "Status", "Time_Left", "Sub_End_Date",
            "Min_Vol", "Min_Price_Pct", "Min_OI_Pct",
            "Alerts_Enabled", "Referrer_ID", "Offer_Accepted_At", "Blacklist"
        ])
        for u in users_rows:
            sub_end = u.get("sub_end_timestamp") or 0
            is_act = sub_end > now_ts
            end_dt = datetime.fromtimestamp(sub_end).strftime("%Y-%m-%d %H:%M") if sub_end > 0 else "-"
            acc_ts = u.get("offer_accepted_at") or 0
            acc_dt = datetime.fromtimestamp(acc_ts).strftime("%Y-%m-%d %H:%M:%S") if acc_ts > 0 else "-"
            writer.writerow([
                u["user_id"],
                "ACTIVE" if is_act else "EXPIRED",
                format_time_left_short(sub_end),
                end_dt,
                u.get("min_volume_mult"),
                u.get("min_price_change"),
                u.get("min_oi_change"),
                u.get("alerts_enabled"),
                u.get("referrer_id") or "",
                acc_dt,
                u.get("blacklist") or ""
            ])

    with open(signals_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "ID", "Created_At", "Symbol", "Side", "Entry_Price",
            "Vol_Ratio", "OI_Change_Pct", "Market_Phase",
            "Max_Profit_15m", "Max_Loss_15m", "Max_Profit_1h", "Result"
        ])
        for s in signals_rows:
            dt_str = datetime.fromtimestamp(s["created_at"]).strftime("%Y-%m-%d %H:%M:%S") if s.get("created_at") else "-"
            writer.writerow([
                s["id"], dt_str, s["symbol"], s["side"], s["entry_price"],
                round(s.get("vol_ratio") or 0, 2),
                round(s.get("oi_change") or 0, 2),
                s.get("market_phase") or "",
                s.get("max_profit_15m"),
                s.get("max_loss_15m"),
                s.get("max_profit_1h"),
                s.get("result")
            ])

    return users_csv, signals_csv, len(users_rows), len(signals_rows)