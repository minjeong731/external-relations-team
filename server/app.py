#!/usr/bin/env python3
"""HDC 인허가 검토: 공동 저장 REST API (Python 3.10+, stdlib + SQLite).

This server must run behind HTTPS before handling real company data.
GitHub Pages is a static frontend; this is NOT running on GitHub Pages.
Never commit the runtime DB, uploads, or credentials to a public repository.
"""
import base64
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

BASE = Path(os.environ.get("PERMIT_DATA_DIR", str(Path.home() / ".hdc-permit-data"))).resolve()
DB_PATH = BASE / "permit.sqlite3"
FILES = BASE / "attachments"
ALLOWED_ORIGIN = os.environ.get("PERMIT_ALLOWED_ORIGIN", "https://minjeong731.github.io").rstrip("/")
HOST = os.environ.get("PERMIT_HOST", "127.0.0.1")
PORT = int(os.environ.get("PERMIT_PORT", "8765"))
DOMAIN = "@hdc-resort.com"
MAX_JSON = 12 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf",
        ".xlsx", ".xls", ".docx", ".hwp", ".hwpx", ".dwg", ".dxf"}
MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".webp": "image/webp", ".gif": "image/gif", ".pdf": "application/pdf"}
FAILED = {}
TEST_AUTO_CREATED = {}

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def connection():
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=20000")
    return db

def passhash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 450000)
    return "pbkdf2-sha256$450000$" + salt.hex() + "$" + digest.hex()

def verify(password, stored):
    try:
        name, count, salt, digest = stored.split("$")
        if name != "pbkdf2-sha256": return False
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(count))
        return hmac.compare_digest(test, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False

def valid_email(email):
    return isinstance(email, str) and len(email) <= 120 and bool(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._%+\-]*@hdc-resort\.com", email, re.I)
    ) and ".." not in email

