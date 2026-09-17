"""تجميع مؤشرات استخدام البوت من عدادات يومية مجهولة الهوية."""

from __future__ import annotations

import html
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from bilingual_content import BILINGUAL_TOPICS

ALLOWED_USAGE_EVENTS = frozenset(
    {
        "start",
        "menu_open",
        "help_view",
        "today_view",
        "topic_view",
        "topic_detail_view",
        "sources_view",
        "quiz_en_started",
        "quiz_en_answered",
        "quiz_en_correct",
        "quiz_ar_started",
        "quiz_ar_answered",
        "quiz_ar_correct",
        "search_success",
        "search_empty",
        "systems_view",
        "stats_view",
    }
)
ALLOWED_TOPIC_IDS = frozenset(BILINGUAL_TOPICS)
TOPIC_LABELS = {
    topic_id: {
        "name_en": str(topic["name_en"]),
        "name_ar": str(topic["name_ar"]),
    }
    for topic_id, topic in BILINGUAL_TOPICS.items()
}


def normalize_usage_event(event_type: str, topic_id: str | None = None) -> tuple[str, str]:
    """التحقق من مفاتيح القياس دون قبول أي نص حر من المستخدم."""
    normalized_event = str(event_type or "").strip()
    normalized_topic = str(topic_id or "").strip()
    if normalized_event not in ALLOWED_USAGE_EVENTS:
        raise ValueError("نوع حدث غير مسموح.")
    if normalized_topic and normalized_topic not in ALLOWED_TOPIC_IDS:
        raise ValueError("معرّف موضوع غير مسموح.")
    return normalized_event, normalized_topic


def completed_week(reference_date: date) -> tuple[date, date]:
    """إرجاع الأيام السبعة المكتملة السابقة حتى أمس."""
    end_date = reference_date - timedelta(days=1)
    return end_date - timedelta(days=6), end_date


