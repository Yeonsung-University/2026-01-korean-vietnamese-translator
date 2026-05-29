import base64
import ctypes
import os
from ctypes import wintypes

from app_config import secure_dir


KEY_FILE = secure_dir() / "groq_api_key.dpapi"


class SecureStoreError(RuntimeError):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    blob._buffer = buffer  # type: ignore[attr-defined]
    return blob


def _require_windows() -> None:
    if os.name != "nt":
        raise SecureStoreError("DPAPI secure storage is only available on Windows.")


def _protect(data: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "Groq API key",
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise SecureStoreError("CryptProtectData failed.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _unprotect(data: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise SecureStoreError("CryptUnprotectData failed.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def save_api_key(api_key: str) -> None:
    encrypted = _protect(api_key.encode("utf-8"))
    KEY_FILE.write_text(base64.b64encode(encrypted).decode("ascii"), encoding="ascii")


def load_api_key() -> str | None:
    if not KEY_FILE.exists():
        return None
    raw = base64.b64decode(KEY_FILE.read_text(encoding="ascii"))
    return _unprotect(raw).decode("utf-8")


def delete_api_key() -> None:
    try:
        KEY_FILE.unlink()
    except FileNotFoundError:
        pass


def has_saved_api_key() -> bool:
    return KEY_FILE.exists()
