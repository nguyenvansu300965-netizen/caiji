from src.sources.osm_overpass import OpenStreetMapSource


def test_builds_country_query_and_maps_phone_records(monkeypatch):
    source = OpenStreetMapSource()
    monkeypatch.setattr(
        "src.sources.osm_overpass.resolve_location",
        lambda _location: (13.0, 52.0, 14.0, 53.0, "DE"),
    )
    monkeypatch.setattr(
        source,
        "_request",
        lambda query: {
            "elements": [
                {
                    "type": "node",
                    "id": 42,
                    "tags": {
                        "name": "Example Machinery",
                        "phone": "+49 30 123456; +49 30 654321",
                    },
                }
            ]
        },
    )
    records = list(source.collect("machinery", "Berlin, Germany"))
    assert len(records) == 2
    assert records[0].company_name == "Example Machinery"
    assert records[0].source_url.endswith("/node/42")


def test_supports_exact_osm_tag_query():
    query = OpenStreetMapSource._build_query(
        "industrial=machinery", 13.0, 52.0, 14.0, 53.0
    )
    assert "(52.000000,13.000000,53.000000,14.000000)" in query
    assert '"industrial"~"^machinery$"' in query


def test_empty_keyword_collects_all_named_phone_records():
    query = OpenStreetMapSource._build_query(
        "", 13.0, 52.0, 14.0, 53.0
    )
    assert 'nwr["name"]["phone"]' in query
    assert 'nwr["operator"]["contact:phone"]' in query
