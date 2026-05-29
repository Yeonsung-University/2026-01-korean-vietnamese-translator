"""
FastAPI + WebSocket live Korean-to-Vietnamese translation server.

Microphone -> Silero VAD -> faster-whisper -> Groq -> host/guest browser UI.
The file intentionally keeps the existing runtime shape while adding diagnostics,
secure API-key handling, QR generation, audio-device selection, and safer logs.
"""
import os
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import asyncio
import csv
import difflib
import io
import json
import platform
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import numpy as np
import pyaudiowpatch as pyaudio
import torch
import uvicorn
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from faster_whisper import WhisperModel
from groq import Groq

try:
    import qrcode
except Exception:  # pragma: no cover - exercised only when dependency is missing.
    qrcode = None

from app_config import (
    APP_NAME,
    APP_VERSION,
    BUILD_TYPE,
    COMPANY_NAME,
    HOST,
    PORT,
    PRODUCT_NAME,
    resource_path,
)
from audio_devices import default_input_index, input_device_exists, list_input_devices
from history_store import SESSION_ID, list_sessions, save_session
from logging_utils import logger, mask_sensitive, recent_errors, record_error, tail_log
from network_utils import can_bind, guest_url, lan_ip_candidates, local_url, port_accepts_connections, primary_lan_ip
from secure_store import delete_api_key, has_saved_api_key, load_api_key, save_api_key
from settings_store import load_settings, save_settings


log = logger()

# Basic runtime settings
SAMPLE_RATE = 16000
CHUNK_MS = 32
CHUNK_SAMPLES = 512
WHISPER_MODEL_SIZE = "base"
WHISPER_LANGUAGE = "ko"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_API_KEY_NAME = "GROQ_API_KEY"


AUDIO_PRESETS: dict[str, dict[str, Any]] = {
    "quiet": {
        "label": "조용한 방",
        "description": "작은 목소리도 잡도록 민감도를 높입니다.",
        "vad_threshold": 0.48,
        "min_volume": 0.025,
        "silence_padding": 24,
        "min_speech_chunks": 4,
    },
    "classroom": {
        "label": "일반 강의실",
        "description": "강의실에서 무난한 기본값입니다.",
        "vad_threshold": 0.6,
        "min_volume": 0.05,
        "silence_padding": 20,
        "min_speech_chunks": 5,
    },
    "noisy": {
        "label": "시끄러운 현장",
        "description": "배경 소음으로 인한 오인식을 줄입니다.",
        "vad_threshold": 0.72,
        "min_volume": 0.08,
        "silence_padding": 16,
        "min_speech_chunks": 6,
    },
}


settings = load_settings()


class PipelineConfig:
    vad_threshold: float = float(settings["vad_threshold"])
    min_volume: float = float(settings["min_volume"])
    silence_padding: int = int(settings["silence_padding"])
    min_speech_chunks: int = int(settings["min_speech_chunks"])
    min_text_chars: int = int(settings["min_text_chars"])
    dedup_window_seconds: int = int(settings["dedup_window_seconds"])
    vad_preset: str = str(settings["vad_preset"])


config = PipelineConfig()


result_history: list[dict[str, Any]] = []
is_mic_muted = False
last_processing_ms: int | None = None

_settings_lock = threading.Lock()
_audio_lock = threading.Lock()
_selected_input_device_index: int | None = settings.get("selected_input_device_index")
_audio_config_version = 0
_audio_state: dict[str, Any] = {
    "selected_input_device_index": _selected_input_device_index,
    "current_input_device_index": None,
    "current_input_device_name": None,
    "default_input_device_index": None,
    "last_rms": 0.0,
    "last_peak": 0.0,
    "last_error": None,
}

_recent_transcripts: list[tuple[float, str]] = []


def _load_initial_api_key() -> tuple[str | None, str]:
    env_key = os.environ.get(GROQ_API_KEY_NAME)
    if env_key:
        return env_key, "env"
    try:
        saved_key = load_api_key()
        if saved_key:
            return saved_key, "saved"
    except Exception as exc:
        record_error("api_key", "저장된 API 키를 불러오지 못했습니다.", exc)
    return None, "none"


_groq_api_key, _groq_api_source = _load_initial_api_key()
_groq_client: Groq | None = Groq(api_key=_groq_api_key, timeout=12.0) if _groq_api_key else None
_groq_lock = threading.Lock()