def previous_period(start_date: date, end_date: date) -> tuple[date, date]:
    """إرجاع فترة سابقة مساوية في الطول للمقارنة."""
    days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    return previous_end - timedelta(days=days - 1), previous_end


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def aggregate_usage_rows(
    rows: Iterable[dict[str, Any]],
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """تحويل صفوف العدادات إلى تقرير دون أي بيانات فردية."""
    if end_date < start_date:
        raise ValueError("نهاية الفترة تسبق بدايتها.")

    event_counts = {event: 0 for event in sorted(ALLOWED_USAGE_EVENTS)}
    daily_counts: dict[str, int] = {}
    cursor = start_date
    while cursor <= end_date:
        daily_counts[cursor.isoformat()] = 0
        cursor += timedelta(days=1)

    topic_views: dict[str, int] = {topic_id: 0 for topic_id in ALLOWED_TOPIC_IDS}
    for row in rows:
        event_type = str(row.get("event_type") or "")
        topic_id = str(row.get("topic_id") or "")
        metric_date = str(row.get("metric_date") or "")
        count = _safe_count(row.get("event_count"))
        if event_type not in ALLOWED_USAGE_EVENTS or metric_date not in daily_counts:
            continue
        if topic_id and topic_id not in ALLOWED_TOPIC_IDS:
            continue
        event_counts[event_type] += count
        daily_counts[metric_date] += count
        if topic_id and event_type in {"today_view", "topic_view"}:
            topic_views[topic_id] += count

    quiz_answered = event_counts["quiz_en_answered"]
    quiz_correct = min(event_counts["quiz_en_correct"], quiz_answered)
    searches = event_counts["search_success"] + event_counts["search_empty"]
    topic_view_total = event_counts["today_view"] + event_counts["topic_view"]
    top_topics = [
        {
            "topic_id": topic_id,
            "name_en": TOPIC_LABELS[topic_id]["name_en"],
            "name_ar": TOPIC_LABELS[topic_id]["name_ar"],
            "views": views,
        }
        for topic_id, views in topic_views.items()
        if views > 0
    ]
    top_topics.sort(key=lambda item: (-item["views"], item["name_en"]))

    total_interactions = sum(event_counts.values())
    return {
        "start_date": start_date,
        "end_date": end_date,
        "days": (end_date - start_date).days + 1,
        "total_interactions": total_interactions,
        "topic_views": topic_view_total,
        "detail_views": event_counts["topic_detail_view"],
        "sources_views": event_counts["sources_view"],
        "quiz_started": event_counts["quiz_en_started"],
        "quiz_answered": quiz_answered,
        "quiz_correct": quiz_correct,
        "quiz_accuracy": round((quiz_correct / quiz_answered) * 100, 1) if quiz_answered else None,
        "searches": searches,
        "search_success_rate": (
            round((event_counts["search_success"] / searches) * 100, 1) if searches else None
        ),
        "top_topics": top_topics[:5],
        "daily": [
            {"date": metric_date, "count": count}
            for metric_date, count in sorted(daily_counts.items())
        ],
        "events": event_counts,
    }


def growth_percentage(current: int, previous: int) -> float | None:
    """حساب التغير النسبي؛ None يعني عدم توفر أساس للمقارنة."""
    if previous <= 0:
        return None
    return round(((current - previous) / previous) * 100, 1)


def format_weekly_usage_report(
    current: dict[str, Any],
    previous: dict[str, Any],
    *,
    test: bool = False,
) -> str:
    """صياغة رسالة Telegram أسبوعية موجزة وآمنة من HTML."""
    title = "تقرير اختباري" if test else "التقرير الأسبوعي"
    growth = growth_percentage(current["total_interactions"], previous["total_interactions"])
    if growth is None:
        trend = "لا توجد فترة سابقة كافية للمقارنة."
    elif growth > 0:
        trend = f"نمو التفاعل: +{growth}% مقارنة بالفترة السابقة."
    elif growth < 0:
        trend = f"تغير التفاعل: {growth}% مقارنة بالفترة السابقة."
    else:
        trend = "التفاعل ثابت مقارنة بالفترة السابقة."

    accuracy = (
        f"{current['quiz_accuracy']}%"
        if current["quiz_accuracy"] is not None
        else "لا توجد إجابات بعد"
    )
    search_rate = (
        f"{current['search_success_rate']}%"
        if current["search_success_rate"] is not None
        else "لا توجد عمليات بحث بعد"
    )
    if current["top_topics"]:
        top_lines = "\n".join(
            f"{index}. {html.escape(item['name_en'])} | {html.escape(item['name_ar'])} — {item['views']}"
            for index, item in enumerate(current["top_topics"][:3], start=1)
        )
    else:
        top_lines = "لا توجد مشاهدات موضوعات في هذه الفترة."

    message = (
        f"<b>{title} لتفاعل @Intmed_edu_bot</b>\n"
        f"{current['start_date'].isoformat()} — {current['end_date'].isoformat()}\n\n"
        f"<b>ملخص التفاعل</b>\n"
        f"• إجمالي التفاعلات: {current['total_interactions']}\n"
        f"• مشاهدات الموضوعات: {current['topic_views']}\n"
        f"• فتح التفاصيل: {current['detail_views']}\n"
        f"• فتح المراجع: {current['sources_views']}\n"
        f"• اختبارات إنجليزية بدأت: {current['quiz_started']}\n"
        f"• إجابات الاختبارات: {current['quiz_answered']}\n"
        f"• دقة الإجابات: {accuracy}\n"
        f"• نجاح البحث: {search_rate}\n\n"
        f"<b>الاتجاه</b>\n{trend}\n\n"
        f"<b>أكثر الموضوعات مشاهدة</b>\n{top_lines}\n\n"
        "<i>البيانات عدادات يومية مجمعة؛ لا تتضمن معرفات مستخدمين أو نصوص رسائل.</i>"
    )
    return message[:3900]
