"""No-network tests for TLS company-email notifications."""
import os
import unittest
from unittest.mock import patch
import mail_delivery


class FakeSMTP:
    sent = []
    last = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port
        self.tls = context is not None
        self.logins = []
        FakeSMTP.last = self

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        self.tls = context is not None

    def login(self, user, password):
        self.logins.append((user, password))

    def send_message(self, message):
        if not self.tls:
            raise AssertionError("Plaintext SMTP is forbidden")
        FakeSMTP.sent.append(message)


SAMPLE = {
    "id": "2026-009", "department": "시설부서", "requester": "테스트직원",
    "title": "건축물 검토 문의", "email": "worker@hdc-resort.com",
    "category": "건축·설계변경", "assigned": "reviewer@hdc-resort.com",
    "review": {"result": "검토 완료", "law": "가상 법령",
               "action": "가상 조치", "period": "약 1주"}
}
SETTINGS = {
    "PERMIT_MAIL_ENABLED": "1",
    "PERMIT_ENABLE_TEST_AUTO_ACCOUNT": "0",
    "PERMIT_SMTP_HOST": "mail.internal.example",
    "PERMIT_SMTP_PORT": "587",
    "PERMIT_SMTP_SECURITY": "starttls",
    "PERMIT_SMTP_USER": "mail-service@hdc-resort.com",
    "PERMIT_SMTP_PASSWORD": "non-real-test-secret",
    "PERMIT_MAIL_FROM": "mail-service@hdc-resort.com",
    "PERMIT_TEAM_MAIL": "permits@hdc-resort.com"
}


class MailDeliveryTests(unittest.TestCase):
    def setUp(self):
        FakeSMTP.sent = []

    def test_default_is_no_send(self):
        with patch.dict(os.environ, {"PERMIT_MAIL_ENABLED": "0"}):
            with patch.object(mail_delivery.smtplib, "SMTP", side_effect=AssertionError("Network should not run")):
                result = mail_delivery.send_event("request", SAMPLE)
        self.assertEqual(result[0], "not_configured")

    def test_tls_sends_request_and_reply_to_company_addresses_only(self):
        with patch.dict(os.environ, SETTINGS):
            with patch.object(mail_delivery.smtplib, "SMTP", FakeSMTP):
                first = mail_delivery.send_event("request", SAMPLE)
                second = mail_delivery.send_event("reply", SAMPLE)
        self.assertEqual(first[:2], ("accepted", "permits@hdc-resort.com"))
        self.assertEqual(second[:2], ("accepted", "worker@hdc-resort.com"))
        self.assertEqual(len(FakeSMTP.sent), 2)
        self.assertIn("2026-009", FakeSMTP.sent[0]["Subject"])
        self.assertIn("검토 완료", FakeSMTP.sent[1].get_content())
        self.assertIn("건축·설계변경", FakeSMTP.sent[1].get_content())
        self.assertEqual(FakeSMTP.last.logins, [("mail-service@hdc-resort.com", "non-real-test-secret")])

    def test_test_auto_account_disables_delivery_even_if_smtp_is_configured(self):
        with patch.dict(os.environ, {**SETTINGS, "PERMIT_ENABLE_TEST_AUTO_ACCOUNT": "1"}):
            self.assertEqual(mail_delivery.send_event("request", SAMPLE)[0], "not_configured")

    def test_outside_recipient_and_insecure_transport_are_rejected(self):
        with patch.dict(os.environ, SETTINGS):
            foreign = dict(SAMPLE, email="external@example.com")
            self.assertRaises(ValueError, mail_delivery.make_message, "reply", foreign, mail_delivery.mail_config())
        with patch.dict(os.environ, {**SETTINGS, "PERMIT_SMTP_SECURITY": "plain"}):
            self.assertIsNone(mail_delivery.mail_config())

    def test_explicit_tls_ssl_mode(self):
        with patch.dict(os.environ, {**SETTINGS, "PERMIT_SMTP_SECURITY": "ssl", "PERMIT_SMTP_PORT": "465"}):
            with patch.object(mail_delivery.smtplib, "SMTP_SSL", FakeSMTP):
                result = mail_delivery.send_event("request", SAMPLE)
        self.assertEqual(result[0], "accepted")


if __name__ == "__main__":
    unittest.main()
