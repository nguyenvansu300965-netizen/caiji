from src.sources.trade_taxonomy import (
    score_commodity_relevance,
    score_trade_relevance,
    terms_for_profile,
)


def test_all_profile_uses_single_unfiltered_pass():
    terms = terms_for_profile("all")
    assert len(terms) == 1
    assert terms[0].match_type == "all"


def test_scores_trade_relevance_from_name_and_category():
    assert score_trade_relevance("Asia Import Export Ltd", "", "") == "high"
    assert score_trade_relevance("Acme", "industrial_equipment_supplier", "") == "medium"
    assert score_trade_relevance("Coffee Corner", "cafe", "") == "low"


def test_commodity_profile_and_scoring():
    terms = terms_for_profile("commodity")
    assert len(terms) == 1
    assert terms[0].match_type == "commodity"
    assert score_commodity_relevance("Global Copper Trading", "", "") == "high"
    assert score_commodity_relevance("Steel Works", "steel_fabricator", "") == "medium"
    assert score_commodity_relevance("Golden Furniture", "furniture_store", "") == "low"
