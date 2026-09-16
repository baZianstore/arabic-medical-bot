"""تحميل إعدادات التطبيق من متغيرات البيئة والتحقق منها."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """خطأ واضح عند نقص إعداد أساسي أو عدم صلاحيته."""


def _parse_time(value: str) -> time:
    """تحويل الوقت بصيغة HH:MM إلى كائن time."""
    try:
        hour_text, minute_text = value.strip().split(":", maxsplit=1)
        hour, minute = int(hour_text), int(minute_text)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError
        return time(hour=hour, minute=minute)
    except (ValueError, AttributeError) as exc:
        raise ConfigurationError("يجب أن تكون DAILY_POST_TIME بصيغة HH:MM، مثل 08:00.") from exc


def _as_bool(value: str | None, default: bool = False) -> bool:
    """تحويل قيم البيئة الشائعة إلى قيمة منطقية."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """إعدادات التطبيق بعد التحقق من القيم الحساسة."""

    bot_token: str
    supabase_url: str
    supabase_key: str
    admin_username: str
    admin_password: str
    flask_secret_key: str
    webhook_secret: str
    scheduler_secret: str
    webhook_url: str | None
    bot_mode: str
    daily_post_time: time
    timezone: ZoneInfo
    timezone_name: str
    port: int
    production: bool
    secure_cookies: bool

    @classmethod
    def from_env(cls, *, require_external: bool = True) -> Settings:
        """قراءة الإعدادات؛ تُشدَّد القواعد تلقائيًا في الإنتاج."""
        load_dotenv()
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        production = app_env == "production" or bool(os.getenv("RENDER"))

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        supabase_key = (
            os.getenv("SUPABASE_SECRET_KEY", "").strip()
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.getenv("SUPABASE_ANON_KEY", "").strip()
        )
        admin_username = os.getenv("ADMIN_USERNAME", "admin").strip()
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123" if not production else "")
        flask_secret_key = os.getenv("FLASK_SECRET_KEY", "")
        webhook_secret = os.getenv("WEBHOOK_SECRET", "")
        scheduler_secret = os.getenv("SCHEDULER_SECRET", "")
        webhook_url = os.getenv("WEBHOOK_URL", "").strip().rstrip("/") or None
        render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
        if not webhook_url and render_host:
            webhook_url = f"https://{render_host}"

        bot_mode = os.getenv("BOT_MODE", "webhook" if production else "polling").strip().lower()
        if bot_mode not in {"polling", "webhook"}:
            raise ConfigurationError("يجب أن تكون BOT_MODE إما polling أو webhook.")

        timezone_name = os.getenv("TIMEZONE", "Asia/Jerusalem").strip()
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigurationError("قيمة TIMEZONE غير معروفة.") from exc

        daily_post_time = _parse_time(os.getenv("DAILY_POST_TIME", "08:00"))
        try:
            port = int(os.getenv("PORT", "8000"))
        except ValueError as exc:
            raise ConfigurationError("يجب أن يكون PORT رقمًا صحيحًا.") from exc

        if require_external:
            missing = [
                name
                for name, value in {
                    "BOT_TOKEN": bot_token,
                    "SUPABASE_URL": supabase_url,
                    "SUPABASE_SECRET_KEY": supabase_key,
                    "ADMIN_USERNAME": admin_username,
                    "ADMIN_PASSWORD": admin_password,
                }.items()
                if not value
            ]
            if missing:
                raise ConfigurationError("متغيرات البيئة الناقصة: " + ", ".join(missing))

        if not flask_secret_key:
            if production:
                raise ConfigurationError("FLASK_SECRET_KEY مطلوب في الإنتاج.")
            flask_secret_key = secrets.token_urlsafe(32)

        if production:
            if admin_password == "admin123" or len(admin_password) < 12:
                raise ConfigurationError("غيّر ADMIN_PASSWORD إلى كلمة قوية من 12 محرفًا على الأقل قبل النشر.")
            if len(flask_secret_key) < 32:
                raise ConfigurationError("يجب أن يحتوي FLASK_SECRET_KEY على 32 محرفًا على الأقل.")
            if bot_mode == "webhook":
                if not webhook_url or not webhook_url.startswith("https://"):
                    raise ConfigurationError("WEBHOOK_URL آمن (HTTPS) مطلوب في وضع webhook.")
                if len(webhook_secret) < 16:
                    raise ConfigurationError("WEBHOOK_SECRET مطلوب ويجب ألا يقل عن 16 محرفًا.")
            if len(scheduler_secret) < 16:
                raise ConfigurationError("SCHEDULER_SECRET مطلوب ويجب ألا يقل عن 16 محرفًا.")
            if not os.getenv("SUPABASE_SECRET_KEY") and not os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
                raise ConfigurationError("استخدم SUPABASE_SECRET_KEY الخادمي في الإنتاج، وليس المفتاح العام.")

        return cls(
            bot_token=bot_token,
            supabase_url=supabase_url,
            supabase_key=supabase_key,
            admin_username=admin_username,
            admin_password=admin_password,
            flask_secret_key=flask_secret_key,
            webhook_secret=webhook_secret,
            scheduler_secret=scheduler_secret,
            webhook_url=webhook_url,
            bot_mode=bot_mode,
            daily_post_time=daily_post_time,
            timezone=timezone,
            timezone_name=timezone_name,
            port=port,
            production=production,
            secure_cookies=_as_bool(os.getenv("SESSION_COOKIE_SECURE"), production),
        )
