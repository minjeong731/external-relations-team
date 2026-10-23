#!/usr/bin/env python3
"""Open the shared app using the user's Windows PC as the office LAN server."""
import getpass
import ipaddress
import logging
import os
import socket
import ssl
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
import re
import sys
import threading
import time
import webbrowser

os.environ.setdefault("PERMIT_HOST", "0.0.0.0")
import app
from lan_app import LANHandler
from http.server import ThreadingHTTPServer

def addresses():
    found = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            found.add(sock.getsockname()[0])
    except OSError:
        pass
    try:
        for entry in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            found.add(entry[4][0])
    except OSError:
        pass
    return sorted(ip for ip in found if
                  ipaddress.ip_address(ip).is_private and
                  not ipaddress.ip_address(ip).is_loopback)

def prepare_first_admin():
    if app.DB_PATH.exists():
        return
    print("\n최초 관리자 계정 설정 (비밀번호는 화면에 표시되지 않습니다)")
    print("계정: " + os.environ.get("PERMIT_ADMIN_EMAIL", "minjeong.kang@hdc-resort.com"))
    print("비밀번호는 이 PC에 직접 입력하고, 대화창이나 GitHub에 올리지 마세요.")
    print("주의: 6자 비밀번호는 가상 자료를 사용하는 초기 테스트에만 권장합니다.")
    while True:
        password = getpass.getpass("6자 이상 관리자 비밀번호: ")
        confirm = getpass.getpass("한 번 더 입력: ")
        if len(password) < 6:
            print("비밀번호는 6자 이상이어야 합니다.")
        elif password != confirm:
            print("입력한 비밀번호가 서로 다릅니다.")
        else:
            os.environ["PERMIT_ADMIN_PASSWORD"] = password
            return

def test_dooray_smtp():
    """Send one harmless test message to the same mailbox; no secrets stored."""
    print("\n[Dooray 회사메일 발송 테스트]")
    print("수신자는 발신자 본인입니다. 실제 검토요청이나 업무자료는 전송하지 않습니다.")
    sender = os.environ.get("PERMIT_ADMIN_EMAIL", "minjeong.kang@hdc-resort.com").strip().lower()
    chosen = input("본인 회사 SMTP 이메일 [" + sender + "]: ").strip().lower()
    if chosen:
        sender = chosen
    if not re.fullmatch(r"[a-z0-9][a-z0-9._%+\-]*@hdc-resort\.com", sender):
        print("회사 이메일 주소를 확인해 주세요. 테스트를 취소합니다.")
        return
    print("설정: smtp.dooray.com / 465 / SSL")
    print("두레이 IMAP 설정 화면의 SMTP 비밀번호를 입력하세요.")
    print("비밀번호는 화면에 표시되지 않고 저장·전송 기록에 남기지 않습니다.")
    password = getpass.getpass("SMTP 비밀번호: ")
    if not password:
        print("비밀번호가 입력되지 않아 취소했습니다.")
        return
    reply = input("본인 이메일 " + sender + " 로 테스트 메일 1통을 보내시겠습니까? [y/N]: ").strip().lower()
    if reply not in ("y", "yes"):
        print("메일 발송 테스트를 취소했습니다.")
        return
    mail = EmailMessage()
    mail["From"] = formataddr(("인허가 검토 시스템", sender))
    mail["To"] = sender
    mail["Subject"] = "[인허가 검토 시스템] Dooray 메일 연결 테스트"
    mail.set_content("인허가 검토 통합관리 시스템의 SMTP 발송 연결 테스트입니다.\n실제 인허가 요청 또는 회신 데이터는 포함하지 않습니다.")
    try:
        with smtplib.SMTP_SSL("smtp.dooray.com", 465, timeout=12, context=ssl.create_default_context()) as smtp:
            smtp.login(sender, password)
            smtp.send_message(mail)
        print("✓ 두레이 SMTP 서버에서 메일을 접수했습니다.")
        print("Dooray 받은편지함 및 스팸함에서 테스트 메일을 확인해 주세요.")
    except smtplib.SMTPAuthenticationError:
        print("× SMTP 인증 실패: 입력한 SMTP 비밀번호와 아이디를 확인하세요.")
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        print("× 메일 연결 또는 발송 실패 (" + type(exc).__name__ + ").")
        print("인터넷 연결, 회사 네트워크의 465 포트 허용 여부, SMTP 사용 설정을 확인하세요.")
    finally:
        # Do not retain the password or message beyond this local smoke test.
        password = None


def console_mail_commands():
    print("메일 연결 테스트: 이 검은 실행창에서 T 입력 후 Enter (종료는 Ctrl+C).")
    while True:
        try:
            command = input()
        except (EOFError, OSError, KeyboardInterrupt):
            return
        if command.strip().lower() == "t":
            try:
                test_dooray_smtp()
            except (EOFError, KeyboardInterrupt):
                print("메일 테스트를 취소했습니다.")
            print("메일 연결 테스트 재실행: T 입력 후 Enter")


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    # Local-network test only: employees first-login to create requester account automatically.
    # No mailbox verification, so this must never be used for actual business records.
    os.environ["PERMIT_ENABLE_TEST_AUTO_ACCOUNT"] = "1"
    prepare_first_admin()
    try:
        app.boot()
    finally:
        os.environ.pop("PERMIT_ADMIN_PASSWORD", None)
    try:
        server = ThreadingHTTPServer((app.HOST, app.PORT), LANHandler)
    except OSError as exc:
        print("서버 시작 실패:", exc)
        print("다른 프로그램이 포트를 사용 중이거나 연결이 차단됐을 수 있습니다.")
        input("엔터를 누르면 종료합니다.")
        return 1
    print("\n" + "=" * 58)
    print("인허가 검토 통합관리 · PC 공동 저장 시작")
    print("내 PC: http://127.0.0.1:" + str(app.PORT) + "/")
    lan = addresses()
    if lan:
        for ip in lan:
            print("직원 접속: http://" + ip + ":" + str(app.PORT) + "/")
    else:
        print("직원 접속 주소는 명령 프롬프트의 ipconfig에서 IPv4 주소를 확인하세요.")
    print("접수·회신·사진 저장 위치: " + str(app.BASE))
    print("종료: 이 창에서 Ctrl+C (저장된 자료는 삭제되지 않음)")
    print("PC 전원 끔/절전 모드에서는 직원 접속이 중단됩니다.")
    print("주의: HTTP 연결이며 실제 회사 업무자료 대신 가상 테스트 자료만 사용하세요.")
    print("필요 시 사내 전산 담당자에게 이 PC의 포트 접근 정책을 확인하세요.")
    print("=" * 58 + "\n")
    threading.Timer(1, lambda: webbrowser.open("http://127.0.0.1:" + str(app.PORT) + "/")).start()
    # Optional human-initiated SMTP smoke test, without changing pilot-mode account safety.
    threading.Thread(target=console_mail_commands, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n프로그램 종료 · 데이터는 남아 있습니다.")
    finally:
        server.server_close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
