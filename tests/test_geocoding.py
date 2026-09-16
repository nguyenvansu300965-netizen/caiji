from src.sources.geocoding import resolve_location


def test_resolves_hong_kong_chinese_alias(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "boundingbox": ["22.1", "22.6", "113.8", "114.5"],
                    "address": {"country_code": "cn"},
                }
            ]

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url, params):
            captured.update(params)
            return Response()

    monkeypatch.setattr("src.sources.geocoding.httpx.Client", lambda **_kwargs: Client())
    result = resolve_location("香港")
    assert captured["q"] == "Hong Kong"
    assert result == (113.8, 22.1, 114.5, 22.6, "CN")
