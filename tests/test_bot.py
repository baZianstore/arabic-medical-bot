"""اختبارات وحدات منطق البوت باستخدام بيانات تعليمية اصطناعية وعامة."""

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace

from analytics import aggregate_usage_rows
from bilingual_content import BILINGUAL_TOPICS
from bot import (
    format_bilingual_question,
    format_bilingual_topic,
    format_disease,
    format_question,
    format_sources,
    link_report_command,
    main_menu_keyboard,
    send_weekly_usage_report,
    topic_actions_keyboard,
    topic_selection_keyboard,
)


def test_format_disease_escapes_html():
    disease = {
        "name_ar": "مرض <تجريبي>",
        "name_en": "Synthetic",
        "definition": "تعريف",
        "symptoms": "أعراض",
        "treatment": "علاج",
    }
    message = format_disease(disease)
    assert "&lt;تجريبي&gt;" in message
    assert "ليس تشخيصًا" in message


def test_format_question_has_four_callbacks():
    question = {
        "id": "00000000-0000-0000-0000-000000000001",
        "question": "سؤال اصطناعي؟",
        "option_a": "أ",
        "option_b": "ب",
        "option_c": "ج",
        "option_d": "د",
    }
    text, keyboard = format_question(question)
    assert "سؤال اصطناعي" in text
    assert len(keyboard.inline_keyboard) == 4
    assert keyboard.inline_keyboard[2][0].callback_data.endswith("|C")


def test_disease_message_stays_under_telegram_limit_with_html_characters():
    disease = {
        "name_ar": "<" * 1000,
        "name_en": "&" * 1000,
        "definition": '"' * 5000,
        "symptoms": ">" * 5000,
        "treatment": "&" * 7000,
    }
    message = format_disease(disease)
    assert len(message) <= 3900
    assert "<script>" not in message


def test_bilingual_topic_has_english_arabic_and_safe_message_lengths():
    topic = BILINGUAL_TOPICS["asthma"]
    summary, details = format_bilingual_topic(topic)
    assert "Asthma" in summary
    assert "الربو" in summary
    assert "Diagnosis" in details
    assert "التفاصيل" in details
    assert len(summary) <= 3900
    assert len(details) <= 3900


def test_bilingual_question_has_four_short_callbacks():
    topic = BILINGUAL_TOPICS["diabetes"]
    text, keyboard = format_bilingual_question(topic)
    assert "English medical question" in text
    assert len(keyboard.inline_keyboard) == 4
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callbacks == [
        "biquiz|diabetes|A",
        "biquiz|diabetes|B",
        "biquiz|diabetes|C",
        "biquiz|diabetes|D",
    ]
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_menu_and_topic_keyboards_are_complete_and_within_callback_limit():
    keyboards = [main_menu_keyboard(), topic_selection_keyboard(), topic_actions_keyboard(BILINGUAL_TOPICS["asthma"])]
    callbacks = [
        button.callback_data
        for keyboard in keyboards
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "menu|today" in callbacks
    assert "topic|asthma" in callbacks
    assert "detail|asthma" in callbacks
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_sources_are_html_links_and_stay_under_limit():
    message = format_sources(BILINGUAL_TOPICS["hypothyroidism"])
    assert "https://" in message
    assert "Official sources" in message
    assert len(message) <= 3900


class FakeMessage:
    def __init__(self): self.replies = []
    async def reply_text(self, text, **_kwargs): self.replies.append(text)


class FakeLinkDatabase:
    def __init__(self): self.calls = []
    def consume_report_link_token(self, token_hash, chat_id):
        self.calls.append((token_hash, chat_id))
        return True


def test_report_link_requires_private_chat_and_consumes_hash_only():
    database = FakeLinkDatabase()
    message = FakeMessage()
    context = SimpleNamespace(
        args=["A" * 32],
        application=SimpleNamespace(bot_data={"database": database}),
    )
    group_update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="group", id=-1001),
    )
    asyncio.run(link_report_command(group_update, context))
    assert database.calls == []
    assert "محادثة خاصة" in message.replies[-1]

    private_update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="private", id=123456),
    )
    asyncio.run(link_report_command(private_update, context))
    assert database.calls[0][1] == 123456
    assert database.calls[0][0] != "A" * 32
    assert len(database.calls[0][0]) == 64
    assert "تم ربط" in message.replies[-1]


class FakeReportDatabase:
    def __init__(self):
        self.claimed = []
        self.completed = []
        self.pruned = []

    def get_report_delivery_config(self):
        return {"telegram_chat_id": 123456}

    def get_completed_week_reports(self, _reference_date):
        current = aggregate_usage_rows(
            [
                {
                    "metric_date": "2026-09-19",
                    "event_type": "topic_view",
                    "topic_id": "asthma",
                    "event_count": 3,
                }
            ],
            date(2026, 9, 13),
            date(2026, 9, 19),
        )
        previous = aggregate_usage_rows([], date(2026, 9, 6), date(2026, 9, 12))
        return current, previous

    def claim_weekly_report(self, week_start):
        self.claimed.append(week_start)
        return len(self.claimed) == 1

    def complete_weekly_report(self, week_start, total_interactions):
        self.completed.append((week_start, total_interactions))

    def prune_usage_data(self, reference_date): self.pruned.append(reference_date)


class FakeReportBot:
    def __init__(self): self.messages = []
    async def send_message(self, **kwargs): self.messages.append(kwargs)


def test_weekly_report_sends_once_and_records_completion():
    database = FakeReportDatabase()
    bot = FakeReportBot()
    now = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    first = asyncio.run(send_weekly_usage_report(bot, database, now=now))
    second = asyncio.run(send_weekly_usage_report(bot, database, now=now))
    assert first["sent"] is True
    assert second == {"sent": False, "reason": "already_sent"}
    assert len(bot.messages) == 1
    assert bot.messages[0]["chat_id"] == 123456
    assert "لا تتضمن معرفات" in bot.messages[0]["text"]
    assert database.completed == [(date(2026, 9, 13), 3)]
    assert database.pruned == [date(2026, 9, 20)]
