import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app_config import sessions_dir


SESSION_ID = datetime.now().strftime("%Y%m%d-%H%M%S")


def session_path() -> Path:
    return sessions_dir() / f"{SESSION_ID}-session.json"


def save_session(history: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> None:
    payload = {
        "session_id": SESSION_ID,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "metadata": metadata or {},
        "items": history,
    }
    session_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_sessions() -> list[dict[str, Any]]:
    items = []
    for path in sorted(sessions_dir().glob("*-session.json"), reverse=True):
        items.append({
            "id": path.stem.replace("-session", ""),
            "file": path.name,
            "size": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return items
