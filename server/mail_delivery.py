"""Optional company-approved outbound SMTP connector (no secrets in source control).

This module never sends unless PERMIT_MAIL_ENABLED=1, a TLS SMTP host is
configured, and the insecure auto-account pilot mode has been turned off.
Credentials must be injected as environment variables on the internal server.
"""
from email.message import EmailMessage
from email.utils import formataddr
import os
import re
import smtplib
import ssl

COMPANY_ADDRESS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%+\-]*@hdc-resort\.com$", re.I)


def mail_config():
    if os.environ.get("PERMIT_MAIL_ENABLED") != "1":
        return None
    if os.environ.get("PERMIT_ENABLE_TEST_AUTO_ACCOUNT") == "1":
        return None
    mode = os.environ.get("PERMIT_SMTP_SECURITY", "starttls").strip().lower()
    if mode not in ("ssl", "starttls"):
        return None
    host = os.environ.get("PERMIT_SMTP_HOST", "").strip()
    from_address = os.environ.get("PERMIT_MAIL_FROM", "").strip().lower()
    team = os.environ.get("PERMIT_TEAM_MAIL", "").strip().lower()
    from_name = os.environ.get("PERMIT_MAIL_FROM_NAME", "인허가 검토 시스템").strip()
    if not from_name or len(from_name) > 60 or "\r" in from_name or "\n" in from_name:
        return None
    if not host or not COMPANY_ADDRESS.fullmatch(from_address) or not COMPANY_ADDRESS.fullmatch(team):
        return None
    try:
        port = int(os.environ.get("PERMIT_SMTP_PORT", "465" if mode == "ssl" else "587"))
    except ValueError:
        return None
    if port < 1 or port > 65535:
        return None
    return {
        "host": host, "port": port, "mode": mode,
        "from": from_address, "from_name": from_name, "team": team,
        "username": os.environ.get("PERMIT_SMTP_USER", ""),
        "password": os.environ.get("PERMIT_SMTP_PASSWORD", "")
    }


def make_message(event, ticket, config):
    if event == "request":
        destination = config["team"]
        subject = "[인허가 검토 요청][" + ticket["id"] + "] " + ticket["title"]
        body = (
            "인허가 검토 요청이 새로 접수되었습니다.\n\n"
            "접수번호: " + ticket["id"] + "\n"
            "요청부서: " + ticket["department"] + "\n"
            "요청자: " + ticket["requester"] + "\n"
            "요청 제목: " + ticket["title"] + "\n\n"
            "인허가 검토 통합관리 시스템에 로그인하여 확인해 주세요.\n"
            "※ 첨부자료와 상세 내용은 시스템에서 확인하세요."
        )
    elif event == "reply":
        destination = ticket["email"]
        if not COMPANY_ADDRESS.fullmatch(destination):
            raise ValueError("수신자 회사 이메일 주소가 유효하지 않습니다.")
        subject = "[인허가 검토 결과][" + ticket["id"] + "] " + ticket["title"]
        review = ticket["review"] or {}
        body = (
            ticket["requester"] + " 님, 요청하신 검토 결과를 안내드립니다.\n\n"
            "접수번호: " + ticket["id"] + "\n"
            "검토분야: " + ticket["category"] + "\n"
            "회신자: " + ticket["assigned"] + "\n\n"
            "1. 검토 결과\n" + (review.get("result") or "별도 기재 없음") + "\n\n"
            "2. 관계 법령 및 검토 근거\n" + (review.get("law") or "별도 기재 없음") + "\n\n"
            "3. 필요한 후속 조치\n" + (review.get("action") or "별도 기재 없음") + "\n\n"
            "4. 예상 소요기간\n" + (review.get("period") or "별도 기재 없음") + "\n\n"
            "인허가 검토 통합관리 시스템에서 회신 내역을 확인할 수 있습니다."
        )
    else:
        raise ValueError("지원하지 않는 메일 이벤트입니다.")
    message = EmailMessage()
    message["From"] = formataddr((config.get("from_name", "인허가 검토 시스템"), config["from"]))
    message["To"] = destination
    message["Subject"] = subject.replace("\r", " ").replace("\n", " ")[:200]
    message.set_content(body)
    return message


def send_event(event, ticket):
    """Return (status, destination, short_failure_reason). Never expose credentials."""
    config = mail_config()
    if config is None:
        return "not_configured", "", "회사 메일 연동 또는 안전한 인증 설정이 아직 완료되지 않았습니다."
    try:
        message = make_message(event, ticket, config)
        context = ssl.create_default_context()
        if config["mode"] == "ssl":
            client = smtplib.SMTP_SSL(config["host"], config["port"], timeout=8, context=context)
        else:
            client = smtplib.SMTP(config["host"], config["port"], timeout=8)
        with client as smtp:
            if config["mode"] == "starttls":
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            if config["username"]:
                smtp.login(config["username"], config["password"])
            smtp.send_message(message)
        return "accepted", message["To"], ""
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        # Exception messages may contain server names or mail content.
        return "failed", "", type(exc).__name__
