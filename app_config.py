import os
import sys
from pathlib import Path


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_NAME = "KoreanVietnameseTranslator"
PRODUCT_NAME = "Korean-Vietnamese Live Translator"
COMPANY_NAME = "Local Classroom Tools"
APP_VERSION = "1.2.0"
BUILD_TYPE = os.environ.get("KVT_BUILD_TYPE", "portable")

HOST = "0.0.0.0"
PORT = int(os.environ.get("KVT_PORT", "8000"))


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".config"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def secure_dir() -> Path:
    path = app_data_dir() / "secure"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sessions_dir() -> Path:
    path = app_data_dir() / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / name
    return Path(__file__).resolve().parent / name


def settings_path() -> Path:
    return app_data_dir() / "settings.json"
