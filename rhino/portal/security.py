"""Request hardening, in one place.

* Every change is POST/DELETE with JSON or multipart - never a GET link (a stray click or an
  <img src> on another site cannot delete a tool).
* A per-process token must come back in the X-Rhino-Token header, and the Origin (if the browser
  sends one) must be this host. Together these stop other web pages from driving the portal.
* The Content-Security-Policy forbids inline script/style and any third-party host, so a stray
  '<' in a tool name or note can never run as code (and the portal works with no internet).
"""
import hmac
import secrets
from urllib.parse import urlparse

from flask import jsonify, request

from ..errors import Fail

TOKEN = secrets.token_urlsafe(24)
HEADER = "X-Rhino-Token"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")


def check_write():
    """Call at the top of every mutating route. Raises Fail with a clear message."""
    if not hmac.compare_digest(request.headers.get(HEADER, ""), TOKEN):
        raise Fail("This page is out of date (the portal was restarted). Reload the page and try again.")
    origin = request.headers.get("Origin")
    if origin and urlparse(origin).netloc != request.host:
        raise Fail("Cross-site request refused.")


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise Fail("Expected a JSON object.")
    return data


def add_headers(resp):
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def error(message, status=400):
    return jsonify({"ok": False, "error": message}), status
