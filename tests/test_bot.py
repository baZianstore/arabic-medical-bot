"""اختبارات وحدات منطق البوت باستخدام بيانات اصطناعية."""

from bot import format_disease, format_question


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
