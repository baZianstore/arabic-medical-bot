"""اختبارات طبقة البيانات بعميل وهمي، بلا اتصال خارجي."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from database import Database


class Query:
    def __init__(self, data):
        self.data = data

    def select(self, *_args, **_kwargs): return self
    def order(self, *_args, **_kwargs): return self
    def eq(self, key, value):
        self.data = [row for row in self.data if row.get(key) == value]
        return self
    def limit(self, number):
        self.data = self.data[:number]
        return self
    def execute(self): return SimpleNamespace(data=self.data, count=len(self.data))


class FakeClient:
    def __init__(self, rows): self.rows = rows
    def table(self, _name): return Query(list(self.rows))


def test_search_diseases_handles_arabic_and_english():
    rows = [
        {"id": "1", "name_ar": "مرض اصطناعي", "name_en": "Synthetic Disease", "week_number": 1},
        {"id": "2", "name_ar": "حالة تجريبية", "name_en": "Test Condition", "week_number": 2},
    ]
    database = Database(client=FakeClient(rows))
    assert database.search_diseases("اصطناعي")[0]["id"] == "1"
    assert database.search_diseases("test")[0]["id"] == "2"
    assert database.search_diseases("") == []


def test_public_topics_are_limited_and_allowlisted():
    rows = [
        {
            "id": "1",
            "name_ar": "مرض اصطناعي",
            "name_en": "Synthetic Disease",
            "system": "جهاز اصطناعي",
            "importance": 2,
            "week_number": 1,
            "treatment": "حقل غير عام",
            "definition": "حقل غير عام",
        }
    ]
    database = Database(client=FakeClient(rows))
    topics = database.list_public_topics(limit=500)
    assert topics == [
        {
            "id": "1",
            "name_ar": "مرض اصطناعي",
            "name_en": "Synthetic Disease",
            "system": "جهاز اصطناعي",
            "importance": 2,
            "week_number": 1,
        }
    ]


class Operation:
    def __init__(self, data=None):
        self.data = data

    def execute(self):
        return SimpleNamespace(data=self.data, count=None)


class AnalyticsClient:
    def __init__(self):
        self.rpc_calls = []
        self.upserts = []
        self.rpc_result = None

    def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        return Operation(self.rpc_result)

    def table(self, name):
        client = self

        class TableOperation(Operation):
            def upsert(self, payload, on_conflict=None):
                client.upserts.append((name, payload, on_conflict))
                return self

        return TableOperation([])


def test_record_usage_event_sends_only_aggregate_allowlisted_fields():
    client = AnalyticsClient()
    database = Database(client=client)
    database.record_usage_event(date(2026, 9, 17), "topic_view", "asthma")
    assert client.rpc_calls == [
        (
            "increment_usage_metric",
            {
                "p_metric_date": "2026-09-17",
                "p_event_type": "topic_view",
                "p_topic_id": "asthma",
            },
        )
    ]
    assert "user_id" not in str(client.rpc_calls)
    with pytest.raises(ValueError):
        database.record_usage_event(date(2026, 9, 17), "free_text", "asthma")
    assert len(client.rpc_calls) == 1


def test_report_link_stores_hash_only_and_consumes_atomically():
    client = AnalyticsClient()
    database = Database(client=client)
    token_hash = "a" * 64
    expires_at = datetime(2026, 9, 17, 10, tzinfo=timezone.utc)
    database.create_report_link_token(token_hash, expires_at)
    assert client.upserts[0][0] == "report_delivery_config"
    assert client.upserts[0][1]["link_token_hash"] == token_hash
    assert "token" not in client.upserts[0][1]

    client.rpc_result = True
    assert database.consume_report_link_token(token_hash, 123456789) is True
    assert client.rpc_calls[-1] == (
        "consume_report_link_token",
        {"p_token_hash": token_hash, "p_chat_id": 123456789},
    )


def test_invalid_report_token_hash_is_rejected_before_database_call():
    client = AnalyticsClient()
    database = Database(client=client)
    with pytest.raises(ValueError):
        database.create_report_link_token("raw-secret-token", datetime.now(timezone.utc))
    assert database.consume_report_link_token("raw-secret-token", 123) is False
    assert client.rpc_calls == []
