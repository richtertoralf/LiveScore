"""Zwei lokale Accounts, atomare Hash-Datei und flüchtige Sessions.

Der Dienst legt keine Konten an und schreibt die Datei beim Start nie neu.
Fehlt sie oder ist sie unbrauchbar, ist nur die Anmeldung gesperrt (#18, #19);
Live-API und Anzeigen laufen weiter. Meldungen nennen nie Hashes (#22).
"""
import argparse
import asyncio
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
import getpass
import hashlib
import hmac
import ipaddress
import logging
import os
from pathlib import Path
import secrets
import shutil
import time
from typing import Any, Literal

import yaml
from pydantic import Field, IPvAnyAddress, SecretStr, field_validator, model_validator

from .models import Model
from .storage import atomic_write, FileLease

USERS = ('admin', 'operator')
RESET_COMMAND = 'sudo livescore --reset-admin-password'
# Vorgabe für neue Passwörter (#12); einstellbar unter auth in livescore.yml.
PASSWORD_LENGTH = (5, 1024)
PASSWORD_HINT_BELOW = 12
# Anmeldelimit (#23): nur Fehlversuche, je Client und insgesamt, im Zeitfenster.
LOGIN_WINDOW_SECONDS = 300
LOGIN_FAILURES_PER_CLIENT = 10
LOGIN_FAILURES_TOTAL = 100
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
    # Bewusst ohne Typprüfung: Ein ungültiger Wert stoppt nichts (password_limits).
    password_min_length: Any = None
    password_max_length: Any = None
    # Nur von diesen Adressen wird X-Forwarded-For für das Anmeldelimit gelesen (#23).
    trusted_proxies: list[IPvAnyAddress] = []


def login_client(peer, forwarded_for, trusted_proxies):
    """Client-Schlüssel für das Anmeldelimit (#23).

    Die direkte Gegenstelle. Nur wenn sie ein eingetragener Proxy ist, gilt der
    rechte Eintrag aus X-Forwarded-For, der selbst kein eingetragener Proxy ist;
    weiter links stehende Einträge kann der Client selbst mitschicken.
    """
    def address(value):
        try:
            return ipaddress.ip_address(value.strip())
        except ValueError:
            return None

    if address(peer) not in trusted_proxies:
        return peer
    for entry in reversed(forwarded_for.split(',')):
        client = address(entry)
        if client not in trusted_proxies:
            return str(client) if client is not None else peer
    return peer


def password_limits(minimum=None, maximum=None, source='livescore.yml'):
    """(min, max, Meldung): ungültige Werte ergeben die Vorgabe und eine Meldung."""
    low, high = PASSWORD_LENGTH
    values = (low if minimum is None else minimum, high if maximum is None else maximum)
    if not all(type(value) is int for value in values):
        reason = 'Werte müssen ganze Zahlen sein'
    elif not 1 <= values[0] <= values[1] <= high:
        reason = f'zulässig ist 1 ≤ Minimum ≤ Maximum ≤ {high}'
    else:
        return values[0], values[1], None
    return low, high, f'Ungültige Längengrenzen in {source}: {reason}. Verwendet werden {low} bis {high}.'


def new_password_error(password, minimum, maximum):
    if not minimum <= len(password) <= maximum:
        return f'Passwort nicht geändert: {minimum} bis {maximum} Zeichen verwenden.'
    return None


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
        # Ein fehlendes Konto richtet der Admin in der Oberfläche oder per Reset ein.
        if not self.users or not set(self.users) <= set(USERS) or any(self.users[name].role != name for name in self.users):
            raise ValueError('Only admin and operator with their fixed roles are supported.')
        return self


def collect_users(raw):
    """Gültige Konten und Namen nicht übernommener Einträge, ohne Werte (#22)."""
    if not isinstance(raw, dict) or not isinstance(raw.get('users'), dict):
        return {}, ['users']
    users, ignored = {}, [str(key) for key in raw if key != 'users']
    for name, value in raw['users'].items():
        try:
            if name not in USERS:
                raise ValueError(name)
            user = User.model_validate(value)
            if user.role != name:
                raise ValueError(name)
        except ValueError:
            ignored.append(f'users.{name}')
            continue
        users[name] = user
    return users, ignored


