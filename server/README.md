# 인허가 검토 시스템 · 공동 저장 API

이 폴더는 GitHub Pages와 **별도로 실행해야 하는 서버 코드**입니다.
기존 웹디자인은 docs/index.html에 유지했습니다.
docs/runtime-config.js에서 PERMIT_API_BASE를 HTTPS 서버 주소로 설정하면 로그인 및 공동 저장 모드로 전환됩니다.

구현: 회사 이메일 로그인, 관리자 직원 등록, SQLite 공용 접수번호/회신/변경기록, 서버 첨부파일 저장, 직원별 권한.

**현재는 코드만 작성된 상태이며 서버를 배포하지 않았습니다.** GitHub Pages는 그대로 시연 화면입니다.
실무자료 사용 전 회사 승인, HTTPS, 방화벽, 서버 백업 및 복구 테스트가 필요합니다. 서버 소스는 공개될 수 있으므로 DB·첨부파일·암호를 GitHub에 올리지 마세요.

Python 3.10+ 표준 라이브러리만 사용합니다.

환경변수:
- PERMIT_DATA_DIR: 비공개 DB/첨부파일 저장 폴더
- PERMIT_ADMIN_EMAIL: 초기 관리자 메일 (기본 minjeong.kang@hdc-resort.com)
- PERMIT_ADMIN_PASSWORD: 첫 실행에 반드시 필요한 12자 이상의 관리자 비밀번호 (코드에 작성 금지)
- PERMIT_HOST: 기본 127.0.0.1, HTTPS 프록시 뒤에 두어야 함
- PERMIT_PORT: 기본 8765
- PERMIT_ALLOWED_ORIGIN: 기본 https://minjeong731.github.io

실행은 python server/app.py. 테스트는 python -m unittest discover -s server -v.
서버가 공개 HTTPS 환경에서 보안 승인을 받은 이후에만 docs/runtime-config.js에 서버 주소를 지정하세요.

아직 미구현: 회사 메일 실제 발송, 회사 통합 로그인, 서버 운영/정기 백업, 보안 감사, 외부 HTTPS 배포.