def classify_groq_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "401" in text or "unauthorized" in text or "invalid api key" in text:
        return "API 키가 유효하지 않습니다."
    if "403" in text or "permission" in text:
        return "Groq API 권한 오류가 발생했습니다."
    if "429" in text or "rate limit" in text:
        return "Groq 요청 한도를 초과했을 수 있습니다."
    if "timeout" in text or "timed out" in text:
        return "Groq 서버 응답 시간이 초과되었습니다."
    if "connection" in text or "network" in text:
        return "Groq 네트워크 연결 오류가 발생했습니다."
    if "5" in text[:20] or "server" in text:
        return "Groq 서버 응답 오류가 발생했습니다."
    return "Groq 요청 중 오류가 발생했습니다."


def groq_api_status_message(error: str | None = None) -> dict[str, Any]:
    with _groq_lock:
        configured = bool(_groq_api_key)
        source = _groq_api_source

    data: dict[str, Any] = {
        "type": "api_status",
        "configured": configured,
        "source": source,
        "saved": has_saved_api_key(),
        "masked": "gsk_***" if configured else "",
    }
    if error:
        data["error"] = error
    return data


def validate_groq_api_key(api_key: str) -> tuple[bool, str]:
    try:
        client = Groq(api_key=api_key, timeout=10.0)
        client.models.list()
        return True, "API 키가 유효합니다."
    except Exception as exc:
        message = classify_groq_error(exc)
        record_error("api_key", message, exc)
        return False, message


def configure_groq_api_key(
    api_key: str,
    *,
    source: str = "app",
    persist: bool = False,
    validate: bool = False,
) -> dict[str, Any]:
    global _groq_api_key, _groq_api_source, _groq_client

    api_key = api_key.strip()
    if not api_key:
        return {"ok": False, "message": "API 키를 입력해 주세요."}

    if validate:
        ok, message = validate_groq_api_key(api_key)
        if not ok:
            return {"ok": False, "message": message}

    try:
        client = Groq(api_key=api_key, timeout=12.0)
        if persist:
            save_api_key(api_key)
    except Exception as exc:
        message = classify_groq_error(exc)
        record_error("api_key", message, exc)
        return {"ok": False, "message": message}

    with _groq_lock:
        _groq_api_key = api_key
        _groq_api_source = source
        _groq_client = client

    log.info("Groq API key configured source=%s saved=%s", source, persist)
    return {"ok": True, "message": "API 키가 저장되었습니다." if persist else "API 키가 설정되었습니다."}


def clear_groq_api_key() -> dict[str, Any]:
    global _groq_api_key, _groq_api_source, _groq_client
    try:
        delete_api_key()
    except Exception as exc:
        record_error("api_key", "저장된 API 키 삭제에 실패했습니다.", exc)
        return {"ok": False, "message": "저장된 API 키 삭제에 실패했습니다."}
    with _groq_lock:
        _groq_api_key = os.environ.get(GROQ_API_KEY_NAME)
        _groq_api_source = "env" if _groq_api_key else "none"
        _groq_client = Groq(api_key=_groq_api_key, timeout=12.0) if _groq_api_key else None
    log.info("Stored Groq API key deleted")
    return {"ok": True, "message": "저장된 API 키를 삭제했습니다."}


def get_groq_client() -> Groq | None:
    with _groq_lock:
        return _groq_client


def get_lan_ip() -> str:
    return primary_lan_ip()


def network_payload() -> dict[str, Any]:
    ips = lan_ip_candidates()
    selected_ip = ips[0]
    return {
        "host": selected_ip,
        "port": PORT,
        "local_url": local_url(PORT),
        "guest_url": guest_url(selected_ip, PORT, include_role=True),
        "guest_base_url": guest_url(selected_ip, PORT, include_role=False),
        "lan_ip_candidates": [
            {
                "ip": ip,
                "selected": ip == selected_ip,
                "guest_url": guest_url(ip, PORT, include_role=True),
            }
            for ip in ips
        ],
    }


def current_config_message() -> dict[str, Any]:
    return {
        "type": "config",
        "vad_threshold": config.vad_threshold,
        "min_volume": config.min_volume,
        "silence_padding": config.silence_padding,
        "min_speech_chunks": config.min_speech_chunks,
        "min_text_chars": config.min_text_chars,
        "dedup_window_seconds": config.dedup_window_seconds,
        "vad_preset": config.vad_preset,
        "audio_presets": AUDIO_PRESETS,
        "selected_input_device_index": get_selected_input_device_index(),
    }