def parse_credentials(text):
    """Gültige Konten und Namen nicht übernommener Einträge.

    Meldungen nennen nur Namen, nie Werte: Pydantic-Fehler enthielten sonst
    Teile von password_hash (#22).
    """
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict) or not isinstance(raw.get('users'), dict):
        raise ValueError('ohne users-Abschnitt')
    users, ignored = collect_users(raw)
    if not users:
        raise ValueError('ohne gültiges Konto')
    return Credentials(users=users), ignored


def unusable_reason(error):
    """Grund ohne Dateiinhalt; YAML-Fehler zitieren sonst Zeilen der Datei."""
    if isinstance(error, FileNotFoundError):
        return 'fehlt'
    if isinstance(error, OSError):
        return 'nicht lesbar'
    if isinstance(error, yaml.YAMLError):
        return 'kein gültiges YAML'
    if isinstance(error, RuntimeError):
        return 'gesperrt'
    return str(error)  # nur eigene Meldungen aus parse_credentials


class Login(Model):
    username: str = Field(max_length=80)
    password: SecretStr = Field(max_length=1024)


class PasswordChange(Model):
    # Längen prüft change_password mit den eingestellten Grenzen (#12).
    username: Literal['admin', 'operator']
    password: SecretStr = Field(max_length=1024)
    repeat: SecretStr = Field(max_length=1024)


@contextmanager
def credentials_lock(path):
    """Shared OS lock for auth reads/writes, not the server's lifetime."""
    lease = FileLease(path)
    lease.acquire(blocking=True)
    try:
        # sudo recovery must not leave a newly created lock owned only by root.
        if os.name != 'nt' and os.geteuid() == 0:
            owner = (path if path.exists() else path.parent).stat()
            os.fchown(lease.file.fileno(), owner.st_uid, owner.st_gid)
        yield
    finally:
        lease.release()


def read_credentials(path):
    """Caller holds credentials_lock. Returns (credentials, ignored entry names)."""
    return parse_credentials(path.read_text(encoding='utf-8'))


def save_credentials(path, credentials):
    """Caller holds credentials_lock; keep service-account ownership after sudo."""
    checked = Credentials.model_validate(credentials.model_dump())
    created = not path.exists()
    atomic_write(path, yaml.safe_dump(checked.model_dump(), sort_keys=False), preserve_owner=True)
    if created and os.name != 'nt' and os.geteuid() == 0:
        # Neu angelegt mit sudo: Eigentümer wie das Config-Verzeichnis (Dienstkonto).
        owner = path.parent.stat()
        os.chown(path, owner.st_uid, owner.st_gid)


def backup_file(path):
    """Kopie vor einer Änderung, die Einträge nicht übernimmt; gleiche Rechte."""
    target = path.with_name(f'{path.name}.defekt-{time.strftime("%Y%m%d-%H%M%S")}')
    while target.exists():
        target = target.with_name(target.name + '-1')
    shutil.copy2(path, target)
    if os.name != 'nt' and os.geteuid() == 0:
        owner = path.stat()
        os.chown(target, owner.st_uid, owner.st_gid)
    return target


def load_credentials_report(path):
    """(credentials, ignored entry names) under the shared lock."""
    with credentials_lock(path):
        return read_credentials(path)


def load_credentials(path):
    return load_credentials_report(path)[0]


