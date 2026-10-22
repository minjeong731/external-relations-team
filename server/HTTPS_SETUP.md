# 기존 GitHub 웹주소 + 내 PC 저장소 연결 (HTTPS)

**목표:** 직원에게는 **기존의 한 웹주소** `https://minjeong731.github.io/external-relations-team/`만 공유합니다. 일반 직원과 인허가팀은 프로그램 설치 없이 브라우저에서 계정 로그인, 접수, 검토, 회신을 사용합니다. 데이터베이스·첨부파일은 기존 PC에 남습니다.

**현재 구현 상태:** 프런트엔드 CORS/API 연결 코드와 PC의 HTTPS Funnel 실행 코드를 작성했습니다. **실제 고정 HTTPS 주소는 PC 소유자가 한 번 활성화해야 발급되므로, 아직 실사용 인터넷 연결은 완료되지 않았습니다.** 서버 주소를 GitHub Pages 설정에 입력하기 전까지 기존 인터넷 주소는 시연 모드입니다.

## PC 소유자가 한 번 해야 할 작업 (직원은 아무것도 설치하지 않음)

1. 회사에서 외부 터널 접속이 허용되는지 확인합니다. **실제 회사 내부 자료를 공개 인터넷에 노출시키지 마세요.** 지금 기능은 가상의 테스트 자료 전용입니다.
2. PC 소유자만 [Tailscale Windows 설치](https://tailscale.com/download/windows)를 진행하고 로그인합니다. Tailscale Funnel은 고정 `*.ts.net` HTTPS 주소를 제공하며, 처음 사용할 때 Funnel 활성화를 승인해야 할 수 있습니다.
3. GitHub 저장소 최상위의 **`PC_HTTPS_웹공유_시작.bat`** 파일을 다운로드해 더블클릭합니다. 실행파일은 원본 GitHub 프로젝트의 최신 소스를 **PC에 자동 동기화**하고, 기존 데이터베이스·첨부파일은 건드리지 않습니다. 이미 기존 PC 서버를 실행 중이면 그 창에서 Ctrl+C로 종료합니다.
4. 최초 Funnel 실행 시 브라우저가 인증/승인을 요구하면 PC 소유자가 승인합니다. 실행창에서 예를 들어 **`https://your-pc.your-tailnet.ts.net`** 형태의 고정 주소를 확인합니다. 이 주소는 예시이며 실제 주소가 아닙니다.
5. 실제로 발급된 HTTPS 주소를 이 대화에 알려주면 GitHub 저장소의 **`docs/runtime-config.js`에 해당 주소를 연결**할 수 있습니다. 비밀번호나 Tailscale 인증 토큰, 사용자의 업무자료는 대화나 GitHub 공개 파일에 붙여넣지 마세요.
6. 연결 설정 배포 후에는 팀장님 포함 직원 모두 **기존 GitHub 웹주소 하나**로 접속합니다. 직원용 PC에는 Tailscale, Python 또는 BAT가 필요하지 않습니다.

연결 전에도 원격 연동을 시험해보려면 GitHub Pages 주소 뒤에 `?server=https%3A%2F%2Fyour-pc.your-tailnet.ts.net`을 붙일 수 있습니다. 이 예시의 터널 주소는 실제 발급된 주소로 바꿔야 합니다. 이 임시 연결 링크는 사이트 코드를 바꾸지 않고도 원격 API를 선택해 테스트하는 용도입니다.

## 중요한 기술 및 보안 조건

- 네 PC가 켜져 있고 HTTPS 터널과 PC 저장 서버가 실행 중일 때만 직원들이 조회·접수할 수 있습니다. PC를 끄면 저장된 데이터는 유지되지만 웹사이트의 공동 저장 기능에는 접속할 수 없습니다.
- Tailscale Funnel은 외부 인터넷 누구나 도달할 수 있는 **공개 HTTPS 경로**입니다. 기존 앱의 `@hdc-resort.com` 입력 방식은 메일 소유권을 검증하지 않습니다. **6자 비밀번호 + 미인증 자동계정 생성 상태는 실제 회사 문서/개인정보를 다룰 수 있는 보안 수준이 아닙니다.**
- 실무 운영 전에는 회사 승인, 안전한 계정 인증(메일 인증 또는 사내 SSO), 암호 정책 강화, 방화벽·접근통제 정책, 감사 로그 보호 및 백업·복원 테스트가 반드시 필요합니다. 이 코드를 완성된 사내 운영시스템으로 소개해서는 안 됩니다.
- 고정 터널 도메인은 PC를 다시 켜도 유지되지만, Funnel 실행 자체는 PC 소유자가 다시 시작해야 할 수 있습니다. Tailscale 계정이나 PC 이름 변경 시 주소가 달라질 수 있습니다.
- 접속 주소를 정한 뒤 GitHub Pages에서 **변경해야 할 값은 URL 하나**입니다. 절대로 관리자 암호, API 토큰, 직원 개인정보, 파일 내용을 이 공개 GitHub 저장소에 올리지 마세요.

## 프로그램 원본

- PC 실행기: `PC_HTTPS_웹공유_시작.bat`
- HTTPS 서버 진입점: `server/start_https.py`
- 기존 웹화면: `docs/index.html`
- 기존 REST API/DB: `server/app.py`
- 원격 주소 연결: `docs/runtime-config.js`
- 자동검증: `python -m unittest discover -s server -v`

참고: [Tailscale Funnel 설명](https://tailscale.com/docs/features/tailscale-funnel) · [안정적인 Funnel 공개 주소](https://tailscale.com/docs/use-cases/application-testing/share-local-dev-server-with-internet)
