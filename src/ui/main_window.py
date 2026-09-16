from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.services.collector import CollectorService
from src.services.exporter import count_companies, export_companies, query_companies


class ProgressBridge(QObject):
    changed = Signal(int, str, int, int, str)

class ExportBridge(QObject):
    finished = Signal(int, str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("外贸客户采集软件")
        self.resize(1100, 720)
        self.collector = CollectorService()
        self.collector.recover_interrupted_tasks()
        self.bridge = ProgressBridge()
        self.bridge.changed.connect(self._on_progress)
        self.export_bridge = ExportBridge()
        self.export_bridge.finished.connect(self._on_export_finished)
        self.export_executor = ThreadPoolExecutor(max_workers=1)
        self.current_page = 1
        self.page_size = 500

        tabs = QTabWidget()
        tabs.addTab(self._build_tasks_tab(), "采集任务")
        tabs.addTab(self._build_results_tab(), "客户数据")
        self.setCentralWidget(tabs)
        self.refresh_tasks()
        self.refresh_results()

    def _build_tasks_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.task_name = QLineEdit()
        self.task_name.setPlaceholderText("例如：德国机械设备经销商")
        self.source = QComboBox()
        self.source.addItem(
            "多来源泛采集（Overture + OSM + Google可选）", "multi"
        )
        self.source.addItem("Overture Maps 官方开放数据", "overture")
        self.source.addItem("OpenStreetMap / Overpass", "openstreetmap")
        self.source.addItem("OpenStreetMap 国家PBF（大批量）", "osm_pbf")
        self.source.addItem("公开企业网页", "public_web")
        self.source.addItem("Google Places 官方 API（注意存储条款）", "google_places")
        self.country = QLineEdit()
        self.country.setPlaceholderText("Overture/OSM：国家、城市或地区，建议用城市缩小范围")
        self.query = QPlainTextEdit()
        self.query.setMaximumHeight(100)
        self.query.setPlaceholderText(
            "Overture：输入企业名称或行业分类关键词\n"
            "OSM：输入名称/行业关键词，或标签 key=value\n"
            "Google Places：每行输入一个产品或行业关键词，可输入多个\n"
            "公开网页：每行输入一个获准采集的企业页面 URL"
        )
        form.addRow("任务名称", self.task_name)
        form.addRow("数据来源", self.source)
        form.addRow("国家/地区", self.country)
        form.addRow("关键词或网址", self.query)
        self.bulk_mode = QCheckBox("国家批量模式（自动分片，支持多来源补充）")
        self.bulk_profile = QComboBox()
        self.bulk_profile.addItem("全部：所有带公开电话企业，采集后评分", "all")
        self.bulk_profile.addItem("大宗商品：金属、能源、农产品、化工", "commodity")
        self.bulk_profile.addItem("均衡：外贸、制造、批发、物流", "balanced")
        self.bulk_profile.addItem("严格：仅进出口、货代、报关", "strict")
        self.bulk_profile.addItem("宽泛：增加供应商和分销商", "broad")
        self.target_count = QSpinBox()
        self.target_count.setRange(1000, 1000000)
        self.target_count.setSingleStep(10000)
        self.target_count.setValue(100000)
        form.addRow("批量采集", self.bulk_mode)
        form.addRow("外贸相关性", self.bulk_profile)
        form.addRow("目标数量", self.target_count)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        for text, handler in (
            ("创建并开始", self.create_and_start),
            ("继续/开始", self.start_selected),
            ("暂停", self.pause_selected),
            ("取消", self.cancel_selected),
            ("重试失败任务", self.retry_selected),
            ("查看覆盖报告", self.show_report),
            ("刷新", self.refresh_tasks),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        splitter = QSplitter(Qt.Vertical)
        self.task_table = QTableWidget(0, 9)
        self.task_table.setHorizontalHeaderLabels(
            ["ID", "任务", "来源", "国家", "状态", "已处理", "任务客户", "重复", "分片进度"]
        )
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.task_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.task_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        splitter.addWidget(self.task_table)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        splitter.addWidget(self.log)
        splitter.setSizes([430, 130])
        layout.addWidget(splitter)
        return page

    def _build_results_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        filters = QHBoxLayout()
        self.filter_keyword = QLineEdit()
        self.filter_keyword.setPlaceholderText("公司名称")
        self.filter_task = QComboBox()
        self.filter_task.addItem("全部任务", "")
        self.filter_country = QLineEdit()
        self.filter_country.setPlaceholderText("国家/地区")
        self.filter_source = QComboBox()
        self.filter_source.addItem("全部来源", "")
        self.filter_source.addItem("Google Places", "google_places")
        self.filter_source.addItem("Overture Maps", "overture")
        self.filter_source.addItem("OpenStreetMap", "openstreetmap")
        self.filter_source.addItem("OSM 国家PBF", "osm_pbf")
        self.filter_source.addItem("公开网页", "public_web")
        self.filter_status = QComboBox()
        self.filter_status.addItem("全部状态", "")
        self.filter_status.addItem("已验证企业号码", "verified")
        self.filter_status.addItem("公开移动号码", "mobile")
        self.filter_status.addItem("待验证", "pending")
        self.filter_relevance = QComboBox()
        self.filter_relevance.addItem("全部相关性", "")
        self.filter_relevance.addItem("高相关", "high")
        self.filter_relevance.addItem("中相关", "medium")
        self.filter_relevance.addItem("低相关", "low")
        filters.addWidget(QLabel("筛选"))
        filters.addWidget(self.filter_task)
        filters.addWidget(self.filter_keyword)
        filters.addWidget(self.filter_country)
        filters.addWidget(self.filter_source)
        filters.addWidget(self.filter_status)
        filters.addWidget(self.filter_relevance)
        refresh = QPushButton("查询")
        refresh.clicked.connect(self.refresh_results)
        export = QPushButton("导出 Excel/CSV")
        export.clicked.connect(self.export_results)
        filters.addWidget(refresh)
        filters.addWidget(export)
        layout.addLayout(filters)

        self.result_table = QTableWidget(0, 8)
        self.result_table.setHorizontalHeaderLabels(
            ["公司名称", "企业电话", "国家", "验证状态", "行业", "相关性", "来源数", "采集时间"]
        )
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.result_table)
        paging = QHBoxLayout()
        previous = QPushButton("上一页")
        previous.clicked.connect(self.previous_page)
        next_page = QPushButton("下一页")
        next_page.clicked.connect(self.next_page)
        self.page_label = QLabel()
        paging.addStretch()
        paging.addWidget(previous)
        paging.addWidget(self.page_label)
        paging.addWidget(next_page)
        layout.addLayout(paging)
        return page

    def create_and_start(self) -> None:
        name = self.task_name.text().strip()
        is_bulk = self.bulk_mode.isChecked()
        query = (
            self.bulk_profile.currentData()
            if is_bulk
            else self.query.toPlainText().strip()
        )
        if not name or not query or not self.country.text().strip():
            QMessageBox.warning(self, "参数不完整", "请填写任务名称和关键词/网址。")
            return
        if is_bulk and self.source.currentData() not in ("overture", "multi"):
            QMessageBox.warning(
                self,
                "数据源不支持",
                "国家批量模式请选择“多来源泛采集”或 Overture。",
            )
            return
        task_id = self.collector.create_task(
            name,
            self.source.currentData(),
            query,
            self.country.text().strip(),
            mode="bulk" if is_bulk else "single",
            target_count=self.target_count.value(),
        )
        self._append_log("已创建任务 #{}：{}".format(task_id, name))
        self.collector.start(task_id, self.bridge.changed.emit)
        self.refresh_tasks()

    def _selected_task_id(self):
        row = self.task_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "请选择任务", "请先选择一行任务。")
            return None
        return int(self.task_table.item(row, 0).text())

    def start_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id is not None:
            self.collector.resume(task_id, self.bridge.changed.emit)
            self._append_log("任务 #{} 已继续".format(task_id))

    def pause_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id is not None:
            self.collector.pause(task_id)
            self.refresh_tasks()

    def cancel_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id is not None:
            self.collector.cancel(task_id)
            self.refresh_tasks()

    def retry_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id is not None:
            self.collector.retry(task_id, self.bridge.changed.emit)
            self._append_log("任务 #{} 正在重试".format(task_id))

    def show_report(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            return
        report = self.collector.get_report(task_id)
        if not report:
            QMessageBox.information(self, "覆盖报告", "任务尚未生成覆盖报告。")
            return
        text = (
            "国家/地区：{country}\n目标：{target_count}\n"
            "已处理：{processed}\n任务唯一客户：{unique_collected}\n"
            "重复：{duplicates}\n无效：{invalid}\n"
            "完成分片：{shards_completed}/{shards_total}\n"
            "失败分片：{shards_failed}\n目标缺口：{shortfall}"
        ).format(**report)
        QMessageBox.information(self, "覆盖报告", text)

    def refresh_tasks(self) -> None:
        tasks = self.collector.list_tasks()
        selected_task_id = self.filter_task.currentData() if hasattr(self, "filter_task") else ""
        self.filter_task.blockSignals(True)
        self.filter_task.clear()
        self.filter_task.addItem("全部任务", "")
        for task in tasks:
            self.filter_task.addItem("{} (#{})".format(task.name, task.id), str(task.id))
        index = self.filter_task.findData(selected_task_id)
        self.filter_task.setCurrentIndex(index if index >= 0 else 0)
        self.filter_task.blockSignals(False)
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            values = [
                task.id,
                task.name,
                task.source_type,
                task.country,
                task.status,
                task.processed,
                task.collected,
                task.duplicate_count,
                "{}/{}".format(task.shard_completed, task.shard_total),
            ]
            for column, value in enumerate(values):
                self.task_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _filters(self):
        return {
            "task_id": self.filter_task.currentData(),
            "keyword": self.filter_keyword.text().strip(),
            "country": self.filter_country.text().strip(),
            "source_type": self.filter_source.currentData(),
            "status": self.filter_status.currentData(),
            "relevance": self.filter_relevance.currentData(),
        }

    def refresh_results(self, *_args) -> None:
        filters = self._filters()
        total = count_companies(**filters)
        max_page = max(1, (total + self.page_size - 1) // self.page_size)
        self.current_page = min(self.current_page, max_page)
        companies = query_companies(
            **filters, page=self.current_page, page_size=self.page_size
        )
        self.result_table.setRowCount(len(companies))
        for row, company in enumerate(companies):
            values = [
                company.name,
                company.normalized_phone,
                company.country,
                company.verification_status,
                company.category,
                company.relevance,
                len(company.sources),
                company.collected_at.strftime("%Y-%m-%d %H:%M"),
            ]
            for column, value in enumerate(values):
                self.result_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.page_label.setText(
            "第 {}/{} 页，共 {} 条".format(self.current_page, max_page, total)
        )

    def previous_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_results()

    def next_page(self) -> None:
        total = count_companies(**self._filters())
        if self.current_page * self.page_size < total:
            self.current_page += 1
            self.refresh_results()

    def export_results(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出客户数据", "外贸客户.xlsx", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        self._append_log("开始后台导出：{}".format(path))
        future = self.export_executor.submit(export_companies, path, self._filters())
        future.add_done_callback(
            lambda item: self.export_bridge.finished.emit(
                item.result() if not item.exception() else 0,
                str(item.exception() or ""),
            )
        )

    def _on_export_finished(self, count: int, error: str) -> None:
        if error:
            QMessageBox.critical(self, "导出失败", error)
        else:
            QMessageBox.information(self, "导出完成", "已导出 {} 条客户数据。".format(count))

    def _on_progress(
        self, task_id: int, status: str, processed: int, collected: int, message: str
    ) -> None:
        text = "任务 #{} {}：处理 {}，新增 {}".format(
            task_id, status, processed, collected
        )
        if message:
            text += "，{}".format(message)
        self._append_log(text)
        self.refresh_tasks()

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText("[{}] {}".format(timestamp, message))

    def closeEvent(self, event) -> None:
        self.collector.shutdown()
        self.export_executor.shutdown(wait=False)
        event.accept()