def update_password(path, username, encoded, expected_admin_hash=None, create=False, repair=False):
    """Read-modify-write on the latest disk state, never a stale RAM snapshot.

    Returns (credentials, accepted, notes). Nicht übernommene Einträge werden
    vorher gesichert und genannt; nichts verschwindet stillschweigend.
    create: eine fehlende Datei anlegen. repair (nur Reset, #20): eine
    unbrauchbare Datei sichern und ihre gültigen Konten übernehmen.
    """
    notes = []
    with credentials_lock(path):
        if create and not path.exists():
            users, ignored = {}, []
            notes.append(f'{path.name} angelegt.')
        elif repair:
            try:
                raw = yaml.safe_load(path.read_text(encoding='utf-8'))
            except (UnicodeDecodeError, yaml.YAMLError):
                raw = None
            users, ignored = collect_users(raw)
            if raw is None:
                ignored = ['gesamte Datei (leer oder kein gültiges YAML)']
        else:
            current, ignored = read_credentials(path)
            users = dict(current.users)
        admin = users.get('admin')
        if expected_admin_hash is not None and (admin is None or admin.password_hash != expected_admin_hash):
            return Credentials(users=users), False, notes  # Recovery revoked this web request's authority.
        if ignored:
            backup = backup_file(path)
            notes.append(f'Nicht übernommen: {", ".join(ignored)}; gesichert in {backup}.')
            logging.warning('Auth-Datei: nicht übernommen: %s; gesichert in %s', ', '.join(ignored), backup)
        users[username] = User(role=username, password_hash=encoded, default_password=False)
        updated = Credentials(users=users)
        save_credentials(path, updated)
        return updated, True, notes


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
        self.failures = deque()  # (Zeitpunkt, Client) fehlgeschlagener Anmeldungen
        self.credentials = None
        self.locked_reason = None
        self.limits = password_limits(config.password_min_length, config.password_max_length)
        if self.limits[2]:
            logging.error(self.limits[2])
        if config.enabled:
            self.dummy_hash = hash_password(secrets.token_urlsafe(32))
            try:
                candidate, ignored = load_credentials_report(config.file)
            except (OSError, ValueError, RuntimeError, yaml.YAMLError) as error:
                # Nur die Anmeldung ist gesperrt; Live-API und Anzeigen laufen weiter.
                self.locked_reason = f'{config.file.name} {unusable_reason(error)}'
                logging.error('LiveScore-Anmeldung gesperrt: %s. Einrichten: %s', self.locked_reason, RESET_COMMAND)
            else:
                self.adopt(candidate, ignored)

    @property
    def locked(self):
        return self.config.enabled and self.credentials is None

    def adopt(self, candidate, ignored=()):
        before = self.credentials.users if self.credentials else {}
        changed = {name for name in USERS if before.get(name) != candidate.users.get(name)}
        self.credentials = candidate
        self.locked_reason = None
        self.sessions = {sid: session for sid, session in self.sessions.items() if session.username not in changed}
        if ignored:
            logging.warning('Auth-Datei: Einträge ignoriert (Datei unverändert): %s', ', '.join(ignored))
        missing = [name for name in USERS if name not in candidate.users]
        if missing:
            logging.warning('Konto nicht eingerichtet: %s. Einrichten unter /users oder: %s', ', '.join(missing), RESET_COMMAND)
        defaults = [name for name, user in candidate.users.items() if user.default_password]
        if defaults:
            logging.warning('Startpasswort noch aktiv: %s. Unter /users ändern.', ', '.join(defaults))

    async def reload(self):
        if not self.config.enabled:
            return False
        async with self.lock:
            try:
                candidate, ignored = await asyncio.to_thread(load_credentials_report, self.config.file)
            except (OSError, ValueError, RuntimeError, yaml.YAMLError) as error:
                # Do not log validation details: they may contain password hashes.
                logging.error('Auth reload rejected (%s); retaining previous credentials and sessions.',
                              unusable_reason(error))
                return False
            lost = [name for name in (self.credentials.users if self.credentials else {}) if name not in candidate.users]
            if lost:
                # Ein fehlerhaft bearbeitetes Konto darf laufende Bedienung nicht aussperren.
                logging.error('Auth reload rejected (account missing or invalid: %s); '
                              'retaining previous credentials and sessions.', ', '.join(lost))
                return False
            self.adopt(candidate, ignored)
            logging.getLogger('uvicorn.error').info('LiveScore authentication reloaded without restart.')
            return True

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
        admin = self.credentials.users.get('admin') if self.credentials else None
        return session.username == 'admin' and admin is not None and admin.default_password

    def public(self, session):
        if not self.config.enabled:
            return dict(enabled=False, authenticated=True, username=None, role='admin', csrf_token='', must_change_password=False, defaults=[])
        if not session:
            return dict(enabled=True, authenticated=False, locked=self.locked)
        defaults = [name for name, user in self.credentials.users.items() if user.default_password] if session.username == 'admin' else []
        return dict(enabled=True, authenticated=True, username=session.username, role=session.username,
                    csrf_token=session.csrf, must_change_password=self.restricted(session), defaults=defaults,
                    password_min_length=self.limits[0], password_max_length=self.limits[1])

    def login_limited(self, client):
        """Ein Client mit vielen Fehlversuchen sperrt nur sich selbst (#23).

        Das höhere Gesamtlimit begrenzt verteiltes Durchprobieren. Höchstens
        LOGIN_FAILURES_TOTAL Einträge, weil gesperrte Anfragen nichts eintragen.
        """
        cutoff = time.monotonic() - LOGIN_WINDOW_SECONDS
        while self.failures and self.failures[0][0] < cutoff:
            self.failures.popleft()
        return (len(self.failures) >= LOGIN_FAILURES_TOTAL
                or sum(entry == client for _, entry in self.failures) >= LOGIN_FAILURES_PER_CLIENT)

    async def login(self, username, password, client):
        if self.locked:
            return 'locked', None
        if self.login_limited(client):
            return 'limited', None
        # Vorab als Fehlversuch zählen: Parallele oder abgebrochene Anfragen umgehen das Limit nicht.
        attempt = (time.monotonic(), client)
        self.failures.append(attempt)
        async with self.login_lock:
            user = self.credentials.users.get(username)
            encoded = user.password_hash if user else self.dummy_hash
            good = await asyncio.to_thread(verify_password, password, encoded)
            # A reset during KDF verification must not create a session with an old password.
            current = self.credentials.users.get(username)
            if not good or not user or current is None or current.password_hash != encoded:
                return 'invalid', None
            # Erfolg zählt nicht und löscht den Zähler dieses Clients; das Gesamtlimit zählt weiter.
            self.failures = deque((at, None if entry == client else entry)
                                  for at, entry in self.failures if (at, entry) != attempt)
            return 'ok', self.new_session(username)

    async def change_password(self, session, command):
        async with self.lock:
            if not any(s is session for s in self.sessions.values()) or session.expires <= time.monotonic():
                return 'auth_required'
            if session.username != 'admin':
                return 'forbidden'
            if self.restricted(session) and command.username != 'admin':
                return 'password_required'
            password = command.password.get_secret_value()
            if password != command.repeat.get_secret_value():
                return 'password_mismatch'
            if new_password_error(password, *self.limits[:2]):
                return 'password_length'
            if password in USERS:
                return 'password_weak'
            encoded = await asyncio.to_thread(hash_password, password)
            if not any(s is session for s in self.sessions.values()) or session.expires <= time.monotonic():
                return 'auth_required'
            task = asyncio.create_task(asyncio.to_thread(update_password, self.config.file,
                command.username, encoded, self.credentials.users['admin'].password_hash))
            cancelled = False
            try:
                candidate, accepted, _notes = await asyncio.shield(task)
            except asyncio.CancelledError:
                candidate, accepted, _notes = await task
                cancelled = True
            self.adopt(candidate)
            if cancelled:
                raise asyncio.CancelledError
            if not accepted:
                return 'auth_required'
        logging.getLogger('uvicorn.error').info('Passwort für %s gesetzt (Oberfläche, durch admin)', command.username)
        return None


