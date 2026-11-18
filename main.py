import asyncio
import logging
import sys
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import state as app_state, BOT_TOKEN, CHANNEL_ID, DB_PATH, WEB_SERVER_PORT
from database import init_db, get_bot_setting
from handlers import register_routers
from handlers.payments import crypto, prodamus_webhook_handler
from handlers.user import get_channel_invite_url
from texts import get_channel_bio
from workers import start_background_workers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SpikePRO.Main")

bot = Bot(token=BOT_TOKEN or "123456:PLACEHOLDER", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
register_routers(dp)


async def start_webhook_server(bot_instance: Bot):
    try:
        app = web.Application()
        app["bot"] = bot_instance
        app.router.add_get("/", lambda _: web.Response(text="Spike PRO is running", status=200))
        app.router.add_post("/prodamus/webhook", prodamus_webhook_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=WEB_SERVER_PORT)
        await site.start()
        logger.info(f"HTTP-сервер вебхуков запущен на порту {WEB_SERVER_PORT}")
        return runner
    except Exception as e:
        logger.warning(f"HTTP-сервер на порту {WEB_SERVER_PORT} не запущен (работаем в режиме поллинга): {e}")
        return None


@dp.startup()
async def on_startup():
    await init_db()

    app_state.solana_enabled = (await get_bot_setting("solana_sniper_enabled", "1")) == "1"
    app_state.emergency_pause = (await get_bot_setting("emergency_pause", "0")) == "1"

    try:
        me = await bot.get_me()
        if me.username:
            app_state.cached_bot_username = me.username
    except Exception:
        pass

    if CHANNEL_ID:
        app_state.cached_channel_url = await get_channel_invite_url(bot)
        try:
            chan_ref = CHANNEL_ID if CHANNEL_ID.startswith("@") else app_state.cached_channel_url
            short_desc = f"Аналитическое ПО мониторинга рыночных метрик Bybit и Solana. Не ИИР. Канал: {chan_ref}"[:120]
            full_desc = (
                f"⚡️ Spike PRO — информационно-аналитическое ПО (мониторинг метрик Bybit Futures и ончейн-данных Raydium).\n"
                f"Информация носит справочный характер и не является ИИР.\n\n"
                f"📢 Официальный канал: {chan_ref}"
            )[:512]
            await bot.set_my_short_description(short_description=short_desc)
            await bot.set_my_description(description=full_desc)
        except Exception as e:
            logger.warning(f"Не удалось обновить описание профиля бота: {e}")

        try:
            chan_bio = get_channel_bio(app_state.cached_bot_username)
            chat_info = await bot.get_chat(CHANNEL_ID)
            if (chat_info.description or "").strip() != chan_bio.strip():
                await bot.set_chat_description(chat_id=CHANNEL_ID, description=chan_bio)
        except Exception as e:
            logger.warning(f"Автосинхронизация описания канала пропущена: {e}")

    dp.workflow_data['bg_tasks'] = start_background_workers(bot)
    dp.workflow_data['web_runner'] = await start_webhook_server(bot)
    logger.info(
        f"Spike PRO (@{app_state.cached_bot_username}) запущен | БД: {DB_PATH} | "
        f"Solana: {'ВКЛ' if app_state.solana_enabled else 'ВЫКЛ'}"
    )


@dp.shutdown()
async def on_shutdown():
    tasks = dp.workflow_data.get('bg_tasks', [])
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    web_runner = dp.workflow_data.get('web_runner')
    if web_runner:
        await web_runner.cleanup()

    if crypto:
        await crypto.close()
    await bot.session.close()


async def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN не задан в .env!")
        return
    await dp.start_polling(bot)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())