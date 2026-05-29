"""
실시간 마이크 입력 → Silero-VAD 발화 구간 감지
→ faster-whisper 한국어 STT
→ Groq API (Llama 3) 한국어→베트남어 번역
→ 터미널 출력: [KO]: ... / [VN]: ...

환경 변수 설정 필요:
  Windows PowerShell:
    $env:GROQ_API_KEY = "gsk_..."
  영구 등록:
    [System.Environment]::SetEnvironmentVariable("GROQ_API_KEY","gsk_...", "User")

하드웨어 최적화:
  - NVIDIA GPU → CUDA + float16
  - 그 외 (CPU) → int8 양자화  ← Ryzen 5600U
"""

import io
import os
import sys
import wave
import threading
import queue
import numpy as np
import pyaudio
import torch
from faster_whisper import WhisperModel
from groq import Groq

# ────────────────────────────────────────────────
# 설정값
# ────────────────────────────────────────────────
SAMPLE_RATE       = 16000
CHUNK_MS          = 30
CHUNK_SAMPLES     = int(SAMPLE_RATE * CHUNK_MS / 1000)   # 480 샘플
CHANNELS          = 1
FORMAT            = pyaudio.paInt16

VAD_THRESHOLD     = 0.5    # Silero-VAD 음성 판별 임계값
SILENCE_PADDING   = 20     # 침묵 지속 청크 수 (×30ms = 600ms)
MIN_SPEECH_CHUNKS = 5      # 최소 발화 청크 (노이즈 무시)

WHISPER_MODEL     = "base"
WHISPER_LANGUAGE  = "ko"

GROQ_MODEL        = "llama-3.3-70b-versatile"   # 가장 빠른 Groq Llama 3 모델
GROQ_API_KEY_NAME = "GROQ_API_KEY"


# ────────────────────────────────────────────────
# 디바이스 자동 감지
# ────────────────────────────────────────────────
def detect_device():
    if torch.cuda.is_available():
        return "cuda", "float16", f"NVIDIA GPU ({torch.cuda.get_device_name(0)})"
    return "cpu", "int8", "CPU (int8 양자화)"


# ────────────────────────────────────────────────
# Groq 클라이언트 초기화
# ────────────────────────────────────────────────
def init_groq_client() -> Groq:
    api_key = os.environ.get(GROQ_API_KEY_NAME)
    if not api_key:
        print(f"\n❌ 환경 변수 '{GROQ_API_KEY_NAME}' 가 설정되지 않았습니다.")
        print("   PowerShell에서 아래 명령어로 설정하세요:")
        print(f'   $env:{GROQ_API_KEY_NAME} = "gsk_..."')
        print("   (영구 등록)")
        print(f'   [System.Environment]::SetEnvironmentVariable("{GROQ_API_KEY_NAME}","gsk_...", "User")')
        sys.exit(1)
    return Groq(api_key=api_key)


# ────────────────────────────────────────────────
# 번역 함수
# ────────────────────────────────────────────────
def translate_ko_to_vn(groq_client: Groq, text: str) -> str:
    """Groq Llama 3 로 한국어 → 베트남어 번역"""
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Bạn là một phiên dịch viên chuyên nghiệp. "
                    "Hãy dịch văn bản tiếng Hàn sau sang tiếng Việt. "
                    "Chỉ trả lời bản dịch, không giải thích thêm."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.3,
        max_tokens=512,
    )
    return response.choices[0].message.content.strip()


# ────────────────────────────────────────────────
# Silero-VAD 로드
# ────────────────────────────────────────────────
def load_silero_vad():
    model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False,
    )
    model.eval()
    return model


# ────────────────────────────────────────────────
# WAV 바이너리 생성 (메모리)
# ────────────────────────────────────────────────
def chunks_to_wav_bytes(chunks: list[bytes]) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(chunks))
    return buf.getvalue()


