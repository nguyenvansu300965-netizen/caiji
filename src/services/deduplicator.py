from typing import Dict, Iterable, List, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import Company, SourceRecord, TaskCompany
from src.services.normalizer import NormalizedLead


def save_lead(session: Session, lead: NormalizedLead, task_id: int) -> Tuple[Company, bool]:
    company = session.scalar(
        select(Company).where(
            Company.normalized_name == lead.normalized_name,
            Company.normalized_phone == lead.normalized_phone,
        )
    )
    created = company is None
    if company is None:
        company = Company(
            name=lead.name,
            normalized_name=lead.normalized_name,
            phone=lead.phone,
            normalized_phone=lead.normalized_phone,
            country=lead.country,
            verification_status=lead.verification_status,
            is_business_phone=lead.is_business_phone,
            category=lead.category,
            website=lead.website,
            relevance=lead.relevance,
        )
        session.add(company)
        session.flush()

    source_exists = any(source.source_url == lead.source_url for source in company.sources)
    if not source_exists:
        company.sources.append(
            SourceRecord(
                task_id=task_id,
                source_type=lead.source_type,
                source_url=lead.source_url,
                keyword=lead.keyword,
                external_id=lead.external_id,
            )
        )
    task_link = session.scalar(
        select(TaskCompany.id).where(
            TaskCompany.task_id == task_id, TaskCompany.company_id == company.id
        )
    )
    if task_link is None:
        session.add(TaskCompany(task_id=task_id, company_id=company.id))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        company = session.scalar(
            select(Company).where(
                Company.normalized_name == lead.normalized_name,
                Company.normalized_phone == lead.normalized_phone,
            )
        )
        created = False
    return company, created


def batch_save_leads(
    session: Session, leads: Iterable[NormalizedLead], task_id: int
) -> Tuple[int, int, int]:
    items = list(leads)
    if not items:
        return 0, 0, 0
    phones = {item.normalized_phone for item in items}
    existing_companies = list(
        session.scalars(select(Company).where(Company.normalized_phone.in_(phones)))
    )
    companies: Dict[Tuple[str, str], Company] = {
        (company.normalized_name, company.normalized_phone): company
        for company in existing_companies
    }
    created = 0
    for lead in items:
        key = (lead.normalized_name, lead.normalized_phone)
        if key in companies:
            continue
        company = Company(
            name=lead.name,
            normalized_name=lead.normalized_name,
            phone=lead.phone,
            normalized_phone=lead.normalized_phone,
            country=lead.country,
            verification_status=lead.verification_status,
            is_business_phone=lead.is_business_phone,
            category=lead.category,
            website=lead.website,
            relevance=lead.relevance,
        )
        session.add(company)
        companies[key] = company
        created += 1
    session.flush()

    company_ids = [company.id for company in companies.values()]
    existing_sources = {
        (source.company_id, source.source_url)
        for source in session.scalars(
            select(SourceRecord).where(SourceRecord.company_id.in_(company_ids))
        )
    }
    for lead in items:
        company = companies[(lead.normalized_name, lead.normalized_phone)]
        if not company.category and lead.category:
            company.category = lead.category
        if not company.website and lead.website:
            company.website = lead.website
        pair = (company.id, lead.source_url)
        if pair in existing_sources:
            continue
        session.add(
            SourceRecord(
                company_id=company.id,
                task_id=task_id,
                source_type=lead.source_type,
                source_url=lead.source_url,
                keyword=lead.keyword,
                external_id=lead.external_id,
            )
        )
        existing_sources.add(pair)
    linked_ids = {
        company_id
        for company_id in session.scalars(
            select(TaskCompany.company_id).where(
                TaskCompany.task_id == task_id,
                TaskCompany.company_id.in_(company_ids),
            )
        )
    }
    task_companies = {
        companies[(lead.normalized_name, lead.normalized_phone)].id for lead in items
    }
    new_task_ids = task_companies - linked_ids
    session.add_all(
        [TaskCompany(task_id=task_id, company_id=company_id) for company_id in new_task_ids]
    )
    return created, len(items) - created, len(new_task_ids)
