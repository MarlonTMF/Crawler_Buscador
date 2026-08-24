from crawler.core import subdomain_finder


class DummyResp:
    def __init__(self):
        self.status_code = 200

    def json(self):
        # crt.sh sometimes returns name_value with newlines
        return [{"name_value": "a.finrural.org.bo\nfinrural.org.bo"}]
    
    def raise_for_status(self):
        return None


class MockRequests:
    @staticmethod
    def get(*args, **kwargs):
        return DummyResp()


def test_find_subdomains(monkeypatch):
    monkeypatch.setattr(subdomain_finder, "requests", MockRequests)
    subs = subdomain_finder.find_subdomains("finrural.org.bo")
    assert "a.finrural.org.bo" in subs
    assert "finrural.org.bo" in subs
