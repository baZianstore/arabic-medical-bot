"""طبقة الوصول إلى Supabase؛ لا تتعامل بقية الوحدات مع العميل مباشرة."""

from __future__ import annotations

import secrets
from datetime import date, datetime, timezone
from typing import Any

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
