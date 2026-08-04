from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import time
from collections.abc import Awaitable, Callable

import bcrypt
from starlette.requests import Request
from starlette.responses import Response

COOKIE_NAME = "sonic_gate"
COOKIE_VERSION = 1
_IDLE_DEFAULT = 3600
_IDLE_REMEMBER = 86400
_LOGIN_FAIL_MAX = 10
_LOGIN_BAN_SEC = 600

_login_lock = asyncio.Lock()
_login_by_ip: dict[str, dict[str, float | int]] = {}


def gate_password_bcrypt_hash() -> str:
    return os.environ.get("SONIC_GATE_PASSWORD_HASH", "").strip()


def gate_enabled() -> bool:
    return bool(gate_password_bcrypt_hash())


def allow_insecure_http() -> bool:
    v = os.environ.get("SONIC_GATE_ALLOW_HTTP", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def allowed_hosts_set() -> frozenset[str]:
    raw = os.environ.get("SONIC_GATE_ALLOWED_HOSTS", "")
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def _hostname_is_ip(hostname: str) -> bool:
    h = (hostname or "").strip()
    if not h:
        return False
    if h.startswith("[") and "]" in h:
        h = h[1 : h.index("]")]
    h = h.split("%", 1)[0]
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def gate_request_ok(request: Request) -> bool:
    if allow_insecure_http():
        return True
    if not cookie_secure(request):
        return False
    hn_raw = request.url.hostname or ""
    if not hn_raw:
        return False
    if _hostname_is_ip(hn_raw):
        return False
    hn = hn_raw.lower()
    hosts = allowed_hosts_set()
    if hosts and hn not in hosts:
        return False
    return True


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "0.0.0.0"


async def ip_login_is_rate_limited(ip: str) -> bool:
    async with _login_lock:
        now = time.time()
        rec = _login_by_ip.get(ip)
        if not rec:
            return False
        return now < float(rec.get("ban_until", 0.0))


async def ip_login_note_failure(ip: str) -> None:
    async with _login_lock:
        now = time.time()
        rec = _login_by_ip.setdefault(ip, {"fails": 0, "ban_until": 0.0})
        if now < float(rec["ban_until"]):
            return
        rec["fails"] = int(rec["fails"]) + 1
        if rec["fails"] >= _LOGIN_FAIL_MAX:
            rec["ban_until"] = now + float(_LOGIN_BAN_SEC)
            rec["fails"] = 0


async def ip_login_note_success(ip: str) -> None:
    async with _login_lock:
        _login_by_ip.pop(ip, None)


def _signing_key() -> bytes:
    h = gate_password_bcrypt_hash()
    return hashlib.sha256(f"{COOKIE_VERSION}:{h}".encode("utf-8")).digest()


def verify_login_password(candidate: str) -> bool:
    h = gate_password_bcrypt_hash()
    if not h:
        return False
    try:
        return bcrypt.checkpw(candidate.encode("utf-8"), h.encode("utf-8"))
    except ValueError:
        return False


def issue_cookie_value(remember_me: bool) -> str:
    now = int(time.time())
    payload = {"v": COOKIE_VERSION, "ls": now, "rm": 1 if remember_me else 0}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sk = _signing_key()
    sig = hmac.new(sk, b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _decode_cookie(token: str) -> dict | None:
    try:
        b64, sig = token.rsplit(".", 1)
        sk = _signing_key()
        if hmac.new(sk, b64.encode("ascii"), hashlib.sha256).hexdigest() != sig:
            return None
        pad = "=" * (-len(b64) % 4)
        raw = base64.urlsafe_b64decode(b64 + pad)
        return json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, OSError, UnicodeError):
        return None


def parse_cookie(token: str | None) -> tuple[int, bool] | None:
    if not token:
        return None
    p = _decode_cookie(token)
    if not p or int(p.get("v") or 0) != COOKIE_VERSION:
        return None
    ls = int(p["ls"])
    rm = bool(int(p.get("rm") or 0))
    now = int(time.time())
    max_idle = _IDLE_REMEMBER if rm else _IDLE_DEFAULT
    if now - ls > max_idle:
        return None
    return ls, rm


def cookie_secure(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower().split(",")[0].strip() == "https"


def attach_refreshed_cookie(
    response: Response, request: Request, remember_me: bool
) -> None:
    val = issue_cookie_value(remember_me)
    response.set_cookie(
        COOKIE_NAME,
        val,
        path="/",
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request),
    )


def not_found() -> Response:
    return Response(status_code=404, content="Not Found", media_type="text/plain")


def is_public_path(path: str, method: str) -> bool:
    p = path.rstrip("/") or "/"
    m = method.upper()
    if p == "/" and m == "GET":
        return True
    if p == "/login" and m == "GET":
        return True
    if p == "/api/auth/login" and m == "POST":
        return True
    if p == "/api/auth/logout" and m == "POST":
        return True
    if p == "/sonik.jpg" and m == "GET":
        return True
    if p == "/favicon.ico" and m == "GET":
        return True
    return False


async def gate_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if not gate_enabled():
        return await call_next(request)
    if not gate_request_ok(request):
        return not_found()
    path = request.url.path
    method = request.method
    if is_public_path(path, method):
        return await call_next(request)
    tok = request.cookies.get(COOKIE_NAME)
    pair = parse_cookie(tok)
    if pair is None:
        return not_found()
    _ls, remember = pair
    response = await call_next(request)
    attach_refreshed_cookie(response, request, remember)
    return response
