from types import SimpleNamespace
from crawler.core import wayback_engine


class DummyResp:
    def __init__(self):
        self.status_code = 200

    def json(self):
        # header row + one result matching a pdf
        return [["original", "statuscode", "mimetype"], ["http://finrural.org.bo/report.pdf", "200", "application/pdf"]]
    
    def raise_for_status(self):
        return None


class MockRequests:
    @staticmethod
    def get(*args, **kwargs):
        return DummyResp()


def test_query_wayback_urls(monkeypatch):
    monkeypatch.setattr(wayback_engine, "requests", MockRequests)
    urls = wayback_engine.query_wayback_urls("finrural.org.bo", file_types=["pdf"], limit=10)
    assert "http://finrural.org.bo/report.pdf" in urls
