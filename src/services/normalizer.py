import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType

from src.sources.base import LeadRecord


COUNTRY_ALIASES = {
    "中国": "CN",
    "中华人民共和国": "CN",
    "印度": "IN",
    "印度尼西亚": "ID",
    "越南": "VN",
    "泰国": "TH",
    "马来西亚": "MY",
    "菲律宾": "PH",
    "阿联酋": "AE",
    "沙特阿拉伯": "SA",
    "土耳其": "TR",
    "俄罗斯": "RU",
    "美国": "US",
    "墨西哥": "MX",
    "巴西": "BR",
    "阿根廷": "AR",
    "英国": "GB",
    "德国": "DE",
    "法国": "FR",
    "意大利": "IT",
    "西班牙": "ES",
    "荷兰": "NL",
    "比利时": "BE",
    "瑞士": "CH",
    "奥地利": "AT",
    "波兰": "PL",
    "瑞典": "SE",
    "挪威": "NO",
    "丹麦": "DK",
    "芬兰": "FI",
    "日本": "JP",
    "韩国": "KR",
    "澳大利亚": "AU",
    "加拿大": "CA",
    "新加坡": "SG",
}


@dataclass
class NormalizedLead:
    name: str
    normalized_name: str
    phone: str
    normalized_phone: str
    country: str
    verification_status: str
    is_business_phone: bool
    source_url: str
    source_type: str
    keyword: str
    external_id: str = ""
    category: str = ""
    website: str = ""
    relevance: str = "medium"


def normalize_company_name(name: str) -> str:
    value = unicodedata.normalize("NFKC", name).casefold().strip()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value)
    suffixes = r"\b(ltd|limited|llc|inc|corp|corporation|co|gmbh|plc|sa|sarl)\b"
    value = re.sub(suffixes, " ", value)
    return re.sub(r"\s+", " ", value).strip()


def country_region(country: str) -> Optional[str]:
    value = country.strip()
    if not value:
        return None
    if len(value) == 2 and value.isalpha():
        return value.upper()
    return COUNTRY_ALIASES.get(value) or COUNTRY_ALIASES.get(value.casefold())


def _parse_phone(phone: str, region: Optional[str]):
    if phone.strip().startswith("+"):
        return phonenumbers.parse(phone, None)
    return phonenumbers.parse(phone, region)


def normalize_lead(record: LeadRecord) -> NormalizedLead:
    region = country_region(record.country)
    try:
        parsed = _parse_phone(record.phone, region)
        possible = phonenumbers.is_possible_number(parsed)
        valid = phonenumbers.is_valid_number(parsed)
        normalized_phone = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
        number_type = phonenumbers.number_type(parsed)
        is_business = number_type not in (
            PhoneNumberType.MOBILE,
            PhoneNumberType.PERSONAL_NUMBER,
            PhoneNumberType.PAGER,
        )
        if valid and is_business:
            status = "verified"
        elif valid:
            status = "mobile"
        else:
            status = "pending"
        if not possible:
            status = "invalid"
    except phonenumbers.NumberParseException:
        normalized_phone = re.sub(r"[^\d+]", "", record.phone)
        is_business = False
        status = "invalid"

    return NormalizedLead(
        name=record.company_name.strip(),
        normalized_name=normalize_company_name(record.company_name),
        phone=record.phone.strip(),
        normalized_phone=normalized_phone,
        country=record.country.strip(),
        verification_status=status,
        is_business_phone=is_business,
        source_url=record.source_url,
        source_type=record.source_type,
        keyword=record.keyword,
        external_id=record.external_id,
        category=record.category,
        website=record.website,
        relevance=record.relevance,
    )
