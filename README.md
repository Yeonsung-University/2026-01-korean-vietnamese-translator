# Korean-Vietnamese Live Translator

Windows PC에서 실행하는 한국어 -> 베트남어 실시간 통역 앱입니다. 호스트 PC는 마이크 입력을 받아 음성 구간 감지, STT, Groq 번역을 수행하고, 같은 Wi-Fi의 게스트는 모바일 브라우저로 번역 자막을 읽습니다.

## 주요 기능

- FastAPI 기반 로컬 서버와 WebSocket 실시간 전송
- 호스트/게스트 역할 선택 UI
- Groq API 키 앱 내 입력 및 Windows DPAPI 기반 로컬 저장
- Silero VAD 기반 발화 구간 감지
- faster-whisper 기반 한국어 STT
- 한국어 -> 베트남어 번역 결과를 호스트/게스트 화면에 동시 표시
- 게스트 접속 URL, QR 코드, 네트워크 진단 정보 제공
- PyInstaller onefile portable EXE 빌드
- Inno Setup 기반 installer 빌드 스크립트

## 저장소 구조

```text
.
├── app_launcher.py              # EXE 진입점, 서버 실행 및 브라우저 자동 오픈
├── server.py                    # FastAPI, WebSocket, 음성/번역 파이프라인
├── index.html                   # 단일 파일 프론트엔드 UI
├── app_config.py                # 앱 이름, 버전, 경로, 포트 설정
├── secure_store.py              # Groq API 키 보안 저장
├── settings_store.py            # 로컬 설정 저장
├── audio_devices.py             # 마이크 장치 조회
├── network_utils.py             # LAN IP/URL 탐색
├── history_store.py             # 세션 기록 저장
├── logging_utils.py             # 로그/오류 기록
├── build_portable.ps1           # portable EXE 빌드
├── build_installer.ps1          # installer 빌드
├── scripts/
│   ├── Resolve-Python.ps1       # Python 실행 파일 탐색
│   ├── smoke_test.ps1           # EXE smoke test
│   └── package_release.ps1      # 배포 ZIP 생성
├── docs/
│   ├── local_first_deployment.md
│   └── windows_signing.md
└── installer/
    └── KoreanVietnameseTranslator.iss
```

## 개발 실행

Python 3.10 이상을 설치한 뒤 PowerShell에서 실행합니다.

```powershell
python -m pip install -r requirements.txt
.\run_app.ps1
```

브라우저가 `http://127.0.0.1:8000`으로 열리면 `Host`를 선택합니다. 게스트는 호스트 화면에 표시되는 LAN URL 또는 QR 코드로 접속합니다.

## EXE 빌드

```powershell
.\build_portable.ps1
```

결과:

```text
dist/KoreanVietnameseTranslator.exe
```

릴리스 ZIP까지 만들려면:

```powershell
.\scripts\package_release.ps1
```

installer 빌드는 Inno Setup 6 설치 후 실행합니다.

```powershell
.\build_installer.ps1
```

## API 키

이 앱은 번역에 Groq API를 사용합니다. 키는 앱 UI에서 입력하거나 `GROQ_API_KEY` 환경변수로 설정할 수 있습니다.

주의:

- 실제 API 키를 GitHub에 commit하지 마세요.
- `.env`, 로그, DPAPI 저장 파일, 빌드 산출물은 `.gitignore`에서 제외합니다.
- 게스트는 앱 설치가 필요 없고 같은 Wi-Fi에서 브라우저로 접속합니다.

## 배포 기준

GitHub 저장소에는 소스 코드와 문서만 올립니다. `dist/`, `build/`, `release/`, `*.exe`, ZIP 산출물은 코드 저장소에 commit하지 않고 GitHub Releases에 첨부하는 방식이 권장됩니다.

## 라이선스

현재 별도 라이선스가 지정되어 있지 않습니다. 재배포 또는 상업적 사용 전 저장소 소유자에게 확인하세요.
