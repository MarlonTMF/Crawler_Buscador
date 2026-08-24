from crawler.core import async_fetcher


class MockResponse:
    def __init__(self):
        self.status_code = 200
        self.headers = {"Content-Length": "123", "ETag": '"abc"'}


class MockClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def head(self, url, allow_redirects=True):
        return MockResponse()


def test_fetch_head_sync(monkeypatch):
    # Replace httpx.AsyncClient with a dummy that returns our MockClient
    fake_httpx = type("h", (), {"AsyncClient": lambda *a, **k: MockClient()})
    monkeypatch.setattr(async_fetcher, "httpx", fake_httpx)

    af = async_fetcher.AsyncFetcher()
    allowed, status, headers = af.fetch_head_sync("http://example.com")
    assert allowed is True
    assert status == 200
    # headers normalized to lower-case keys in implementation
    assert headers.get("content-length") == "123"
