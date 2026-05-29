import json
from typing import Any

from app_config import settings_path


DEFAULT_SETTINGS: dict[str, Any] = {
    "selected_input_device_index": None,
    "vad_preset": "classroom",
    "vad_threshold": 0.6,
    "min_volume": 0.05,
    "silence_padding": 20,
    "min_speech_chunks": 5,
    "min_text_chars": 2,
    "dedup_window_seconds": 8,
}


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return DEFAULT_SETTINGS.copy()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        data = DEFAULT_SETTINGS.copy()
        if isinstance(loaded, dict):
            data.update(loaded)
        return data
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict[str, Any]) -> None:
    data = DEFAULT_SETTINGS.copy()
    data.update(settings)
    settings_path().write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
