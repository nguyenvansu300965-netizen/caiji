import csv
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.db.models import Company, SourceRecord, TaskCompany
from src.db.session import SessionLocal


HEADERS = [
    "公司名称",
    "企业电话",
    "国家/地区",
    "验证状态",
    "行业分类",
    "外贸相关性",
    "网站",
    "来源",
    "采集时间",
]

ILLEGAL_EXCEL_CHARACTERS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _excel_safe(value):
    if not isinstance(value, str):
        return value
    return ILLEGAL_EXCEL_CHARACTERS.sub("", value)[:32767]


def query_companies(
    keyword: str = "",
    country: str = "",
    source_type: str = "",
    status: str = "",
    relevance: str = "",
    task_id: str = "",
    page: int = 1,
    page_size: int = 500,
) -> List[Company]:
    statement = select(Company).options(selectinload(Company.sources))
    if keyword:
        statement = statement.where(Company.name.ilike("%{}%".format(keyword)))
    if country:
        statement = statement.where(Company.country == country)
    if status:
        statement = statement.where(Company.verification_status == status)
    if relevance:
        statement = statement.where(Company.relevance == relevance)
    if task_id:
        statement = statement.where(
            Company.id.in_(
                select(TaskCompany.company_id)
                .where(TaskCompany.task_id == int(task_id))
            )
        )
    if source_type:
        statement = (
            statement.join(Company.sources)
            .where(SourceRecord.source_type == source_type)
            .distinct()
        )
    statement = (
        statement.order_by(Company.collected_at.desc())
        .limit(page_size)
        .offset(max(page - 1, 0) * page_size)
    )
    with SessionLocal() as session:
        return list(session.scalars(statement).unique())


def count_companies(
    keyword: str = "",
    country: str = "",
    source_type: str = "",
    status: str = "",
    relevance: str = "",
    task_id: str = "",
) -> int:
    statement = select(func.count(func.distinct(Company.id)))
    if source_type:
        statement = statement.join(Company.sources)
    if keyword:
        statement = statement.where(Company.name.ilike("%{}%".format(keyword)))
    if country:
        statement = statement.where(Company.country == country)
    if status:
        statement = statement.where(Company.verification_status == status)
    if relevance:
        statement = statement.where(Company.relevance == relevance)
    if task_id:
        statement = statement.where(
            Company.id.in_(
                select(TaskCompany.company_id)
                .where(TaskCompany.task_id == int(task_id))
            )
        )
    if source_type:
        statement = statement.where(SourceRecord.source_type == source_type)
    with SessionLocal() as session:
        return session.scalar(statement) or 0


def _rows(companies: Iterable[Company]) -> Iterable[List[str]]:
    for company in companies:
        sources = "; ".join(sorted({source.source_url for source in company.sources}))
        yield [
            company.name,
            company.normalized_phone,
            company.country,
            company.verification_status,
            company.category,
            company.relevance,
            company.website,
            sources,
            company.collected_at.strftime("%Y-%m-%d %H:%M:%S"),
        ]


def _iter_export_rows(filters: Dict[str, str]):
    task_id = filters.get("task_id", "")
    source_condition = SourceRecord.company_id == Company.id
    if task_id:
        source_condition = (
            source_condition & (SourceRecord.task_id == int(task_id))
        )
    source_urls = (
        select(func.group_concat(SourceRecord.source_url, "; "))
        .where(source_condition)
        .correlate(Company)
        .scalar_subquery()
    )
    statement = select(
        Company.name,
        Company.normalized_phone,
        Company.country,
        Company.verification_status,
        Company.category,
        Company.relevance,
        Company.website,
        source_urls,
        Company.collected_at,
    )
    keyword = filters.get("keyword", "")
    country = filters.get("country", "")
    source_type = filters.get("source_type", "")
    status = filters.get("status", "")
    relevance = filters.get("relevance", "")
    if source_type:
        statement = statement.join(Company.sources).distinct()
        statement = statement.where(SourceRecord.source_type == source_type)
    if keyword:
        statement = statement.where(Company.name.ilike("%{}%".format(keyword)))
    if country:
        statement = statement.where(Company.country == country)
    if status:
        statement = statement.where(Company.verification_status == status)
    if relevance:
        statement = statement.where(Company.relevance == relevance)
    if task_id:
        statement = statement.where(
            Company.id.in_(
                select(TaskCompany.company_id)
                .where(TaskCompany.task_id == int(task_id))
            )
        )
    statement = statement.order_by(Company.id)
    with SessionLocal() as session:
        result = session.execute(statement.execution_options(yield_per=1000))
        for row in result:
            values = list(row)
            values[-1] = values[-1].strftime("%Y-%m-%d %H:%M:%S")
            yield values


def export_companies(
    path: str,
    filters: Dict[str, str],
    progress: Optional[Callable[[int], None]] = None,
) -> int:
    target = Path(path)
    count = 0
    if target.suffix.lower() == ".csv":
        with target.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(HEADERS)
            for row in _iter_export_rows(filters):
                writer.writerow(row)
                count += 1
                if progress and count % 1000 == 0:
                    progress(count)
    else:
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("外贸客户")
        sheet.title = "外贸客户"
        sheet.append(HEADERS)
        for row in _iter_export_rows(filters):
            sheet.append([_excel_safe(value) for value in row])
            count += 1
            if progress and count % 1000 == 0:
                progress(count)
        workbook.save(target)
    return count
