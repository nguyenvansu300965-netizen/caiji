from src.sources.overture import OvertureMapsSource


def test_maps_overture_rows_to_leads(monkeypatch):
    source = OvertureMapsSource()
    monkeypatch.setattr(source, "_latest_release", lambda: "2026-07-22.0")
    monkeypatch.setattr(
        "src.sources.overture.resolve_bbox",
        lambda _location: (13.0, 52.0, 14.0, 53.0),
    )
    monkeypatch.setattr(
        source,
        "_query_places",
        lambda *_args: [
            (
                "place-1",
                "Berlin Machines",
                ["+49 30 123456"],
                "DE",
            )
        ],
    )
    records = list(source.collect("machinery", "Berlin, Germany"))
    assert len(records) == 1
    assert records[0].company_name == "Berlin Machines"
    assert records[0].country == "DE"
    assert "place-1" in records[0].source_url


def test_extracts_release_from_catalog_url(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"latest": "release/2026-07-22.0"}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url):
            return Response()

    monkeypatch.setattr("src.sources.overture.httpx.Client", lambda **_kwargs: Client())
    assert OvertureMapsSource()._latest_release() == "2026-07-22.0"


def test_query_page_returns_cursor_and_metadata(monkeypatch):
    class Result:
        def fetchall(self):
            return [
                (
                    "id-9",
                    "Trade Parts",
                    ["+4930123456"],
                    "DE",
                    "wholesaler",
                    "https://trade.example",
                )
            ]

    class Connection:
        def execute(self, _sql, _params):
            return Result()

    source = OvertureMapsSource()
    source._release = "2026-07-22.0"
    monkeypatch.setattr(source, "_get_connection", lambda: Connection())
    leads, cursor, row_count = source.query_page(
        "wholesaler", "category", "medium", 10, 20, 11, 21
    )
    assert row_count == 1
    assert cursor == "id-9"
    assert leads[0].category == "wholesaler"
    assert leads[0].website == "https://trade.example"


def test_query_page_all_mode_scores_results(monkeypatch):
    class Result:
        def fetchall(self):
            return [("id-1", "Global Import Export", ["+85221234567"], "HK", "office", "")]

    class Connection:
        def execute(self, _sql, _params):
            return Result()

    source = OvertureMapsSource()
    source._release = "2026-08-19.0"
    monkeypatch.setattr(source, "_get_connection", lambda: Connection())
    leads, _, _ = source.query_page(
        "*", "all", "low", 113.8, 22.1, 114.5, 22.6
    )
    assert leads[0].relevance == "high"