def save_current_settings() -> None:
    save_settings({
        "selected_input_device_index": get_selected_input_device_index(),
        "vad_preset": config.vad_preset,
        "vad_threshold": config.vad_threshold,
        "min_volume": config.min_volume,
        "silence_padding": config.silence_padding,
        "min_speech_chunks": config.min_speech_chunks,
        "min_text_chars": config.min_text_chars,
        "dedup_window_seconds": config.dedup_window_seconds,
    })


def get_selected_input_device_index() -> int | None:
    with _audio_lock:
        return _selected_input_device_index


def audio_state_snapshot() -> dict[str, Any]:
    with _audio_lock:
        return dict(_audio_state)


def set_selected_input_device(index: int | None) -> dict[str, Any]:
    global _selected_input_device_index, _audio_config_version
    if index is not None and not input_device_exists(index):
        return {"ok": False, "message": "선택한 마이크 장치를 찾을 수 없습니다."}

    with _audio_lock:
        _selected_input_device_index = index
        _audio_state["selected_input_device_index"] = index
        _audio_config_version += 1

    save_current_settings()
    log.info("Audio input device changed index=%s", index)
    return {"ok": True, "message": "마이크 장치 설정을 저장했습니다."}


def stats_message() -> dict[str, Any]:
    return {
        "type": "stats",
        "host_count": len(manager.hosts),
        "guest_count": len(manager.guests),
        "translation_count": len(result_history),
        "last_processing_ms": last_processing_ms,
    }


# WebSocket is a persistent connection between the browser and this server.
# Unlike normal HTTP, the server can push new translations to host/guest screens
# as soon as they are ready, without the browser repeatedly asking for updates.
class ConnectionManager:
    def __init__(self):
        # Hosts can control the mic/API/settings; guests only receive subtitles.
        self.hosts: list[WebSocket] = []
        self.guests: list[WebSocket] = []

    def all(self) -> list[WebSocket]:
        return self.hosts + self.guests

    async def connect_host(self, ws: WebSocket):
        await ws.accept()
        self.hosts.append(ws)
        log.info("Host websocket connected hosts=%s guests=%s", len(self.hosts), len(self.guests))
        # Send recent subtitles and current operating state to a newly opened host page.
        for item in result_history[-30:]:
            await _safe_send(ws, item)
        await _safe_send(ws, {"type": "mic_status", "muted": is_mic_muted})
        await _safe_send(ws, current_config_message())
        await _safe_send(ws, groq_api_status_message())
        await _safe_send(ws, stats_message())

    async def connect_guest(self, ws: WebSocket):
        await ws.accept()
        self.guests.append(ws)
        log.info("Guest websocket connected hosts=%s guests=%s", len(self.hosts), len(self.guests))
        # A guest who joins late still receives recent subtitles immediately.
        for item in result_history[-30:]:
            await _safe_send(ws, item)
        await self.broadcast(stats_message(), hosts_only=True)

    def disconnect(self, ws: WebSocket) -> str | None:
        for role, lst in (("host", self.hosts), ("guest", self.guests)):
            try:
                lst.remove(ws)
                log.info("%s websocket disconnected hosts=%s guests=%s", role, len(self.hosts), len(self.guests))
                return role
            except ValueError:
                pass
        return None

    async def broadcast(self, data: dict[str, Any], hosts_only: bool = False):
        targets = self.hosts if hosts_only else self.all()
        dead = []
        for ws in targets:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


async def _safe_send(ws: WebSocket, data: dict[str, Any]) -> None:
    try:
        await ws.send_json(data)
    except Exception:
        pass


manager = ConnectionManager()


def detect_device():
    if torch.cuda.is_available():
        return "cuda", "float16", f"NVIDIA GPU ({torch.cuda.get_device_name(0)})"
    return "cpu", "int8", "CPU (int8 quantized)"


print("디바이스 감지 중...", flush=True)
_device, _compute_type, _label = detect_device()
log.info("Device selected: %s", _label)

