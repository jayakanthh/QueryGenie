"""
Development only: serve desktop/ui over HTTP and expose desktop/api.Api at POST /api/<method>,
so the interface can be developed and screenshotted in an ordinary browser. The packaged app
uses pywebview's direct bridge instead (desktop/main.py).

    python desktop/devserver.py            # http://127.0.0.1:8765/  (add ?os=win to preview Windows)
"""
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import main  # noqa: F401 - sets up sys.path and the per-user data folders
from api import Api

API = Api()
UI = main.UI


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=UI, **kw)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/devmode.js"):
            body = b"window.QG_DEV = true;"
            self.send_response(200); self.send_header("Content-Type", "text/javascript"); self.end_headers()
            return self.wfile.write(body)
        return super().do_GET()

    def do_POST(self):
        if not self.path.startswith("/api/"):
            return self.send_error(404)
        name = self.path[5:]
        if name.startswith("_") or not hasattr(API, name):
            return self.send_error(404)
        args = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"[]")
        try:
            body, code = json.dumps(getattr(API, name)(*args)), 200
        except Exception as exc:  # noqa: BLE001
            body, code = json.dumps({"error": f"{type(exc).__name__}: {exc}"}), 500
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())


if __name__ == "__main__":
    port = int(os.environ.get("QG_DEV_PORT", "8765"))
    print(f"http://127.0.0.1:{port}/", file=sys.stderr)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
