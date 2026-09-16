from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, CollectionTask, Company, SourceRecord, TaskCompany
from src.services.deduplicator import batch_save_leads
from src.services.normalizer import NormalizedLead


def _lead(name, phone, source):
    return NormalizedLead(
        name=name,
        normalized_name=name.lower(),
        phone=phone,
        normalized_phone=phone,
        country="DE",
        verification_status="verified",
        is_business_phone=True,
        source_url=source,
        source_type="overture",
        keyword="wholesaler",
        external_id=source.rsplit("=", 1)[-1],
        category="wholesaler",
    )


def test_batch_writer_deduplicates_and_links_task():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        task = CollectionTask(name="bulk", source_type="overture", query="balanced")
        session.add(task)
        session.flush()
        leads = [
            _lead("Acme", "+4930123", "https://source?id=1"),
            _lead("Acme", "+4930123", "https://source?id=1"),
            _lead("Parts", "+4930456", "https://source?id=2"),
        ]
        created, duplicates, task_new = batch_save_leads(session, leads, task.id)
        session.commit()
        assert created == 2
        assert duplicates == 1
        assert task_new == 2
        assert session.scalar(select(func.count(Company.id))) == 2
        assert session.scalar(select(func.count(SourceRecord.id))) == 2
        assert session.scalar(select(func.count(TaskCompany.id))) == 2
