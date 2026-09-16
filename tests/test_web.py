"""اختبارات تكامل Flask ببيانات اصطناعية فقط."""

import re
from datetime import time
from zoneinfo import ZoneInfo

from config import Settings
from web import create_web_app


class FakeDatabase:
    deleted_disease = None

    def get_stats(self): return {"diseases": 2, "questions": 6, "subscribers": 3}
    def list_diseases(self): return []
    def list_questions(self): return []
    def get_disease(self, disease_id): return {"id": disease_id, "name_ar": "مرض اصطناعي"}
    def delete_disease(self, disease_id): self.deleted_disease = disease_id


def settings():
    return Settings(
        bot_token="123:test",
        supabase_url="https://example.supabase.co",
        supabase_key="sb_secret_test",
        admin_username="admin",
        admin_password="admin123",
        flask_secret_key="f" * 40,
        webhook_secret="w" * 20,
        scheduler_secret="s" * 20,
        webhook_url=None,
        bot_mode="polling",
        daily_post_time=time(8, 0),
        timezone=ZoneInfo("Asia/Jerusalem"),
        timezone_name="Asia/Jerusalem",
        port=8000,
        production=False,
        secure_cookies=False,
    )


def create_client():
    app = create_web_app(settings(), FakeDatabase())
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app.test_client()


def test_login_post_without_csrf_is_rejected_when_protection_is_enabled():
    app = create_web_app(settings(), FakeDatabase())
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    client = app.test_client()
    response = client.post("/login", data={"username": "admin", "password": "admin123"})
    assert response.status_code == 400
    assert "انتهت صلاحية النموذج".encode() in response.data


def test_login_with_real_csrf_token_succeeds():
    app = create_web_app(settings(), FakeDatabase())
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    client = app.test_client()
    login_page = client.get("/login")
    match = re.search(rb'name="csrf_token" type="hidden" value="([^"]+)"', login_page.data)
    assert match is not None
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123", "csrf_token": match.group(1).decode()},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "لوحة المعلومات".encode() in response.data


def test_dashboard_denies_anonymous_user():
    client = create_client()
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_login_and_dashboard_are_arabic_and_secure():
    client = create_client()
    response = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    assert response.status_code == 200
    assert "لوحة المعلومات".encode() in response.data
    cookie = response.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")


def test_invalid_login_is_rejected():
    client = create_client()
    response = client.post("/login", data={"username": "admin", "password": "wrong"}, follow_redirects=True)
    assert "غير صحيحين".encode() in response.data


def test_scheduler_endpoint_fails_closed_without_bot_application():
    client = create_client()
    response = client.post("/tasks/daily-publish", headers={"Authorization": "Bearer " + "s" * 20})
    assert response.status_code == 503


def test_delete_disease_requires_confirmation_page_then_post():
    database = FakeDatabase()
    app = create_web_app(settings(), database)
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "admin123"})
    disease_id = "00000000-0000-0000-0000-000000000001"
    confirmation = client.get(f"/diseases/{disease_id}/delete")
    assert confirmation.status_code == 200
    assert "تأكيد حذف المرض".encode() in confirmation.data
    assert database.deleted_disease is None
    result = client.post(f"/diseases/{disease_id}/delete")
    assert result.status_code == 302
    assert database.deleted_disease == disease_id
