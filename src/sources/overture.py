import re
from typing import Iterable, List, Tuple

import duckdb
import httpx

from src.config import settings
from src.sources.base import LeadRecord, SourceAdapter
from src.sources.geocoding import resolve_bbox
from src.sources.trade_taxonomy import (
    score_commodity_relevance,
    score_trade_relevance,
)


class OvertureMapsSource(SourceAdapter):
    """直接查询 Overture 官方 S3 GeoParquet 发布数据。"""

    source_type = "overture"
    catalog_url = "https://stac.overturemaps.org/catalog.json"
    s3_template = (
        "s3://overturemaps-us-west-2/release/{}/"
        "theme=places/type=place/*"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connection = None
        self._release = ""

    def collect(self, query: str, country: str = "") -> Iterable[LeadRecord]:
        if not query.strip():
            raise ValueError("请输入企业名称或 Overture 行业分类关键词")
        if not country.strip():
            raise ValueError("Overture 数据源要求填写国家、城市或地区")
        self.check_cancelled()
        release = self._latest_release()
        west, south, east, north = resolve_bbox(country)
        rows = self._query_places(release, query.strip(), west, south, east, north)
        for place_id, name, phones, result_country in rows:
            self.check_cancelled()
            if not name or not phones:
                continue
            source_url = "https://overturemaps.org/?place_id={}".format(place_id)
            for phone in self._phones(phones):
                yield LeadRecord(
                    company_name=name,
                    phone=phone,
                    country=result_country or self._country_fallback(country),
                    source_url=source_url,
                    source_type=self.source_type,
                    keyword=query,
                )

    def _latest_release(self) -> str:
        with httpx.Client(
            timeout=settings.request_timeout,
            headers={"User-Agent": settings.user_agent},
        ) as client:
            response = client.get(self.catalog_url)
            response.raise_for_status()
            catalog = response.json()
        latest = catalog.get("latest", "")
        if isinstance(latest, dict):
            latest = latest.get("id") or latest.get("href") or ""
        match = re.search(r"\d{4}-\d{2}-\d{2}\.\d+", str(latest))
        if not match:
            raise RuntimeError("无法从 Overture STAC 目录确定最新版本")
        return match.group(0)

    def _query_places(
        self,
        release: str,
        keyword: str,
        west: float,
        south: float,
        east: float,
        north: float,
    ) -> list:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", release):
            raise ValueError("Overture 版本格式无效")
        path = self.s3_template.format(release)
        pattern = "%{}%".format(keyword)
        connection = duckdb.connect()
        try:
            try:
                connection.execute("LOAD httpfs")
            except duckdb.Error:
                connection.execute("INSTALL httpfs")
                connection.execute("LOAD httpfs")
            connection.execute("SET s3_region='us-west-2'")
            sql = """
                SELECT
                    id,
                    names.primary AS name,
                    phones,
                    addresses[1].country AS country
                FROM read_parquet(?, filename=true, hive_partitioning=1)
                WHERE bbox.xmin BETWEEN ? AND ?
                  AND bbox.ymin BETWEEN ? AND ?
                  AND phones IS NOT NULL
                  AND array_length(phones) > 0
                  AND (
                    names.primary ILIKE ?
                    OR categories.primary ILIKE ?
                    OR CAST(categories.alternate AS VARCHAR) ILIKE ?
                  )
                LIMIT 500
            """
            return connection.execute(
                sql, [path, west, east, south, north, pattern, pattern, pattern]
            ).fetchall()
        finally:
            connection.close()

    def query_page(
        self,
        keyword: str,
        match_type: str,
        relevance: str,
        west: float,
        south: float,
        east: float,
        north: float,
        cursor: str = "",
        limit: int = 500,
    ) -> Tuple[List[LeadRecord], str, int]:
        self.check_cancelled()
        if not self._release:
            self._release = self._latest_release()
        connection = self._get_connection()
        path = self.s3_template.format(self._release)
        if match_type == "all":
            match_sql = "TRUE"
            match_params = []
        elif match_type == "commodity":
            match_sql = (
                "((regexp_matches(COALESCE(categories.primary, ''), ?) OR "
                "regexp_matches(COALESCE(CAST(categories.alternate AS VARCHAR), ''), ?) OR "
                "(regexp_matches(COALESCE(names.primary, ''), ?) AND "
                "regexp_matches(COALESCE(names.primary, ''), ?))) AND "
                "COALESCE(categories.primary, '') NOT IN ("
                "'gas_station','oil_change_station','restaurant','chinese_restaurant',"
                "'liquor_store','grocery_store','supermarket','convenience_store',"
                "'hardware_store','furniture_store','toy_store','sporting_goods_store',"
                "'sign_making','dermatologist','diagnostic_services','plastic_surgeon',"
                "'clinic','hospital','doctor'))"
            )
            pattern = "(?i){}".format(keyword)
            trade_pattern = (
                "(?i)(^|[^a-z])(trading|import|export|wholesale|"
                "supplier|commodities)([^a-z]|$)"
            )
            match_params = [pattern, pattern, pattern, trade_pattern]
        elif match_type == "category":
            match_sql = (
                "(categories.primary = ? OR "
                "list_contains(categories.alternate, ?))"
            )
            match_params = [keyword, keyword]
        else:
            match_sql = "names.primary ILIKE ?"
            match_params = ["%{}%".format(keyword)]
        sql = """
            SELECT
                id,
                names.primary AS name,
                phones,
                addresses[1].country AS country,
                categories.primary AS category,
                websites[1] AS website
            FROM read_parquet(?, filename=true, hive_partitioning=1)
            WHERE bbox.xmin >= ? AND bbox.xmin < ?
              AND bbox.ymin >= ? AND bbox.ymin < ?
              AND phones IS NOT NULL
              AND array_length(phones) > 0
              AND id > ?
              AND {match_sql}
            ORDER BY id
            LIMIT ?
        """.format(match_sql=match_sql)
        params = [
            path,
            west,
            east,
            south,
            north,
            cursor,
        ] + match_params + [limit]
        rows = connection.execute(sql, params).fetchall()
        leads = []
        for place_id, name, phones, country, category, website in rows:
            if match_type == "all":
                row_relevance = score_trade_relevance(
                    name or "", category or "", website or ""
                )
            elif match_type == "commodity":
                row_relevance = score_commodity_relevance(
                    name or "", category or "", website or ""
                )
            else:
                row_relevance = relevance
            if match_type == "commodity" and row_relevance == "low":
                continue
            for phone in self._phones(phones):
                leads.append(
                    LeadRecord(
                        company_name=name or "",
                        phone=phone,
                        country=country or "",
                        source_url="https://overturemaps.org/?place_id={}".format(
                            place_id
                        ),
                        source_type=self.source_type,
                        keyword=keyword,
                        external_id=str(place_id),
                        category=category or "",
                        website=website or "",
                        relevance=row_relevance,
                    )
                )
        next_cursor = str(rows[-1][0]) if rows else cursor
        return leads, next_cursor, len(rows)

    def _get_connection(self):
        if self._connection is None:
            connection = duckdb.connect()
            try:
                connection.execute("LOAD httpfs")
            except duckdb.Error:
                connection.execute("INSTALL httpfs")
                connection.execute("LOAD httpfs")
            connection.execute("SET s3_region='us-west-2'")
            self._connection = connection
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @staticmethod
    def _phones(value) -> List[str]:
        if isinstance(value, str):
            return [value]
        return [str(phone).strip() for phone in value or [] if str(phone).strip()]

    @staticmethod
    def _country_fallback(location: str) -> str:
        value = location.strip().upper()
        return value if re.fullmatch(r"[A-Z]{2}", value) else ""
