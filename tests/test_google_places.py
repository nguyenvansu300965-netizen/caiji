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
