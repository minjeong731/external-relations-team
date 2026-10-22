"""Static & CORS checks for the HTTPS bridge built for the same GitHub Pages URL."""
import ast
from pathlib import Path
import urllib.request
import unittest

ROOT = Path(__file__).resolve().parent.parent

class HttpsBridgeTests(unittest.TestCase):
    def test_launcher_is_valid_python_and_local_only(self):
        code=(ROOT/"server"/"start_https.py").read_text(encoding="utf-8")
        ast.parse(code)
        self.assertIn('os.environ["PERMIT_HOST"] = "127.0.0.1"', code)
        self.assertIn('"funnel", "--bg", str(app.PORT)', code)
        self.assertIn("server.shutdown()", code)
        self.assertIn("prepare_first_admin()", code)

    def test_windows_launcher_syncs_code_and_leaves_db_private(self):
        code=(ROOT/"PC_HTTPS_웹공유_시작.bat").read_text(encoding="utf-8")
        self.assertIn("start_https.py",code)
        self.assertIn("docs/runtime-config.js",code)
        self.assertIn("docs/index.html",code)
        self.assertNotIn("permit.sqlite3",code)
        self.assertNotIn("attachments/",code)

    def test_frontend_can_select_stable_https_backend(self):
        config=(ROOT/"docs"/"runtime-config.js").read_text(encoding="utf-8")
        client=(ROOT/"docs"/"live-api.js").read_text(encoding="utf-8")
        self.assertIn('window.PERMIT_API_BASE = ""', config)
        self.assertIn("window.location.search",config)
        self.assertIn("ts\\\\.net",config)
        self.assertIn("parsed.protocol === \\"https:\\"",config)
        self.assertIn("window.PERMIT_API_BASE",client)
        self.assertIn("fetch(path(endpoint)",client)

if __name__=="__main__":
    unittest.main()
