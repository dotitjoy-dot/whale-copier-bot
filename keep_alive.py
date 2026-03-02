"""
Simple HTTP server to keep the bot alive on free hosting services (like Render Web Services)
by binding to the assigned PORT and returning a valid HTTP 200 response.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import time

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

    def log_message(self, format, *args):
        # Suppress logging of ping requests to avoid console spam
        pass

def run_server():
    # Render and Heroku pass port via environment variable; 8080 is a safe fallback
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), KeepAliveHandler)
    print(f"Keep-alive server started on port {port}")
    server.serve_forever()

def keep_alive():
    """Starts the dummy web server in a background thread."""
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
