import re
from typing import Optional
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import state as app_state, GMGN_BASE_URL, GMGN_REF_CODE


def get_sub_gate_keyboard(channel_url: str, ref_arg: Optional[str] = None) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📢 Подписаться на канал", url=channel_url))
    safe_ref = ref_arg if (ref_arg and re.fullmatch(r"r\d{1,20}", ref_arg)) else None
    check_cb = f"check_sub_{safe_ref}" if safe_ref else "check_sub"
    builder.row(types.InlineKeyboardButton(text="🔄 Проверить подписку", callback_data=check_cb))
    return builder.as_markup()


def get_main_menu(is_enabled: bool) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status_text = "🟢 Сигналы: ВКЛ" if is_enabled else "🔴 Сигналы: ПАУЗА"
    builder.row(types.InlineKeyboardButton(text=status_text, callback_data="toggle_alerts"))
    builder.row(
        types.InlineKeyboardButton(text="👤 Мой профиль", callback_data="my_profile"),
        types.InlineKeyboardButton(text="⚙️ Настройки", callback_data="start_setup")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔇 Блэклист", callback_data="blacklist_menu"),
        types.InlineKeyboardButton(text="📚 FAQ & Оферта", callback_data="faq_menu")
    )
    builder.row(
        types.InlineKeyboardButton(text="⚡️ Тест алерта", callback_data="send_test_alert"),
        types.InlineKeyboardButton(text="🧪 Связь", callback_data="run_diagnostics")
    )
    if app_state.cached_channel_url and app_state.cached_channel_url != "https://t.me/":
        builder.row(
            types.InlineKeyboardButton(text="📢 Наш канал", url=app_state.cached_channel_url),
            types.InlineKeyboardButton(text="💬 Поддержка", callback_data="feedback_start")
        )
    else:
        builder.row(
            types.InlineKeyboardButton(text="💬 Поддержка", callback_data="feedback_start")
        )
    return builder.as_markup()


def get_profile_menu() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💎 Управление PRO-доступом", callback_data="buy_sub"))
    builder.row(types.InlineKeyboardButton(text="🎁 Реферальная программа", callback_data="ref_menu"))
    builder.row(types.InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_main"))
    return builder.as_markup()


def get_presets_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="⚖️ Базовый (Vol 3x | Цена 1.5% | ОИ 1.2%)",
        callback_data="preset_base"
    ))
    builder.row(types.InlineKeyboardButton(
        text="⚡️ Частый (Vol 2.2x | Цена 1.0% | ОИ 0.8%)",
        callback_data="preset_fast"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🐋 Крупный (Vol 5x | Цена 2.5% | ОИ 2.0%)",
        callback_data="preset_whale"
    ))
    builder.row(types.InlineKeyboardButton(
        text="✏️ Ввести значения вручную",
        callback_data="setup_manual"
    ))
    builder.row(types.InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_main"))
    return builder.as_markup()


def get_setup_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⏭ Пропустить шаг", callback_data="skip_setup_step"))
    builder.row(types.InlineKeyboardButton(text="◀️ Отмена", callback_data="back_main"))
    return builder.as_markup()


def create_sniper_keyboard(identifier: str, dex_url: Optional[str] = None) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    chart_url = dex_url or f"https://dexscreener.com/solana/{identifier}"
    rugcheck_url = f"https://rugcheck.xyz/tokens/{identifier}"
    ref_tail = f"?ref={GMGN_REF_CODE}" if GMGN_REF_CODE else ""
    gmgn_trade_url = f"{GMGN_BASE_URL}/sol/token/{identifier}{ref_tail}"

    builder.row(types.InlineKeyboardButton(text="📊 График и контракт (GMGN)", url=gmgn_trade_url))
    builder.row(
        types.InlineKeyboardButton(text="📈 DexScreener", url=chart_url),
        types.InlineKeyboardButton(text="🛡 RugCheck", url=rugcheck_url)
    )
    return builder.as_markup()


def get_admin_menu() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📊 Аналитика и лимит НПД", callback_data="admin_stats"),
        types.InlineKeyboardButton(text="📋 База и таблицы", callback_data="admin_tbl_users_0")
    )
    builder.row(
        types.InlineKeyboardButton(text="🎯 Аудит точности", callback_data="admin_accuracy"),
        types.InlineKeyboardButton(text="🎁 Выдать PRO", callback_data="admin_give_sub")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔍 Проверить ID", callback_data="admin_find_user"),
        types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")
    )
    sol_text = "🎯 Solana: ВКЛ 🟢" if app_state.solana_enabled else "🎯 Solana: ВЫКЛ 🔴"
    pause_text = "▶️ Возобновить всё" if app_state.emergency_pause else "⏸ Общая пауза"
    builder.row(
        types.InlineKeyboardButton(text=sol_text, callback_data="admin_toggle_solana"),
        types.InlineKeyboardButton(text=pause_text, callback_data="admin_toggle_pause")
    )
    builder.row(
        types.InlineKeyboardButton(text="🗑 Сброс аудита", callback_data="admin_clear_signals"),
        types.InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")
    )
    return builder.as_markup()