# Silero VAD (Voice Activity Detection) decides whether an audio chunk contains speech.
# It lets the app ignore silence/background noise and send only real utterances to Whisper.
print("Silero-VAD 로드 중...", flush=True)
_vad_model, _ = torch.hub.load(
    repo_or_dir="snakers4/silero-vad",
    model="silero_vad",
    force_reload=False,
    onnx=False,
)
_vad_model.eval()
log.info("Silero-VAD loaded")

print(f"faster-whisper '{WHISPER_MODEL_SIZE}' 로드 중...", flush=True)
_whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=_device, compute_type=_compute_type)
log.info("Whisper model loaded size=%s device=%s compute=%s", WHISPER_MODEL_SIZE, _device, _compute_type)
print("모델 로드 완료. 서버 준비 완료.", flush=True)


def translate_ko_to_vn(client: Groq, text: str) -> str:
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Bạn là phiên dịch viên chuyên nghiệp Hàn-Việt. "
                    "Dịch chính xác văn bản tiếng Hàn sang tiếng Việt tự nhiên. "
                    "Chỉ trả lời bản dịch, không giải thích thêm."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.2,
        max_tokens=512,
    )
    return response.choices[0].message.content.strip()


class AudioRestartRequested(Exception):
    pass


def _select_input_device(pa: pyaudio.PyAudio) -> tuple[int | None, dict[str, Any] | None]:
    selected = get_selected_input_device_index()
    default_index = None

    try:
        wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_index = wasapi_info.get("defaultInputDevice")
    except Exception:
        try:
            default_index = pa.get_default_input_device_info().get("index")
        except Exception:
            default_index = None

    with _audio_lock:
        _audio_state["default_input_device_index"] = default_index

    for candidate in (selected, default_index):
        if candidate is None:
            continue
        try:
            info = pa.get_device_info_by_index(int(candidate))
            if int(info.get("maxInputChannels", 0)) > 0:
                return int(candidate), info
        except Exception:
            continue

    return None, None


def _resample_to_16khz(audio_np: np.ndarray, native_rate: int) -> np.ndarray:
    if native_rate == SAMPLE_RATE or len(audio_np) == 0:
        return audio_np.astype(np.float32, copy=False)
    target_len = max(1, int(len(audio_np) * SAMPLE_RATE / native_rate))
    source_x = np.linspace(0, len(audio_np), num=len(audio_np), endpoint=False)
    target_x = np.linspace(0, len(audio_np), num=target_len, endpoint=False)
    return np.interp(target_x, source_x, audio_np).astype(np.float32)


def _normalize_text(text: str) -> str:
    return re.sub(r"[^\w가-힣]+", "", text, flags=re.UNICODE).lower()


def should_skip_transcript(text: str) -> tuple[bool, str]:
    normalized = _normalize_text(text)
    if len(normalized) < config.min_text_chars:
        return True, f"too_short chars={len(normalized)}"

    now = time.monotonic()
    window = float(config.dedup_window_seconds)
    _recent_transcripts[:] = [(ts, value) for ts, value in _recent_transcripts if now - ts <= window]
    for _, previous in _recent_transcripts:
        if normalized == previous:
            return True, "duplicate_exact"
        if previous and difflib.SequenceMatcher(None, normalized, previous).ratio() >= 0.92:
            return True, "duplicate_similar"

    _recent_transcripts.append((now, normalized))
    return False, ""


