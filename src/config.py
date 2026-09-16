from dataclasses import dataclass
from pathlib import Path
import json
import os
import sys


APP_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "TradeLeadCollector"
APP_DIR.mkdir(parents=True, exist_ok=True)


def _config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config.json"
    return Path(__file__).resolve().parents[1] / "config.json"


def _ensure_config_file(path: Path) -> None:
    if path.exists() or not getattr(sys, "frozen", False):
        return
    try:
        path.write_text(
            json.dumps(
                {
                    "google_places_api_key": "",
                    "contact_email": "",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _load_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


CONFIG_PATH = _config_path()
_ensure_config_file(CONFIG_PATH)
FILE_CONFIG = _load_config(CONFIG_PATH)


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///" + str(APP_DIR / "collector.db")
    google_places_api_key: str = os.getenv("GOOGLE_PLACES_API_KEY", "") or str(
        FILE_CONFIG.get("google_places_api_key", "")
    ).strip()
    request_timeout: float = 20.0
    max_workers: int = 3
    per_domain_delay: float = 1.5
    max_retries: int = 3
    batch_size: int = 400
    page_size: int = 500
    bulk_page_size: int = 5000
    max_grid_tiles: int = 144
    progress_interval: float = 0.75
    bulk_target_count: int = 100000
    contact_email: str = os.getenv("COLLECTOR_CONTACT_EMAIL", "") or str(
        FILE_CONFIG.get("contact_email", "")
    ).strip()

    @property
    def user_agent(self) -> str:
        contact = (
            "mailto:{}".format(self.contact_email)
            if self.contact_email
            else "local-desktop-application"
        )
        return "TradeLeadCollector/0.1 (+{}; respects robots.txt)".format(contact)


settings = Settings()
