"""اختبارات قبول أمنية ثابتة تستخدم بيانات ومفاتيح اصطناعية فقط."""

from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from config import Settings
from seed_data import DISEASES
from web import create_web_app


class FakeDatabase:
    def get_stats(self): return {"diseases": 0, "questions": 0, "subscribers": 0}
    def list_diseases(self): return []


def make_settings(*, production=False, secure_cookies=False):
    return Settings(
        bot_token="123:test", supabase_url="https://example.supabase.co", supabase_key="sb_secret_test",
        admin_username="admin", admin_password="a-strong-test-password", flask_secret_key="f" * 40,
        webhook_secret="w" * 20, scheduler_secret="s" * 20, webhook_url="https://example.test",
        bot_mode="webhook", daily_post_time=time(8), timezone=ZoneInfo("Asia/Jerusalem"),
        timezone_name="Asia/Jerusalem", port=8000, production=production, secure_cookies=secure_cookies,
    )


def test_seed_contains_five_diseases_and_fifteen_questions():
    assert len(DISEASES) == 5
    assert sum(len(item["questions"]) for item in DISEASES) == 15
    assert all(item["definition"] and item["diagnosis"] and item["treatment"] for item in DISEASES)


def test_schema_denies_public_roles_and_enables_rls():
    sql = Path("schema.sql").read_text(encoding="utf-8").lower()
    assert "alter default privileges for role postgres" in sql
    for table in (
        "diseases",
        "questions",
        "subscribers",
        "daily_publications",
        "usage_daily_metrics",
        "report_delivery_config",
        "weekly_report_deliveries",
    ):
        assert f"alter table public.{table} enable row level security" in sql
        assert f"revoke all on table public.{table}" in sql
        assert "anon, authenticated" in sql


def test_analytics_schema_is_aggregate_only_and_functions_are_service_role_only():
    sql = Path("schema.sql").read_text(encoding="utf-8").lower()
    metrics_block = sql.split("create table if not exists public.usage_daily_metrics", 1)[1].split(
        "create table if not exists public.report_delivery_config", 1
    )[0]
    for forbidden in ("user_id", "chat_id", "username", "message", "query_text", "answer_text"):
        assert forbidden not in metrics_block
    assert "security invoker" in sql
    assert "revoke all on function public.increment_usage_metric" in sql
    assert "revoke all on function public.consume_report_link_token" in sql
    assert "grant execute on function public.increment_usage_metric(date, text, text) to service_role" in sql
    assert "grant execute on function public.consume_report_link_token(text, bigint) to service_role" in sql


def test_webhook_rejects_wrong_secret_before_processing_payload():
    app = create_web_app(make_settings(), FakeDatabase(), bot_application=object())
    app.config.update(TESTING=True)
    client = app.test_client()
    response = client.post(
        "/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert response.status_code == 403


def test_production_cookie_has_secure_attribute():
    app = create_web_app(make_settings(production=True, secure_cookies=True), FakeDatabase())
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": "admin", "password": "a-strong-test-password"},
    )
    cookie = response.headers.get("Set-Cookie", "")
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_templates_do_not_load_external_scripts_or_styles():
    template_text = "\n".join(path.read_text(encoding="utf-8") for path in Path("templates").rglob("*.html"))
    assert "https://" not in template_text
    assert "localStorage" not in template_text
    assert "sessionStorage" not in template_text
