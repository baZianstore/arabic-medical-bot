"""نقطة تشغيل البوت ولوحة الإدارة محليًا أو عبر webhook سحابي."""

from __future__ import annotations

import asyncio
import logging
import threading

import uvicorn
from asgiref.wsgi import WsgiToAsgi
from telegram import Update

from bot import configure_bot_commands, create_bot_application
from config import ConfigurationError, Settings
from database import Database
from web import create_web_app

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _build_components(settings: Settings):
    """إنشاء قاعدة البيانات والبوت والويب بحقن مشترك للاعتماديات."""
    database = Database(settings.supabase_url, settings.supabase_key)
    bot_application = create_bot_application(settings, database)
    flask_app = create_web_app(settings, database, bot_application)
    return bot_application, flask_app


def run_polling(settings: Settings) -> None:
    """تشغيل لوحة Flask في خيط والبوت بالاقتراع للاستخدام المحلي."""
    bot_application, flask_app = _build_components(settings)

    def run_dashboard() -> None:
        flask_app.run(host="0.0.0.0", port=settings.port, debug=False, use_reloader=False, threaded=True)

    threading.Thread(target=run_dashboard, name="dashboard", daemon=True).start()
    logger.info("بدأت لوحة الإدارة المحلية على المنفذ %s.", settings.port)
    bot_application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
        bootstrap_retries=3,
    )


async def run_webhook(settings: Settings) -> None:
    """تشغيل Flask والبوت في حلقة واحدة خلف Uvicorn."""
    if not settings.webhook_url:
        raise ConfigurationError("WEBHOOK_URL مطلوب في وضع webhook.")
    bot_application, flask_app = _build_components(settings)
    webhook_endpoint = f"{settings.webhook_url}/telegram/webhook"

    async with bot_application:
        await bot_application.bot.set_webhook(
            url=webhook_endpoint,
            secret_token=settings.webhook_secret,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
        )
        await configure_bot_commands(bot_application)
        await bot_application.start()
        logger.info("بدأت الخدمة في وضع webhook.")
        server = uvicorn.Server(
            uvicorn.Config(
                app=WsgiToAsgi(flask_app),
                host="0.0.0.0",
                port=settings.port,
                log_level="info",
                access_log=False,
                proxy_headers=True,
            )
        )
        try:
            await server.serve()
        finally:
            await bot_application.stop()


def main() -> None:
    """اختيار وضع التشغيل من البيئة مع رسالة خطأ قابلة للفهم."""
    try:
        settings = Settings.from_env()
        if settings.bot_mode == "polling":
            run_polling(settings)
        else:
            asyncio.run(run_webhook(settings))
    except ConfigurationError as exc:
        logger.error("خطأ في الإعدادات: %s", exc)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
