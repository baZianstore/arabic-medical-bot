"""طبقة الوصول إلى Supabase؛ لا تتعامل بقية الوحدات مع العميل مباشرة."""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any

from analytics import (
    aggregate_usage_rows,
    completed_week,
    normalize_usage_event,
    previous_period,
)
from supabase import Client, create_client


class DatabaseError(RuntimeError):
    """خطأ عام لا يسرّب تفاصيل Supabase إلى المستخدم النهائي."""


class Database:
    """مستودع بيانات المحتوى التعليمي والمشتركين."""

    def __init__(self, url: str | None = None, key: str | None = None, *, client: Client | Any = None):
        if client is not None:
            self.client = client
        elif url and key:
            self.client = create_client(url, key)
        else:
            raise ValueError("يلزم تمرير url وkey أو عميل Supabase جاهز.")

    @staticmethod
    def _first(data: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        return data[0] if data else None

    def list_diseases(self) -> list[dict[str, Any]]:
        """إرجاع الأمراض مرتبة حسب الأسبوع ثم الاسم العربي."""
        try:
            response = self.client.table("diseases").select("*").order("week_number").order("name_ar").execute()
            return response.data or []
        except Exception as exc:
            raise DatabaseError("تعذر تحميل قائمة الأمراض.") from exc

    def list_public_topics(self, limit: int = 100) -> list[dict[str, Any]]:
        """إرجاع حقول الفهرس العامة فقط دون التفاصيل العلاجية أو بيانات المشتركين."""
        safe_limit = max(1, min(limit, 100))
        fields = ("id", "name_ar", "name_en", "system", "importance", "week_number")
        try:
            response = (
                self.client.table("diseases")
                .select(",".join(fields))
                .order("week_number")
                .order("name_ar")
                .limit(safe_limit)
                .execute()
            )
            return [
                {field: row.get(field) for field in fields}
                for row in (response.data or [])
                if isinstance(row, dict)
            ]
        except Exception as exc:
            raise DatabaseError("تعذر تحميل الفهرس العام.") from exc

    def get_disease(self, disease_id: str) -> dict[str, Any] | None:
        """إرجاع مرض واحد، أو None إذا لم يكن موجودًا."""
        try:
            response = self.client.table("diseases").select("*").eq("id", disease_id).limit(1).execute()
            return self._first(response.data)
        except Exception as exc:
            raise DatabaseError("تعذر تحميل المرض.") from exc

    def get_daily_disease(self, target_date: date | None = None) -> dict[str, Any] | None:
        """اختيار مرض اليوم بالتناوب الحتمي بين المحتويات المنشورة."""
        diseases = self.list_diseases()
        if not diseases:
            return None
        selected_date = target_date or datetime.now(timezone.utc).date()
        index = selected_date.toordinal() % len(diseases)
        return diseases[index]

    def search_diseases(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """بحث محلي آمن بعد جلب قائمة المحتوى الصغيرة لتجنب بناء مرشح نصي خام."""
        normalized = query.strip().casefold()
        if not normalized:
            return []
        matches = [
            disease
            for disease in self.list_diseases()
            if normalized in str(disease.get("name_ar", "")).casefold()
            or normalized in str(disease.get("name_en", "")).casefold()
        ]
        return matches[:limit]

    def create_disease(self, payload: dict[str, Any]) -> dict[str, Any]:
        """إنشاء مرض جديد وإرجاع السجل المنشأ."""
        try:
            response = self.client.table("diseases").insert(payload).execute()
            return self._first(response.data) or payload
        except Exception as exc:
            raise DatabaseError("تعذر إضافة المرض.") from exc

    def update_disease(self, disease_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """تعديل مرض موجود."""
        try:
            response = self.client.table("diseases").update(payload).eq("id", disease_id).execute()
            return self._first(response.data)
        except Exception as exc:
            raise DatabaseError("تعذر تعديل المرض.") from exc

    def delete_disease(self, disease_id: str) -> None:
        """حذف مرض؛ تحذف قاعدة البيانات أسئلته عبر ON DELETE CASCADE."""
        try:
            self.client.table("diseases").delete().eq("id", disease_id).execute()
        except Exception as exc:
            raise DatabaseError("تعذر حذف المرض.") from exc

    def list_questions(self) -> list[dict[str, Any]]:
        """إرجاع جميع الأسئلة مع اسم المرض المرتبط إن أمكن."""
        try:
            response = self.client.table("questions").select("*, diseases(name_ar, name_en)").order("created_at", desc=True).execute()
            return response.data or []
        except Exception as exc:
            raise DatabaseError("تعذر تحميل قائمة الأسئلة.") from exc

    def get_question(self, question_id: str) -> dict[str, Any] | None:
        """إرجاع سؤال واحد."""
        try:
            response = self.client.table("questions").select("*").eq("id", question_id).limit(1).execute()
            return self._first(response.data)
        except Exception as exc:
            raise DatabaseError("تعذر تحميل السؤال.") from exc

    def random_question(self) -> dict[str, Any] | None:
        """اختيار سؤال عشوائي من المجموعة المتاحة."""
        try:
            response = self.client.table("questions").select("*").execute()
            questions = response.data or []
            return secrets.choice(questions) if questions else None
        except Exception as exc:
            raise DatabaseError("تعذر تحميل سؤال عشوائي.") from exc

    def create_question(self, payload: dict[str, Any]) -> dict[str, Any]:
        """إنشاء سؤال جديد."""
        try:
            response = self.client.table("questions").insert(payload).execute()
            return self._first(response.data) or payload
        except Exception as exc:
            raise DatabaseError("تعذر إضافة السؤال.") from exc

    def update_question(self, question_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """تعديل سؤال موجود."""
        try:
            response = self.client.table("questions").update(payload).eq("id", question_id).execute()
            return self._first(response.data)
        except Exception as exc:
            raise DatabaseError("تعذر تعديل السؤال.") from exc

    def delete_question(self, question_id: str) -> None:
        """حذف سؤال واحد."""
        try:
            self.client.table("questions").delete().eq("id", question_id).execute()
        except Exception as exc:
            raise DatabaseError("تعذر حذف السؤال.") from exc

    def upsert_subscriber(self, user_id: int) -> None:
        """تسجيل معرّف تيليغرام الضروري للتوصيل دون حفظ اسم المستخدم."""
        payload = {"user_id": user_id, "username": None, "is_active": True}
        try:
            self.client.table("subscribers").upsert(payload, on_conflict="user_id").execute()
        except Exception as exc:
            raise DatabaseError("تعذر تحديث الاشتراك.") from exc

    def deactivate_subscriber(self, user_id: int) -> None:
        """تعطيل مشترك توقف حسابه عن استقبال الرسائل."""
        try:
            self.client.table("subscribers").update({"is_active": False}).eq("user_id", user_id).execute()
        except Exception as exc:
            raise DatabaseError("تعذر تعطيل الاشتراك.") from exc

    def list_active_subscribers(self) -> list[dict[str, Any]]:
        """إرجاع معرفات المشتركين النشطين اللازمة للنشر فقط."""
        try:
            response = self.client.table("subscribers").select("user_id").eq("is_active", True).execute()
            return response.data or []
        except Exception as exc:
            raise DatabaseError("تعذر تحميل المشتركين.") from exc

    def get_stats(self) -> dict[str, int]:
        """حساب أعداد الأمراض والأسئلة والمشتركين النشطين."""
        try:
            diseases = self.client.table("diseases").select("id", count="exact").execute()
            questions = self.client.table("questions").select("id", count="exact").execute()
            subscribers = self.client.table("subscribers").select("id", count="exact").eq("is_active", True).execute()
            return {
                "diseases": diseases.count if diseases.count is not None else len(diseases.data or []),
                "questions": questions.count if questions.count is not None else len(questions.data or []),
                "subscribers": subscribers.count if subscribers.count is not None else len(subscribers.data or []),
            }
        except Exception as exc:
            raise DatabaseError("تعذر تحميل الإحصاءات.") from exc

    def claim_daily_publication(self, publication_date: date, disease_id: str) -> bool:
        """حجز نشر اليوم مرة واحدة لمنع التكرار بين المجدول الداخلي والخارجي."""
        try:
            self.client.table("daily_publications").insert(
                {"publication_date": publication_date.isoformat(), "disease_id": disease_id}
            ).execute()
            return True
        except Exception as exc:
            code = getattr(exc, "code", "")
            message = str(exc).lower()
            if code == "23505" or "duplicate key" in message or "unique" in message:
                return False
            raise DatabaseError("تعذر حجز النشر اليومي.") from exc

    def record_usage_event(
        self,
        metric_date: date,
        event_type: str,
        topic_id: str | None = None,
    ) -> None:
        """زيادة عداد يومي مجمع؛ لا تستقبل الدالة أي معرف مستخدم أو نص حر."""
        normalized_event, normalized_topic = normalize_usage_event(event_type, topic_id)
        try:
            self.client.rpc(
                "increment_usage_metric",
                {
                    "p_metric_date": metric_date.isoformat(),
                    "p_event_type": normalized_event,
                    "p_topic_id": normalized_topic,
                },
            ).execute()
        except Exception as exc:
            raise DatabaseError("تعذر تحديث عداد الاستخدام.") from exc

    def get_usage_rows(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        """قراءة العدادات المجمعة داخل فترة محددة فقط."""
        if end_date < start_date:
            raise ValueError("نهاية الفترة تسبق بدايتها.")
        try:
            response = (
                self.client.table("usage_daily_metrics")
                .select("metric_date,event_type,topic_id,event_count")
                .gte("metric_date", start_date.isoformat())
                .lte("metric_date", end_date.isoformat())
                .order("metric_date")
                .execute()
            )
            return response.data or []
        except Exception as exc:
            raise DatabaseError("تعذر تحميل عدادات الاستخدام.") from exc

    def get_usage_report(self, start_date: date, end_date: date) -> dict[str, Any]:
        """تجميع تقرير فترة من عدادات مجهولة الهوية."""
        rows = self.get_usage_rows(start_date, end_date)
        return aggregate_usage_rows(rows, start_date, end_date)

    def get_usage_dashboard(self, reference_date: date) -> dict[str, Any]:
        """إرجاع مؤشرات 7 و30 يومًا ومقارنة الأسبوع السابق للوحة الإدارة."""
        start_30 = reference_date - timedelta(days=29)
        start_14 = reference_date - timedelta(days=13)
        start_7 = reference_date - timedelta(days=6)
        previous_end = start_7 - timedelta(days=1)
        rows = self.get_usage_rows(start_30, reference_date)
        return {
            "last_7": aggregate_usage_rows(rows, start_7, reference_date),
            "previous_7": aggregate_usage_rows(rows, start_14, previous_end),
            "last_30": aggregate_usage_rows(rows, start_30, reference_date),
        }

    def get_completed_week_reports(self, reference_date: date) -> tuple[dict[str, Any], dict[str, Any]]:
        """إرجاع الأسبوع المكتمل السابق والفترة السابقة المساوية له."""
        current_start, current_end = completed_week(reference_date)
        previous_start, previous_end = previous_period(current_start, current_end)
        rows = self.get_usage_rows(previous_start, current_end)
        return (
            aggregate_usage_rows(rows, current_start, current_end),
            aggregate_usage_rows(rows, previous_start, previous_end),
        )

    def create_report_link_token(self, token_hash: str, expires_at: datetime) -> None:
        """حفظ بصمة رمز ربط مؤقت؛ لا يُحفظ الرمز الخام."""
        if len(token_hash) != 64 or any(character not in "0123456789abcdef" for character in token_hash):
            raise ValueError("بصمة رمز الربط غير صالحة.")
        payload = {
            "id": 1,
            "link_token_hash": token_hash,
            "link_token_expires_at": expires_at.astimezone(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.client.table("report_delivery_config").upsert(payload, on_conflict="id").execute()
        except Exception as exc:
            raise DatabaseError("تعذر إنشاء رمز ربط التقرير.") from exc

    def consume_report_link_token(self, token_hash: str, chat_id: int) -> bool:
        """استهلاك رمز ربط مرة واحدة وتعيين مستلم التقرير إداريًا."""
        if len(token_hash) != 64 or any(character not in "0123456789abcdef" for character in token_hash):
            return False
        try:
            response = self.client.rpc(
                "consume_report_link_token",
                {"p_token_hash": token_hash, "p_chat_id": int(chat_id)},
            ).execute()
            return response.data is True or response.data == [True]
        except Exception as exc:
            raise DatabaseError("تعذر ربط مستلم التقرير.") from exc

    def get_report_delivery_config(self) -> dict[str, Any] | None:
        """قراءة إعداد التوصيل دون إعادة بصمة الرمز المؤقت."""
        try:
            response = (
                self.client.table("report_delivery_config")
                .select("telegram_chat_id,linked_at")
                .eq("id", 1)
                .limit(1)
                .execute()
            )
            return self._first(response.data)
        except Exception as exc:
            raise DatabaseError("تعذر تحميل إعداد توصيل التقرير.") from exc

    def claim_weekly_report(self, week_start: date) -> bool:
        """حجز تقرير أسبوعي مرة واحدة قبل إرساله."""
        try:
            self.client.table("weekly_report_deliveries").insert(
                {"week_start": week_start.isoformat(), "status": "pending"}
            ).execute()
            return True
        except Exception as exc:
            code = getattr(exc, "code", "")
            message = str(exc).lower()
            if code == "23505" or "duplicate key" in message or "unique" in message:
                return False
            raise DatabaseError("تعذر حجز التقرير الأسبوعي.") from exc

    def complete_weekly_report(self, week_start: date, total_interactions: int) -> None:
        """تسجيل نجاح إرسال التقرير الأسبوعي."""
        try:
            self.client.table("weekly_report_deliveries").update(
                {
                    "status": "sent",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "total_interactions": max(0, int(total_interactions)),
                }
            ).eq("week_start", week_start.isoformat()).execute()
        except Exception as exc:
            raise DatabaseError("تعذر إكمال سجل التقرير الأسبوعي.") from exc

    def release_weekly_report(self, week_start: date) -> None:
        """تحرير الحجز بعد فشل الإرسال للسماح بمحاولة لاحقة."""
        try:
            self.client.table("weekly_report_deliveries").delete().eq(
                "week_start", week_start.isoformat()
            ).eq("status", "pending").execute()
        except Exception as exc:
            raise DatabaseError("تعذر تحرير حجز التقرير الأسبوعي.") from exc

    def prune_usage_data(self, reference_date: date) -> None:
        """حذف العدادات الأقدم من 400 يوم وسجلات التقارير الأقدم من 420 يومًا."""
        try:
            self.client.table("usage_daily_metrics").delete().lt(
                "metric_date", (reference_date - timedelta(days=400)).isoformat()
            ).execute()
            self.client.table("weekly_report_deliveries").delete().lt(
                "week_start", (reference_date - timedelta(days=420)).isoformat()
            ).execute()
        except Exception as exc:
            raise DatabaseError("تعذر تطبيق سياسة احتفاظ التحليلات.") from exc
