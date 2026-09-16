import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from src.config import APP_DIR
from src.db.session import init_db
from src.ui.main_window import MainWindow


def _configure_logging() -> None:
    logging.basicConfig(
        filename=str(APP_DIR / "collector.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> int:
    _configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("外贸客户采集软件")
    try:
        init_db()
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as exc:
        logging.exception("程序启动失败")
        QMessageBox.critical(None, "启动失败", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
