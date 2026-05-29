# Windows Code Signing Notes

이 앱은 PyInstaller로 만든 Windows exe입니다. 코드 서명 인증서가 없으면 SmartScreen 경고를 완전히 없앨 수 없습니다.

## 현실적인 선택지

- OV 코드 서명 인증서: 일반 배포에 사용 가능하지만 SmartScreen 평판은 시간이 지나며 쌓입니다.
- EV 코드 서명 인증서: 초기 SmartScreen 신뢰 확보에 더 유리하지만 비용과 발급 절차가 큽니다.
- 자체 서명 인증서: 내부 테스트에는 가능하지만 외부 PC에서는 신뢰되지 않습니다.

## 서명 예시

Windows SDK의 `signtool.exe`가 PATH에 있어야 합니다.

```powershell
.\sign_app.ps1 -ExePath .\dist\KoreanVietnameseTranslator.exe -CertificateThumbprint "YOUR_CERT_THUMBPRINT"
```

직접 실행하려면:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /sha1 YOUR_CERT_THUMBPRINT .\dist\KoreanVietnameseTranslator.exe
signtool verify /pa /v .\dist\KoreanVietnameseTranslator.exe
```

## 배포 체크리스트

- exe 또는 installer를 같은 이름/버전으로 반복 배포하지 말고 버전을 올립니다.
- 다운로드 페이지, 배포 도메인, 인증서 주체명을 일관되게 유지합니다.
- 백신 오탐이 발생하면 해당 보안 벤더에 false positive 신고를 합니다.
- API 키나 로그 파일은 배포물에 포함하지 않습니다.
