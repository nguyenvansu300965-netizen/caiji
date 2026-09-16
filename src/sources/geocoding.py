from typing import Tuple

import httpx

from src.config import settings


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

LOCATION_ALIASES = {
    "中国": "China",
    "香港": "Hong Kong",
    "中国香港": "Hong Kong",
    "澳门": "Macao",
    "中国澳门": "Macao",
    "台湾": "Taiwan",
    "中国台湾": "Taiwan",
    "美国": "United States",
    "英国": "United Kingdom",
    "德国": "Germany",
    "法国": "France",
    "日本": "Japan",
    "韩国": "South Korea",
    "新加坡": "Singapore",
    "马来西亚": "Malaysia",
    "印度": "India",
    "澳大利亚": "Australia",
    "加拿大": "Canada",
}


def resolve_location(location: str) -> Tuple[float, float, float, float, str]:
    """返回 west, south, east, north, country_code。"""
    location = location.strip()
    search_location = LOCATION_ALIASES.get(location, location)
    params = {
        "q": search_location,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
    }
    if len(search_location) == 2 and search_location.isalpha():
        params["countrycodes"] = search_location.lower()
    with httpx.Client(
        timeout=settings.request_timeout,
        headers={"User-Agent": settings.user_agent},
    ) as client:
        response = client.get(NOMINATIM_URL, params=params)
        response.raise_for_status()
        results = response.json()
    if not results:
        raise ValueError("无法定位国家/地区：{}".format(location))
    south, north, west, east = map(float, results[0]["boundingbox"])
    country_code = (
        results[0].get("address", {}).get("country_code", "").strip().upper()
    )
    return west, south, east, north, country_code


def resolve_bbox(location: str) -> Tuple[float, float, float, float]:
    return resolve_location(location)[:4]
