"""اختبارات وحدات منطق البوت باستخدام بيانات تعليمية اصطناعية وعامة."""

from bilingual_content import BILINGUAL_TOPICS
from bot import (
    format_bilingual_question,
    format_bilingual_topic,
    format_disease,
    format_question,
    format_sources,
    main_menu_keyboard,
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
