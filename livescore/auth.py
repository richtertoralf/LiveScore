"""Zwei lokale Accounts, atomare Hash-Datei und flüchtige Sessions."""
import argparse
import asyncio
from collections import deque
from dataclasses import dataclass
import getpass
import hashlib
import hmac
from pathlib import Path
import secrets
import time
from typing import Literal

import yaml
from pydantic import Field, SecretStr, field_validator, model_validator

from .models import Model
from .storage import atomic_write

USERS = ('admin', 'operator')
COOKIE = 'livescore_session'
LOGIN_COOKIE = 'livescore_login'
# OWASP scrypt alternative: N=2^15, r=8, p=3 (32 MiB per running KDF).
N, R, P = 32768, 8, 3


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32, maxmem=64*1024*1024)
    return f'scrypt${N}${R}${P}${salt.hex()}${digest.hex()}'


def parse_hash(encoded):
    kind, n, r, p, salt, digest = encoded.split('$')
    if kind != 'scrypt' or (int(n), int(r), int(p)) != (N, R, P):
        raise ValueError('Unsupported password hash parameters.')
    salt, digest = bytes.fromhex(salt), bytes.fromhex(digest)
    if len(salt) != 16 or len(digest) != 32:
        raise ValueError('Invalid password hash.')
    return salt, digest


def verify_password(password, encoded):
    salt, digest = parse_hash(encoded)
    actual = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32, maxmem=64*1024*1024)
    return hmac.compare_digest(actual, digest)


class AuthConfig(Model):
    enabled: bool = True
    file: Path = Path('auth.yml')
    session_hours: int = Field(default=12, strict=True, ge=1, le=168)
    secure_cookie: bool = False


class User(Model):
    role: Literal['admin', 'operator']
    password_hash: str
    default_password: bool = True

    @field_validator('password_hash')
    @classmethod
    def valid_hash(cls, value):
        parse_hash(value)
        return value


class Credentials(Model):
    users: dict[str, User]

    @model_validator(mode='after')
    def fixed_users(self):
        if set(self.users) != set(USERS) or any(self.users[name].role != name for name in USERS):
            raise ValueError('Exactly admin and operator with their fixed roles are required.')
        return self


class Login(Model):
    username: str = Field(max_length=80)
    password: SecretStr = Field(max_length=1024)


class PasswordChange(Model):
    username: Literal['admin', 'operator']
    password: SecretStr = Field(min_length=12, max_length=1024)
    repeat: SecretStr = Field(min_length=12, max_length=1024)


@dataclass
class Session:
    username: str
    csrf: str
    expires: float


class Auth:
    def __init__(self, config):
        self.config = config
        self.sessions = {}
        self.lock = asyncio.Lock()
        self.login_lock = asyncio.Lock()
        self.attempts = deque()
        self.credentials = None
        if config.enabled:
            if config.file.exists():
                raw = yaml.safe_load(config.file.read_text())
                if not isinstance(raw, dict) or not isinstance(raw.get('users'), dict):
                    raise ValueError('Auth configuration requires a users mapping.')
                # Retain the two supported accounts exactly; remove obsolete settings.
                # Validation precedes the atomic rewrite, under the application's file lease.
                current = {'users': {name: raw['users'].get(name) for name in USERS}}
                self.credentials = Credentials.model_validate(current)
                if raw != self.credentials.model_dump():
                    self.save(self.credentials)
            else:
                self.credentials = Credentials(users={name: User(role=name, password_hash=hash_password(name)) for name in USERS})
                self.save(self.credentials)
            self.dummy_hash = hash_password(secrets.token_urlsafe(32))

    def save(self, credentials):
        checked = Credentials.model_validate(credentials.model_dump())
        atomic_write(self.config.file, yaml.safe_dump(checked.model_dump(), sort_keys=False))

    def session(self, sid):
        session = self.sessions.get(sid)
        if session and session.expires <= time.monotonic():
            self.sessions.pop(sid, None)
            return None
        return session

    def new_session(self, username):
        self.sessions = {sid: s for sid, s in self.sessions.items() if s.expires > time.monotonic()}
        # A small fixed upper bound also limits memory use on long-running instances.
        if len(self.sessions) >= 1000:
            self.sessions.pop(next(iter(self.sessions)))
        sid = secrets.token_urlsafe(32)
        self.sessions[sid] = Session(username, secrets.token_urlsafe(32), time.monotonic()+self.config.session_hours*3600)
        return sid

    def restricted(self, session):
        return session.username == 'admin' and self.credentials.users['admin'].default_password

    def public(self, session):
        if not self.config.enabled:
            return dict(enabled=False, authenticated=True, username=None, role='admin', csrf_token='', must_change_password=False, defaults=[])
        if not session:
            return dict(enabled=True, authenticated=False)
        defaults = [name for name, user in self.credentials.users.items() if user.default_password] if session.username == 'admin' else []
        return dict(enabled=True, authenticated=True, username=session.username, role=session.username,
                    csrf_token=session.csrf, must_change_password=self.restricted(session), defaults=defaults)

    async def login(self, username, password):
        # Global limit works even behind a proxy without trusting forwarded client IPs.
        now = time.monotonic()
        while self.attempts and self.attempts[0] < now-300:
            self.attempts.popleft()
        if len(self.attempts) >= 30:
            return 'limited', None
        self.attempts.append(now)
        async with self.login_lock:
            user = self.credentials.users.get(username)
            encoded = user.password_hash if user else self.dummy_hash
            good = await asyncio.to_thread(verify_password, password, encoded)
            # A reset during KDF verification must not create a session with an old password.
            if not good or not user or self.credentials.users[username].password_hash != encoded:
                return 'invalid', None
            return 'ok', self.new_session(username)

    async def change_password(self, session, command):
        async with self.lock:
            if not any(s is session for s in self.sessions.values()) or session.expires <= time.monotonic():
                return 'auth_required'
            if self.restricted(session) and command.username != 'admin':
                return 'password_required'
            password = command.password.get_secret_value()
            if password != command.repeat.get_secret_value():
                return 'password_mismatch'
            if password in USERS:
                return 'password_weak'
            encoded = await asyncio.to_thread(hash_password, password)
            candidate = self.credentials.model_copy(deep=True)
            candidate.users[command.username] = User(role=command.username, password_hash=encoded, default_password=False)
            # Same cancellation-safe persistence as tournament changes.
            from .service import persist
            cancelled = await persist(self.save, candidate)
            self.credentials = candidate
            self.sessions = {sid: s for sid, s in self.sessions.items() if s.username != command.username}
            if cancelled:
                raise asyncio.CancelledError
        return None


def main():
    parser = argparse.ArgumentParser(description='LiveScore password hash helper')
    parser.add_argument('command', choices=['hash-password'])
    parser.parse_args()
    password = getpass.getpass('Password: ')
    if len(password) < 12 or len(password) > 1024:
        parser.error('Use 12–1024 characters.')
    if password != getpass.getpass('Repeat password: '):
        parser.error('Passwords do not match.')
    print(hash_password(password))


if __name__ == '__main__':
    main()