def create_accounts(path):
    """Erstinstallation: beide Konten mit je eigenem Zufallspasswort, einmal angezeigt (#18)."""
    with credentials_lock(path):
        if path.exists():
            print(f'{path} vorhanden; Konten bleiben unverändert.')
            return 0
        passwords = {name: secrets.token_urlsafe(15) for name in USERS}  # 20 Zeichen
        save_credentials(path, Credentials(users={
            name: User(role=name, password_hash=hash_password(password), default_password=False)
            for name, password in passwords.items()}))
    print('LiveScore-Konten angelegt. Passwörter werden nur jetzt angezeigt:')
    for name, password in passwords.items():
        print(f'  {name}: {password}')
    print(f'Ändern: im Browser unter /users oder mit {RESET_COMMAND}')
    return 0


def main():
    parser = argparse.ArgumentParser(description='LiveScore password hash helper')
    parser.add_argument('command', choices=['hash-password', 'create-accounts'])
    parser.add_argument('--file', type=Path, help='auth.yml für create-accounts')
    args = parser.parse_args()
    if args.command == 'create-accounts':
        if not args.file:
            parser.error('create-accounts braucht --file.')
        raise SystemExit(create_accounts(args.file))
    password = getpass.getpass('Password: ').strip()  # wie Anmeldung und Oberfläche (#21)
    low, high = PASSWORD_LENGTH
    if not low <= len(password) <= high:
        parser.error(f'Use {low}–{high} characters.')
    if password != getpass.getpass('Repeat password: ').strip():
        parser.error('Passwords do not match.')
    print(hash_password(password))


if __name__ == '__main__':
    main()
