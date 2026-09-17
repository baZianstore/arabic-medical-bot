"""اختبارات بيانات البطاقات الطبية الثنائية باستخدام محتوى عام فقط."""

from pathlib import Path

from bilingual_content import (
    BILINGUAL_TOPICS,
    all_bilingual_topics,
    get_bilingual_topic,
)


def test_all_five_reviewed_topics_are_available_in_stable_order():
    assert [topic["id"] for topic in all_bilingual_topics()] == [
        "diabetes",
        "asthma",
        "hypertension",
        "gastritis",
        "hypothyroidism",
    ]


def test_lookup_accepts_arabic_english_and_partial_terms():
    assert get_bilingual_topic("Asthma")["name_ar"] == "الربو"
    assert get_bilingual_topic("السكري")["id"] == "diabetes"
    assert get_bilingual_topic("thyroid")["id"] == "hypothyroidism"
    assert get_bilingual_topic("") is None


def test_each_topic_has_safe_question_references_and_local_image():
    root = Path(__file__).resolve().parents[1]
    for topic in BILINGUAL_TOPICS.values():
        assert topic["overview_en"]
        assert topic["explanation_ar"]
        assert len(topic["mcq"]["options_en"]) == 4
        assert topic["mcq"]["correct_index"] in range(4)
        assert len(topic["references"]) >= 2
        assert all(reference["url"].startswith("https://") for reference in topic["references"])
        image = root / topic["image_path"]
        assert image.is_file()
        assert image.read_bytes().startswith(b"\xff\xd8\xff")


def test_content_has_no_patient_record_fields_or_personalization_promises():
    forbidden_keys = {"patient_id", "patient_name", "diagnose_user", "prescribe_user"}
    for topic in BILINGUAL_TOPICS.values():
        assert not forbidden_keys.intersection(topic)
