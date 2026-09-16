from src.config import _load_config


def test_loads_utf8_config_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        '{"google_places_api_key": "test-key", "contact_email": "a@example.com"}',
        encoding="utf-8",
    )
    config = _load_config(path)
    assert config["google_places_api_key"] == "test-key"


def test_invalid_config_returns_empty_dict(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{invalid", encoding="utf-8")
    assert _load_config(path) == {}
