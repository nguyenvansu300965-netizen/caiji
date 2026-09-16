import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import CollectionTask, QualityReport, TaskShard


def build_quality_report(session: Session, task: CollectionTask) -> dict:
    failed = session.scalar(
        select(func.count(TaskShard.id)).where(
            TaskShard.task_id == task.id, TaskShard.status == "failed"
        )
    ) or 0
    metrics = {
        "task_id": task.id,
        "country": task.country,
        "target_count": task.target_count,
        "processed": task.processed,
        "unique_collected": task.collected,
        "duplicates": task.duplicate_count,
        "invalid": task.invalid_count,
        "shards_total": task.shard_total,
        "shards_completed": task.shard_completed,
        "shards_failed": failed,
        "shortfall": max(task.target_count - task.collected, 0),
        "coverage_status": (
            "target_reached" if task.collected >= task.target_count else "all_available"
        ),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    report = session.scalar(
        select(QualityReport).where(QualityReport.task_id == task.id)
    )
    if report is None:
        report = QualityReport(task_id=task.id, metrics_json="")
        session.add(report)
    report.metrics_json = json.dumps(metrics, ensure_ascii=False)
    return metrics
