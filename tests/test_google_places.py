from src.sources.google_places import GooglePlacesSource


class FakeResponse:
    def json(self):
        return {
            "places": [
                {
                    "displayName": {"text": "Example Machinery"},
                    "internationalPhoneNumber": "+49 30 123456",
                    "googleMapsUri": "https://maps.google.com/example",
                },
                {"displayName": {"text": "No Phone"}},
            ]
        }


def test_google_places_maps_official_response(monkeypatch):
    source = GooglePlacesSource(api_key="test-key")
    monkeypatch.setattr(source, "_request", lambda _client, _payload: FakeResponse())
    records = list(source.collect("machinery", "DE"))
    assert len(records) == 1
    assert records[0].company_name == "Example Machinery"
    assert records[0].phone == "+49 30 123456"


def test_google_places_accepts_multiple_queries_and_deduplicates_places(monkeypatch):
    source = GooglePlacesSource(api_key="test-key")

    class MultiQueryResponse:
        def __init__(self, query):
            self.query = query

        def json(self):
            if self.query.startswith("machinery"):
                return {
                    "places": [
                        {
                            "id": "place-1",
                            "displayName": {"text": "Example Machinery"},
                            "internationalPhoneNumber": "+49 30 123456",
                        }
                    ]
                }
            return {
                "places": [
                    {
                        "id": "place-1",
                        "displayName": {"text": "Example Machinery"},
                        "internationalPhoneNumber": "+49 30 123456",
                    },
                    {
                        "id": "place-2",
                        "displayName": {"text": "Example Supplier"},
                        "internationalPhoneNumber": "+49 30 654321",
                    },
                ]
            }

    monkeypatch.setattr(
        source,
        "_request",
        lambda _client, payload: MultiQueryResponse(payload["textQuery"]),
    )
    records = list(source.collect("machinery\nsupplier", "DE"))

    assert [record.company_name for record in records] == [
        "Example Machinery",
        "Example Supplier",
    ]
    assert [record.keyword for record in records] == ["machinery", "supplier"]
