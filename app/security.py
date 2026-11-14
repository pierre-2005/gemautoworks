"""Passwords, CSRF, sessions, rate limits and input cleaning."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request

_PH = PasswordHasher()
_RATE: dict[str, deque] = defaultdict(deque)
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$')


def hash_password(password: str) -> str:
    return _PH.hash(password)


def verify_password(stored: str | None, password: str) -> bool:
    if not stored:
        # spend the same time so a missing account cannot be told apart from a wrong password
        try:
            _PH.verify(_DUMMY, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            pass
        return False
    try:
        return _PH.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


_DUMMY = _PH.hash('not-a-real-password-for-timing-only')


def password_problem(password: str) -> str | None:
    if len(password) < 10:
        return 'Use at least 10 characters for your password.'
    if len(password) > 200:
        return 'Use 200 characters or fewer for your password.'
    return None


def csrf_token(request: Request) -> str:
    token = request.session.get('csrf')
    if not token:
        token = secrets.token_urlsafe(32)
        request.session['csrf'] = token
    return token


def check_csrf(request: Request, token: str | None) -> None:
    expected = request.session.get('csrf')
    if not expected or not token or not hmac.compare_digest(expected, token):
        raise HTTPException(400, 'This form expired. Go back, reload the page and try again.')


def client_ip(request: Request) -> str:
    """The visitor's address. Behind the Cloudflare tunnel every request arrives from the tunnel (loopback or a private
    Docker address), so only then is Cloudflare's own CF-Connecting-IP header believed; a visitor cannot set it."""
    host = request.client.host if request.client else 'unknown'
    try:
        trusted = ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:
        trusted = False
    cf = request.headers.get('cf-connecting-ip', '').strip()
    return cf[:64] if trusted and cf else host


def throttle(request: Request, purpose: str, max_count: int = 8, seconds: int = 3600) -> None:
    key = f'{purpose}:{client_ip(request)}'
    now = time.monotonic()
    q = _RATE[key]
    while q and now - q[0] > seconds:
        q.popleft()
    if len(q) >= max_count:
        raise HTTPException(429, 'Too many attempts from this connection. Wait a little and try again.')
    q.append(now)


def reset_throttles() -> None:
    _RATE.clear()


def clean(value: str | None, limit: int = 300) -> str:
    value = (value or '').replace('\x00', '').strip()
    value = re.sub(r'[\r\n\t]+', ' ', value) if limit <= 300 else value.replace('\r\n', '\n')
    return value[:limit]


def email_ok(value: str) -> bool:
    return bool(EMAIL_RE.match(value or '')) and len(value) <= 254


def phone_ok(value: str) -> bool:
    digits = re.sub(r'\D', '', value or '')
    return 10 <= len(digits) <= 15


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_rotate(request: Request) -> None:
    """New session contents on sign-in so an old cookie cannot ride along."""
    keep = {k: request.session[k] for k in ('csrf',) if k in request.session}
    request.session.clear()
    request.session.update(keep)
    request.session['csrf'] = secrets.token_urlsafe(32)
