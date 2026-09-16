from dataclasses import replace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, CollectionTask, QualityReport, TaskShard
from src.services import collector
from src.sources.base import LeadRecord


def test_bulk_collector_creates_shards_and_completes(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(collector, "SessionLocal", Session)
    monkeypatch.setattr(
        collector,
        "resolve_location",
        lambda _country: (13.0, 52.0, 13.1, 52.1, "DE"),
    )

    class FakeOverture:
        def __init__(self, **_kwargs):
            pass

        def query_page(self, keyword, relevance, **_kwargs):
            return (
                [
                    LeadRecord(
                        company_name="Trade GmbH",
                        phone="+4930123456",
                        country="DE",
                        source_url="https://source?id=1",
                        source_type="overture",
                        keyword=keyword,
                        external_id="1",
                        category="import_export_company",
                        relevance=relevance,
                    )
                ],
                "1",
                1,
            )

        def close(self):
            pass

    monkeypatch.setattr(collector, "OvertureMapsSource", FakeOverture)
    with Session() as session:
        task = CollectionTask(
            name="Germany bulk",
            source_type="overture",
            query="strict",
            country="DE",
            mode="bulk",
            target_count=10,
        )
        session.add(task)
        session.commit()
        task_id = task.id

    service = collector.CollectorService()
    service._run(task_id, collector.TaskControl(), None)
    service.executor.shutdown(wait=True)

    with Session() as session:
        task = session.get(CollectionTask, task_id)
        assert task.status == "completed"
        assert task.collected == 1
        assert task.shard_completed == task.shard_total
        assert session.scalar(select(func.count(TaskShard.id))) == task.shard_total
        assert session.scalar(select(func.count(QualityReport.id))) == 1


def test_multi_bulk_adds_openstreetmap_results(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(collector, "SessionLocal", Session)
    monkeypatch.setattr(
        collector,
        "resolve_location",
        lambda _country: (114.0, 22.2, 114.1, 22.3, "HK"),
    )

    class FakeOverture:
        def __init__(self, **_kwargs):
            pass

        def query_page(self, keyword, relevance, **_kwargs):
            return (
                [
                    LeadRecord(
                        company_name="Alpha Trading",
                        phone="+85221234567",
                        country="HK",
                        source_url="https://overture.example/1",
                        source_type="overture",
                        keyword=keyword,
                        relevance=relevance,
                    )
                ],
                "1",
                1,
            )

        def close(self):
            pass

    class FakeOsm:
        def collect(self, query, country):
            assert query == ""
            yield LeadRecord(
                company_name="Beta Limited",
                phone="+85229876543",
                country=country,
                source_url="https://openstreetmap.org/node/2",
                source_type="openstreetmap",
                keyword="",
            )

    monkeypatch.setattr(collector, "OvertureMapsSource", FakeOverture)
    monkeypatch.setattr(
        collector,
        "settings",
        replace(collector.settings, google_places_api_key=""),
    )
    with Session() as session:
        task = CollectionTask(
            name="Hong Kong multi",
            source_type="multi",
            query="all",
            country="HK",
            mode="bulk",
            target_count=10,
        )
        session.add(task)
        session.commit()
        task_id = task.id

    service = collector.CollectorService()
    monkeypatch.setattr(service, "_adapter", lambda _source, _control: FakeOsm())
    service._run(task_id, collector.TaskControl(), None)
    service.executor.shutdown(wait=True)

    with Session() as session:
        task = session.get(CollectionTask, task_id)
        assert task.source_type == "multi"
        assert task.status == "completed"
        assert task.collected == 2
        assert "Overture、OpenStreetMap" in task.error_message
