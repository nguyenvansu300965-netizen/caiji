"""10万条批量写入基准，不读取或修改正式数据库。"""

import os
import tempfile
import time

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, CollectionTask, Company
from src.services.deduplicator import batch_save_leads
from src.services.normalizer import NormalizedLead
from src.services import exporter


def main():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    engine = create_engine("sqlite:///{}".format(path))
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    started = time.monotonic()
    try:
        with Session() as session:
            task = CollectionTask(
                name="100k benchmark",
                source_type="benchmark",
                query="balanced",
                country="XX",
                mode="bulk",
            )
            session.add(task)
            session.commit()
            for start in range(0, 100000, 400):
                leads = []
                for index in range(start, min(start + 400, 100000)):
                    phone = "+999{:09d}".format(index)
                    leads.append(
                        NormalizedLead(
                            name="Company {}".format(index),
                            normalized_name="company {}".format(index),
                            phone=phone,
                            normalized_phone=phone,
                            country="XX",
                            verification_status="pending",
                            is_business_phone=True,
                            source_url="https://benchmark/{}".format(index),
                            source_type="benchmark",
                            keyword="balanced",
                            external_id=str(index),
                            category="wholesaler",
                        )
                    )
                batch_save_leads(session, leads, task.id)
                session.commit()
            count = session.scalar(select(func.count(Company.id)))
        elapsed = time.monotonic() - started
        print("rows={} elapsed={:.2f}s rate={:.0f}/s".format(
            count, elapsed, count / elapsed
        ))
        export_path = path + ".csv"
        exporter.SessionLocal = Session
        export_started = time.monotonic()
        exported = exporter.export_companies(export_path, {})
        export_elapsed = time.monotonic() - export_started
        print(
            "exported={} elapsed={:.2f}s size_mb={:.1f}".format(
                exported, export_elapsed, os.path.getsize(export_path) / 1024 / 1024
            )
        )
        os.remove(export_path)
    finally:
        engine.dispose()
        os.remove(path)


if __name__ == "__main__":
    main()
