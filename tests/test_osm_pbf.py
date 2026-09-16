from src.sources.osm_pbf import OsmPbfSource


def test_osm_pbf_exact_tag_clause_is_parameterized():
    clause, params = OsmPbfSource._match_clause("industrial=machinery")
    assert clause == "tags['industrial'] = ?"
    assert params == ["machinery"]


def test_osm_pbf_keyword_searches_trade_tags():
    clause, params = OsmPbfSource._match_clause("export")
    assert "tags['name'] ILIKE ?" in clause
    assert len(params) == 6
