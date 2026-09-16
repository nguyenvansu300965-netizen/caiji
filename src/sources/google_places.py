import time
import re
from typing import Iterable, List

import httpx

from src.config import settings
from src.sources.base import LeadRecord, SourceAdapter


class GooglePlacesSource(SourceAdapter):
    """Google Places API (New) 文本搜索适配器。"""

    source_type = "google_places"
    endpoint = "https://places.googleapis.com/v1/places:searchText"

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or settings.google_places_api_key

    def collect(self, query: str, country: str = "") -> Iterable[LeadRecord]:
        if not self.api_key:
            raise ValueError("未配置 GOOGLE_PLACES_API_KEY")

        queries = self._split_queries(query)
        if not queries:
            raise ValueError("请输入至少一个 Google Places 搜索关键词")
        seen_place_ids = set()
        with httpx.Client(timeout=settings.request_timeout) as client:
            for search_query in queries:
                page_token = None
                while True:
                    self.check_cancelled()
                    text_query = " ".join(
                        part for part in (search_query, country.strip()) if part
                    )
                    payload = {"textQuery": text_query, "pageSize": 20}
                    if page_token:
                        payload["pageToken"] = page_token
                    response = self._request(client, payload)
                    data = response.json()
                    for place in data.get("places", []):
                        self.check_cancelled()
                        place_id = place.get("id", "")
                        if place_id and place_id in seen_place_ids:
                            continue
                        if place_id:
                            seen_place_ids.add(place_id)
                        phone = (
                            place.get("internationalPhoneNumber")
                            or place.get("nationalPhoneNumber")
                            or ""
                        )
                        name = place.get("displayName", {}).get("text", "")
                        if not name or not phone:
                            continue
                        yield LeadRecord(
                            company_name=name,
                            phone=phone,
                            country=country,
                            source_url=place.get("googleMapsUri", ""),
                            source_type=self.source_type,
                            keyword=search_query,
                            external_id=place_id,
                        )
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
                    time.sleep(2)

    @staticmethod
    def _split_queries(query: str) -> List[str]:
        return [
            value.strip()
            for value in re.split(r"[\n,;]+", query)
            if value.strip()
        ]

    def _request(self, client: httpx.Client, payload: dict) -> httpx.Response:
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "places.displayName,places.nationalPhoneNumber,"
                "places.internationalPhoneNumber,places.googleMapsUri,nextPageToken"
            ),
        }
        last_error = None
        for attempt in range(settings.max_retries):
            try:
                response = client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt + 1 < settings.max_retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError("Google Places 请求失败: {}".format(last_error))
