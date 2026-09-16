from abc import abstractmethod
from dataclasses import dataclass
from typing import Iterable, Optional

from src.sources.base import LeadRecord, SourceAdapter


@dataclass
class ProviderPage:
    records: Iterable[LeadRecord]
    next_cursor: Optional[str]
    remaining_quota: Optional[int] = None


class LicensedProviderSource(SourceAdapter):
    """付费数据供应商统一协议；仅在取得正式凭据和许可后实现。"""

    source_type = "licensed_provider"

    @abstractmethod
    def fetch_page(
        self, country: str, query: str, cursor: Optional[str] = None
    ) -> ProviderPage:
        raise NotImplementedError

    def collect(self, query: str, country: str = "") -> Iterable[LeadRecord]:
        cursor = None
        while True:
            self.check_cancelled()
            page = self.fetch_page(country, query, cursor)
            for record in page.records:
                yield record
            cursor = page.next_cursor
            if not cursor:
                break
