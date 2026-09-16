from dataclasses import dataclass
import re
from typing import Dict, List


@dataclass(frozen=True)
class TradeTerm:
    value: str
    match_type: str
    relevance: str


STRICT_TERMS = [
    TradeTerm("import_export_company", "category", "high"),
    TradeTerm("exporter", "category", "high"),
    TradeTerm("importer", "category", "high"),
    TradeTerm("freight_forwarding_service", "category", "high"),
    TradeTerm("customs_broker", "category", "high"),
    TradeTerm("international_trade_consultant", "category", "high"),
]

BALANCED_TERMS = STRICT_TERMS + [
    TradeTerm("wholesaler", "category", "medium"),
    TradeTerm("manufacturer", "category", "medium"),
    TradeTerm("distribution_service", "category", "medium"),
    TradeTerm("logistics_service", "category", "medium"),
    TradeTerm("industrial_equipment_supplier", "category", "medium"),
    TradeTerm("business_to_business_service", "category", "medium"),
    TradeTerm("trading", "name", "medium"),
    TradeTerm("import export", "name", "high"),
    TradeTerm("international logistics", "name", "medium"),
]

BROAD_TERMS = BALANCED_TERMS + [
    TradeTerm("supplier", "name", "low"),
    TradeTerm("wholesale", "name", "low"),
    TradeTerm("manufacturing", "name", "low"),
    TradeTerm("distribution", "name", "low"),
]

COMMODITY_PATTERN = (
    "(^|[^a-z])(commodity|commodities|raw.?materials?|metals?|steel|copper|"
    "aluminium|aluminum|minerals?|mining|ores?|oil|petroleum|natural.?gas|"
    "coal|energy.?trading|grains?|wheat|corn|soy|rice|sugar|cotton|feed|"
    "agricultural|chemicals?|plastics?|polymers?|rubber)([^a-z]|$)"
)

PROFILES: Dict[str, List[TradeTerm]] = {
    "all": [TradeTerm("*", "all", "low")],
    "commodity": [TradeTerm(COMMODITY_PATTERN, "commodity", "medium")],
    "strict": STRICT_TERMS,
    "balanced": BALANCED_TERMS,
    "broad": BROAD_TERMS,
}


def terms_for_profile(profile: str) -> List[TradeTerm]:
    return list(PROFILES.get(profile, BALANCED_TERMS))


def score_trade_relevance(name: str, category: str, website: str = "") -> str:
    value = " ".join((name or "", category or "", website or "")).casefold()
    high_terms = (
        "import",
        "export",
        "international trade",
        "trading",
        "freight forward",
        "customs broker",
    )
    medium_terms = (
        "wholesale",
        "manufacturer",
        "manufacturing",
        "supplier",
        "distribution",
        "logistics",
        "industrial",
        "b2b",
    )
    if any(term in value for term in high_terms):
        return "high"
    if any(term in value for term in medium_terms):
        return "medium"
    return "low"


def score_commodity_relevance(name: str, category: str, website: str = "") -> str:
    value = " ".join((name or "", category or "", website or "")).casefold()
    commodity_match = re.search(COMMODITY_PATTERN, value) is not None
    trade_match = (
        re.search(
            r"(^|[^a-z])(trading|import|export|wholesale|supplier)([^a-z]|$)",
            value,
        )
        is not None
    )
    if commodity_match and trade_match:
        return "high"
    return "medium" if commodity_match else "low"