def mic_pipeline(loop: asyncio.AbstractEventLoop, q: asyncio.Queue):
    vad_model = _vad_model
    whisper = _whisper_model

    def push(data: dict[str, Any]):
        loop.call_soon_threadsafe(q.put_nowait, data)

    log.info("Microphone pipeline started")
    push({"type": "status", "status": "idle"})
    push(groq_api_status_message())

    triggered = False
    speech_chunks: list[np.ndarray] = []
    silence_counter = 0
    seg_index = 0
    last_volume_push = 0.0

    while True:
        stream = None
        pa = None
        local_audio_version = _audio_config_version
        try:
            pa = pyaudio.PyAudio()
            mic_idx, mic_info = _select_input_device(pa)
            if mic_idx is None or mic_info is None:
                message = "마이크 입력 장치를 찾을 수 없습니다. Windows 마이크 권한과 연결 상태를 확인하세요."
                with _audio_lock:
                    _audio_state["last_error"] = message
                record_error("microphone", message)
                push({"type": "error", "category": "microphone", "message": message})
                time.sleep(3)
                continue

            native_rate = int(float(mic_info["defaultSampleRate"]))
            native_channels = int(mic_info["maxInputChannels"])
            chunk_frames = max(1, int(native_rate * CHUNK_MS / 1000))

            with _audio_lock:
                _audio_state["current_input_device_index"] = mic_idx
                _audio_state["current_input_device_name"] = str(mic_info.get("name", "Unknown microphone"))
                _audio_state["last_error"] = None

            log.info(
                "Microphone opened index=%s name=%s rate=%s channels=%s",
                mic_idx,
                mask_sensitive(mic_info.get("name", "")),
                native_rate,
                native_channels,
            )

            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=native_channels,
                rate=native_rate,
                input=True,
                frames_per_buffer=chunk_frames,
                input_device_index=mic_idx,
            )

            triggered = False
            speech_chunks = []
            silence_counter = 0
            push({"type": "status", "status": "idle"})

            while True:
                if local_audio_version != _audio_config_version:
                    raise AudioRestartRequested()

                raw = stream.read(chunk_frames, exception_on_overflow=False)

                if is_mic_muted:
                    now = time.monotonic()
                    if now - last_volume_push > 0.5:
                        push({"type": "volume", "rms": 0.0, "peak": 0.0})
                        last_volume_push = now
                    if triggered:
                        triggered = False
                        speech_chunks = []
                        silence_counter = 0
                        push({"type": "status", "status": "idle"})
                    continue

                audio_np = np.frombuffer(raw, dtype=np.float32)
                if len(audio_np) == 0:
                    continue

                if native_channels > 1:
                    audio_np = audio_np.reshape(-1, native_channels).mean(axis=1)

                audio_np = _resample_to_16khz(audio_np, native_rate)
                rms = float(np.sqrt(np.mean(np.square(audio_np)))) if len(audio_np) else 0.0
                peak = float(np.max(np.abs(audio_np))) if len(audio_np) else 0.0

                with _audio_lock:
                    _audio_state["last_rms"] = round(rms, 4)
                    _audio_state["last_peak"] = round(peak, 4)

                now = time.monotonic()
                if now - last_volume_push > 0.2:
                    push({"type": "volume", "rms": round(rms, 4), "peak": round(peak, 4)})
                    last_volume_push = now

                tensor = torch.from_numpy(audio_np)
                with torch.no_grad():
                    # Silero returns a speech probability from 0.0 to 1.0 for this short audio chunk.
                    prob = vad_model(tensor, SAMPLE_RATE).item()

                # Start recording a sentence only when both speech probability and volume are high enough.
                if prob >= config.vad_threshold and peak >= config.min_volume:
                    if not triggered:
                        triggered = True
                        silence_counter = 0
                        push({"type": "status", "status": "recording"})
                    speech_chunks.append(audio_np)
                    silence_counter = 0
                elif triggered:
                    silence_counter += 1
                    speech_chunks.append(audio_np)

                    if silence_counter >= config.silence_padding:
                        if len(speech_chunks) >= config.min_speech_chunks:
                            push({"type": "status", "status": "processing"})
                            audio_float = np.concatenate(speech_chunks)
                            duration_s = round(len(audio_float) / SAMPLE_RATE, 1)

                            stt_started = time.perf_counter()
                            segs, _ = whisper.transcribe(
                                audio_float,
                                language=WHISPER_LANGUAGE,
                                beam_size=5,
                                # Silero already cut the speech segment, so Whisper's own VAD is disabled here.
                                vad_filter=False,
                            )
                            stt_ms = int((time.perf_counter() - stt_started) * 1000)
                            ko_text = "".join(segment.text for segment in segs).strip()

                            if ko_text:
                                skip, reason = should_skip_transcript(ko_text)
                                if skip:
                                    log.info("Transcript filtered reason=%s chars=%s duration_s=%s", reason, len(ko_text), duration_s)
                                else:
                                    groq_client = get_groq_client()
                                    if groq_client is None:
                                        message = "Groq API 키를 먼저 입력해 주세요."
                                        record_error("api_key", message)
                                        push({"type": "api_error", "message": message})
                                        push({"type": "error", "category": "api_key", "message": message})
                                    else:
                                        try:
                                            translate_started = time.perf_counter()
                                            vn_text = translate_ko_to_vn(groq_client, ko_text)
                                            translate_ms = int((time.perf_counter() - translate_started) * 1000)
                                        except Exception as exc:
                                            message = classify_groq_error(exc)
                                            record_error("translation", message, exc)
                                            push({"type": "api_error", "message": message})
                                            push({"type": "error", "category": "translation", "message": message})
                                        else:
                                            seg_index += 1
                                            global last_processing_ms
                                            last_processing_ms = stt_ms + translate_ms
                                            result = {
                                                "type": "result",
                                                "id": seg_index,
                                                "ko": ko_text,
                                                "vn": vn_text,
                                                "duration": duration_s,
                                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                                                "stt_ms": stt_ms,
                                                "translate_ms": translate_ms,
                                                "processing_ms": last_processing_ms,
                                            }
                                            log.info(
                                                "Translation completed id=%s ko_chars=%s vn_chars=%s stt_ms=%s translate_ms=%s",
                                                seg_index,
                                                len(ko_text),
                                                len(vn_text),
                                                stt_ms,
                                                translate_ms,
                                            )
                                            push(result)

                        triggered = False
                        speech_chunks = []
                        silence_counter = 0
                        push({"type": "status", "status": "idle"})

        except AudioRestartRequested:
            log.info("Microphone pipeline restarting for audio config change")
            push({"type": "status", "status": "idle"})
        except Exception as exc:
            message = "마이크 파이프라인 오류가 발생했습니다. 마이크 연결과 권한을 확인하세요."
            with _audio_lock:
                _audio_state["last_error"] = f"{message} {mask_sensitive(exc)}"
            record_error("microphone", message, exc)
            push({"type": "error", "category": "microphone", "message": message})
            time.sleep(2)
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if pa is not None:
                pa.terminate()


