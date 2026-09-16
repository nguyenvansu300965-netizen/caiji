from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass
class LeadRecord:
    company_name: str
    phone: str
    country: str
    source_url: str
    source_type: str
    keyword: str = ""
    external_id: str = ""
    category: str = ""
    website: str = ""
    relevance: str = "medium"


class CollectionCancelled(Exception):
    pass


class SourceAdapter(ABC):
    source_type = "base"

    def __init__(self, is_cancelled: Callable[[], bool] = lambda: False):
        self.is_cancelled = is_cancelled

    def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise CollectionCancelled()

    @abstractmethod
    def collect(self, query: str, country: str = "") -> Iterable[LeadRecord]:
        raise NotImplementedError
