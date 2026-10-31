"""Lesender Betriebsstatus für `livescore --status` (ADR-002).

Verändert keine Dateien oder Dienste und gibt keine Geheimnisse aus. Ohne
Leserecht auf die Betreiberkonfiguration gelten die Installer-Standardwerte;
das wird angezeigt und ist kein Fehler.

Rückgabe: 0 kein technischer Fehler (auch bei bewusst gestopptem Dienst),
1 technischer Fehler (Dienst fehlgeschlagen, aktiver Dienst nicht erreichbar,
keine Installation), 2 ungültige Konfiguration.
"""
import ipaddress
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
UNIT = 'livescore.service'
DEFAULT_CONFIG = Path('/etc/livescore/livescore.yml')
DEFAULT_DATA = Path('/var/lib/livescore/data')
DEFAULT_PORT = 8730
# Virtuelle Schnittstellen sind für Browser im LAN keine sinnvolle Adresse.
VIRTUAL = ('docker', 'br-', 'veth', 'virbr', 'lxcbr', 'cni', 'flannel')


def command(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def service():
    """LoadState, ActiveState und UnitFileState von livescore.service."""
    output = command('systemctl', 'show', UNIT, '--no-pager',
                     '--property=LoadState,ActiveState,UnitFileState') or ''
    return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)


def lan_addresses():
    """IPv4-Adressen aktiver, nicht virtueller Schnittstellen."""
    try:
        interfaces = json.loads(command('ip', '-j', '-4', 'address', 'show', 'up') or '[]')
    except ValueError:
        return []
    found = []
    for interface in interfaces:
        if 'LOOPBACK' in interface.get('flags', []) or interface.get('ifname', '').startswith(VIRTUAL):
            continue
        for info in interface.get('addr_info', []):
            address = info.get('local', '')
            if address and not address.startswith('169.254.') and address not in found:
                found.append(address)
    return found


def url(host, port):
    return f"http://[{host}]:{port}/" if ':' in host else f"http://{host}:{port}/"


def urls(bind_host, port):
    """Browser-Adressen passend zur Bind-Adresse; Hinweis bei Loopback."""
    if bind_host in ('0.0.0.0', '::', ''):
        return [url(a, port) for a in lan_addresses()] or [url('127.0.0.1', port)], None
    try:
        loopback = bind_host == 'localhost' or ipaddress.ip_address(bind_host).is_loopback
    except ValueError:
        loopback = False
    if loopback:
        return [url('127.0.0.1', port)], f'nur lokal erreichbar (bind_host {bind_host})'
    return [url(bind_host, port)], None


def probe(bind_host, port):
    """Laufende Version über /api/version, kurzer Timeout; (version, fehler)."""
    host = {'0.0.0.0': '127.0.0.1', '': '127.0.0.1', '::': '::1', 'localhost': '127.0.0.1'}.get(bind_host, bind_host)
    try:
        with urlopen(url(host, port) + 'api/version', timeout=2) as response:
            return json.load(response).get('version'), None
    except (OSError, ValueError, AttributeError) as exc:
        return None, f'{url(host, port)}: {getattr(exc, "reason", exc)}'


def header(version, settings):
    parts = [f'LiveScore {version}',
             f"Commit {settings['commit'][:7]}" if settings.get('commit') else 'Commit unbekannt']
    if settings.get('dirty'):
        parts[-1] += ' (dirty)'
    if settings.get('branch'):
        parts.append(f"Branch {settings['branch']}")
    origin = f"{settings.get('source') or ''} {settings.get('installed_at') or ''}".strip()
    if origin:
        parts.append(origin)
    return ' · '.join(parts)


def report(root=ROOT):
    """(Ausgabezeilen, Rückgabecode)."""
    version = (root / 'VERSION').read_text().strip()
    metadata = root / 'installation.json'
    try:
        settings = json.loads(metadata.read_text())
    except (OSError, ValueError):
        settings = None
    if settings is None:
        return [f'LiveScore {version}', '',
                f'Keine Installation gefunden: {root} ist keine installierte Laufzeit.',
                'Installation: sudo ./install.sh im Checkout'], 1

    lines, notes, code = [header(version, settings), ''], [], 0
    config_path = Path(settings.get('config') or DEFAULT_CONFIG)
    bind_host, port, data_dir, port_known = '0.0.0.0', DEFAULT_PORT, DEFAULT_DATA, False
    try:
        from .config import load_config
        config = load_config(config_path)
        bind_host, port, data_dir, port_known = config.bind_host, config.port, config.data_dir, True
    except PermissionError:
        notes.append(f'Konfiguration ohne Leserecht; Standardwerte angenommen (Port {DEFAULT_PORT}). '
                     'Vollständig: sudo livescore --status')
    except FileNotFoundError:
        notes.append(f'Konfiguration fehlt: {config_path}')
        code = 1
    except Exception as exc:  # YAML- oder Validierungsfehler der Betreiberdatei
        notes.append(f'Konfiguration ungültig ({type(exc).__name__}): {config_path}')
        code = 2

    unit = service()
    active, load = unit.get('ActiveState', ''), unit.get('LoadState', '')
    autostart = 'Autostart an' if unit.get('UnitFileState') == 'enabled' else 'Autostart aus'
    if settings.get('staging_root'):
        state = 'kein Dienst (Staging-Installation)'
    elif load in ('', 'not-found'):
        state, code = 'nicht eingerichtet', max(code, 1)
    else:
        state = {'active': 'läuft', 'inactive': 'gestoppt', 'failed': 'fehlgeschlagen',
                 'activating': 'startet', 'deactivating': 'stoppt'}.get(active, active or 'unbekannt')
        state += f' ({autostart})'
        if active == 'failed':
            code = max(code, 1)
            notes.append(f'Fehlerursache: journalctl -u {UNIT} -n 50')
    lines.append(f'Dienst:        {state}')

    running, error = probe(bind_host, port)
    if running:
        web = 'erreichbar' + (f' – läuft noch {running}, Neustart nötig' if running != version else '')
    else:
        web = 'nicht erreichbar'
        notes.append(error)
        # Ein aktiver Dienst ohne Antwort ist ein Fehler, sofern der Port bekannt ist.
        if active == 'active' and port_known:
            code = max(code, 1)
    lines.append(f'Weboberfläche: {web}')

    addresses, hint = urls(bind_host, port)
    lines += ['', 'Adressen:'] + [f'  {address}' for address in addresses]
    if hint:
        lines.append(f'  ({hint})')
    lines += ['', f'Konfiguration: {config_path.parent}', f'Veranstaltungsdaten: {data_dir}']
    if notes:
        lines += [''] + [f'Hinweis: {note}' for note in notes]
    return lines, code


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if arguments:
        print('Aufruf: livescore --status', file=sys.stderr)
        return 2
    lines, code = report()
    print('\n'.join(lines))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
