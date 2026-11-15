"""Interactive local recovery; never stop/start/restart a server."""
import getpass
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import warnings

import yaml

from .auth import (PASSWORD_HINT_BELOW, PASSWORD_LENGTH, USERS, hash_password, new_password_error,
                   password_limits, update_password)

UNIT = 'livescore.service'


def reload_running_service(config_path):
    """Only reload the matching managed process if it actually catches SIGHUP."""
    manual = ('A standalone LiveScore process still needs an auth reload: '
              'send SIGHUP to its verified PID. Do not restart it. '
              'Otherwise the file will be loaded at the next normal start.')
    if sys.platform != 'linux' or not shutil.which('systemctl'):
        print('No systemd LiveScore service detected. ' + manual)
        return True
    try:
        result = subprocess.run(['systemctl', 'show', UNIT,
            '--property=LoadState,ActiveState,MainPID,FragmentPath,ExecReload'],
            capture_output=True, text=True, timeout=10, check=False)
        info = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if result.returncode or info.get('LoadState') != 'loaded' or info.get('ActiveState') != 'active':
            print('No active systemd LiveScore service detected. ' + manual)
            return True
        pid = int(info.get('MainPID', '0'))
        if pid <= 0:
            raise ValueError('Missing service PID')
        unit_file = Path(info.get('FragmentPath', ''))
        command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        argv = [arg.decode() for arg in command if arg]
        actual_config = Path(argv[argv.index('--config') + 1]).resolve()
        if actual_config != config_path.resolve():
            print('The systemd service uses a different configuration. ' + manual)
            return True
        reload_command = info.get('ExecReload', '')
        supported = re.search(r'path=/bin/kill\s*;\s*argv\[\]=/bin/kill -HUP (\$MAINPID|' + str(pid) + r')\s*;', reload_command)
        status = Path(f'/proc/{pid}/status').read_text()
        caught = int(re.search(r'^SigCgt:\s*([0-9a-fA-F]+)$', status, re.M)[1], 16)
        if (not unit_file.read_text().startswith('# Managed by the LiveScore installer;')
                or not supported or reload_command.count('path=') != 1
                or not caught & (1 << (signal.SIGHUP - 1))):
            print('Password saved, but safe SIGHUP reload is not available in the running service. '
                  'No signal or restart sent. Use a running version with auth-reload support.', file=sys.stderr)
            return False
        subprocess.run(['systemctl', 'reload', UNIT], check=True, capture_output=True, timeout=15)
        after = subprocess.run(['systemctl', 'show', UNIT, '--property=MainPID', '--value'],
                               check=True, capture_output=True, text=True, timeout=10)
        if after.stdout.strip() != str(pid):
            raise RuntimeError('Service PID changed unexpectedly')
        # ExecReload sends SIGHUP; validation happens asynchronously in the server.
        print('LiveScore authentication reload requested. No restart was required.')
        print('Reload validation is reported in the LiveScore service log.')
        return True
    except (OSError, ValueError, IndexError, TypeError, RuntimeError, subprocess.SubprocessError):
        print('Password saved, but the auth reload could not be confirmed. '
              'Check the service and send SIGHUP to its verified PID; no restart was requested.', file=sys.stderr)
        return False


def recovery_settings(config_path):
    """Nur Ort der Kontendatei und Längengrenzen, unabhängig von der übrigen Konfiguration (#20).

    Returns (auth_file, minimum, maximum, notes). Eine defekte oder ergänzte
    livescore.yml blockiert den Reset nicht; verwendete Ersatzwerte werden genannt.
    """
    config_path = Path(config_path).resolve()
    default_file = config_path.parent / 'auth.yml'
    notes = []
    try:
        raw = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        raw = None
        notes.append(f'{config_path} nicht lesbar oder kein gültiges YAML. '
                     f'Verwendet werden {default_file} und {PASSWORD_LENGTH[0]} bis {PASSWORD_LENGTH[1]} Zeichen.')
    auth = raw.get('auth') if isinstance(raw, dict) else None
    auth = auth if isinstance(auth, dict) else {}
    configured = auth.get('file', 'auth.yml')
    if isinstance(configured, str) and configured.strip():
        auth_file = (config_path.parent / configured).resolve()
    else:
        auth_file = default_file
        notes.append(f'auth.file in {config_path} ungültig. Verwendet wird {default_file}.')
    minimum, maximum, error = password_limits(auth.get('password_min_length'), auth.get('password_max_length'),
                                              str(config_path))
    if error and raw is not None:
        notes.append(error)
    return auth_file, minimum, maximum, notes


def reset_admin_password(config_path, username='admin'):
    if username not in USERS:
        print('Nur die Konten admin oder operator. Passwörter ausschließlich interaktiv eingeben.', file=sys.stderr)
        return 2
    auth_file, minimum, maximum, settings_notes = recovery_settings(config_path)
    for note in settings_notes:
        print(note, file=sys.stderr)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            entered = getpass.getpass(f'New {username} password: ')
            repeated = getpass.getpass(f'Repeat new {username} password: ')
        # Wie Anmeldung und Oberfläche: Leerzeichen am Rand zählen nicht (#21).
        password = entered.strip()
        if password != repeated.strip():
            print('Passwords do not match.', file=sys.stderr)
            return 1
        error = new_password_error(password, minimum, maximum)
        if error:
            print(error, file=sys.stderr)
            return 1
        _, _, notes = update_password(auth_file, username, hash_password(password), create=True, repair=True)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError):
        print(f'{username} password not changed: auth file inaccessible or locked.', file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print(f'{username} password not changed. Use an interactive terminal with hidden input.', file=sys.stderr)
        return 1
    _syslog(f'Passwort für {username} gesetzt (--reset-admin-password)')
    if password != entered:
        notes.append('Leerzeichen am Rand entfernt, wie bei der Anmeldung.')
    for note in notes:
        print(note)
    if len(password) < PASSWORD_HINT_BELOW:
        print(f'Hinweis: Passwörter unter {PASSWORD_HINT_BELOW} Zeichen sind im Netz leichter zu erraten.')
    print(f'{"Admin" if username == "admin" else "Operator"} password updated in {auth_file}.')
    return 0 if reload_running_service(config_path) else 1


def _syslog(message):
    """Protokoll ohne Geheimnisse (Facility auth)."""
    try:
        import syslog
        syslog.openlog('livescore', syslog.LOG_PID, syslog.LOG_AUTH)
        syslog.syslog(syslog.LOG_NOTICE, message)
        syslog.closelog()
    except (ImportError, OSError):
        pass
