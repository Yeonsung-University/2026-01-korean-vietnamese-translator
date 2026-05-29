# Local-First Deployment Guide

이 앱은 AWS나 외부 서버 없이 호스트 PC 한 대에서 실행되는 Windows용 실시간 한국어-베트남어 통역 앱입니다.

## 실행 방식

1. `KoreanVietnameseTranslator.exe`를 실행합니다.
2. 브라우저가 `http://127.0.0.1:8000`으로 자동 열립니다.
3. 역할 선택 화면에서 `호스트 / Host`를 선택합니다.
4. Groq API 키가 저장되어 있지 않다면 앱 안에서 입력합니다.
5. 호스트 화면의 `게스트 휴대폰 접속 주소` 또는 QR 코드를 게스트에게 공유합니다.
6. 게스트 휴대폰은 같은 Wi-Fi에서 `http://호스트IP:8000/?role=guest`로 접속합니다.

게스트는 앱 설치가 필요 없습니다. 호스트 PC만 exe를 실행합니다.

## 배포 권장 형태

일반 배포는 아래 파일 하나로 충분합니다.

```text
KoreanVietnameseTranslator.exe
```

운영자용 배포 묶음은 `scripts/package_release.ps1`로 생성합니다.

```powershell
.\scripts\package_release.ps1
```

생성물:

- `release/KoreanVietnameseTranslator-1.2.0-portable/KoreanVietnameseTranslator.exe`
- `release/KoreanVietnameseTranslator-1.2.0-portable/README_RUN.md`
- `release/KoreanVietnameseTranslator-1.2.0-portable/CHECKLIST.txt`
- `release/KoreanVietnameseTranslator-1.2.0-portable.zip`

## 현장 체크리스트

- 호스트 PC와 게스트 휴대폰이 같은 Wi-Fi에 있는지 확인합니다.
- 게스트 휴대폰에서 `127.0.0.1` 주소를 열지 않습니다.
- Windows 방화벽에서 이 exe를 개인 네트워크에 허용합니다.
- 회사/학교 Wi-Fi는 기기 간 통신을 차단할 수 있습니다.
- 호스트 PC가 절전 모드로 들어가지 않게 설정합니다.
- 마이크 입력 레벨이 움직이는지 확인합니다.
- 앱 진단 패널에서 게스트 URL, 포트, 마이크, 최근 오류를 확인합니다.

## 검증

개발/배포 PC에서 exe smoke test를 실행할 수 있습니다.

```powershell
.\scripts\smoke_test.ps1
```

검증 항목:

- exe 실행
- `/api/health`
- 메인 UI 로드
- LAN 게스트 URL 생성
- QR PNG 생성
- 진단 endpoint 응답
- 게스트 WebSocket 연결 등록

## 설정

기본 포트는 `8000`입니다.
다른 프로그램이 이미 `8000` 포트를 쓰고 있으면 앱은 자동으로 다음 빈 포트(`8001`부터)를 찾아 실행합니다. 이 경우 앱 화면에 표시되는 게스트 URL의 포트 번호를 그대로 사용하면 됩니다.

다른 포트를 써야 하면 실행 전에 환경변수를 지정합니다.

```powershell
$env:KVT_PORT="8010"
.\KoreanVietnameseTranslator.exe
```

`KVT_PORT`를 직접 지정한 경우에는 그 포트를 반드시 사용합니다. 해당 포트가 이미 사용 중이면 앱이 종료되므로 다른 포트 번호로 다시 지정하세요.

테스트 자동화에서 브라우저 자동 열기를 끄려면:

```powershell
$env:KVT_NO_BROWSER="1"
.\KoreanVietnameseTranslator.exe
```

## 데이터 저장 위치

앱 로그와 세션 기록은 Windows 사용자 데이터 폴더에 저장됩니다.

```text
%APPDATA%\KoreanVietnameseTranslator\logs\
%APPDATA%\KoreanVietnameseTranslator\sessions\
```

API 키는 Windows DPAPI 기반 로컬 보안 저장소를 사용합니다. 앱 화면에서 저장된 키 삭제도 가능합니다.
