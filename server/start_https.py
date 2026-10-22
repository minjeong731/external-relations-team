#!/usr/bin/env python3
"""Prototype HTTPS bridge: retain the existing GitHub Pages site and use this PC as storage.

Prerequisites (owner PC only):
- Python 3.10+
- Tailscale installed, signed in, and Funnel enabled/approved by the owner.
- Fictional data ONLY; this is not a company-approved production deployment.

Staff do not install Python/Tailscale or run BAT files.
"""
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer

# Import after setting HOST, so the bridge listens only on this PC.
os.environ["PERMIT_HOST"] = "127.0.0.1"
os.environ["PERMIT_ENABLE_TEST_AUTO_ACCOUNT"] = "1"
import app
from lan_app import LANHandler
from start_lan import prepare_first_admin


def tailscale_cli():
    found = shutil.which("tailscale")
    if found:
        return str(found)
    for var in ("ProgramFiles", "ProgramW6432"):
        folder = os.environ.get(var, "")
        if folder:
            candidate = Path(folder) / "Tailscale" / "tailscale.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def run_funnel(command, *args, timeout=90):
    return subprocess.run(
        [command, *args], stdin=None, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, check=False
    )


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("\n" + "=" * 58)
    print("인허가 검토 통합관리 - 고정 HTTPS 웹주소 연결 준비")
    print("=" * 58)
    print("이 실행기는 테스트용입니다. 실제 회사 자료나 회사 로그인 암호는 입력하지 마세요.")
    print("직원에게는 인터넷 웹주소만 전달하고 프로그램 설치를 요구하지 않습니다.")
    print("HTTPS 주소는 외부에 공개됩니다. PC에서 실행을 종료하면 공동 저장 접속도 중단됩니다.")
    print("회사 보안 정책상 외부 터널 사용이 허용되는지 확인한 후 실행하세요.\n")
    cli = tailscale_cli()
    if not cli:
        print("PC에서 Tailscale을 찾지 못했습니다.")
        print("PC 소유자만 https://tailscale.com/download/windows 에서 설치하고 로그인하세요.")
        print("설치 후 이 파일을 다시 실행하면 고정 HTTPS 연결을 설정합니다.")
        return 2
    check = run_funnel(cli, "status", timeout=20)
    if check.returncode:
        print("Tailscale 로그인이 아직 완료되지 않았거나 네트워크가 연결되지 않았습니다.")
        print(check.stdout[-1400:])
        return 3
    prepare_first_admin()
    try:
        app.boot()
    finally:
        os.environ.pop("PERMIT_ADMIN_PASSWORD", None)
    try:
        server = ThreadingHTTPServer((app.HOST, app.PORT), LANHandler)
    except OSError as e:
        print("PC 서버 시작 실패:", e)
        print("현재 실행 중인 기존 PC 공동저장 프로그램을 먼저 종료해 주세요.")
        return 4
    print("PC 서버 가동: http://127.0.0.1:" + str(app.PORT))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print("Tailscale Funnel HTTPS 연결을 준비합니다. 최초 사용 시 브라우저에서 허용이 필요할 수 있습니다.")
        try:
            result = run_funnel(cli, "funnel", "--bg", str(app.PORT), timeout=180)
        except subprocess.TimeoutExpired:
            print("Tailscale Funnel 응답이 없었습니다. 승인 창을 확인하고 다시 시도하세요.")
            return 5
        if result.returncode:
            print("HTTPS 연결 승인 또는 설정이 완료되지 않았습니다.")
            print(result.stdout[-2600:])
            print("자세한 설명: https://tailscale.com/docs/features/tailscale-funnel")
            return 6
        print("\n" + result.stdout.strip())
        status = run_funnel(cli, "funnel", "status", timeout=25)
        raw = result.stdout + "\n" + status.stdout
        matches = re.findall(r"https://[A-Za-z0-9.-]+\.ts\.net(?::\d+)?", raw, re.I)
        if matches:
            public = matches[0]
            print("\n" + "=" * 58)
            print("HTTPS 저장 서버 주소:", public)
            print("이 주소에는 실제 비밀번호가 아니라 서버의 위치만 담겨 있습니다.")
            print("이 주소를 ChatGPT 대화로 전달하면 기존 GitHub Pages 웹주소와 연결 설정을 마칠 수 있습니다.")
        else:
            print("고정 HTTPS 주소를 인식하지 못했습니다.")
            print("다음 명령으로 주소를 확인할 수 있습니다: tailscale funnel status")
            print(status.stdout[-1800:])
        print("네 PC 저장 경로:", app.BASE)
        print("이 PC 전원을 끄면 접속은 끊기지만 자료는 계속 보관됩니다.")
        print("PC 서버는 실행 중이며 이 창을 닫거나 Ctrl+C를 누르면 중단됩니다.")
        print("실제 회사 자료 입력은 금지됩니다. 먼저 가상 자료로 확인하세요.")
        print("=" * 58 + "\n")
        webbrowser.open("http://127.0.0.1:" + str(app.PORT))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=4)
        print("PC 저장 서버 종료. Funnel 연결 상태는 Tailscale 설정에서 확인하세요.")


if __name__ == "__main__":
    sys.exit(main())
