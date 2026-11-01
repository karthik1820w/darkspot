import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from http.server import BaseHTTPRequestHandler
from darkspot.api import serve, send, do_checklist

class handler(BaseHTTPRequestHandler):
    def do_POST(self): serve(self, do_checklist)
    def do_GET(self): send(self, 405, {"error": "Use POST."})
    def log_message(self, *a): pass
