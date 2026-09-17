"""لوحة إدارة Flask ومسارات التكامل الآمنة."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from http import HTTPStatus
from typing import Any, TypeVar
from uuid import UUID

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFError, CSRFProtect
from telegram import Update
from telegram.ext import Application

from bot import publish_daily_content
from config import Settings
from database import Database, DatabaseError
from forms import DeleteForm, DiseaseForm, LoginForm, QuestionForm

logger = logging.getLogger(__name__)
csrf = CSRFProtect()
F = TypeVar("F", bound=Callable[..., Any])
PUBLIC_TOPIC_WEIGHTS = {1: "متوسط", 2: "عالٍ", 3: "عالي جدًا"}
PUBLIC_TOPICS_CACHE_SECONDS = 60


class LoginAttemptGuard:
    """حاجز ذاكرة قصير ضد محاولات تسجيل الدخول المتكررة."""

    def __init__(self, limit: int = 5, window_seconds: int = 300):
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def allowed(self, key: str) -> bool:
        """تحديد السماح دون حفظ عنوان العميل خارج الذاكرة."""
        now = time.monotonic()
        attempts = self._attempts[key]
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()
        return len(attempts) < self.limit

    def failure(self, key: str) -> None:
        self._attempts[key].append(time.monotonic())

    def success(self, key: str) -> None:
        self._attempts.pop(key, None)


def login_required(view: F) -> F:
    """رفض الوصول افتراضيًا ما لم تحمل الجلسة دور الإدارة."""

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if session.get("role") != "admin":
            flash("يرجى تسجيل الدخول أولًا.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def _safe_compare(left: str, right: str) -> bool:
    """مقارنة ثابتة الزمن قدر الإمكان لبيانات الدخول والأسرار."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _fill_disease_choices(form: QuestionForm, database: Database) -> None:
    """ملء قائمة الأمراض والتحقق ضمن القيم المتاحة فقط."""
    diseases = database.list_diseases()
    form.disease_id.choices = [(str(item["id"]), str(item["name_ar"])) for item in diseases]


