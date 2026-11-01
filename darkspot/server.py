"""Local dev server: same API functions as the Vercel functions, plus static files from public/. Run: python -m darkspot"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .api import ROUTES, send, serve

UI = Path(__file__).resolve().parent.parent / "public"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/favicon.svg": ("favicon.svg", "image/svg+xml")}

class H(BaseHTTPRequestHandler):
    server_version = "DarkSpot"
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in STATIC:
            f, ct = STATIC[path]; return send(self, 200, (UI / f).read_bytes(), ct)
        send(self, 404, {"error": "Not found."})
    def do_POST(self):
        fn = ROUTES.get(self.path.split("?")[0])
        if not fn: return send(self, 404, {"error": "Not found."})
        serve(self, fn)
    def log_message(self, *a): pass

def main():
    host, port = os.environ.get("DARKSPOT_HOST", "127.0.0.1"), int(os.environ.get("DARKSPOT_PORT", "8000"))
    print(f"DarkSpot running at http://{host}:{port}"); ThreadingHTTPServer((host, port), H).serve_forever()
