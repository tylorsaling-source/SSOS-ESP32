"""One-submission, expiring credential form behind Tailscale Serve HTTPS.

The backend binds only loopback. Tailscale strips/replaces identity headers.
Never expose this HTTP backend directly to a LAN or tailnet interface.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import urlsplit

PAGE = b'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SSOS - TypeSafe key</title><link rel="stylesheet" href="/style.css">
<script src="/app.js" defer></script></head><body><main>
<p class="eyebrow">SSOS / JEV EXPERIMENT</p><h1>Connect TypeSafe</h1>
<p>Enter your API key to continue the Jev experiment on Gamer.</p>
<form id="capture" autocomplete="off"><label for="key">TypeSafe API key</label>
<input id="key" name="key" type="password" autocomplete="off" autocapitalize="none"
spellcheck="false" required maxlength="4096" placeholder="Paste your API key">
<button type="submit">Save key securely</button></form>
<p id="status" role="status" aria-live="polite"></p>
<p class="note">Private Tailscale connection. Encrypted storage on Gamer.
This form closes after the key is saved. Your key is never shown in chat.</p>
</main></body></html>'''

STYLE = b'''*{box-sizing:border-box}body{margin:0;background:#101820;color:#edf4f5;
font:17px/1.55 system-ui,sans-serif;padding:8vh 20px}main{max-width:480px;margin:auto}
h1{font-size:36px;line-height:1.1;letter-spacing:-1px}p{color:#b9cbd1}
.eyebrow{font-size:12px;letter-spacing:2px;color:#79dec7}label{display:block;margin-top:32px}
input,button{width:100%;font:inherit;border-radius:10px;padding:14px;margin-top:12px}
input{background:#1d2b35;border:1px solid #677f8a;color:white}
button{border:0;background:#79dec7;color:#102b29;font-weight:650;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}.note{font-size:13px;margin-top:32px}
#status{color:#79dec7;min-height:26px}'''

SCRIPT = b'''"use strict";
let token = location.hash.slice(1);
history.replaceState(null, "", location.pathname);
const form = document.getElementById("capture");
const status = document.getElementById("status");
const input = document.getElementById("key");
const button = form.querySelector("button");
if (!token) { button.disabled = true; status.textContent = "Open the complete capture link from Codex."; }
form.addEventListener("submit", async event => {
  event.preventDefault(); button.disabled = true; status.textContent = "Saving securely...";
  let key = input.value.trim(); input.value = "";
  try {
    const result = await fetch("/capture", {method:"POST", cache:"no-store",
      credentials:"omit", headers:{"Content-Type":"application/json", "X-Capture-Token":token},
      body:JSON.stringify({key})});
    key = "";
    if (!result.ok) throw new Error("rejected");
    token = ""; form.hidden = true;
    status.textContent = "Key saved on Gamer. Return to Codex and say 'saved' to continue.";
  } catch (_) {
    key = ""; button.disabled = false;
    status.textContent = "Could not save. The link may have expired or already been used. Return to Codex for help.";
  }
});'''


def store_key(key: str, key_file: Path) -> None:
    if key_file.exists():
        raise RuntimeError("A credential already exists; capture is closed.")
    helper = Path(__file__).with_name("set_typesafe_key_windows.ps1")
    # Windows PowerShell must build its own module path instead of inheriting
    # PowerShell 7 modules through the Python parent process.
    environment = {name: value for name, value in os.environ.items()
                   if name.upper() != "PSMODULEPATH"}
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(helper), "-FromStdin", "-KeyFile", str(key_file)],
        input=key, text=True, capture_output=True, timeout=30,
        env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode or not key_file.is_file():
        raise RuntimeError("Encrypted credential storage failed.")


class CaptureServer(HTTPServer):
    def __init__(self, address, origin, allowed_user, token, deadline, writer):
        super().__init__(address, CaptureHandler)
        self.origin = origin
        self.host = urlsplit(origin).netloc
        self.allowed_user = allowed_user
        self.token = token
        self.deadline = deadline
        self.writer = writer
        self.saved = False
        self.timeout = 1


class CaptureHandler(BaseHTTPRequestHandler):
    server: CaptureServer

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_args):
        pass  # No request paths, headers, form data, or credentials in logs.

    def reply(self, status, body=b"", content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'none'; base-uri 'none'")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def permitted(self):
        if self.headers.get("Host") != self.server.host:
            self.reply(403)
            return False
        if self.headers.get("Tailscale-User-Login") != self.server.allowed_user:
            self.reply(403, b"Connect using your own Tailscale account.")
            return False
        if self.server.saved or time.monotonic() >= self.server.deadline:
            self.reply(410, b"This capture link has closed.")
            return False
        return True

    def do_GET(self):
        if not self.permitted():
            return
        content = {"/": (PAGE, "text/html; charset=utf-8"),
                   "/app.js": (SCRIPT, "text/javascript; charset=utf-8"),
                   "/style.css": (STYLE, "text/css; charset=utf-8")}.get(self.path)
        if content is None:
            self.reply(404)
        else:
            self.reply(200, *content)

    def do_POST(self):
        if not self.permitted():
            return
        if self.path != "/capture":
            self.reply(404)
            return
        if (self.headers.get("Origin") != self.server.origin or
            not secrets.compare_digest(self.headers.get("X-Capture-Token", "").encode(), self.server.token.encode())):
            self.reply(403)
            return
        if self.headers.get("Content-Type") != "application/json" or self.headers.get("Transfer-Encoding"):
            self.reply(415)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 8192:
                self.reply(413)
                return
            data = json.loads(self.rfile.read(length))
            key = data.get("key") if isinstance(data, dict) else None
            if (not isinstance(key, str) or not 8 <= len(key.strip()) <= 4096 or
                any(ord(char) < 33 or ord(char) > 126 for char in key.strip())):
                self.reply(400, b"Enter a valid API key.")
                return
            self.server.writer(key.strip())
        except (ValueError, UnicodeError):
            self.reply(400)
            return
        except Exception:
            self.reply(500, b"Unable to save the credential.")
            return
        self.server.saved = True
        self.server.token = ""
        self.reply(200, b'{"saved":true}', "application/json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18761)
    parser.add_argument("--https-port", type=int, default=8447)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--allowed-user", required=True)
    parser.add_argument("--minutes", type=int, default=30)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, default=Path(os.environ.get("LOCALAPPDATA", ".")) / "SSOS-ESP32/typesafe-api-key.dpapi")
    args = parser.parse_args()
    if args.key_file.exists():
        raise SystemExit("Credential already exists; refusing to replace it.")
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=args.minutes)
    state = {"status": "waiting", "url": args.origin + "/#" + token,
             "expires_utc": expires.isoformat(), "pid": os.getpid()}
    server = CaptureServer(("127.0.0.1", args.port), args.origin, args.allowed_user,
                           token, time.monotonic() + args.minutes * 60,
                           lambda key: store_key(key, args.key_file))
    args.status_file.parent.mkdir(parents=True, exist_ok=True)
    args.status_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    try:
        while not server.saved and time.monotonic() < server.deadline:
            server.handle_request()
    finally:
        server.server_close()
        state.pop("url", None)
        state["status"] = "saved" if server.saved else "expired"
        args.status_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        # This dedicated port was assigned only to the capture service.
        subprocess.run(["tailscale", "serve", f"--https={args.https_port}", "off"],
                       capture_output=True, timeout=20,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


if __name__ == "__main__":
    main()
