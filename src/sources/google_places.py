import time
from typing import Iterable

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

        text_query = " ".join(part for part in (query.strip(), country.strip()) if part)
        page_token = None
        with httpx.Client(timeout=settings.request_timeout) as client:
            while True:
                self.check_cancelled()
                payload = {"textQuery": text_query, "pageSize": 20}
                if page_token:
                    payload["pageToken"] = page_token
                response = self._request(client, payload)
                data = response.json()
                for place in data.get("places", []):
                    self.check_cancelled()
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
                        keyword=query,
                    )
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
                time.sleep(2)

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