def create_web_app(settings: Settings, database: Database, bot_application: Application | None = None) -> Flask:
    """إنشاء تطبيق الويب مع حقن الاعتماديات لتسهيل الاختبار."""
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.flask_secret_key,
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=settings.secure_cookies,
        SESSION_COOKIE_SAMESITE="Lax",
        WTF_CSRF_TIME_LIMIT=3600,
    )
    csrf.init_app(app)
    guard = LoginAttemptGuard()
    public_topics_cache: dict[str, Any] = {"expires_at": 0.0, "payload": None, "etag": ""}

    @app.after_request
    def add_security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' https: data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers.setdefault("Cache-Control", "no-store")
        if settings.production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/public/topics")
    def public_topics():
        """إرجاع فهرس تعليمي عام فقط، بلا أسرار أو تفاصيل علاجية أو بيانات مستخدمين."""
        now = time.monotonic()
        payload = public_topics_cache["payload"]
        if payload is None or now >= public_topics_cache["expires_at"]:
            try:
                rows = database.list_public_topics(limit=100)
            except DatabaseError:
                logger.exception("فشل تحميل الفهرس العام من قاعدة البيانات.")
                response = jsonify({"error": "تعذر تحديث الفهرس مؤقتًا."})
                response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
                response.headers["Retry-After"] = "60"
                response.headers["Access-Control-Allow-Origin"] = "*"
                return response

            topics = []
            for position, row in enumerate(rows, start=1):
                title = str(row.get("name_ar") or "").strip()[:200]
                if not title:
                    continue
                try:
                    importance = int(row.get("importance") or 1)
                except (TypeError, ValueError):
                    importance = 1
                try:
                    order = int(row.get("week_number") or position)
                except (TypeError, ValueError):
                    order = position
                topics.append(
                    {
                        "id": str(row.get("id") or position)[:64],
                        "title": title,
                        "title_en": str(row.get("name_en") or "").strip()[:200],
                        "specialty": str(row.get("system") or "طب عام").strip()[:120],
                        "audience": "تعليم طبي عام",
                        "weight": PUBLIC_TOPIC_WEIGHTS.get(importance, "متوسط"),
                        "status": "منشور",
                        "order": max(1, min(order, 53)),
                    }
                )

            payload = {"topics": topics, "count": len(topics), "source": "supabase"}
            etag_source = json.dumps(topics, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            public_topics_cache.update(
                expires_at=now + PUBLIC_TOPICS_CACHE_SECONDS,
                payload=payload,
                etag=hashlib.sha256(etag_source.encode("utf-8")).hexdigest(),
            )

        etag = public_topics_cache["etag"]
        if etag and request.if_none_match.contains_weak(etag):
            response = app.response_class(status=HTTPStatus.NOT_MODIFIED)
        else:
            response = jsonify(payload)
        if etag:
            response.set_etag(etag)
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET"
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        return response

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("role") == "admin":
            return redirect(url_for("dashboard"))
        form = LoginForm()
        client_key = request.remote_addr or "unknown"
        if form.validate_on_submit():
            if not guard.allowed(client_key):
                flash("محاولات كثيرة. انتظر خمس دقائق ثم حاول مرة أخرى.", "danger")
                return render_template("login.html", form=form), HTTPStatus.TOO_MANY_REQUESTS
            valid = _safe_compare(form.username.data, settings.admin_username) and _safe_compare(
                form.password.data, settings.admin_password
            )
            if valid:
                guard.success(client_key)
                session.clear()
                session["role"] = "admin"
                session.permanent = True
                flash("تم تسجيل الدخول بنجاح.", "success")
                return redirect(url_for("dashboard"))
            guard.failure(client_key)
            flash("اسم المستخدم أو كلمة المرور غير صحيحين.", "danger")
        return render_template("login.html", form=form)

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("تم تسجيل الخروج.", "success")
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        return redirect(url_for("dashboard" if session.get("role") == "admin" else "login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        try:
            stats = database.get_stats()
            return render_template("dashboard.html", stats=stats)
        except DatabaseError:
            logger.exception("فشل تحميل لوحة المعلومات.")
            return render_template("error.html", message="تعذر تحميل الإحصاءات مؤقتًا."), 503

    @app.get("/diseases")
    @login_required
    def disease_list():
        try:
            return render_template("diseases/list.html", diseases=database.list_diseases())
        except DatabaseError:
            logger.exception("فشل تحميل صفحة الأمراض.")
            return render_template("error.html", message="تعذر تحميل الأمراض مؤقتًا."), 503

    @app.route("/diseases/new", methods=["GET", "POST"])
    @login_required
    def disease_create():
        form = DiseaseForm()
        if form.validate_on_submit():
            try:
                database.create_disease(form.to_payload())
                flash("تمت إضافة المرض.", "success")
                return redirect(url_for("disease_list"))
            except DatabaseError:
                flash("تعذر إضافة المرض. تحقق من البيانات ثم حاول مرة أخرى.", "danger")
        return render_template("diseases/form.html", form=form, title="إضافة مرض")

    @app.route("/diseases/<uuid:disease_id>/edit", methods=["GET", "POST"])
    @login_required
    def disease_edit(disease_id: UUID):
        try:
            disease = database.get_disease(str(disease_id))
        except DatabaseError:
            return render_template("error.html", message="تعذر تحميل المرض مؤقتًا."), 503
        if not disease:
            abort(404)
        form = DiseaseForm(data=disease)
        if form.validate_on_submit():
            try:
                database.update_disease(str(disease_id), form.to_payload())
                flash("تم تعديل المرض.", "success")
                return redirect(url_for("disease_list"))
            except DatabaseError:
                flash("تعذر تعديل المرض.", "danger")
        return render_template("diseases/form.html", form=form, title="تعديل مرض")

    @app.route("/diseases/<uuid:disease_id>/delete", methods=["GET", "POST"])
    @login_required
    def disease_delete(disease_id: UUID):
        form = DeleteForm()
        try:
            disease = database.get_disease(str(disease_id))
            if not disease:
                abort(404)
            if form.validate_on_submit():
                database.delete_disease(str(disease_id))
                flash("تم حذف المرض والأسئلة المرتبطة به.", "success")
                return redirect(url_for("disease_list"))
        except DatabaseError:
            return render_template("error.html", message="تعذر حذف المرض مؤقتًا."), 503
        return render_template(
            "confirm_delete.html",
            form=form,
            title="تأكيد حذف المرض",
            item_name=disease["name_ar"],
            warning="سيُحذف المرض وكل الأسئلة المرتبطة به نهائيًا.",
            cancel_url=url_for("disease_list"),
        )

    @app.get("/questions")
    @login_required
    def question_list():
        try:
            return render_template("questions/list.html", questions=database.list_questions())
        except DatabaseError:
            logger.exception("فشل تحميل صفحة الأسئلة.")
            return render_template("error.html", message="تعذر تحميل الأسئلة مؤقتًا."), 503

    @app.route("/questions/new", methods=["GET", "POST"])
    @login_required
    def question_create():
        form = QuestionForm()
        try:
            _fill_disease_choices(form, database)
        except DatabaseError:
            return render_template("error.html", message="أضف مرضًا أولًا أو حاول لاحقًا."), 503
        if form.validate_on_submit():
            try:
                database.create_question(form.to_payload())
                flash("تمت إضافة السؤال.", "success")
                return redirect(url_for("question_list"))
            except DatabaseError:
                flash("تعذر إضافة السؤال.", "danger")
        return render_template("questions/form.html", form=form, title="إضافة سؤال")

    @app.route("/questions/<uuid:question_id>/edit", methods=["GET", "POST"])
    @login_required
    def question_edit(question_id: UUID):
        try:
            question = database.get_question(str(question_id))
        except DatabaseError:
            return render_template("error.html", message="تعذر تحميل السؤال مؤقتًا."), 503
        if not question:
            abort(404)
        form = QuestionForm(data=question)
        try:
            _fill_disease_choices(form, database)
        except DatabaseError:
            return render_template("error.html", message="تعذر تحميل الأمراض."), 503
        if form.validate_on_submit():
            try:
                database.update_question(str(question_id), form.to_payload())
                flash("تم تعديل السؤال.", "success")
                return redirect(url_for("question_list"))
            except DatabaseError:
                flash("تعذر تعديل السؤال.", "danger")
        return render_template("questions/form.html", form=form, title="تعديل سؤال")

    @app.route("/questions/<uuid:question_id>/delete", methods=["GET", "POST"])
    @login_required
    def question_delete(question_id: UUID):
        form = DeleteForm()
        try:
            question = database.get_question(str(question_id))
            if not question:
                abort(404)
            if form.validate_on_submit():
                database.delete_question(str(question_id))
                flash("تم حذف السؤال.", "success")
                return redirect(url_for("question_list"))
        except DatabaseError:
            return render_template("error.html", message="تعذر حذف السؤال مؤقتًا."), 503
        return render_template(
            "confirm_delete.html",
            form=form,
            title="تأكيد حذف السؤال",
            item_name=question["question"],
            warning="سيُحذف هذا السؤال نهائيًا.",
            cancel_url=url_for("question_list"),
        )

    @app.post("/telegram/webhook")
    @csrf.exempt
    async def telegram_webhook():
        if bot_application is None or not settings.webhook_secret:
            abort(503)
        provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not _safe_compare(provided, settings.webhook_secret):
            abort(403)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            abort(400)
        update = Update.de_json(payload, bot_application.bot)
        await bot_application.update_queue.put(update)
        return "", HTTPStatus.NO_CONTENT

    @app.post("/tasks/daily-publish")
    @csrf.exempt
    async def trigger_daily_publish():
        if bot_application is None or not settings.scheduler_secret:
            abort(503)
        provided = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.scheduler_secret}"
        if not _safe_compare(provided, expected):
            abort(403)
        try:
            local_now = datetime.now(settings.timezone)
            configured_minutes = settings.daily_post_time.hour * 60 + settings.daily_post_time.minute
            current_minutes = local_now.hour * 60 + local_now.minute
            if current_minutes < configured_minutes:
                return jsonify({"published": False, "reason": "before_scheduled_time"})
            result = await publish_daily_content(
                bot_application.bot,
                database,
                now=local_now,
                settings=settings,
            )
            return jsonify(result)
        except DatabaseError:
            logger.exception("فشل استدعاء النشر المجدول.")
            return jsonify({"error": "تعذر تنفيذ النشر."}), 503

    @app.errorhandler(CSRFError)
    def csrf_error(_error):
        return render_template("error.html", message="انتهت صلاحية النموذج. أعد تحميل الصفحة وحاول مرة أخرى."), 400

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", message="الصفحة المطلوبة غير موجودة."), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return render_template("error.html", message="حدث خطأ غير متوقع. حاول لاحقًا."), 500

    return app
