import re
import threading
import time
from typing import Iterable, List

import httpx

from src.config import settings
from src.sources.base import LeadRecord, SourceAdapter
from src.sources.geocoding import resolve_location


class OpenStreetMapSource(SourceAdapter):
    """通过公共 Overpass 实例查询带企业电话的 OSM 地点。"""

    source_type = "openstreetmap"
    endpoint = "https://overpass-api.de/api/interpreter"
    _request_lock = threading.Lock()
    _last_request = 0.0

    def collect(self, query: str, country: str = "") -> Iterable[LeadRecord]:
        if not country.strip():
            raise ValueError("OpenStreetMap 数据源要求填写国家、城市或地区")
        west, south, east, north, country_code = resolve_location(country)
        overpass_query = self._build_query(
            query.strip(), west, south, east, north
        )
        data = self._request(overpass_query)
        for element in data.get("elements", []):
            self.check_cancelled()
            tags = element.get("tags", {})
            name = tags.get("name") or tags.get("operator") or tags.get("brand")
            phones = tags.get("contact:phone") or tags.get("phone") or ""
            if not name or not phones:
                continue
            source_url = "https://www.openstreetmap.org/{}/{}".format(
                element.get("type", "node"), element.get("id", "")
            )
            for phone in self._split_phones(phones):
                yield LeadRecord(
                    company_name=name,
                    phone=phone,
                    country=country_code,
                    source_url=source_url,
                    source_type=self.source_type,
                    keyword=query,
                )

    @staticmethod
    def _split_phones(value: str) -> List[str]:
        return [part.strip() for part in re.split(r"[;/]", value) if part.strip()]

    @staticmethod
    def _build_query(
        keyword: str, west: float, south: float, east: float, north: float
    ) -> str:
        bbox = "({:.6f},{:.6f},{:.6f},{:.6f})".format(
            south, west, north, east
        )
        if not keyword:
            body = (
                'nwr["name"]["phone"]{bbox};'
                'nwr["name"]["contact:phone"]{bbox};'
                'nwr["operator"]["phone"]{bbox};'
                'nwr["operator"]["contact:phone"]{bbox};'
            ).format(bbox=bbox)
        elif re.fullmatch(r"[\w:.-]+=[^=\r\n]+", keyword):
            key, value = keyword.split("=", 1)
            key = re.escape(key.strip())
            value = re.escape(value.strip())
            selectors = [
                'nwr["{key}"~"^{value}$",i]["phone"]{bbox};',
                'nwr["{key}"~"^{value}$",i]["contact:phone"]{bbox};',
            ]
            body = "".join(
                item.format(key=key, value=value, bbox=bbox) for item in selectors
            )
        else:
            pattern = re.escape(keyword)
            keys = ("name", "description", "product", "industrial", "craft", "shop")
            selectors = []
            for key in keys:
                selectors.append(
                    'nwr["{}"~"{}",i]["phone"]{};'.format(key, pattern, bbox)
                )
                selectors.append(
                    'nwr["{}"~"{}",i]["contact:phone"]{};'.format(
                        key, pattern, bbox
                    )
                )
            body = "".join(selectors)
        return "[out:json][timeout:60];({});out tags 500;".format(body)

    def _request(self, query: str) -> dict:
        headers = {"User-Agent": settings.user_agent}
        last_error = None
        with self._request_lock:
            wait = 2.0 - (time.monotonic() - self.__class__._last_request)
            if wait > 0:
                time.sleep(wait)
            with httpx.Client(timeout=75.0, headers=headers) as client:
                for attempt in range(settings.max_retries):
                    self.check_cancelled()
                    try:
                        response = client.post(self.endpoint, data={"data": query})
                        self.__class__._last_request = time.monotonic()
                        if response.status_code == 429:
                            delay = min(
                                float(response.headers.get("Retry-After", 5)), 60.0
                            )
                            time.sleep(delay)
                            continue
                        response.raise_for_status()
                        data = response.json()
                        if data.get("remark"):
                            raise RuntimeError(data["remark"])
                        return data
                    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                        last_error = exc
                        if attempt + 1 < settings.max_retries:
                            time.sleep(2 ** attempt)
        raise RuntimeError("OpenStreetMap 查询失败：{}".format(last_error))
