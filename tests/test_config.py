"""اختبارات الإعدادات دون استخدام أي أسرار حقيقية."""

import pytest

from config import ConfigurationError, Settings, _parse_time


def test_parse_time_accepts_valid_value():
    parsed = _parse_time("08:30")
    assert parsed.hour == 8
    assert parsed.minute == 30


def test_parse_time_rejects_invalid_value():
    with pytest.raises(ConfigurationError):
        _parse_time("25:99")


def test_production_rejects_default_password(monkeypatch):
    values = {
        "APP_ENV": "production",
        "BOT_TOKEN": "123:test-token",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SECRET_KEY": "sb_secret_test_only",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "admin123",
        "FLASK_SECRET_KEY": "x" * 40,
        "WEBHOOK_SECRET": "w" * 20,
        "SCHEDULER_SECRET": "s" * 20,
        "WEBHOOK_URL": "https://example.test",
        "BOT_MODE": "webhook",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ConfigurationError, match="ADMIN_PASSWORD"):
        Settings.from_env()


def test_render_external_url_configures_webhook_without_manual_url(monkeypatch):
    values = {
        "APP_ENV": "production",
        "BOT_TOKEN": "123:test-token",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SECRET_KEY": "sb_secret_test_only",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "strong-password-2026",
        "FLASK_SECRET_KEY": "x" * 40,
        "WEBHOOK_SECRET": "w" * 20,
        "SCHEDULER_SECRET": "s" * 20,
        "RENDER_EXTERNAL_URL": "https://example.onrender.com/",
        "BOT_MODE": "webhook",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)

    settings = Settings.from_env()

    assert settings.webhook_url == "https://example.onrender.com"
