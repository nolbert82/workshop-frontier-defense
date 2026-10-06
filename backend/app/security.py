import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        raw = base64.b64decode(encoded, validate=True)
        actual = hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1)
        return hmac.compare_digest(actual, raw[16:])
    except (ValueError, TypeError):
        return False


class Auth:
    def __init__(self, settings):
        self.settings = settings
        self.sessions = {}
        self.attempts = defaultdict(deque)

    def check_origin(self, origin):
        if origin not in self.settings.origins:
            raise HTTPException(403, "Origine refusée")

    def session(self, token):
        key = hashlib.sha256((token or "").encode()).hexdigest()
        data = self.sessions.get(key)
        if not data or data["expires"] <= time.monotonic():
            self.sessions.pop(key, None)
            raise HTTPException(401, "Session expirée")
        return data

    def read(self, request: Request):
        return self.session(request.cookies.get("sentinel_session"))

    def write(self, request: Request):
        data = self.read(request)
        self.check_origin(request.headers.get("origin"))
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), data["csrf"]):
            raise HTTPException(403, "Jeton CSRF refusé")
        return data

    def login(self, request, username, password):
        self.check_origin(request.headers.get("origin"))
        host = request.client.host if request.client else "unknown"
        attempts = self.attempts[host]
        now = time.monotonic()
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= 5:
            raise HTTPException(429, "Trop de tentatives ; réessayez dans une minute")
        attempts.append(now)
        if username != "operateur" or not verify_password(password, self.settings.password_hash):
            raise HTTPException(401, "Identifiants incorrects")
        # Purge expired sessions; cap memory for this single-operator prototype.
        self.sessions = {k: v for k, v in self.sessions.items() if v["expires"] > now}
        if len(self.sessions) >= 100:
            self.sessions.pop(next(iter(self.sessions)))
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.sessions[hashlib.sha256(token.encode()).hexdigest()] = {"csrf": csrf, "expires": now + 8*3600}
        return token, csrf

    def service(self, request: Request):
        expected = "Bearer " + self.settings.vision_token
        if not hmac.compare_digest(request.headers.get("authorization", ""), expected):
            raise HTTPException(401, "Secret vision refusé")