def boot():
    BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
    FILES.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(BASE, 0o700)
        os.chmod(FILES, 0o700)
    except OSError:
        pass
    with connection() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE,
          passhash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('requester','reviewer','admin')),
          created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          expires INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tickets (
          id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
          department TEXT NOT NULL, requester TEXT NOT NULL, email TEXT NOT NULL,
          date TEXT NOT NULL, title TEXT NOT NULL, site TEXT, category TEXT NOT NULL,
          question TEXT NOT NULL, current TEXT NOT NULL, purpose TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT '접수', assigned TEXT NOT NULL DEFAULT '',
          created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS replies (
          ticket_id TEXT PRIMARY KEY REFERENCES tickets(id),
          result TEXT NOT NULL, law TEXT NOT NULL, action TEXT NOT NULL,
          period TEXT NOT NULL, sent_at TEXT
        );
        CREATE TABLE IF NOT EXISTS attachments (
          id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES tickets(id),
          name TEXT NOT NULL, saved_name TEXT NOT NULL UNIQUE,
          size INTEGER NOT NULL, ext TEXT NOT NULL, created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL, actor_id INTEGER NOT NULL,
          action TEXT NOT NULL, occurred TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS security_events (
          id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL, target_id INTEGER NOT NULL,
          action TEXT NOT NULL, occurred TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tickets_owner ON tickets(owner_id);
        CREATE INDEX IF NOT EXISTS idx_attach_ticket ON attachments(ticket_id,id);
        """)
        columns = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
        if "must_change_password" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
        admin_email = os.environ.get("PERMIT_ADMIN_EMAIL", "minjeong.kang@hdc-resort.com").strip().lower()
        existing = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if not existing:
            password = os.environ.get("PERMIT_ADMIN_PASSWORD", "")
            if not valid_email(admin_email) or len(password) < 6:
                raise RuntimeError("First start: set PERMIT_ADMIN_EMAIL and PERMIT_ADMIN_PASSWORD (6+ chars).")
            db.execute("INSERT INTO users(email,passhash,role,created) VALUES(?,?,?,?)",
                       (admin_email, passhash(password), "admin", now()))
    logging.info("SQLite initialized at %s", DB_PATH)

def public_user(u):
    return {"id": u["id"], "email": u["email"], "role": u["role"],
            "mustChangePassword": bool(u["must_change_password"])}

def ticket_for(db, r):
    d = dict(r)
    d.pop("owner_id", None)
    a = db.execute("SELECT id,name,size,ext FROM attachments WHERE ticket_id=? ORDER BY id",
                   (r["id"],)).fetchall()
    d["fileNames"] = [x["name"] for x in a]
    d["attachments"] = [dict(x) for x in a]
    rev = db.execute("SELECT result,law,action,period,sent_at FROM replies WHERE ticket_id=?",
                     (r["id"],)).fetchone()
    d["review"] = ({"result": rev["result"], "law": rev["law"], "action": rev["action"],
                    "period": rev["period"], "sentAt": rev["sent_at"]} if rev else None)
    return d

def audit(db, ticket_id, who, action):
    db.execute("INSERT INTO audit(ticket_id,actor_id,action,occurred) VALUES(?,?,?,?)",
               (ticket_id, who["id"], action, now()))

def field(obj, key, required=False, maxlen=3000):
    v = obj.get(key, "")
    if not isinstance(v, str) or len(v) > maxlen or (required and not v.strip()):
        raise ValueError(key + " 항목을 확인해 주세요.")
    return v.strip()

def file_kind(name, raw):
    ext = Path(name).suffix.lower()
    if ext not in EXTS:
        raise ValueError("지원되지 않는 첨부파일 확장자입니다.")
    if ext == ".pdf" and not raw.startswith(b"%PDF-"):
        raise ValueError("PDF 파일 형식이 올바르지 않습니다.")
    if ext in (".png",) and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG 파일 형식이 올바르지 않습니다.")
    if ext in (".jpg", ".jpeg") and not raw.startswith(b"\xff\xd8\xff"):
        raise ValueError("JPG 파일 형식이 올바르지 않습니다.")
    if ext == ".gif" and not raw.startswith((b"GIF87a", b"GIF89a")):
        raise ValueError("GIF 파일 형식이 올바르지 않습니다.")
    if ext == ".webp" and not (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"):
        raise ValueError("WEBP 파일 형식이 올바르지 않습니다.")
    return ext

class Handler(BaseHTTPRequestHandler):
    server_version = "PermitStore/0.1"
    def end_headers(self):
        origin = self.headers.get("Origin", "")
        if origin == ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def origin_allowed(self):
        """Accept our own private-LAN page origin, or configured trusted origin."""
        origin = self.headers.get("Origin")
        if not origin or origin == ALLOWED_ORIGIN:
            return True
        host = self.headers.get("Host", "")
        if origin != "http://" + host:
            return False
        try:
            name = urlsplit(origin).hostname
            return name == "localhost" or ipaddress.ip_address(name).is_private
        except (ValueError, TypeError):
            return False

    def do_OPTIONS(self):
        if not self.origin_allowed():
            return self.json_response(403, {"error": "Origin not allowed"})
        self.send_response(204); self.end_headers()

    def json_response(self, status, data):
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def data(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > MAX_JSON:
            raise ValueError("전송 크기가 허용 범위를 벗어났습니다.")
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("JSON 형식만 전송할 수 있습니다.")
        o = json.loads(self.rfile.read(size))
        if not isinstance(o, dict):
            raise ValueError("JSON 객체가 필요합니다.")
        return o

    def user(self, db):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or len(auth) > 200:
            return None
        token = auth[7:]
        digest = hashlib.sha256(token.encode()).hexdigest()
        return db.execute("""SELECT u.id,u.email,u.role,u.must_change_password FROM users u
          JOIN sessions s ON s.user_id=u.id
          WHERE s.token_hash=? AND s.expires>?""", (digest, int(time.time()))).fetchone()

    def permitted_ticket(self, db, who, ticket_id):
        row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if row and (who["role"] in ("admin", "reviewer") or row["owner_id"] == who["id"]):
            return row
        return None

    def serve_file(self, db, who, ticket_id, fid):
        if not self.permitted_ticket(db, who, ticket_id):
            return self.json_response(404, {"error": "검토 요청을 찾을 수 없습니다."})
        item = db.execute("SELECT * FROM attachments WHERE id=? AND ticket_id=?",
                          (fid, ticket_id)).fetchone()
        if not item:
            return self.json_response(404, {"error": "첨부파일을 찾을 수 없습니다."})
        path = FILES / item["saved_name"]
        if not path.is_file():
            return self.json_response(404, {"error": "저장된 첨부파일이 없습니다."})
        mime = MEDIA.get(item["ext"], "application/octet-stream")
        preview = item["ext"] in MEDIA
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", ("inline" if preview else "attachment") + "; filename=attachment")
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.end_headers()
        with path.open("rb") as file:
            while data := file.read(65536):
                self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            return self.json_response(200, {"status": "ok", "storage": "server"})
        with connection() as db:
            who = self.user(db)
            if not who:
                return self.json_response(401, {"error": "로그인이 필요합니다."})
            if path == "/api/me":
                return self.json_response(200, {"user": public_user(who)})
            if who["must_change_password"]:
                return self.json_response(403, {"error": "임시 비밀번호를 변경한 후 이용할 수 있습니다."})
            if path == "/api/users":
                if who["role"] != "admin":
                    return self.json_response(403, {"error": "관리자 권한이 필요합니다."})
                rows = db.execute("""SELECT id,email,role,created,must_change_password
                                     FROM users ORDER BY email""").fetchall()
                return self.json_response(200, {"users": [
                    {"id": row["id"], "email": row["email"], "role": row["role"],
                     "created": row["created"],
                     "mustChangePassword": bool(row["must_change_password"])}
                    for row in rows]})
            if path == "/api/tickets":
                if who["role"] in ("reviewer", "admin"):
                    rows = db.execute("SELECT * FROM tickets ORDER BY created DESC").fetchall()
                else:
                    rows = db.execute("SELECT * FROM tickets WHERE owner_id=? ORDER BY created DESC",
                                      (who["id"],)).fetchall()
                return self.json_response(200, {"tickets": [ticket_for(db, x) for x in rows]})
            if path == "/api/audit":
                if who["role"] not in ("reviewer", "admin"):
                    return self.json_response(403, {"error": "인허가팀 권한이 필요합니다."})
                rows = db.execute("""SELECT a.ticket_id,a.action,a.occurred,u.email AS actor
                                      FROM audit a JOIN users u ON u.id=a.actor_id
                                      ORDER BY a.id DESC LIMIT 1000""").fetchall()
                return self.json_response(200, {"changes": [dict(x) for x in rows]})
            m = re.fullmatch(r"/api/tickets/(\d{4}-\d+)/attachments/(\d+)", path)
            if m:
                return self.serve_file(db, who, m[1], int(m[2]))
            m = re.fullmatch(r"/api/tickets/(\d{4}-\d+)", path)
            if m:
                row = self.permitted_ticket(db, who, m[1])
                return self.json_response(200, {"ticket": ticket_for(db, row)}) if row else self.json_response(404, {"error": "조회할 수 없습니다."})
        self.json_response(404, {"error": "API 경로를 찾을 수 없습니다."})

    def do_POST(self):
        path = urlsplit(self.path).path
        if not self.origin_allowed():
            return self.json_response(403, {"error": "Origin not allowed"})
        try:
            body = self.data()
            with connection() as db:
                if path == "/api/login":
                    return self.login(db, body)
                who = self.user(db)
                if not who:
                    return self.json_response(401, {"error": "로그인이 필요합니다."})
                if path == "/api/change-temporary-password":
                    return self.change_temporary_password(db, who, body)
                if who["must_change_password"] and path != "/api/logout":
                    return self.json_response(403, {"error": "임시 비밀번호 변경이 필요합니다."})
                if path == "/api/logout":
                    token = self.headers.get("Authorization", "")[7:]
                    db.execute("DELETE FROM sessions WHERE token_hash=?",
                               (hashlib.sha256(token.encode()).hexdigest(),))
                    db.commit()
                    return self.json_response(200, {"ok": True})
                if path == "/api/users":
                    if who["role"] != "admin":
                        return self.json_response(403, {"error": "관리자 권한이 필요합니다."})
                    email = field(body, "email", True, 120).lower()
                    password = field(body, "password", True, 200)
                    role = field(body, "role", True, 20)
                    if not valid_email(email) or len(password) < 6 or role not in ("requester", "reviewer", "admin"):
                        raise ValueError("회사 이메일, 6자 이상 비밀번호, 올바른 권한을 입력하세요.")
                    try:
                        db.execute("INSERT INTO users(email,passhash,role,created) VALUES(?,?,?,?)",
                                   (email, passhash(password), role, now()))
                    except sqlite3.IntegrityError:
                        raise ValueError("이미 등록된 계정입니다.")
                    db.commit()
                    return self.json_response(201, {"ok": True, "email": email})
                m = re.fullmatch(r"/api/users/(\d+)/reset-password", path)
                if m:
                    return self.reset_password(db, who, int(m[1]), body)
                m = re.fullmatch(r"/api/users/(\d+)/role", path)
                if m:
                    return self.update_staff_role(db, who, int(m[1]), body)
                if path == "/api/tickets":
                    return self.create_ticket(db, who, body)
                m = re.fullmatch(r"/api/tickets/(\d{4}-\d+)/attachments", path)
                if m:
                    return self.upload(db, who, m[1], body)
                m = re.fullmatch(r"/api/tickets/(\d{4}-\d+)/review", path)
                if m:
                    return self.review(db, who, m[1], body)
        except (ValueError, json.JSONDecodeError) as exc:
            return self.json_response(400, {"error": str(exc)})
        except sqlite3.IntegrityError:
            return self.json_response(409, {"error": "충돌이 발생했습니다."})
        except Exception:
            logging.exception("Server error")
            return self.json_response(500, {"error": "서버 처리 중 오류가 발생했습니다."})
        self.json_response(404, {"error": "API 경로를 찾을 수 없습니다."})

    def update_staff_role(self, db, who, target_id, body):
        """Only an existing administrator may grant or revoke reviewer privileges."""
        if who["role"] != "admin":
            return self.json_response(403, {"error": "관리자만 계정 권한을 변경할 수 있습니다."})
        desired = field(body, "role", True, 30)
        if desired not in ("requester", "reviewer"):
            return self.json_response(400, {"error": "일반 직원 또는 인허가팀 권한만 지정할 수 있습니다."})
        admin_password = field(body, "adminPassword", True, 200)
        admin_record = db.execute("SELECT passhash FROM users WHERE id=?",
                                  (who["id"],)).fetchone()
        if not admin_record or not verify(admin_password, admin_record["passhash"]):
            return self.json_response(403, {"error": "관리자 비밀번호가 일치하지 않습니다."})
        target = db.execute("SELECT id,email,role FROM users WHERE id=?",
                            (target_id,)).fetchone()
        if not target:
            return self.json_response(404, {"error": "직원 계정을 찾을 수 없습니다."})
        if target["role"] == "admin":
            return self.json_response(403, {"error": "관리자 계정의 권한은 변경할 수 없습니다."})
        if target["role"] == desired:
            return self.json_response(200, {"ok": True, "unchanged": True,
                                            "email": target["email"], "role": desired})
        db.execute("UPDATE users SET role=? WHERE id=?", (desired, target_id))
        # Existing sessions are removed so the employee signs in again
        # and receives the correct reviewer/requester menus.
        db.execute("DELETE FROM sessions WHERE user_id=?", (target_id,))
        db.execute("""INSERT INTO security_events(actor_id,target_id,action,occurred)
                      VALUES(?,?,?,?)""",
                   (who["id"], target_id,
                    "인허가팀 권한 부여" if desired == "reviewer" else "인허가팀 권한 해제",
                    now()))
        db.commit()
        return self.json_response(200, {"ok": True, "email": target["email"],
                                        "role": desired, "requiresRelogin": True})

    def reset_password(self, db, who, target_id, body):
        if who["role"] != "admin":
            return self.json_response(403, {"error": "관리자만 비밀번호를 초기화할 수 있습니다."})
        # A fresh confirmation of the current administrator password is mandatory.
        admin_password = field(body, "adminPassword", True, 200)
        admin_record = db.execute("SELECT passhash FROM users WHERE id=?",
                                  (who["id"],)).fetchone()
        if not admin_record or not verify(admin_password, admin_record["passhash"]):
            return self.json_response(403, {"error": "관리자 비밀번호가 일치하지 않습니다."})
        target = db.execute("SELECT id,email,role FROM users WHERE id=?", (target_id,)).fetchone()
        if not target:
            return self.json_response(404, {"error": "직원 계정을 찾을 수 없습니다."})
        if target["role"] == "admin":
            return self.json_response(403, {"error": "관리자 계정은 이 화면에서 초기화할 수 없습니다."})
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
        temporary = "".join(secrets.choice(alphabet) for _ in range(12))
        db.execute("UPDATE users SET passhash=?, must_change_password=1 WHERE id=?",
                   (passhash(temporary), target_id))
        db.execute("DELETE FROM sessions WHERE user_id=?", (target_id,))
        db.execute("""INSERT INTO security_events(actor_id,target_id,action,occurred)
                      VALUES(?,?,?,?)""", (who["id"],target_id,"비밀번호 초기화",now()))
        db.commit()
        # One-time secret: sent only in this response, never persisted as plaintext.
        return self.json_response(200, {"email": target["email"],
                                        "temporaryPassword": temporary,
                                        "mustChangePassword": True})

    def change_temporary_password(self, db, who, body):
        if not who["must_change_password"]:
            return self.json_response(403, {"error": "임시 비밀번호 변경 대상이 아닙니다."})
        new_password = field(body, "newPassword", True, 200)
        if len(new_password) < 6:
            raise ValueError("새 비밀번호는 6자 이상이어야 합니다.")
        stored = db.execute("SELECT passhash FROM users WHERE id=?",
                            (who["id"],)).fetchone()
        if verify(new_password, stored["passhash"]):
            raise ValueError("임시 비밀번호와 다른 비밀번호를 설정해 주세요.")
        db.execute("UPDATE users SET passhash=?,must_change_password=0 WHERE id=?",
                   (passhash(new_password), who["id"]))
        current_token = self.headers.get("Authorization", "")[7:]
        current_hash = hashlib.sha256(current_token.encode()).hexdigest()
        db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash!=?",
                   (who["id"], current_hash))
        db.execute("""INSERT INTO security_events(actor_id,target_id,action,occurred)
                      VALUES(?,?,?,?)""",(who["id"],who["id"],"임시 비밀번호 변경",now()))
        db.commit()
        updated = db.execute("""SELECT id,email,role,must_change_password FROM users
                                WHERE id=?""", (who["id"],)).fetchone()
        return self.json_response(200, {"user": public_user(updated)})

    def login(self, db, body):
        ip = self.client_address[0]
        attempts = [t for t in FAILED.get(ip, []) if time.monotonic() - t < 600]
        if len(attempts) >= 6:
            FAILED[ip] = attempts
            return self.json_response(429, {"error": "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."})
        email = field(body, "email", True, 120).lower()
        password = field(body, "password", True, 200)
        record = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        just_created = False
        if record is None and os.environ.get("PERMIT_ENABLE_TEST_AUTO_ACCOUNT") == "1":
            # This PC-pilot convenience is NOT mailbox/identity verification.
            # The first person entering an unused address establishes its password.
            if not valid_email(email) or len(password) < 6:
                return self.json_response(400, {"error": "첫 로그인에서는 회사 이메일 ID와 6자 이상 비밀번호를 입력해 주세요."})
            creations = [t for t in TEST_AUTO_CREATED.get(ip, []) if time.monotonic() - t < 600]
            if len(creations) >= 6:
                TEST_AUTO_CREATED[ip] = creations
                return self.json_response(429, {"error": "새 계정 생성 시도가 너무 많습니다. 잠시 후 다시 시도하세요."})
            creations.append(time.monotonic())
            TEST_AUTO_CREATED[ip] = creations
            try:
                db.execute("INSERT INTO users(email,passhash,role,created) VALUES(?,?,?,?)",
                           (email, passhash(password), "requester", now()))
                db.commit()
                just_created = True
            except sqlite3.IntegrityError:
                db.rollback()
            record = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not record or not verify(password, record["passhash"]):
            attempts.append(time.monotonic()); FAILED[ip] = attempts
            # In the test-only PC mode, explicitly tell employees when the
            # password for their existing account does not match.
            if record and os.environ.get("PERMIT_ENABLE_TEST_AUTO_ACCOUNT") == "1":
                return self.json_response(401, {"error": "비밀번호가 일치하지 않습니다. 처음 로그인할 때 설정한 비밀번호를 입력해 주세요."})
            return self.json_response(401, {"error": "이메일 또는 비밀번호가 올바르지 않습니다."})
        FAILED.pop(ip, None)
        token = secrets.token_urlsafe(36)
        db.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))
        db.execute("INSERT INTO sessions(token_hash,user_id,expires) VALUES(?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), record["id"], int(time.time())+43200))
        db.commit()
        return self.json_response(200, {"token": token, "user": public_user(record), "created": just_created})

    def create_ticket(self, db, who, b):
        vals = {k: field(b,k,k in ("department","requester","date","title","question","current","purpose"),
                          120 if k in ("department","requester","date","title","site","category") else 3000)
                for k in ("department","requester","date","title","site","category","question","current","purpose")}
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", vals["date"]):
            raise ValueError("요청일자가 올바르지 않습니다.")
        # BEGIN IMMEDIATE prevents two employees from receiving the same sequential ID.
        db.execute("BEGIN IMMEDIATE")
        year = str(dt.datetime.now().year)
        last = db.execute("SELECT MAX(CAST(SUBSTR(id,6) AS INTEGER)) FROM tickets WHERE id LIKE ?",
                          (year+"-%",)).fetchone()[0] or 0
        ticket_id = year + "-" + str(last+1).zfill(3)
        db.execute("""INSERT INTO tickets(id,owner_id,department,requester,email,date,title,site,category,question,current,purpose,created)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (ticket_id,who["id"],vals["department"],vals["requester"],who["email"],
                    vals["date"],vals["title"],vals["site"],vals["category"],
                    vals["question"],vals["current"],vals["purpose"],now()))
        audit(db, ticket_id, who, "요청접수")
        db.commit()
        row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return self.json_response(201, {"ticket": ticket_for(db, row)})

    def upload(self, db, who, ticket_id, b):
        row = self.permitted_ticket(db, who, ticket_id)
        if not row:
            return self.json_response(404, {"error": "요청을 찾을 수 없습니다."})
        if who["role"] == "requester" and row["status"] == "회신완료":
            return self.json_response(403, {"error": "회신 완료 후 첨부는 허용되지 않습니다."})
        name = field(b,"name",True,180)
        name = Path(name.replace("\\","/")).name
        encoded = field(b,"data",True,MAX_JSON)
        try: raw = base64.b64decode(encoded, validate=True)
        except Exception: raise ValueError("파일 인코딩이 올바르지 않습니다.")
        if not raw or len(raw)>MAX_FILE:
            raise ValueError("첨부파일은 8MB 이하만 허용됩니다.")
        ext = file_kind(name, raw)
        saved_name = secrets.token_hex(18)
        path = FILES / saved_name
        with path.open("xb") as f:
            f.write(raw)
        try:
            db.execute("""INSERT INTO attachments(ticket_id,name,saved_name,size,ext,created)
                          VALUES(?,?,?,?,?,?)""",
                       (ticket_id,name,saved_name,len(raw),ext,now()))
            audit(db, ticket_id, who, "첨부등록")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        db.commit()
        row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return self.json_response(201, {"ticket": ticket_for(db,row)})

    def review(self, db, who, ticket_id, b):
        if who["role"] not in ("admin","reviewer"):
            return self.json_response(403, {"error": "검토자 권한이 필요합니다."})
        row = self.permitted_ticket(db, who, ticket_id)
        if not row:
            return self.json_response(404, {"error": "요청을 찾을 수 없습니다."})
        if row["status"] == "회신완료":
            return self.json_response(409, {"error": "완료된 회신은 덮어쓸 수 없습니다."})
        completed = b.get("complete") is True
        fields = {k: field(b,k,k=="assigned",3000) for k in
                  ("assigned","result","law","action","period")}
        if completed and not fields["result"]:
            raise ValueError("회신을 완료하려면 검토 결과가 필요합니다.")
        db.execute("""INSERT INTO replies(ticket_id,result,law,action,period,sent_at)
                      VALUES(?,?,?,?,?,?)
                      ON CONFLICT(ticket_id) DO UPDATE SET result=excluded.result,
                      law=excluded.law,action=excluded.action,period=excluded.period,
                      sent_at=excluded.sent_at""",
                   (ticket_id,fields["result"],fields["law"],fields["action"],
                    fields["period"],now() if completed else None))
        db.execute("UPDATE tickets SET assigned=?,status=? WHERE id=?",
                   (fields["assigned"],"회신완료" if completed else "검토중",ticket_id))
        audit(db,ticket_id,who,"회신확정" if completed else "검토수정")
        db.commit()
        row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return self.json_response(200, {"ticket": ticket_for(db,row)})

def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    boot()
    logging.warning("This service needs HTTPS and access control before any real business data.")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

if __name__ == "__main__":
    run()
