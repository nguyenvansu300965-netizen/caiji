import threading
import json
from datetime import datetime
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, Optional

from sqlalchemy import func, select, update

from src.config import settings
from src.db.models import CollectionTask, FailureRecord, QualityReport, TaskShard
from src.db.session import SessionLocal
from src.services.deduplicator import batch_save_leads
from src.services.normalizer import normalize_lead
from src.services.partition import subdivide_bbox
from src.services.quality_report import build_quality_report
from src.sources.base import CollectionCancelled, SourceAdapter
from src.sources.google_places import GooglePlacesSource
from src.sources.osm_overpass import OpenStreetMapSource
from src.sources.osm_pbf import OsmPbfSource
from src.sources.overture import OvertureMapsSource
from src.sources.public_web import PublicWebSource
from src.sources.geocoding import resolve_location
from src.sources.trade_taxonomy import terms_for_profile


ProgressCallback = Callable[[int, str, int, int, str], None]


class TaskControl:
    def __init__(self):
        self.cancel = threading.Event()
        self.run = threading.Event()
        self.shutdown_requested = False
        self.run.set()


class CollectorService:
    def __init__(self):
        self.executor = ThreadPoolExecutor(
            max_workers=settings.max_workers, thread_name_prefix="collector"
        )
        self.controls: Dict[int, TaskControl] = {}
        self.futures: Dict[int, Future] = {}
        self._lock = threading.Lock()

    def recover_interrupted_tasks(self) -> None:
        with SessionLocal() as session:
            session.execute(
                update(CollectionTask)
                .where(CollectionTask.status == "running")
                .values(status="paused", error_message="程序上次退出，任务已安全暂停")
            )
            session.execute(
                update(TaskShard)
                .where(TaskShard.status == "running")
                .values(status="pending", error_message="程序退出后等待恢复")
            )
            session.commit()

    def create_task(
        self,
        name: str,
        source_type: str,
        query: str,
        country: str,
        mode: str = "single",
        target_count: int = 100000,
    ) -> int:
        with SessionLocal() as session:
            task = CollectionTask(
                name=name,
                source_type=source_type,
                query=query,
                country=country,
                mode=mode,
                target_count=target_count,
            )
            session.add(task)
            session.commit()
            return task.id

    def start(self, task_id: int, callback: Optional[ProgressCallback] = None) -> None:
        with self._lock:
            future = self.futures.get(task_id)
            if future and not future.done():
                self.resume(task_id)
                return
            control = TaskControl()
            self.controls[task_id] = control
            self.futures[task_id] = self.executor.submit(
                self._run, task_id, control, callback
            )

    def pause(self, task_id: int) -> None:
        control = self.controls.get(task_id)
        if control:
            control.run.clear()
            self._set_status(task_id, "paused")

    def resume(self, task_id: int, callback: Optional[ProgressCallback] = None) -> None:
        control = self.controls.get(task_id)
        future = self.futures.get(task_id)
        if control and future and not future.done():
            control.run.set()
            self._set_status(task_id, "running")
        else:
            self.start(task_id, callback)

    def cancel(self, task_id: int) -> None:
        control = self.controls.get(task_id)
        if control:
            control.cancel.set()
            control.run.set()
        self._set_status(task_id, "cancelled")

    def retry(self, task_id: int, callback: Optional[ProgressCallback] = None) -> None:
        with SessionLocal() as session:
            task = session.get(CollectionTask, task_id)
            if task:
                task.error_message = ""
                task.status = "pending"
                session.commit()
        self.start(task_id, callback)

    def shutdown(self) -> None:
        for task_id, control in list(self.controls.items()):
            control.shutdown_requested = True
            control.cancel.set()
            control.run.set()
            self._set_status(task_id, "paused")
        self.executor.shutdown(wait=False)

    def _run(
        self, task_id: int, control: TaskControl, callback: Optional[ProgressCallback]
    ) -> None:
        with SessionLocal() as session:
            task = session.get(CollectionTask, task_id)
            if not task:
                return
            task.status = "running"
            task.error_message = ""
            task.started_at = task.started_at or datetime.utcnow()
            session.commit()
            try:
                if task.mode == "bulk" and task.source_type == "multi":
                    self._run_multi_bulk(session, task, control, callback)
                    return
                if task.mode == "bulk" and task.source_type == "overture":
                    self._run_overture_bulk(session, task, control, callback)
                    return
                if task.source_type == "multi":
                    self._run_multi_single(session, task, control, callback)
                    return
                adapter = self._adapter(task.source_type, control)
                buffer = []
                for raw_lead in adapter.collect(task.query, task.country):
                    while not control.run.wait(timeout=0.25):
                        if control.cancel.is_set():
                            raise CollectionCancelled()
                    if control.cancel.is_set():
                        raise CollectionCancelled()
                    lead = normalize_lead(raw_lead)
                    task.processed += 1
                    if (
                        lead.normalized_name
                        and lead.normalized_phone
                        and lead.verification_status != "invalid"
                    ):
                        buffer.append(lead)
                    else:
                        task.invalid_count += 1
                    remaining = max(task.target_count - task.collected, 1)
                    if len(buffer) >= min(settings.batch_size, remaining):
                        self._flush_buffer(session, task, buffer)
                        self._notify(callback, task, "")
                        if task.collected >= task.target_count:
                            break
                if buffer:
                    self._flush_buffer(session, task, buffer)
                task.status = "completed"
                task.finished_at = datetime.utcnow()
                session.commit()
                self._notify(callback, task, "")
            except CollectionCancelled:
                task.status = "paused" if control.shutdown_requested else "cancelled"
                session.commit()
                self._notify(
                    callback,
                    task,
                    "程序退出，任务已保存断点"
                    if control.shutdown_requested
                    else "任务已取消",
                )
            except Exception as exc:
                task.status = "failed"
                task.error_message = str(exc)
                session.add(
                    FailureRecord(
                        task_id=task.id,
                        target=task.query,
                        error_type=type(exc).__name__,
                        message=str(exc),
                        retry_count=settings.max_retries,
                    )
                )
                session.commit()
                self._notify(callback, task, str(exc))

    def _run_multi_single(
        self,
        session,
        task: CollectionTask,
        control: TaskControl,
        callback: Optional[ProgressCallback],
    ) -> None:
        sources = [
            ("overture", task.query),
            ("openstreetmap", task.query),
        ]
        if settings.google_places_api_key:
            sources.append(("google_places", task.query))
        failures = self._collect_supplemental_sources(
            session, task, control, callback, sources
        )
        task.status = "partial" if failures else "completed"
        task.finished_at = datetime.utcnow()
        task.error_message = (
            "部分来源失败：{}".format("、".join(failures)) if failures else ""
        )
        session.commit()
        self._notify(callback, task, task.error_message)

    def _run_multi_bulk(
        self,
        session,
        task: CollectionTask,
        control: TaskControl,
        callback: Optional[ProgressCallback],
    ) -> None:
        self._run_overture_bulk(session, task, control, callback)
        if task.status in ("paused", "cancelled", "failed"):
            return

        overture_partial = task.status == "partial"
        failures = []
        if task.collected < task.target_count:
            task.status = "running"
            task.finished_at = None
            session.commit()
            sources = [("openstreetmap", "")]
            if settings.google_places_api_key:
                sources.extend(
                    ("google_places", query)
                    for query in (
                        "company",
                        "manufacturer",
                        "wholesaler",
                        "supplier",
                        "import export company",
                        "logistics company",
                    )
                )
            failures = self._collect_supplemental_sources(
                session, task, control, callback, sources
            )

        build_quality_report(session, task)
        task.status = "partial" if overture_partial or failures else "completed"
        task.finished_at = datetime.utcnow()
        source_note = "已联合采集 Overture、OpenStreetMap"
        if settings.google_places_api_key:
            source_note += "、Google Places"
        else:
            source_note += "；未配置 Google Places 密钥，已自动跳过"
        if failures:
            source_note += "；失败来源：{}".format("、".join(failures))
        if task.collected < task.target_count:
            source_note += "；距目标还差 {} 条".format(
                task.target_count - task.collected
            )
        task.error_message = source_note
        session.commit()
        self._notify(callback, task, source_note)

    def _collect_supplemental_sources(
        self,
        session,
        task: CollectionTask,
        control: TaskControl,
        callback: Optional[ProgressCallback],
        sources,
    ):
        failures = []
        for source_type, query in sources:
            if task.collected >= task.target_count:
                break
            self._wait_for_control(control)
            self._notify(callback, task, "正在补充来源：{}".format(source_type))
            adapter = self._adapter(source_type, control)
            buffer = []
            try:
                for raw_lead in adapter.collect(query, task.country):
                    self._wait_for_control(control)
                    lead = normalize_lead(raw_lead)
                    task.processed += 1
                    if (
                        lead.normalized_name
                        and lead.normalized_phone
                        and lead.verification_status != "invalid"
                    ):
                        buffer.append(lead)
                    else:
                        task.invalid_count += 1
                    if len(buffer) >= settings.batch_size:
                        self._flush_buffer(session, task, buffer)
                        self._notify(callback, task, source_type)
                        if task.collected >= task.target_count:
                            break
                if buffer:
                    self._flush_buffer(session, task, buffer)
            except CollectionCancelled:
                raise
            except Exception as exc:
                failures.append(source_type)
                session.add(
                    FailureRecord(
                        task_id=task.id,
                        target="{}:{}".format(source_type, query or "all"),
                        error_type=type(exc).__name__,
                        message=str(exc),
                        retry_count=settings.max_retries,
                    )
                )
                session.commit()
                self._notify(
                    callback,
                    task,
                    "{} 来源失败，继续其他来源：{}".format(source_type, exc),
                )
            finally:
                close = getattr(adapter, "close", None)
                if close:
                    close()
        return failures

    @staticmethod
    def _flush_buffer(session, task: CollectionTask, buffer: list) -> None:
        _created, duplicates, task_new = batch_save_leads(
            session, buffer, task.id
        )
        task.collected += task_new
        task.duplicate_count += duplicates
        buffer.clear()
        session.add(task)
        session.commit()

    def _run_overture_bulk(
        self,
        session,
        task: CollectionTask,
        control: TaskControl,
        callback: Optional[ProgressCallback],
    ) -> None:
        self._prepare_bulk_shards(session, task)
        adapter = OvertureMapsSource(is_cancelled=control.cancel.is_set)
        try:
            while task.collected < task.target_count:
                self._wait_for_control(control)
                shard = session.scalar(
                    select(TaskShard)
                    .where(
                        TaskShard.task_id == task.id,
                        TaskShard.status.in_(("pending", "failed")),
                        TaskShard.retry_count < settings.max_retries,
                    )
                    .order_by(TaskShard.id)
                )
                if shard is None:
                    break
                shard.status = "running"
                shard.error_message = ""
                session.commit()
                try:
                    while True:
                        self._wait_for_control(control)
                        page_limit = settings.bulk_page_size
                        leads, next_cursor, row_count = adapter.query_page(
                            keyword=shard.keyword,
                            match_type=shard.match_type,
                            relevance=self._term_relevance(task.query, shard.keyword),
                            west=shard.west,
                            south=shard.south,
                            east=shard.east,
                            north=shard.north,
                            cursor=shard.cursor,
                            limit=page_limit,
                        )
                        normalized = [normalize_lead(lead) for lead in leads]
                        valid = [
                            lead
                            for lead in normalized
                            if lead.normalized_name
                            and lead.normalized_phone
                            and lead.verification_status != "invalid"
                        ]
                        duplicates, task_new = self._save_valid_batches(
                            session, valid, task.id
                        )
                        task.processed += len(normalized)
                        task.collected += task_new
                        task.duplicate_count += duplicates
                        task.invalid_count += len(normalized) - len(valid)
                        shard.processed += len(normalized)
                        shard.collected += task_new
                        shard.cursor = next_cursor
                        if row_count < page_limit:
                            shard.status = "completed"
                        session.commit()
                        self._refresh_shard_progress(session, task)
                        self._notify(
                            callback,
                            task,
                            "分片 {}/{}".format(
                                task.shard_completed, task.shard_total
                            ),
                        )
                        if (
                            row_count < page_limit
                            or task.collected >= task.target_count
                        ):
                            break
                    if task.collected >= task.target_count:
                        session.execute(
                            update(TaskShard)
                            .where(
                                TaskShard.task_id == task.id,
                                TaskShard.status == "pending",
                            )
                            .values(status="skipped")
                        )
                        session.commit()
                except CollectionCancelled:
                    raise
                except Exception as exc:
                    shard.status = "failed"
                    shard.retry_count += 1
                    shard.error_message = str(exc)
                    session.add(
                        FailureRecord(
                            task_id=task.id,
                            target="{}:{}".format(shard.tile_key, shard.keyword),
                            error_type=type(exc).__name__,
                            message=str(exc),
                            retry_count=shard.retry_count,
                        )
                    )
                    session.commit()
            self._refresh_shard_progress(session, task)
            build_quality_report(session, task)
            failed = session.scalar(
                select(func.count(TaskShard.id)).where(
                    TaskShard.task_id == task.id, TaskShard.status == "failed"
                )
            ) or 0
            task.status = "partial" if failed else "completed"
            task.finished_at = datetime.utcnow()
            if failed:
                task.error_message = "{} 个分片失败，可点击重试".format(failed)
            elif task.collected < task.target_count:
                task.error_message = "已采集全部可用数据，距目标还差 {} 条".format(
                    task.target_count - task.collected
                )
            else:
                task.error_message = "已达到目标数量"
            session.commit()
            self._notify(callback, task, task.error_message)
        except CollectionCancelled:
            task.status = "paused" if control.shutdown_requested else "cancelled"
            session.commit()
            self._notify(
                callback,
                task,
                "程序退出，任务已保存断点"
                if control.shutdown_requested
                else "任务已取消",
            )
        finally:
            adapter.close()

    @staticmethod
    def _save_valid_batches(session, leads: list, task_id: int):
        duplicates = 0
        task_new = 0
        for start in range(0, len(leads), settings.batch_size):
            _created, batch_duplicates, batch_task_new = batch_save_leads(
                session, leads[start : start + settings.batch_size], task_id
            )
            duplicates += batch_duplicates
            task_new += batch_task_new
        return duplicates, task_new

    @staticmethod
    def _wait_for_control(control: TaskControl) -> None:
        while not control.run.wait(timeout=0.25):
            if control.cancel.is_set():
                raise CollectionCancelled()
        if control.cancel.is_set():
            raise CollectionCancelled()

    @staticmethod
    def _term_relevance(profile: str, keyword: str) -> str:
        for term in terms_for_profile(profile):
            if term.value == keyword:
                return term.relevance
        return "medium"

    @staticmethod
    def _refresh_shard_progress(session, task: CollectionTask) -> None:
        task.shard_completed = session.scalar(
            select(func.count(TaskShard.id)).where(
                TaskShard.task_id == task.id,
                TaskShard.status.in_(("completed", "skipped")),
            )
        ) or 0
        session.commit()

    @staticmethod
    def _prepare_bulk_shards(session, task: CollectionTask) -> None:
        existing = session.scalar(
            select(func.count(TaskShard.id)).where(TaskShard.task_id == task.id)
        ) or 0
        if existing:
            task.shard_total = existing
            session.commit()
            return
        west, south, east, north, _country_code = resolve_location(task.country)
        tiles = subdivide_bbox(
            west, south, east, north, max_tiles=settings.max_grid_tiles
        )
        terms = terms_for_profile(task.query)
        shards = [
            TaskShard(
                task_id=task.id,
                source_type="overture",
                tile_key=tile.key,
                keyword=term.value,
                match_type=term.match_type,
                west=tile.west,
                south=tile.south,
                east=tile.east,
                north=tile.north,
            )
            for tile in tiles
            for term in terms
        ]
        session.add_all(shards)
        task.shard_total = len(shards)
        session.commit()

    @staticmethod
    def _adapter(source_type: str, control: TaskControl) -> SourceAdapter:
        cancelled = control.cancel.is_set
        if source_type == GooglePlacesSource.source_type:
            return GooglePlacesSource(is_cancelled=cancelled)
        if source_type == PublicWebSource.source_type:
            return PublicWebSource(is_cancelled=cancelled)
        if source_type == OpenStreetMapSource.source_type:
            return OpenStreetMapSource(is_cancelled=cancelled)
        if source_type == OvertureMapsSource.source_type:
            return OvertureMapsSource(is_cancelled=cancelled)
        if source_type == OsmPbfSource.source_type:
            return OsmPbfSource(is_cancelled=cancelled)
        raise ValueError("未知数据源: {}".format(source_type))

    @staticmethod
    def _notify(
        callback: Optional[ProgressCallback], task: CollectionTask, message: str
    ) -> None:
        if callback:
            callback(task.id, task.status, task.processed, task.collected, message)

    @staticmethod
    def _set_status(task_id: int, status: str) -> None:
        with SessionLocal() as session:
            task = session.get(CollectionTask, task_id)
            if task:
                task.status = status
                session.commit()

    @staticmethod
    def list_tasks():
        with SessionLocal() as session:
            return list(
                session.scalars(
                    select(CollectionTask).order_by(CollectionTask.created_at.desc())
                )
            )

    @staticmethod
    def get_report(task_id: int):
        with SessionLocal() as session:
            report = session.scalar(
                select(QualityReport).where(QualityReport.task_id == task_id)
            )
            return json.loads(report.metrics_json) if report else None
