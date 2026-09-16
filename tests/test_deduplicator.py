from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, Company
from src.services.deduplicator import save_lead
from src.services.normalizer import NormalizedLead


def _lead(url):
    return NormalizedLead(
        name="Acme Ltd",
        normalized_name="acme",
        phone="+1 202 456 1111",
        normalized_phone="+12024561111",
        country="US",
        verification_status="verified",
        is_business_phone=True,
        source_url=url,
        source_type="test",
        keyword="parts",
    )


def test_same_company_phone_merges_sources():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        _, first_created = save_lead(session, _lead("https://a.example"), 1)
        _, second_created = save_lead(session, _lead("https://b.example"), 1)
        company = session.scalar(select(Company))
        assert first_created is True
        assert second_created is False
        assert len(company.sources) == 2