async def broadcaster(q: asyncio.Queue):
    while True:
        data = await q.get()
        if data.get("type") == "result":
            result_history.append(data)
            if len(result_history) > 100:
                result_history.pop(0)
            try:
                session_metadata = {"app_version": APP_VERSION, "session_id": SESSION_ID}
                save_session(result_history, session_metadata)
            except Exception as exc:
                record_error("session", "세션 저장에 실패했습니다.", exc)

        hosts_only = data.get("type") in {
            "status",
            "api_status",
            "api_error",
            "error",
            "volume",
            "config",
            "stats",
        }
        await manager.broadcast(data, hosts_only=hosts_only)
        if data.get("type") == "result":
            await manager.broadcast(stats_message(), hosts_only=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    log.info("App starting version=%s build=%s port=%s", APP_VERSION, BUILD_TYPE, PORT)
    thread = threading.Thread(target=mic_pipeline, args=(loop, q), daemon=True)
    thread.start()

    task = asyncio.create_task(broadcaster(q))
    yield
    task.cancel()
    log.info("App stopping")


app = FastAPI(title=PRODUCT_NAME, version=APP_VERSION, lifespan=lifespan)


@app.get("/")
async def serve_index():
    return FileResponse(resource_path("index.html"))


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "app": APP_NAME,
        "product": PRODUCT_NAME,
        "version": APP_VERSION,
        "build_type": BUILD_TYPE,
        "port": PORT,
    }


@app.get("/api/network")
async def network_info():
    return network_payload()


