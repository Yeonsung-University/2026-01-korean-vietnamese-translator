# Security Policy

## 민감 정보

이 저장소에는 실제 API 키, 토큰, 인증서, 로그 원문을 commit하지 않습니다.

특히 다음 값은 GitHub에 올리지 마세요.

- Groq API key
- GitHub token
- Windows code-signing certificate
- `.env` 파일
- `%APPDATA%/KoreanVietnameseTranslator` 아래의 로컬 보안 저장 파일
- 실행 로그 또는 진단 로그

## API 키 저장

앱은 Windows 환경에서 Groq API 키를 DPAPI 기반 로컬 저장소에 보관하도록 설계되어 있습니다. UI에는 전체 키를 표시하지 말고 설정 여부만 표시해야 합니다.

## 취약점 보고

private 저장소로 운영하는 동안에는 저장소 관리자에게 직접 보고하세요. 공개 배포 전에는 별도 보안 연락처와 릴리스 절차를 문서화하는 것을 권장합니다.
