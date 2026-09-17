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


MAP_BUSINESS_KEYWORDS = [
    # 企业与生产基地
    "企业", "公司", "集团公司", "总部", "工厂", "生产基地", "制造基地",
    "办公室", "仓库", "配送中心", "工业园", "产业园", "经济开发区",
    "企业园区", "工业区", "保税区", "保税仓", "出口加工区",
    "制造商", "供应商", "批发商", "经销商", "分销商", "贸易公司",
    # 批发、采购与大型商贸场所
    "批发市场", "商品城", "商贸城", "国际商贸城", "采购中心", "采购市场",
    "交易市场", "交易中心", "商品交易中心", "国际交易中心", "展览中心",
    "会展中心", "工业品市场", "建材市场", "农产品批发市场", "物流市场",
    "大型批发商", "采购代理", "贸易中心", "商务中心", "商业中心",
    # 物流、港口与跨境贸易
    "物流公司", "国际物流", "货运代理", "国际货运代理", "运输公司", "航运公司",
    "海运公司", "空运公司", "集装箱运输", "供应链公司", "仓储物流",
    "物流园", "物流园区", "港口", "码头", "货运码头", "集装箱码头",
    "国际机场货运", "机场物流", "铁路货运", "铁路物流", "报关公司", "清关公司",
    "海关监管仓", "跨境电商园区", "海外仓",
    # 大宗商品与工业交易
    "大宗商品", "大宗商品交易", "原材料交易", "金属交易", "钢材市场", "钢铁贸易",
    "有色金属交易", "矿产交易", "能源交易", "石油贸易", "天然气贸易",
    "煤炭贸易", "粮食交易", "农产品交易", "化工产品交易", "塑料原料交易",
    "橡胶交易", "木材交易", "建筑材料交易", "工业设备交易",
    # English discovery terms
    "business", "company", "enterprise", "corporate headquarters", "factory",
    "manufacturing plant", "production facility", "office", "warehouse",
    "distribution center", "industrial park", "industrial zone", "free trade zone",
    "bonded warehouse", "export processing zone", "manufacturer", "supplier",
    "wholesaler", "distributor", "trading company", "trade center", "business center",
    "commercial center", "wholesale market", "commodity market", "procurement center",
    "industrial market", "building materials market", "logistics company",
    "international logistics", "freight forwarder", "shipping company", "cargo company",
    "container terminal", "seaport", "port logistics", "airport cargo", "rail freight",
    "supply chain company", "logistics park", "customs broker", "customs clearance",
    "cross border logistics", "ecommerce logistics", "commodity trading",
    "raw materials trading", "metal trading", "steel trading", "mineral trading",
    "energy trading", "oil trading", "natural gas trading", "coal trading",
    "agricultural commodities", "chemical trading", "plastic raw materials",
    "rubber trading", "timber trading", "building materials trading",
    "industrial equipment trading", "import export company",
]


def terms_for_profile(profile: str) -> List[TradeTerm]:
    return list(PROFILES.get(profile, BALANCED_TERMS))


def generate_map_keywords(profile: str = "balanced") -> List[str]:
    """Generate broad map-business discovery terms without an external API call."""
    keywords = MAP_BUSINESS_KEYWORDS.copy()
    if profile == "strict":
        keywords = [
            keyword for keyword in keywords
            if any(term in keyword.casefold() for term in ("贸易", "进出口", "进口", "出口", "import", "export", "trade", "supplier"))
        ]
    return list(dict.fromkeys(keyword.strip() for keyword in keywords if keyword.strip()))


def generate_trade_keywords(profile: str = "balanced") -> List[str]:
    """Backward-compatible name for broad business discovery keywords."""
    return generate_map_keywords(profile)


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
