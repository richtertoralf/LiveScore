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

from .auth import hash_password, load_credentials, update_password

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


def reset_admin_password(config_path, config):
    try:
        # Recovery requires an existing, completely valid file; never seed accounts.
        load_credentials(config.auth.file)
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('New admin password: ')
            repeated = getpass.getpass('Repeat new admin password: ')
        if not 12 <= len(password) <= 1024:
            print('Use 12–1024 characters.', file=sys.stderr)
            return 1
        if password != repeated:
            print('Passwords do not match.', file=sys.stderr)
            return 1
        update_password(config.auth.file, 'admin', hash_password(password))
    except (OSError, ValueError, RuntimeError, yaml.YAMLError):
        print('Admin password not changed: existing auth file invalid, inaccessible or locked.', file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print('Admin password not changed. Use an interactive terminal with hidden input.', file=sys.stderr)
        return 1
    print('Admin password updated.')
    return 0 if reload_running_service(config_path) else 1
