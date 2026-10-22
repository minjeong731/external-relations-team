"""Office PC launcher / same-origin static page functional tests."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

import app
from lan_app import LANHandler


class LanServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.oldbase, cls.oldpath, cls.oldfiles = app.BASE, app.DB_PATH, app.FILES
        app.BASE = Path(cls.temp.name)
        app.DB_PATH = app.BASE / "permit.sqlite3"
        app.FILES = app.BASE / "attachments"
        os.environ["PERMIT_ADMIN_PASSWORD"] = "abcdef"
        app.boot()
        os.environ.pop("PERMIT_ADMIN_PASSWORD", None)
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), LANHandler)
        cls.base = "http://127.0.0.1:" + str(cls.http.server_port)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=4)
        app.BASE, app.DB_PATH, app.FILES = cls.oldbase, cls.oldpath, cls.oldfiles
        cls.temp.cleanup()

    def get(self, path):
        with urlopen(self.base + path, timeout=5) as response:
            return response.status, response.read().decode()

    def test_same_origin_web_and_runtime_config(self):
        status, html = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn('id="live-login-form"', html)
        self.assertIn('src="./live-api.js"', html)
        status, config = self.get("/runtime-config.js")
        self.assertEqual(status, 200)
        self.assertIn("window.PERMIT_API_BASE = window.location.origin;", config)
        status, js = self.get("/live-api.js")
        self.assertEqual(status, 200)
        self.assertIn("window.location.origin", js)
        status, health = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(health)["storage"], "server")

    def test_staff_can_self_register_but_not_claim_review_role(self):
        os.environ["PERMIT_ENABLE_TEST_SELF_SIGNUP"] = "1"
        try:
            email = "staff.selftest@hdc-resort.com"
            def post(data):
                body = json.dumps(data).encode()
                req = Request(self.base + "/api/signup", body,
                              headers={"Content-Type": "application/json", "Origin": self.base})
                try:
                    with urlopen(req, timeout=5) as response:
                        return response.status, json.loads(response.read())
                except __import__("urllib.error", fromlist=["HTTPError"]).HTTPError as err:
                    return err.code, json.loads(err.read())
            status, _ = post({"email": email, "password": "12345"})
            self.assertEqual(status, 400)
            status, account = post({"email": email, "password": "abcdef", "role": "reviewer"})
            self.assertEqual(status, 201)
            self.assertEqual(account["role"], "requester")
            self.assertIs(account["verified"], False)
            status, _ = post({"email": email, "password": "abcdef"})
            self.assertEqual(status, 400)
            login_body = json.dumps({"email": email, "password": "abcdef"}).encode()
            req = Request(self.base + "/api/login", login_body,
                          headers={"Content-Type": "application/json", "Origin": self.base})
            with urlopen(req, timeout=5) as response:
                user = json.loads(response.read())["user"]
            self.assertEqual(user["role"], "requester")
        finally:
            os.environ.pop("PERMIT_ENABLE_TEST_SELF_SIGNUP", None)

    def test_post_login_from_lan_origin_and_db_reopen(self):
        body = json.dumps({"email": "minjeong.kang@hdc-resort.com",
                           "password": "abcdef"}).encode()
        req = Request(self.base + "/api/login", body,
                      headers={"Content-Type": "application/json", "Origin": self.base})
        with urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)
            logged_in = json.loads(response.read())
            self.assertEqual(logged_in["user"]["role"], "admin")
        with app.connection() as db:
            count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        self.assertGreaterEqual(count, 1)
        # The database persists when new SQLite connections are opened.
        with app.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], count)


if __name__ == "__main__":
    unittest.main()
