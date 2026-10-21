#!/usr/bin/env python3
"""Serve the existing interface and SQLite API from one office PC on the LAN.

This is an HTTP-only prototype for a trusted network and fictitious test records.
Actual business files and passwords require company-approved HTTPS and controls.
"""
from pathlib import Path
from urllib.parse import urlsplit

import app

PUBLIC = Path(__file__).resolve().parent.parent / "docs"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/live-api.js": ("live-api.js", "text/javascript; charset=utf-8"),
}

class LANHandler(app.Handler):
    def serve_bytes(self, data, media_type):
        self.send_response(200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Security-Policy",
                         "frame-ancestors 'none'; object-src 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/runtime-config.js":
            return self.serve_bytes(
                b"window.PERMIT_API_BASE = window.location.origin;\n",
                "text/javascript; charset=utf-8",
            )
        if path in STATIC:
            filename, media = STATIC[path]
            return self.serve_bytes((PUBLIC / filename).read_bytes(), media)
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        return super().do_GET()

if __name__ == "__main__":
    raise SystemExit("Use start_lan.py to start the database and local website.")
