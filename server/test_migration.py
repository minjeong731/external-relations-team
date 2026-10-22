"""Verify schema migration keeps existing accounts and their password hashes."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import app

class OldDbMigration(unittest.TestCase):
 def test_old_user_password_is_not_reset(self):
  original=(app.BASE,app.DB_PATH,app.FILES)
  with tempfile.TemporaryDirectory() as directory:
   try:
    app.BASE=Path(directory)
    app.DB_PATH=app.BASE/"permit.sqlite3"
    app.FILES=app.BASE/"attachments"
    with sqlite3.connect(app.DB_PATH) as db:
     db.execute("""CREATE TABLE users (
      id INTEGER PRIMARY KEY,email TEXT NOT NULL UNIQUE,
      passhash TEXT NOT NULL,role TEXT NOT NULL,created TEXT NOT NULL
     )""")
     db.execute("INSERT INTO users(email,passhash,role,created) VALUES(?,?,?,?)",
                ("already.account@hdc-resort.com","existing-secret-hash","requester","2026-10-01"))
     db.commit()
    app.boot()
    with app.connection() as db:
     old=db.execute("SELECT email,passhash,must_change_password FROM users").fetchone()
     self.assertEqual(old["email"],"already.account@hdc-resort.com")
     self.assertEqual(old["passhash"],"existing-secret-hash")
     self.assertEqual(old["must_change_password"],0)
     self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0],1)
    app.boot()
    with app.connection() as db:
     self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0],1)
   finally:
    app.BASE,app.DB_PATH,app.FILES=original
