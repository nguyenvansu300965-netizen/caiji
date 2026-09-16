import json
import re
import time
from collections import defaultdict
from typing import Dict, Iterable, Iterator, List
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.sources.base import LeadRecord, SourceAdapter


class PublicWebSource(SourceAdapter):
    """解析用户提供的公开企业页面，不执行搜索引擎抓取或登录绕过。"""

    source_type = "public_web"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._robots: Dict[str, RobotFileParser] = {}
        self._last_request = defaultdict(float)

    def collect(self, query: str, country: str = "") -> Iterable[LeadRecord]:
        urls = [
            line.strip()
            for line in query.replace(",", "\n").splitlines()
            if line.strip()
        ]
        with httpx.Client(
            timeout=settings.request_timeout,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        ) as client:
            for url in urls:
                self.check_cancelled()
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                if not self._allowed(client, url):
                    raise PermissionError("robots.txt 不允许采集: {}".format(url))
                response = self._get(client, url)
                for name, phone in self._extract(response.text):
                    yield LeadRecord(
                        company_name=name,
                        phone=phone,
                        country=country,
                        source_url=str(response.url),
                        source_type=self.source_type,
                        keyword="direct_url",
                    )

    def _allowed(self, client: httpx.Client, url: str) -> bool:
        parsed = urlparse(url)
        origin = "{}://{}".format(parsed.scheme, parsed.netloc)
        if origin not in self._robots:
            robots_url = urljoin(origin, "/robots.txt")
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                response = client.get(robots_url)
                if response.status_code == 404:
                    parser.parse([])
                else:
                    response.raise_for_status()
                    parser.parse(response.text.splitlines())
            except httpx.HTTPError:
                return False
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(settings.user_agent, url)

    def _get(self, client: httpx.Client, url: str) -> httpx.Response:
        domain = urlparse(url).netloc
        wait = settings.per_domain_delay - (time.monotonic() - self._last_request[domain])
        if wait > 0:
            time.sleep(wait)
        last_error = None
        for attempt in range(settings.max_retries):
            try:
                response = client.get(url)
                self._last_request[domain] = time.monotonic()
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", ""):
                    raise ValueError("目标不是 HTML 页面: {}".format(url))
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt + 1 < settings.max_retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError("页面请求失败: {}".format(last_error))

    @staticmethod
    def _extract(html: str) -> Iterator[tuple]:
        soup = BeautifulSoup(html, "html.parser")
        found = set()
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            for item in PublicWebSource._jsonld_items(data):
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    is_org = any(t in ("Organization", "LocalBusiness") for t in item_type)
                else:
                    is_org = item_type in ("Organization", "LocalBusiness")
                if not is_org:
                    continue
                name = str(item.get("name", "")).strip()
                phones = item.get("telephone", [])
                if isinstance(phones, str):
                    phones = [phones]
                for phone in phones:
                    pair = (name, str(phone).strip())
                    if all(pair) and pair not in found:
                        found.add(pair)
                        yield pair

        fallback_name = PublicWebSource._page_name(soup)
        for link in soup.select('a[href^="tel:"]'):
            phone = link.get("href", "")[4:].split("?")[0].strip()
            pair = (fallback_name, phone)
            if all(pair) and pair not in found:
                found.add(pair)
                yield pair

        text = soup.get_text(" ", strip=True)
        phone_pattern = re.compile(
            r"(?:Tel(?:ephone)?|Phone|电话)\s*[:：]?\s*"
            r"(\+?[\d(][\d\s().-]{6,}\d)",
            re.IGNORECASE,
        )
        for match in phone_pattern.finditer(text):
            pair = (fallback_name, match.group(1).strip())
            if all(pair) and pair not in found:
                found.add(pair)
                yield pair

    @staticmethod
    def _jsonld_items(data) -> List[dict]:
        if isinstance(data, list):
            return [item for value in data for item in PublicWebSource._jsonld_items(value)]
        if not isinstance(data, dict):
            return []
        graph = data.get("@graph")
        return PublicWebSource._jsonld_items(graph) if graph else [data]

    @staticmethod
    def _page_name(soup: BeautifulSoup) -> str:
        meta = soup.select_one('meta[property="og:site_name"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        return title.split("|")[0].split("–")[0].strip()