# ────────────────────────────────────────────────
# STT + 번역 워커 (별도 스레드)
# ────────────────────────────────────────────────
def stt_translate_worker(
    whisper_model: WhisperModel,
    groq_client: Groq,
    audio_queue: queue.Queue,
):
    seg_index = 0
    while True:
        item = audio_queue.get()
        if item is None:
            break

        seg_index += 1
        wav_bytes  = item
        duration_s = (len(wav_bytes) - 44) / (SAMPLE_RATE * 2)

        print(f"\n[#{seg_index}] 음성 감지됨 ({duration_s:.1f}초) — STT 처리 중...")

        # ① faster-whisper STT
        audio_np = (
            np.frombuffer(wav_bytes[44:], dtype=np.int16).astype(np.float32) / 32768.0
        )
        segments, _ = whisper_model.transcribe(
            audio_np,
            language=WHISPER_LANGUAGE,
            beam_size=5,
            vad_filter=False,
        )
        ko_text = "".join(seg.text for seg in segments).strip()

        if not ko_text:
            print("  (인식된 텍스트 없음)")
            audio_queue.task_done()
            continue

        print(f"  [KO]: {ko_text}")

        # ② Groq 번역
        print("  번역 중...", end="\r")
        try:
            vn_text = translate_ko_to_vn(groq_client, ko_text)
            print(f"  [KO]: {ko_text}")
            print(f"  [VN]: {vn_text}")
        except Exception as e:
            print(f"  ⚠️  번역 실패: {e}")

        print("─" * 45)
        audio_queue.task_done()


# ────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────
def main():
    device, compute_type, label = detect_device()
    print(f"⚙️  실행 디바이스 : {label}")

    # Groq 클라이언트 (API 키 없으면 여기서 종료)
    groq_client = init_groq_client()
    print(f"✅ Groq API 연결 : {GROQ_MODEL}")

    print("📦 Silero-VAD 로드 중...")
    vad_model = load_silero_vad()

    print(f"📦 faster-whisper '{WHISPER_MODEL}' 로드 중 (최초 실행 시 다운로드)...")
    whisper_model = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute_type)

    print("\n🎙️  마이크 모니터링 시작 (Ctrl+C 로 종료)")
    print("─" * 45)

    audio_queue: queue.Queue = queue.Queue()
    worker = threading.Thread(
        target=stt_translate_worker,
        args=(whisper_model, groq_client, audio_queue),
        daemon=True,
    )
    worker.start()

    pa     = pyaudio.PyAudio()
    stream = pa.open(
        rate=SAMPLE_RATE,
        channels=CHANNELS,
        format=FORMAT,
        input=True,
        frames_per_buffer=CHUNK_SAMPLES,
    )

    triggered       = False
    speech_chunks   = []
    silence_counter = 0
    wav_segments    = []

    try:
        while True:
            raw      = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
            audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            tensor   = torch.from_numpy(audio_np)

            with torch.no_grad():
                speech_prob = vad_model(tensor, SAMPLE_RATE).item()

            if speech_prob >= VAD_THRESHOLD:
                if not triggered:
                    triggered = True
                    silence_counter = 0
                    print("🔴 녹음 중...", end="\r")
                speech_chunks.append(raw)
                silence_counter = 0
            else:
                if triggered:
                    silence_counter += 1
                    speech_chunks.append(raw)

                    if silence_counter >= SILENCE_PADDING:
                        if len(speech_chunks) >= MIN_SPEECH_CHUNKS:
                            wav_bytes = chunks_to_wav_bytes(speech_chunks)
                            wav_segments.append(wav_bytes)
                            audio_queue.put(wav_bytes)

                        triggered       = False
                        speech_chunks   = []
                        silence_counter = 0

    except KeyboardInterrupt:
        print(f"\n\n⏹️  종료. 총 {len(wav_segments)}개 음성 구간 처리됨.")
        audio_queue.put(None)
        audio_queue.join()
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    return wav_segments


if __name__ == "__main__":
    main()
