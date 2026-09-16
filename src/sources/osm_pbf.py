import re
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import duckdb
import httpx

from src.config import APP_DIR, settings
from src.sources.base import LeadRecord, SourceAdapter
from src.sources.geocoding import resolve_location


class OsmPbfSource(SourceAdapter):
    """下载 Geofabrik OSM 国家数据后在本地批量查询。"""

    source_type = "osm_pbf"
    index_url = "https://download.geofabrik.de/index-v1.json"

    def collect(self, query: str, country: str = "") -> Iterable[LeadRecord]:
        if not country.strip():
            raise ValueError("OSM 本地数据源要求指定国家")
        _, _, _, _, country_code = resolve_location(country)
        if not country_code:
            raise ValueError("无法确定国家代码：{}".format(country))
        pbf_url = self._resolve_pbf_url(country_code)
        pbf_path = self._download(pbf_url)
        connection = duckdb.connect()
        try:
            try:
                connection.execute("LOAD spatial")
            except duckdb.Error:
                connection.execute("INSTALL spatial")
                connection.execute("LOAD spatial")
            clause, params = self._match_clause(query)
            sql = """
                SELECT
                    kind,
                    id,
                    COALESCE(tags['name'], tags['operator'], tags['brand']) AS name,
                    COALESCE(tags['contact:phone'], tags['phone']) AS phone,
                    COALESCE(tags['industrial'], tags['shop'], tags['craft']) AS category,
                    COALESCE(tags['contact:website'], tags['website']) AS website
                FROM ST_ReadOSM(?)
                WHERE COALESCE(tags['contact:phone'], tags['phone']) IS NOT NULL
                  AND COALESCE(tags['name'], tags['operator'], tags['brand']) IS NOT NULL
                  AND {clause}
            """.format(clause=clause)
            cursor = connection.execute(sql, [str(pbf_path)] + params)
            while True:
                self.check_cancelled()
                rows = cursor.fetchmany(settings.batch_size)
                if not rows:
                    break
                for kind, osm_id, name, phones, category, website in rows:
                    for phone in re.split(r"[;/]", phones or ""):
                        if phone.strip():
                            yield LeadRecord(
                                company_name=name,
                                phone=phone.strip(),
                                country=country_code,
                                source_url="https://www.openstreetmap.org/{}/{}".format(
                                    kind, osm_id
                                ),
                                source_type=self.source_type,
                                keyword=query,
                                external_id="{}:{}".format(kind, osm_id),
                                category=category or "",
                                website=website or "",
                                relevance="medium",
                            )
        finally:
            connection.close()

    def _resolve_pbf_url(self, country_code: str) -> str:
        with httpx.Client(
            timeout=settings.request_timeout,
            headers={"User-Agent": settings.user_agent},
        ) as client:
            response = client.get(self.index_url)
            response.raise_for_status()
            features = response.json().get("features", [])
        matches = []
        for feature in features:
            properties = feature.get("properties", {})
            codes = properties.get("iso3166-1:alpha2", [])
            if isinstance(codes, str):
                codes = [codes]
            url = properties.get("urls", {}).get("pbf")
            if country_code in codes and url:
                matches.append(url)
        if not matches:
            raise ValueError(
                "Geofabrik 没有该国家的单一 PBF，请改用 Overture：{}".format(
                    country_code
                )
            )
        return min(matches, key=len)

    def _download(self, url: str) -> Path:
        folder = APP_DIR / "osm"
        folder.mkdir(parents=True, exist_ok=True)
        name = Path(urlparse(url).path).name
        target = folder / name
        partial = target.with_suffix(target.suffix + ".part")
        if target.exists():
            return target
        downloaded = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": settings.user_agent}
        if downloaded:
            headers["Range"] = "bytes={}-".format(downloaded)
        with httpx.stream(
            "GET", url, headers=headers, timeout=120.0, follow_redirects=True
        ) as response:
            response.raise_for_status()
            mode = "ab" if downloaded and response.status_code == 206 else "wb"
            with partial.open(mode) as file:
                for chunk in response.iter_bytes(1024 * 1024):
                    self.check_cancelled()
                    file.write(chunk)
        partial.replace(target)
        return target

    @staticmethod
    def _match_clause(query: str):
        value = query.strip()
        exact = re.fullmatch(r"([\w:.-]+)=([^=\r\n]+)", value)
        if exact:
            key, tag_value = exact.groups()
            return "tags['{}'] = ?".format(key), [tag_value]
        pattern = "%{}%".format(value)
        return (
            "(tags['name'] ILIKE ? OR tags['description'] ILIKE ? "
            "OR tags['product'] ILIKE ? OR tags['industrial'] ILIKE ? "
            "OR tags['shop'] ILIKE ? OR tags['craft'] ILIKE ?)",
            [pattern] * 6,
        )