@app.get("/api/qr")
async def qr_code(url: str | None = Query(default=None)):
    if qrcode is None:
        return JSONResponse(
            {"ok": False, "message": "qrcode 패키지가 설치되어 있지 않습니다."},
            status_code=503,
        )
    target_url = url or network_payload()["guest_url"]
    image = qrcode.make(target_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(
        buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/audio/devices")
async def audio_devices_endpoint():
    try:
        devices = list_input_devices(get_selected_input_device_index())
        return {
            "ok": True,
            "selected_input_device_index": get_selected_input_device_index(),
            "default_input_device_index": default_input_index(),
            "current": audio_state_snapshot(),
            "devices": devices,
        }
    except Exception as exc:
        message = "마이크 장치 목록을 가져오지 못했습니다."
        record_error("microphone", message, exc)
        return JSONResponse({"ok": False, "message": message, "devices": []}, status_code=500)


@app.get("/api/settings")
async def get_settings_endpoint():
    return {
        "ok": True,
        "config": current_config_message(),
        "audio_state": audio_state_snapshot(),
    }


@app.post("/api/settings")
async def post_settings_endpoint(request: Request):
    payload = await request.json()

    if "selected_input_device_index" in payload:
        value = payload["selected_input_device_index"]
        result = set_selected_input_device(None if value in ("", None, "default") else int(value))
        if not result["ok"]:
            return JSONResponse(result, status_code=400)

    if "vad_preset" in payload:
        preset = str(payload["vad_preset"])
        if preset not in AUDIO_PRESETS:
            return JSONResponse({"ok": False, "message": "알 수 없는 프리셋입니다."}, status_code=400)
        preset_values = AUDIO_PRESETS[preset]
        config.vad_preset = preset
        config.vad_threshold = float(preset_values["vad_threshold"])
        config.min_volume = float(preset_values["min_volume"])
        config.silence_padding = int(preset_values["silence_padding"])
        config.min_speech_chunks = int(preset_values["min_speech_chunks"])

    for key, caster in (
        ("vad_threshold", float),
        ("min_volume", float),
        ("silence_padding", int),
        ("min_speech_chunks", int),
        ("min_text_chars", int),
        ("dedup_window_seconds", int),
    ):
        if key in payload:
            setattr(config, key, caster(payload[key]))

    save_current_settings()
    await manager.broadcast(current_config_message(), hosts_only=True)
    return {"ok": True, "config": current_config_message()}


@app.get("/api/diagnostics")
async def diagnostics():
    network = network_payload()
    try:
        devices = list_input_devices(get_selected_input_device_index())
    except Exception as exc:
        devices = []
        record_error("microphone", "진단 중 마이크 장치 목록을 가져오지 못했습니다.", exc)

    return {
        "app": {
            "name": APP_NAME,
            "product": PRODUCT_NAME,
            "version": APP_VERSION,
            "company": COMPANY_NAME,
            "build_type": BUILD_TYPE,
            "session_id": SESSION_ID,
        },
        "system": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "frozen": bool(getattr(sys, "frozen", False)),
        },
        "network": {
            **network,
            "bind_host": HOST,
            "binds_all_interfaces": HOST == "0.0.0.0",
            "localhost_accepts_connections": port_accepts_connections("127.0.0.1", PORT),
            "port_available_for_new_server": can_bind("0.0.0.0", PORT),
            "websocket_host_endpoint": f"ws://127.0.0.1:{PORT}/ws/host",
            "websocket_guest_endpoint": f"ws://{network['host']}:{PORT}/ws/guest",
            "firewall_guidance": [
                "Windows 방화벽에서 이 exe 또는 Python을 개인 네트워크에 허용하세요.",
                "게스트 휴대폰과 호스트 PC가 같은 Wi-Fi에 있어야 합니다.",
                "회사/학교 Wi-Fi는 기기 간 통신을 차단할 수 있습니다.",
                "게스트 휴대폰에서는 127.0.0.1 주소가 아니라 LAN IP 주소를 열어야 합니다.",
            ],
        },
        "websocket": {
            "host_count": len(manager.hosts),
            "guest_count": len(manager.guests),
        },
        "audio": {
            "state": audio_state_snapshot(),
            "devices": devices,
            "config": current_config_message(),
        },
        "api_key": {
            "configured": groq_api_status_message()["configured"],
            "source": groq_api_status_message()["source"],
            "saved": has_saved_api_key(),
        },
        "history": {
            "translation_count": len(result_history),
            "last_processing_ms": last_processing_ms,
            "session_id": SESSION_ID,
        },
        "recent_errors": recent_errors(10),
        "recent_log": tail_log(40),
    }


@app.post("/api/api-key")
async def api_key_endpoint(request: Request):
    payload = await request.json()
    action = str(payload.get("action", "set"))

    if action == "delete":
        result = clear_groq_api_key()
        await manager.broadcast(groq_api_status_message(result.get("message") if not result["ok"] else None), hosts_only=True)
        return result | {"status": groq_api_status_message()}

    if action == "status":
        return {"ok": True, "status": groq_api_status_message()}

    api_key = str(payload.get("api_key", ""))
    persist = bool(payload.get("save", True))
    validate = bool(payload.get("validate", True))
    result = configure_groq_api_key(api_key, source="app", persist=persist, validate=validate)
    await manager.broadcast(groq_api_status_message(result.get("message") if not result["ok"] else None), hosts_only=True)
    status_code = 200 if result["ok"] else 400
    return JSONResponse(result | {"status": groq_api_status_message()}, status_code=status_code)


@app.get("/api/export")
async def export_history(format: str = Query(default="txt")):
    fmt = format.lower()
    if fmt == "json":
        return JSONResponse({
            "session_id": SESSION_ID,
            "app_version": APP_VERSION,
            "items": result_history,
        })
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["id", "timestamp", "duration", "ko", "vn", "stt_ms", "translate_ms", "processing_ms"])
        writer.writeheader()
        for item in result_history:
            writer.writerow({key: item.get(key, "") for key in writer.fieldnames})
        return Response(
            output.getvalue().encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{SESSION_ID}-translations.csv"'},
        )

    lines = ["실시간 한국어 -> 베트남어 번역 기록", "=" * 40, ""]
    for item in result_history:
        lines.extend([
            f"[{item.get('timestamp')}] [#{item.get('id')}] [{item.get('duration')}s]",
            f"KO: {item.get('ko', '')}",
            f"VI: {item.get('vn', '')}",
            "",
        ])
    return PlainTextResponse(
        "\n".join(lines),
        headers={"Content-Disposition": f'attachment; filename="{SESSION_ID}-translations.txt"'},
    )


