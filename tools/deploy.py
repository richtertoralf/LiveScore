#!/usr/bin/env python3
"""Small Linux installer. Code swaps are separate from config, credentials and data."""
import argparse
from contextlib import contextmanager
import fcntl
import getpass
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from uuid import uuid4

REPOSITORY = 'https://github.com/richtertoralf/LiveScore.git'
AUTH_FAILED = ('Anmeldung fehlgeschlagen – Username/Token prüfen, '
               'Token braucht Leserecht auf richtertoralf/LiveScore')
# Liest die Zugangsdaten nur aus der Umgebung des git-Subprozesses; das Skript selbst enthält nichts Geheimes.
ASKPASS = '''#!/bin/sh
case "$1" in
  Username*) printf '%s\\n' "$LIVESCORE_GIT_USERNAME" ;;
  *) printf '%s\\n' "$LIVESCORE_GIT_TOKEN" ;;
esac
'''
UNIT = 'livescore.service'
MARKER = '.livescore-managed'
RUNTIME = ('livescore', 'static', 'bin', 'tools', 'systemd', 'imports', 'examples', 'docs')
FILES = ('VERSION', 'requirements.txt', 'install.sh', 'upgrade.sh', 'uninstall.sh', 'README.md')


def fail(message):
    raise RuntimeError(message)


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def atomic_text(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.' + uuid4().hex)
    try:
        with tmp.open('x', encoding='utf-8') as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        tmp.chmod(mode)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def version(root):
    value = (root / 'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        fail('Ungültige VERSION: MAJOR.MINOR.PATCH erwartet.')
    return value


def clone(target, ask=input, ask_secret=getpass.getpass):
    """Privates Repository per HTTPS klonen; Username/Token bei jedem Aufruf abfragen, nichts speichern."""
    username = ask('GitHub-Username: ').strip()
    token = ask_secret('GitHub-Token (Eingabe unsichtbar): ').strip()
    if not username or not token:
        fail('GitHub-Username und Token sind erforderlich.')
    handle, askpass = tempfile.mkstemp(prefix='.askpass-', dir=Path(target).parent)
    try:
        with os.fdopen(handle, 'w') as file:
            file.write(ASKPASS)
        os.chmod(askpass, 0o700)
        # Token nur als Env-Variable des Subprozesses, nie in URL oder Argumenten;
        # ein leerer credential.helper verhindert jede Speicherung durch Git.
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_ASKPASS=askpass,
                   LIVESCORE_GIT_USERNAME=username, LIVESCORE_GIT_TOKEN=token)
        result = subprocess.run(['git', '-c', 'credential.helper=', 'clone', '--depth', '1', '--branch', 'main',
                                 '--', REPOSITORY, str(target)], env=env, check=False)
    finally:
        Path(askpass).unlink(missing_ok=True)
    if result.returncode == 128:
        fail(AUTH_FAILED)
    if result.returncode:
        fail(f'GitHub-Download fehlgeschlagen (git-Exitcode {result.returncode}).')


class Deployment:
    def __init__(self, staging_root=None):
        self.staging = Path(staging_root).resolve() if staging_root else None
        if self.staging == Path('/'):
            fail('--staging-root darf nicht / sein.')
        root = self.staging or Path('/')
        self.prefix = root / 'opt/livescore'
        self.config = root / 'etc/livescore'
        self.state = root / 'var/lib/livescore'
        self.cli = root / 'usr/local/bin/livescore'
        self.unit = root / 'etc/systemd/system' / UNIT
        self.current = self.prefix / 'current'
        self.config_file = self.config / 'livescore.yml'

    def preflight(self):
        if sys.platform != 'linux' or sys.version_info < (3, 12):
            fail('Linux mit Python >= 3.12 erforderlich.')
        if not self.staging and os.geteuid() != 0:
            fail('Bitte mit sudo ausführen; Tests mit --staging-root PFAD.')
        for path in (self.prefix, self.config, self.state, self.cli.parent, self.unit.parent):
            if any(p.is_symlink() for p in (path, *path.parents)):
                fail(f'Symbolischer Link im Installationspfad: {path}')
        for path in (self.prefix, self.config, self.state):
            if path.exists() and (not path.is_dir() or any(path.iterdir())):
                if not (path / MARKER).is_file() or (path / MARKER).read_text() != 'LiveScore\n':
                    fail(f'Fremdes oder unmarkiertes Verzeichnis bleibt unverändert: {path}')
        if self.cli.exists() or self.cli.is_symlink():
            if not self.cli.is_symlink() or os.readlink(self.cli) != str(self.current / 'bin/livescore'):
                fail(f'Fremdes CLI-Ziel bleibt unverändert: {self.cli}')
        if self.unit.is_symlink() or (self.unit.exists() and not self.unit.read_text().startswith('# Managed by the LiveScore installer;')):
            fail(f'Fremde Service-Datei bleibt unverändert: {self.unit}')
        for directory in (self.config, self.state):
            if directory.exists() and any(p.is_symlink() for p in directory.rglob('*')):
                fail('Keine symbolischen Links in verwalteten Config-/Datenverzeichnissen erlaubt.')
        if self.current.exists() or self.current.is_symlink():
            if not self.current.is_symlink() or self.current.resolve().parent != self.prefix / 'releases':
                fail('Unbekannte current-Laufzeit; keine Änderung.')
        if not self.staging:
            for command in ('systemctl', 'useradd', 'getent'):
                if not shutil.which(command):
                    fail(f'{command} fehlt. Linux mit systemd und Python-venv erforderlich.')
            fragment = run('systemctl', 'show', UNIT, '--property=FragmentPath', '--value',
                           capture_output=True, text=True).stdout.strip()
            if fragment and (fragment != str(self.unit) or not self.unit.exists()):
                fail('Bereits vorhandener fremder LiveScore-Dienst bleibt unverändert.')

    @contextmanager
    def lock(self):
        self.prefix.parent.mkdir(parents=True, exist_ok=True)
        with (self.prefix.parent / '.livescore-deploy.lock').open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fail('Eine Installation oder Deinstallation läuft bereits.')
            yield

    def systemctl(self, *args):
        if not self.staging:
            run('systemctl', *args)

    def active(self):
        return not self.staging and subprocess.run(
            ['systemctl', 'is-active', '--quiet', UNIT], check=False).returncode == 0

    def mark(self, path):
        path.mkdir(parents=True, exist_ok=True)
        atomic_text(path / MARKER, 'LiveScore\n')

    def build(self, source):
        source = Path(source).resolve()
        target_version = version(source)
        for name in (*RUNTIME, *FILES, 'config/livescore.yml', 'config/auth.example.yml'):
            if not (source / name).exists():
                fail(f'Unvollständige Quelle: {name}')
        self.mark(self.prefix)
        self.prefix.chmod(0o755)
        releases = self.prefix / 'releases'
        releases.mkdir(exist_ok=True)
        releases.chmod(0o755)
        target = Path(tempfile.mkdtemp(prefix='runtime-', dir=releases))
        target.chmod(0o755)
        try:
            for name in RUNTIME:
                shutil.copytree(source / name, target / name,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.lock', '*.tmp'))
            for name in FILES:
                shutil.copy2(source / name, target / name)
            (target / 'config').mkdir()
            for name in ('livescore.yml', 'auth.example.yml'):
                shutil.copy2(source / 'config' / name, target / 'config' / name)
            atomic_text(target / 'installation.json', json.dumps({
                'config': str(self.config_file),
                'staging_root': str(self.staging) if self.staging else None,
            }))
            print(f'Baue LiveScore {target_version}: {target}', flush=True)
            # The venv stays at this exact path, including after the current-link swap.
            environment = dict(os.environ, TMPDIR=str(target))
            run(sys.executable, '-m', 'venv', target / '.venv', env=environment)
            python = target / '.venv/bin/python'
            run(python, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir',
                '-r', target / 'requirements.txt', env=environment)
            run(python, '-m', 'pip', 'check', env=environment)
            run(python, '-m', 'compileall', '-q', target / 'livescore', target / 'tools')
            run(python, '-m', 'livescore', '--version', cwd=target)
            # Validate the canonical seed even for upgrades, without installing it.
            run(python, '-c', 'from livescore.storage import load; from pathlib import Path; load(Path("imports/prague-2026.json"))', cwd=target)
            return target
        except BaseException:
            shutil.rmtree(target)
            raise

    def inspect(self, target):
        result = run(target / '.venv/bin/python', '-m', 'livescore.bootstrap',
                     '--config', self.config_file, cwd=target, capture_output=True, text=True)
        info = json.loads(result.stdout)
        # Managed data must stay outside replaceable program code. External paths
        # require a manual deployment; never recursively chown/purge arbitrary paths.
        if not Path(info['data_dir']).is_relative_to(self.state / 'data'):
            fail('Installer erwartet data_dir innerhalb /var/lib/livescore/data (bzw. Staging-Pfad).')
        if not Path(info['auth_file']).is_relative_to(self.config):
            fail('Installer erwartet auth.file innerhalb des LiveScore-Config-Verzeichnisses.')
        return info

    def create_config(self):
        self.mark(self.config)
        self.mark(self.state)
        self.config.chmod(0o750)
        self.state.chmod(0o750)
        if not self.config_file.exists():
            atomic_text(self.config_file,
                        'bind_host: 0.0.0.0\nport: 8730\ndata_dir: ' + json.dumps(str(self.state / 'data')) +
                        '\nauth:\n  enabled: true\n  file: auth.yml\n  session_hours: 12\n  secure_cookie: false\n', 0o640)

    def account(self):
        if self.staging:
            return
        try:
            user = pwd.getpwnam('livescore')
            if user.pw_dir != str(self.state) or user.pw_shell not in ('/usr/sbin/nologin', '/sbin/nologin'):
                fail('Vorhandenes Konto livescore ist kein passendes Dienstkonto.')
        except KeyError:
            run('useradd', '--system', '--user-group', '--home-dir', self.state,
                '--shell', '/usr/sbin/nologin', 'livescore')
            user = pwd.getpwnam('livescore')
        for directory in (self.config, self.state):
            for path in (directory, *directory.rglob('*')):
                if path.is_symlink():
                    fail('Keine symbolischen Links in verwalteten Config-/Datenverzeichnissen erlaubt.')
                os.chown(path, user.pw_uid, user.pw_gid)

    def switch(self, target):
        temporary = self.prefix / ('.current-' + uuid4().hex)
        temporary.symlink_to(target)
        os.replace(temporary, self.current)

    def health(self, info, expected):
        if self.staging:
            return
        host = info['bind_host']
        host = '127.0.0.1' if host == '0.0.0.0' else '::1' if host == '::' else host
        if ':' in host:
            host = '[' + host + ']'
        for _ in range(30):
            try:
                with urlopen(f'http://{host}:{info["port"]}/api/version', timeout=1) as response:
                    if json.load(response)['version'] == expected and self.active():
                        return
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(1)
        fail('Dienst antwortet nach Start nicht korrekt; journalctl -u livescore prüfen.')

    def deploy(self, source, upgrade=False):
        old = self.current.resolve() if self.current.exists() else None
        if upgrade and not old:
            fail('Keine installierte Laufzeit gefunden. Zuerst install.sh ausführen.')
        if not upgrade and old:
            fail('Bereits installiert. Unverändert; bitte sudo livescore --upgrade verwenden.')
        if old:
            print(f'Installiert: {version(old)}; Ziel: {version(Path(source))}', flush=True)
            if tuple(map(int, version(Path(source)).split('.'))) < tuple(map(int, version(old).split('.'))):
                fail('Downgrade wird nicht ausgeführt.')
        target = self.build(source)
        switched = False
        stopped = False
        was_active = self.active()
        old_unit = self.unit.read_bytes() if self.unit.exists() else None
        try:
            if upgrade:
                if not self.config_file.is_file():
                    fail('Config fehlt; Upgrade erzeugt keine Ersatzkonfiguration.')
            else:
                self.create_config()
            info = self.inspect(target)
            if upgrade and info['auth_enabled'] and not Path(info['auth_file']).is_file():
                fail('Auth-Datei fehlt; Upgrade setzt keine Passwörter auf Initialwerte zurück.')
            if not self.staging and not was_active:
                # Refuse to start over an unrelated listener; never stop its process.
                with socket.socket(socket.AF_INET6 if ':' in info['bind_host'] else socket.AF_INET) as sock:
                    sock.bind((info['bind_host'], info['port']))
            if not upgrade:
                run(target / '.venv/bin/python', '-m', 'livescore.bootstrap', '--config', self.config_file,
                    '--seed', target / 'imports/prague-2026.json', cwd=target)
            self.account()
            # Download/build/validation happen while the old service is still running.
            if was_active:
                self.systemctl('stop', UNIT)
                stopped = True
            if old:
                backup = self.state / 'backups' / ('before-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
                backup.mkdir(parents=True, mode=0o700)
                shutil.copytree(self.config, backup / 'config')
                if (self.state / 'data').exists():
                    shutil.copytree(self.state / 'data', backup / 'data', ignore=shutil.ignore_patterns('*.lock'))
            self.switch(target)
            switched = True
            atomic_text(self.unit, (target / 'systemd' / UNIT).read_text())
            self.cli.parent.mkdir(parents=True, exist_ok=True)
            if not self.cli.is_symlink():
                self.cli.symlink_to(self.current / 'bin/livescore')
            self.systemctl('daemon-reload')
            if not old:
                self.systemctl('enable', UNIT)
            self.systemctl('restart', UNIT)
            self.health(info, version(target))
        except BaseException:
            rollback_errors = []

            def restore(function, *args):
                try:
                    function(*args)
                except Exception as error:
                    rollback_errors.append(str(error))

            if switched:
                # A broken systemctl must not prevent restoring the code pointer.
                restore(self.systemctl, 'stop', UNIT)
                if old:
                    restore(self.switch, old)
                else:
                    self.current.unlink(missing_ok=True)
                    self.cli.unlink(missing_ok=True)
                    restore(self.systemctl, 'disable', UNIT)
                if old_unit is not None:
                    restore(atomic_text, self.unit, old_unit.decode())
                else:
                    self.unit.unlink(missing_ok=True)
                restore(self.systemctl, 'daemon-reload')
            if stopped:
                restore(self.systemctl, 'start', UNIT)
            if self.current.resolve() != target:
                restore(shutil.rmtree, target)
            print('Installation fehlgeschlagen; bisherige Laufzeit und Daten bleiben gespeichert.', file=sys.stderr)
            if rollback_errors:
                print('Rollback unvollständig; current und Dienststatus prüfen: ' + '; '.join(rollback_errors), file=sys.stderr)
            raise
        # Keep the immediate previous runtime as a code backup, never runtime data here.
        for previous in (self.prefix / 'releases').iterdir():
            if previous not in (target, old):
                shutil.rmtree(previous)
        print(f'LiveScore {version(target)} installiert. Web: http://HOST:{info["port"]}/')
        print(f'CLI: {self.cli}\nConfig/Auth: {self.config}\nDaten: {self.state / "data"}')
        print('Staging: keine Systemdienste/Konten verändert; Server nicht gestartet.' if self.staging
              else 'Dienst: systemctl status livescore. Startpasswörter vor Internetfreigabe ändern.')

    def uninstall(self, purge=False):
        if not any((p / MARKER).exists() for p in (self.prefix, self.config, self.state)):
            fail('Keine verwaltete LiveScore-Installation gefunden.')
        if self.unit.exists():
            self.systemctl('stop', UNIT)
            self.systemctl('disable', UNIT)
            self.unit.unlink()
            self.systemctl('daemon-reload')
        self.cli.unlink(missing_ok=True)
        if self.prefix.exists():
            shutil.rmtree(self.prefix)
        if purge:
            for path in (self.config, self.state):
                if path.exists():
                    shutil.rmtree(path)
        print('LiveScore entfernt. ' + ('Config/Auth/Eventdaten und Backups gelöscht (--purge).'
                                      if purge else 'Config/Auth/Eventdaten und Backups bleiben erhalten.'))


def main():
    parser = argparse.ArgumentParser(description='LiveScore Linux installation and upgrade')
    parser.add_argument('operation', choices=('install', 'upgrade', 'uninstall'))
    parser.add_argument('--source', type=Path, help='lokaler Quellstand; Default: GitHub/main mit Username/Token-Abfrage')
    metadata = Path(__file__).resolve().parents[1] / 'installation.json'
    staging_default = json.loads(metadata.read_text()).get('staging_root') if metadata.exists() else None
    parser.add_argument('--staging-root', type=Path, default=staging_default,
                        help='isoliertes Testziel, keine Systemdienste oder Benutzer')
    parser.add_argument('--purge', action='store_true', help='Uninstall: auch Config, Passwörter, Daten und Backups löschen')
    args = parser.parse_args()
    if args.purge and args.operation != 'uninstall':
        parser.error('--purge nur bei uninstall')
    if args.source and args.operation == 'uninstall':
        parser.error('--source nicht bei uninstall')
    deployment = Deployment(args.staging_root)
    os.umask(0o022)
    try:
        deployment.preflight()
        with deployment.lock():
            if args.operation == 'uninstall':
                deployment.uninstall(args.purge)
            elif args.source:
                deployment.deploy(args.source.resolve(), args.operation == 'upgrade')
            else:
                upgrade = args.operation == 'upgrade'
                # Vor der Zugangsdatenabfrage prüfen, ob der Vorgang überhaupt möglich ist.
                if upgrade and not deployment.current.exists():
                    fail('Keine Installation gefunden.')
                if not upgrade and deployment.current.exists():
                    fail('Bereits installiert. Unverändert; bitte sudo livescore --upgrade verwenden.')
                if upgrade:
                    print(f'Installiert: {version(deployment.current)}. Lade GitHub/main.', flush=True)
                else:
                    print('Lade GitHub/main.', flush=True)
                deployment.mark(deployment.prefix)
                # Download-Verzeichnis samt Klon wird in jedem Fall gelöscht.
                with tempfile.TemporaryDirectory(prefix='.download-', dir=deployment.prefix) as temporary:
                    source = Path(temporary) / 'source'
                    clone(source)
                    deployment.deploy(source, upgrade=upgrade)
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.CalledProcessError) as exc:
        # No configuration contents, password hashes or captured output in errors.
        print(f'FEHLER: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
