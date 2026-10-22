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

    def test_admin_settings_are_separate_from_review_inbox(self):
        status, html = self.get("/")
        self.assertEqual(status, 200)
        review = html.split('<section id="screen-team" hidden>', 1)[1].split('<section id="screen-admin" hidden>', 1)[0]
        admin = html.split('<section id="screen-admin" hidden>', 1)[1].split('<section id="screen-archive" hidden>', 1)[0]
        self.assertNotIn('id="live-admin-users"', review)
        self.assertNotIn('id="live-reset-form"', review)
        self.assertIn('id="live-admin-users"', admin)
        self.assertIn('id="live-reset-form"', admin)
        self.assertIn('data-screen="admin" id="admin-menu" hidden', html)
        self.assertIn('data-screen="admin" id="admin-mobile-menu" hidden', html)
        self.assertIn("screen === 'admin' && isAdmin", html)
        self.assertIn("live.user?.role==='admin'", html)
        self.assertIn('id="live-accounts-list"', admin)
        self.assertIn('id="live-role-form"', admin)
        self.assertNotIn('id="live-admin-form"', admin)
        self.assertIn("live.updateUserRole(target.id,destination", html)


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

    def test_admin_reset_and_forced_password_change_preserves_requests(self):
        import urllib.error
        def req(path, body=None, token=None):
            headers = {"Origin": self.base}
            if token: headers["Authorization"] = "Bearer " + token
            if body is not None: headers["Content-Type"] = "application/json"
            request = Request(self.base + path,
                              json.dumps(body).encode() if body is not None else None,
                              headers=headers)
            try:
                with urlopen(request, timeout=6) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read())
        code, admin_login = req("/api/login", {"email":"minjeong.kang@hdc-resort.com", "password":"abcdef"})
        self.assertEqual(code, 200)
        admin = admin_login["token"]
        staff_email = "reset-test-employee@hdc-resort.com"
        code, _ = req("/api/users", {"email":staff_email,"password":"original123","role":"requester"}, admin)
        self.assertEqual(code, 201)
        code, staff_login = req("/api/login", {"email":staff_email,"password":"original123"})
        self.assertEqual(code, 200)
        staff_token = staff_login["token"]
        owner_id = staff_login["user"]["id"]
        ticket_body = {"department":"시험팀","requester":"테스트직원","date":"2026-10-22",
                       "title":"초기화 후에도 남아야 할 요청","site":"가상 현장","category":"건축",
                       "question":"가상 질문","current":"가상 현황","purpose":"테스트"}
        code, made = req("/api/tickets", ticket_body, staff_token)
        self.assertEqual(code, 201)
        ticket_id = made["ticket"]["id"]
        code, _ = req("/api/users",token=staff_token)
        self.assertEqual(code, 403)
        code, allusers = req("/api/users",token=admin)
        self.assertEqual(code, 200)
        target = next(x for x in allusers["users"] if x["email"]==staff_email)
        self.assertEqual(target["id"],owner_id)
        reset_route = "/api/users/" + str(owner_id) + "/reset-password"
        code, _ = req(reset_route, {"adminPassword":"abcdef"},staff_token)
        self.assertEqual(code, 403)
        code, _ = req(reset_route, {"adminPassword":"incorrect"},admin)
        self.assertEqual(code, 403)
        code, _ = req("/api/users/"+str(admin_login["user"]["id"])+"/reset-password",
                      {"adminPassword":"abcdef"},admin)
        self.assertEqual(code, 403)
        code, reset = req(reset_route, {"adminPassword":"abcdef"},admin)
        self.assertEqual(code, 200)
        self.assertEqual(reset["email"],staff_email)
        self.assertGreaterEqual(len(reset["temporaryPassword"]), 12)
        self.assertTrue(reset["mustChangePassword"])
        temporary = reset["temporaryPassword"]
        code, _ = req("/api/tickets",token=staff_token)
        self.assertEqual(code, 401)  # Original session revoked.
        code, _ = req("/api/login", {"email":staff_email,"password":"original123"})
        self.assertEqual(code, 401)
        code, temporary_login = req("/api/login", {"email":staff_email,"password":temporary})
        self.assertEqual(code, 200)
        self.assertTrue(temporary_login["user"]["mustChangePassword"])
        new_session = temporary_login["token"]
        code, _ = req("/api/tickets",token=new_session)
        self.assertEqual(code, 403)  # Must choose own password before viewing data.
        code, _ = req("/api/change-temporary-password",{"newPassword":"abc"},new_session)
        self.assertEqual(code, 400)
        code, _ = req("/api/change-temporary-password",{"newPassword":temporary},new_session)
        self.assertEqual(code, 400)
        code, changed = req("/api/change-temporary-password",
                            {"newPassword":"myNewPassword123"},new_session)
        self.assertEqual(code, 200)
        self.assertFalse(changed["user"]["mustChangePassword"])
        code, tickets = req("/api/tickets",token=new_session)
        self.assertEqual(code, 200)
        self.assertTrue(any(t["id"]==ticket_id for t in tickets["tickets"]))
        code, _ = req("/api/login",{"email":staff_email,"password":temporary})
        self.assertEqual(code, 401)
        code, new_login = req("/api/login",{"email":staff_email,"password":"myNewPassword123"})
        self.assertEqual(code, 200)
        self.assertFalse(new_login["user"]["mustChangePassword"])
        with app.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users WHERE email=?",(staff_email,)).fetchone()[0],1)
            self.assertGreaterEqual(db.execute("SELECT COUNT(*) FROM security_events WHERE target_id=?",(owner_id,)).fetchone()[0],2)
            self.assertEqual(db.execute("SELECT owner_id FROM tickets WHERE id=?",(ticket_id,)).fetchone()[0],owner_id)

    def test_admin_promotes_self_created_account_without_changing_password(self):
        import urllib.error
        def api(path, body=None, token=None):
            headers={"Origin": self.base}
            if token: headers["Authorization"]="Bearer "+token
            if body is not None: headers["Content-Type"]="application/json"
            req=Request(self.base+path, json.dumps(body).encode() if body is not None else None,headers=headers)
            try:
                with urlopen(req,timeout=8) as response:
                    return response.status,json.loads(response.read())
            except urllib.error.HTTPError as err:
                return err.code,json.loads(err.read())
        status,admin_login=api("/api/login",{"email":"minjeong.kang@hdc-resort.com","password":"abcdef"})
        self.assertEqual(status,200)
        admin=admin_login["token"]
        employee_email="role-change-employee@hdc-resort.com"
        os.environ["PERMIT_ENABLE_TEST_AUTO_ACCOUNT"]="1"
        try:
            status,initial=api("/api/login",{"email":employee_email,"password":"worker-pass-123","role":"admin"})
            self.assertEqual(status,200)
            self.assertTrue(initial["created"])
            self.assertEqual(initial["user"]["role"],"requester")
            staff=initial["token"]
            staff_id=initial["user"]["id"]
            with app.connection() as db:
                prior_hash=db.execute("SELECT passhash FROM users WHERE id=?",(staff_id,)).fetchone()[0]
            ticket={"department":"샘플부서","requester":"가상 사용자","date":"2026-10-22",
                    "title":"권한 변경 전 접수","site":"가상 현장","category":"기타",
                    "question":"가상 질문","current":"현황","purpose":"테스트"}
            status,created=api("/api/tickets",ticket,staff)
            self.assertEqual(status,201)
            ticket_id=created["ticket"]["id"]
            status,all_users=api("/api/users",token=admin)
            self.assertEqual(status,200)
            user=next(x for x in all_users["users"] if x["email"]==employee_email)
            self.assertEqual(user["role"],"requester")
            self.assertTrue(user["created"].startswith("2026-"))
            endpoint="/api/users/"+str(staff_id)+"/role"
            status,_=api(endpoint,{"role":"reviewer","adminPassword":"abcdef"},staff)
            self.assertEqual(status,403)
            status,_=api(endpoint,{"role":"reviewer","adminPassword":"wrong"},admin)
            self.assertEqual(status,403)
            status,_=api(endpoint,{"role":"admin","adminPassword":"abcdef"},admin)
            self.assertEqual(status,400)
            admin_id=admin_login["user"]["id"]
            status,_=api("/api/users/"+str(admin_id)+"/role",
                         {"role":"requester","adminPassword":"abcdef"},admin)
            self.assertEqual(status,403)
            status,upgraded=api(endpoint,{"role":"reviewer","adminPassword":"abcdef"},admin)
            self.assertEqual(status,200)
            self.assertEqual(upgraded["role"],"reviewer")
            self.assertTrue(upgraded["requiresRelogin"])
            status,_=api("/api/tickets",token=staff)
            self.assertEqual(status,401) # Old session invalidated
            status,reviewer_login=api("/api/login",{"email":employee_email,"password":"worker-pass-123"})
            self.assertEqual(status,200)
            self.assertFalse(reviewer_login["created"])
            self.assertEqual(reviewer_login["user"]["role"],"reviewer")
            status,requests=api("/api/tickets",token=reviewer_login["token"])
            self.assertEqual(status,200)
            self.assertIn(ticket_id,[r["id"] for r in requests["tickets"]])
            with app.connection() as db:
                self.assertEqual(db.execute("SELECT passhash FROM users WHERE id=?",(staff_id,)).fetchone()[0],prior_hash)
                action=db.execute("SELECT action FROM security_events WHERE target_id=? ORDER BY id DESC",(staff_id,)).fetchone()[0]
                self.assertEqual(action,"인허가팀 권한 부여")
            status,demoted=api(endpoint,{"role":"requester","adminPassword":"abcdef"},admin)
            self.assertEqual(status,200)
            self.assertEqual(demoted["role"],"requester")
            status,staff_again=api("/api/login",{"email":employee_email,"password":"worker-pass-123"})
            self.assertEqual(status,200)
            self.assertEqual(staff_again["user"]["role"],"requester")
            status,requests=api("/api/tickets",token=staff_again["token"])
            self.assertEqual(status,200)
            self.assertEqual([r["id"] for r in requests["tickets"]],[ticket_id])
            with app.connection() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM users WHERE email=?",(employee_email,)).fetchone()[0],1)
                self.assertEqual(db.execute("SELECT passhash FROM users WHERE id=?",(staff_id,)).fetchone()[0],prior_hash)
        finally:
            os.environ.pop("PERMIT_ENABLE_TEST_AUTO_ACCOUNT",None)

    def test_first_login_auto_creates_requester_only(self):
        import urllib.error
        email = "staff.firstlogin@hdc-resort.com"
        def post(data, path="/api/login"):
            body = json.dumps(data).encode()
            req = Request(self.base + path, body,
                          headers={"Content-Type": "application/json", "Origin": self.base})
            try:
                with urlopen(req, timeout=5) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read())
        status, _ = post({"email": email, "password": "abcdef"})
        self.assertEqual(status, 401)  # No automatic accounts outside PC pilot.
        os.environ["PERMIT_ENABLE_TEST_AUTO_ACCOUNT"] = "1"
        try:
            status, _ = post({"email": email, "password": "abcde"})
            self.assertEqual(status, 400)
            status, created = post({"email": email, "password": "abcdef", "role": "admin"})
            self.assertEqual(status, 200)
            self.assertTrue(created["created"])
            self.assertEqual(created["user"]["role"], "requester")
            status, wrong = post({"email": email, "password": "wrongpw"})
            self.assertEqual(status, 401)  # Cannot reset another person's password.
            self.assertIn("비밀번호가 일치하지 않습니다", wrong["error"])
            status, logged_in = post({"email": email, "password": "abcdef"})
            self.assertEqual(status, 200)
            self.assertFalse(logged_in["created"])
            self.assertEqual(logged_in["user"]["id"], created["user"]["id"])
            with app.connection() as db:
                count = db.execute("SELECT COUNT(*) FROM users WHERE email=?", (email,)).fetchone()[0]
            self.assertEqual(count, 1)
            status, _ = post({"email": "staff.other@hdc-resort.com", "password": "abcdef"}, "/api/signup")
            self.assertEqual(status, 401)  # No anonymous signup endpoint; authentication is required.
        finally:
            os.environ.pop("PERMIT_ENABLE_TEST_AUTO_ACCOUNT", None)

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