@app.get("/api/sessions")
async def sessions_endpoint():
    return {"ok": True, "sessions": list_sessions()}


@app.get("/manifest.webmanifest")
async def manifest():
    return JSONResponse({
        "name": PRODUCT_NAME,
        "short_name": "한베통역",
        "start_url": "/?role=guest",
        "display": "standalone",
        "background_color": "#030a17",
        "theme_color": "#063f2d",
        "lang": "ko",
    })


@app.get("/service-worker.js")
async def service_worker():
    script = """
self.addEventListener('install', event => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin === location.origin && event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => fetch('/')));
  }
});
"""
    return Response(script.strip(), media_type="text/javascript")


@app.websocket("/ws/host")
async def ws_host(ws: WebSocket):
    # Host WebSocket: receives control messages from the PC UI
    # and receives live status/translation updates from the server.
    global is_mic_muted
    await manager.connect_host(ws)
    try:
        while True:
            data_str = await ws.receive_text()
            try:
                data = json.loads(data_str)
                cmd = data.get("type")

                if cmd == "control" and data.get("command") == "toggle_mic":
                    is_mic_muted = not is_mic_muted
                    log.info("Microphone mute toggled muted=%s", is_mic_muted)
                    await manager.broadcast({"type": "mic_status", "muted": is_mic_muted}, hosts_only=True)

                elif cmd == "set_api_key":
                    result = configure_groq_api_key(str(data.get("api_key", "")), source="app", persist=True, validate=True)
                    await manager.broadcast(
                        groq_api_status_message(result.get("message") if not result["ok"] else None),
                        hosts_only=True,
                    )

                elif cmd == "update_config":
                    for key, caster in (
                        ("vad_threshold", float),
                        ("min_volume", float),
                        ("silence_padding", int),
                        ("min_speech_chunks", int),
                        ("min_text_chars", int),
                        ("dedup_window_seconds", int),
                    ):
                        if key in data:
                            setattr(config, key, caster(data[key]))
                    if "vad_preset" in data and data["vad_preset"] in AUDIO_PRESETS:
                        config.vad_preset = str(data["vad_preset"])
                    save_current_settings()
                    await manager.broadcast(current_config_message(), hosts_only=True)
                    log.info(
                        "Audio config updated preset=%s vad=%s volume=%s silence=%s min_chunks=%s",
                        config.vad_preset,
                        config.vad_threshold,
                        config.min_volume,
                        config.silence_padding,
                        config.min_speech_chunks,
                    )

            except Exception as exc:
                record_error("websocket", "호스트 WebSocket 메시지 처리 중 오류가 발생했습니다.", exc)
    except WebSocketDisconnect:
        manager.disconnect(ws)
        await manager.broadcast(stats_message(), hosts_only=True)


@app.websocket("/ws/guest")
async def ws_guest(ws: WebSocket):
    # Guest WebSocket: keeps the phone browser connected so translated subtitles
    # appear instantly without refreshing the page.
    await manager.connect_guest(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
        await manager.broadcast(stats_message(), hosts_only=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"서버 시작 -> {local_url(PORT)}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
