import os
import time
from dataclasses import dataclass, field
from datetime import timezone, timedelta
from typing import Dict, List, Set
from dotenv import load_dotenv

load_dotenv()


def _clean_env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip().replace('"', '').replace("'", "")


BOT_TOKEN = _clean_env("BOT_TOKEN")
SOLANA_WSS = _clean_env("SOLANA_WSS")
PROXY_URL = _clean_env("PROXY_URL") or None
CHANNEL_ID = _clean_env("CHANNEL_ID") or None

SELF_EMPLOYED_NAME = _clean_env("SELF_EMPLOYED_NAME", "Самозанятый (плательщик НПД)")
SELF_EMPLOYED_INN = _clean_env("SELF_EMPLOYED_INN", "указывается в чеке ФНС «Мой налог»")
NPD_ANNUAL_LIMIT_RUB = 2_400_000
NPD_WARNING_THRESHOLD_RUB = 2_200_000

PRODAMUS_URL = _clean_env("PRODAMUS_URL")
PRODAMUS_SECRET_KEY = _clean_env("PRODAMUS_SECRET_KEY")
WEB_SERVER_PORT = int(_clean_env("PORT", "80") or "80")

ENABLE_CRYPTO_PAY = _clean_env("ENABLE_CRYPTO_PAY", "0") == "1"
CRYPTO_PAY_TOKEN = _clean_env("CRYPTO_PAY_TOKEN") if ENABLE_CRYPTO_PAY else ""

DEFAULT_DB_PATH = "/data/screener_saas.db" if os.path.isdir("/data") else "screener_saas.db"
DB_PATH = _clean_env("DB_PATH", DEFAULT_DB_PATH)

BYBIT_REF_CODE = _clean_env("BYBIT_REF_CODE", "J8MV1P")
BYBIT_REF_URL = _clean_env(
    "BYBIT_REF_URL",
    "https://www.bybit.com/invite?ref=J8MV1P&medium=referral&utm_campaign=evergreen&share_to=link"
)
GMGN_REF_CODE = _clean_env("GMGN_REF_CODE", "6MGcIBsj")
GMGN_BASE_URL = "https://gmgn.ai"
FOMO_REF_CODE = _clean_env("FOMO_REF_CODE", "bayazitov")
FOMO_BASE_URL = "https://fomo.family"

admin_raw = _clean_env("ADMIN_ID", "0").replace(' ', '')
ADMIN_IDS: List[int] = [
    int(part) for part in admin_raw.split(',')
    if part.lstrip('-').isdigit() and int(part) != 0
]

TARIFFS = {
    "1_month": {"days": 30, "price_rub": 1490, "price_usdt": 15.0, "name": "1 Месяц"},
    "3_months": {"days": 90, "price_rub": 3990, "price_usdt": 40.0, "name": "3 Месяца (-11%)"}
}
REF_DISCOUNT_PERCENT = 15
TRIAL_DAYS = 3
REF_BONUS_DAYS = 3
EXPIRY_REMINDER_HOURS = 12

CHECK_INTERVAL_SEC = 8
TIMEFRAME = "5"
TOP_PAIRS_LIMIT = 50
ALERT_COOLDOWN_SEC = 1200
CONCURRENT_REQUESTS_LIMIT = 10

CHANNEL_MIN_VOL = 6.0
CHANNEL_MIN_PRICE_CHANGE = 1.8
CHANNEL_MAX_PRICE_CHANGE = 5.5
CHANNEL_MIN_OI_CHANGE = 1.2
CHANNEL_DAILY_LIMIT = 15
CHANNEL_POST_INTERVAL_SEC = 3600

MIN_POOL_LIQUIDITY_USD = 6000.0
SNIPER_GLOBAL_COOLDOWN_SEC = 600
CHANNEL_SOLANA_MIN_LIQUIDITY_USD = 25000.0
CHANNEL_SOLANA_INTERVAL_SEC = 7200
CHANNEL_SOLANA_DAILY_LIMIT = 6

TZ_LOCAL = timezone(timedelta(hours=5))

EXCLUDED_SYMBOLS = {
    "TSLAUSDT", "QQQUSDT", "SPYUSDT", "NVDAUSDT", "INTCUSDT", "MUUSDT",
    "MSTRUSDT", "SKHYUSDT", "SOXSUSDT", "XAUUSDT", "XAGUSDT", "AAPLUSDT",
    "AMZNUSDT", "MSFTUSDT", "GOOGLUSDT", "COINUSDT", "SNXXUSDT",
    "USDCUSDT", "USDEUSDT", "FDUSDUSDT", "TUSDUSDT", "DAIUSDT", "USD1USDT",
    "XAUTUSDT", "PAXGUSDT", "EURUSDT", "GBPUSDT"
}

RAYDIUM_V4_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
RAYDIUM_CPMM_PROGRAM_ID = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"

BASE_TOKENS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "USDH1SM1ojREvvVJ6oWujt2rVC87C2LfbwpzF6SSsh5",
    "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr",
}

CRYPTO_RSS_URL = "https://forklog.com/feed"
ALLOWED_USER_FIELDS = {"min_volume_mult", "min_price_change", "min_oi_change", "alerts_enabled", "blacklist"}


@dataclass
class RuntimeState:
    emergency_pause: bool = False
    solana_enabled: bool = True
    cached_channel_url: str = f"https://t.me/{CHANNEL_ID[1:]}" if CHANNEL_ID and CHANNEL_ID.startswith("@") else ""
    cached_bot_username: str = "Spike_probot"

    recent_alerts: Dict[str, float] = field(default_factory=dict)
    recent_channel_alerts: Dict[str, float] = field(default_factory=dict)
    processing_invoices: Set[int] = field(default_factory=set)

    channel_last_post_time: float = 0.0
    channel_posts_today: int = 0
    channel_day_timestamp: float = field(default_factory=time.time)

    last_sniper_alert_time: float = 0.0
    channel_solana_last_post_time: float = 0.0
    channel_solana_posts_today: int = 0
    channel_solana_day_timestamp: float = field(default_factory=time.time)

    processed_mints_cache: Dict[str, float] = field(default_factory=dict)
    pending_mints_lock: Set[str] = field(default_factory=set)
    processed_signatures_cache: Dict[str, float] = field(default_factory=dict)


app_state = RuntimeState()
state = app_state