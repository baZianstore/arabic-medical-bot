"""اختبارات طبقة البيانات بعميل وهمي، بلا اتصال خارجي."""

from types import SimpleNamespace

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
