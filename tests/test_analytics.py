"""اختبارات التحليلات المجمعة باستخدام عدادات اصطناعية فقط."""

from datetime import date

import pytest

from analytics import (
    aggregate_usage_rows,
    completed_week,
    format_weekly_usage_report,
    growth_percentage,
    normalize_usage_event,
    previous_period,
)


def test_usage_event_allowlist_rejects_free_text_and_unknown_topic():
    assert normalize_usage_event("topic_view", "asthma") == ("topic_view", "asthma")
    assert normalize_usage_event("start") == ("start", "")
    with pytest.raises(ValueError):
        normalize_usage_event("patient_symptoms", "asthma")
    with pytest.raises(ValueError):
        normalize_usage_event("topic_view", "private-case-42")


def test_aggregate_usage_rows_calculates_kpis_without_identifiers():
    rows = [
        {"metric_date": "2026-09-14", "event_type": "topic_view", "topic_id": "asthma", "event_count": 4},
        {"metric_date": "2026-09-15", "event_type": "today_view", "topic_id": "diabetes", "event_count": 2},
        {"metric_date": "2026-09-15", "event_type": "quiz_en_started", "topic_id": "asthma", "event_count": 3},
        {"metric_date": "2026-09-15", "event_type": "quiz_en_answered", "topic_id": "asthma", "event_count": 3},
        {"metric_date": "2026-09-15", "event_type": "quiz_en_correct", "topic_id": "asthma", "event_count": 2},
        {"metric_date": "2026-09-16", "event_type": "search_success", "topic_id": "", "event_count": 3},
        {"metric_date": "2026-09-16", "event_type": "search_empty", "topic_id": "", "event_count": 1},
        {"metric_date": "2026-09-16", "event_type": "unknown", "topic_id": "", "event_count": 99},
    ]
    report = aggregate_usage_rows(rows, date(2026, 9, 14), date(2026, 9, 16))
    assert report["topic_views"] == 6
    assert report["quiz_accuracy"] == 66.7
    assert report["search_success_rate"] == 75.0
    assert report["top_topics"][0]["topic_id"] == "asthma"
    assert report["top_topics"][0]["views"] == 4
    assert len(report["daily"]) == 3
    assert "user_id" not in report


def test_completed_week_and_growth_are_deterministic():
    current_start, current_end = completed_week(date(2026, 9, 20))
    assert (current_start, current_end) == (date(2026, 9, 13), date(2026, 9, 19))
    assert previous_period(current_start, current_end) == (date(2026, 9, 6), date(2026, 9, 12))
    assert growth_percentage(15, 10) == 50.0
    assert growth_percentage(0, 0) is None


def test_weekly_message_is_arabic_bilingual_and_under_telegram_limit():
    current = aggregate_usage_rows(
        [
            {"metric_date": "2026-09-19", "event_type": "topic_view", "topic_id": "asthma", "event_count": 8},
            {"metric_date": "2026-09-19", "event_type": "quiz_en_answered", "topic_id": "asthma", "event_count": 4},
            {"metric_date": "2026-09-19", "event_type": "quiz_en_correct", "topic_id": "asthma", "event_count": 3},
        ],
        date(2026, 9, 13),
        date(2026, 9, 19),
    )
    previous = aggregate_usage_rows([], date(2026, 9, 6), date(2026, 9, 12))
    message = format_weekly_usage_report(current, previous)
    assert "@Intmed_edu_bot" in message
    assert "Asthma | الربو" in message
    assert "75.0%" in message
    assert "لا تتضمن معرفات" in message
    assert len(message) <= 3900
