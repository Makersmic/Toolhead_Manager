"""Rhino Studio's nginx site (service/rhino-studio.nginx), run in a real nginx.

    python3 dev/test_studio_site.py

Fills in the site the way install.sh does, starts nginx with it (its own temporary prefix, nothing in /etc is
touched) and fake Moonraker, Portal and camera servers behind it, then checks what reaches each one and what
comes back: Studio's files and cache headers, Moonraker with the browser's Host (Moonraker's own origin check),
the websocket upgrade, /portal with the Host the Portal's write check compares, big slicer uploads, the
cameras unbuffered, WebAssembly's type. SKIP without nginx, or when port 5000 or 8080 is taken.
"""
import http.client
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


NGINX = shutil.which("nginx") or ("/usr/sbin/nginx" if os.path.exists("/usr/sbin/nginx") else None)
if not NGINX:
    print("SKIP Studio site test: nginx is not installed")
    sys.exit(0)
for p in (5000, 8080):
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", p)) == 0:
            print(f"SKIP Studio site test: port {p} is in use on this computer")
            sys.exit(0)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


SEEN = {}


def upstream(name, port):
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _answer(self):
            n = int(self.headers.get("Content-Length") or 0)
            got = 0
            while got < n:
                chunk = self.rfile.read(min(1 << 20, n - got))
                if not chunk:
                    break
                got += len(chunk)
            SEEN[name] = {"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": got, "method": self.command}
            b = json.dumps({"from": name, "path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        do_GET = do_POST = _answer

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


ROOT = tempfile.mkdtemp(prefix="rhino-studio-site-")
WWW = os.path.join(ROOT, "rhino-studio")
os.makedirs(os.path.join(WWW, "assets"))
os.makedirs(os.path.join(WWW, "kiri", "wasm"))
open(os.path.join(WWW, "index.html"), "w").write("<!doctype html><title>Rhino Studio</title>" + "x" * 4000)
open(os.path.join(WWW, "assets", "index-abc123.js"), "w").write("console.log(1);" * 400)
open(os.path.join(WWW, "kiri", "wasm", "slicer.wasm"), "wb").write(b"\0asm\1\0\0\0")

MOON = free_port()
PORT = free_port()
servers = [upstream("moonraker", MOON), upstream("portal", 5000), upstream("webcam", 8080)]
site = open(os.path.join(REPO, "service", "rhino-studio.nginx")).read()
site = site.replace("@PORT@", str(PORT)).replace("@ROOT@", WWW).replace("@MOONRAKER@", str(MOON))
site = site.replace("/var/log/nginx/rhino-studio-error.log", os.path.join(ROOT, "error.log"))
open(os.path.join(ROOT, "rhino-studio.conf"), "w").write(site)
mime = "/etc/nginx/mime.types"
conf = f"""{"user root;" if os.geteuid() == 0 else ""}
worker_processes 1;
pid {ROOT}/nginx.pid;
error_log {ROOT}/error.log;
events {{ worker_connections 64; }}
http {{
    {"include " + mime + ";" if os.path.exists(mime) else ""}
    default_type application/octet-stream;
    client_body_temp_path {ROOT}/body;
    proxy_temp_path {ROOT}/proxy;
    fastcgi_temp_path {ROOT}/fcgi;
    uwsgi_temp_path {ROOT}/uwsgi;
    scgi_temp_path {ROOT}/scgi;
    include {ROOT}/rhino-studio.conf;
}}
"""
open(os.path.join(ROOT, "nginx.conf"), "w").write(conf)

t = subprocess.run([NGINX, "-t", "-p", ROOT, "-c", os.path.join(ROOT, "nginx.conf")], capture_output=True, text=True)
ok(t.returncode == 0, "nginx -t accepts the filled-in site" + ("" if t.returncode == 0 else f": {t.stderr[-400:]}"))
proc = subprocess.Popen([NGINX, "-p", ROOT, "-c", os.path.join(ROOT, "nginx.conf"), "-g", "daemon off;"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def req(method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, data


try:
    for _ in range(50):
        try:
            req("GET", "/")
            break
        except OSError:
            time.sleep(0.1)
    host = f"127.0.0.1:{PORT}"

    st, h, b = req("GET", "/", headers={"Accept-Encoding": "gzip"})
    ok(st == 200 and h.get("content-encoding") == "gzip", "Studio's page served, gzipped")
    st, h, b = req("GET", "/index.html")
    ok(st == 200 and "no-cache" in h.get("cache-control", ""), "index.html is never kept stale (no-cache)")
    st, h, b = req("GET", "/assets/index-abc123.js")
    ok(st == 200 and "immutable" in h.get("cache-control", "") and "javascript" in h.get("content-type", ""), "built files: kept by the browser (immutable), JavaScript type")
    st, h, b = req("GET", "/kiri/wasm/slicer.wasm")
    ok(st == 200 and h.get("content-type") == "application/wasm", "WebAssembly served as application/wasm")
    st, h, b = req("GET", "/some/screen")
    ok(st == 200 and b"Rhino Studio" in b, "any other path gets Studio's page")

    st, h, b = req("GET", "/server/info?x=1")
    s = SEEN.get("moonraker", {})
    ok(st == 200 and s.get("path") == "/server/info?x=1" and s["headers"].get("host") == host and s["headers"].get("x-real-ip") == "127.0.0.1",
       "Moonraker gets /server/... as is, with the browser's Host and X-Real-IP (as Mainsail sends them)")
    for p in ("/printer/objects/list", "/machine/system_info", "/access/info", "/api/version"):
        req("GET", p)
        ok(SEEN["moonraker"]["path"] == p, f"{p.split('/')[1]} goes to Moonraker")
    req("GET", "/websocket", headers={"Upgrade": "websocket", "Connection": "Upgrade", "Origin": f"http://{host}"})
    s = SEEN["moonraker"]
    ok(s["path"] == "/websocket" and s["headers"].get("upgrade") == "websocket" and s["headers"].get("connection", "").lower() == "upgrade"
       and s["headers"].get("host") == host, "the websocket upgrade reaches Moonraker with Upgrade, Connection and the browser's Host")
    st, h, b = req("POST", "/server/files/upload", body=b"x" * (30 * 1024 * 1024), headers={"Content-Type": "application/octet-stream"})
    ok(st == 200 and SEEN["moonraker"]["body"] == 30 * 1024 * 1024, "a 30 MB G-code upload reaches Moonraker (no size limit of nginx's own)")

    st, h, b = req("GET", "/portal/api/maint/summary")
    s = SEEN.get("portal", {})
    ok(st == 200 and s.get("path") == "/api/maint/summary", "/portal/... reaches the Portal without the /portal prefix")
    req("POST", "/portal/api/tools/x", body=b"{}", headers={"Origin": f"http://{host}", "Content-Type": "application/json"})
    s = SEEN["portal"]
    from urllib.parse import urlparse
    ok(s["headers"].get("host") == host and urlparse(s["headers"].get("origin", "")).netloc == s["headers"].get("host"),
       "the Portal sees Origin and Host agree, so its cross-site check lets Studio's changes through")
    st, h, b = req("POST", "/portal/api/slicer/slice", body=b"x" * (60 * 1024 * 1024), headers={"Content-Type": "application/octet-stream"})
    ok(st == 200 and SEEN["portal"]["body"] == 60 * 1024 * 1024, "a 60 MB part reaches the slicer")
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.putrequest("POST", "/portal/api/slicer/slice")
    c.putheader("Content-Length", str(300 * 1024 * 1024))
    c.endheaders()
    r = c.getresponse()
    ok(r.status == 413, f"...and over 210 MB nginx refuses it (HTTP {r.status})")
    c.close()

    st, h, b = req("GET", "/webcam/?action=snapshot")
    ok(st == 200 and SEEN.get("webcam", {}).get("path") == "/?action=snapshot", "/webcam/ goes to crowsnest's first camera (port 8080), prefix removed")
finally:
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
    for s in servers:
        s.shutdown()
    shutil.rmtree(ROOT, ignore_errors=True)

print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
