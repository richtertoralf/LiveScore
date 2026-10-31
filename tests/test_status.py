"""livescore --status: lesend, mit Doubles für systemctl/ip und lokalem HTTP-Server."""
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / 'VERSION').read_text().strip()
INTERFACES = [
    {'ifname': 'lo', 'flags': ['LOOPBACK', 'UP'], 'addr_info': [{'local': '127.0.0.1'}]},
    {'ifname': 'enp1s0', 'flags': ['UP'], 'addr_info': [{'local': '10.0.0.5'}]},
    {'ifname': 'wg0', 'flags': ['UP'], 'addr_info': [{'local': '172.16.1.2'}]},
    {'ifname': 'docker0', 'flags': ['UP'], 'addr_info': [{'local': '172.17.0.1'}]},
    {'ifname': 'eth9', 'flags': ['UP'], 'addr_info': [{'local': '169.254.3.3'}]},
]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class StatusTest(unittest.TestCase):
    def setUp(self):
        (ROOT / '.test-artifacts').mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=ROOT / '.test-artifacts')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        shutil.copytree(ROOT / 'livescore', self.runtime / 'livescore', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT / 'bin', self.runtime / 'bin')
        shutil.copy2(ROOT / 'VERSION', self.runtime / 'VERSION')
        (self.runtime / '.venv').symlink_to(ROOT / '.venv', target_is_directory=True)
        self.config = self.root / 'etc/livescore.yml'
        self.config.parent.mkdir()
        self.port = free_port()
        self.write_config('0.0.0.0', self.port)
        (self.runtime / 'installation.json').write_text(json.dumps({
            'config': str(self.config), 'staging_root': None, 'commit': '8e5707112fcb31da0ad354bd135c24be05bd8dbc',
            'branch': 'main', 'dirty': False, 'source': 'github main', 'installed_at': '2026-10-31T14:17:14+0100'}))
        self.bin = self.root / 'commands'
        self.bin.mkdir()
        (self.bin / 'ip').write_text(f"#!/bin/sh\necho '{json.dumps(INTERFACES)}'\n")
        self.service('active', 'enabled')

    def write_config(self, bind_host, port):
        self.config.write_text(f'bind_host: {bind_host}\nport: {port}\ndata_dir: data\n'
                               'auth:\n  enabled: true\n  file: auth.yml\n')

    def service(self, active, enabled, load='loaded'):
        systemctl = self.bin / 'systemctl'
        systemctl.write_text(f'#!/bin/sh\nprintf "LoadState={load}\\nActiveState={active}\\nUnitFileState={enabled}\\n"\n')
        for path in self.bin.iterdir():
            path.chmod(0o755)

    def serve(self, version=VERSION):
        body = json.dumps({'version': version}).encode()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib hook name
                self.send_response(200 if self.path == '/api/version' else 404)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        server = http.server.HTTPServer(('127.0.0.1', self.port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def status(self):
        env = {**os.environ, 'PATH': f'{self.bin}:{os.environ["PATH"]}'}
        return subprocess.run([str(self.runtime / 'bin/livescore'), '--status'], env=env,
                              capture_output=True, text=True, timeout=30)

    def test_running_service_lists_lan_addresses_and_paths(self):
        self.serve()
        result = self.status()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith(
            f'LiveScore {VERSION} · Commit 8e57071 · Branch main · github main 2026-10-31T14:17:14+0100\n'))
        self.assertIn('Dienst:        läuft (Autostart an)', result.stdout)
        self.assertIn('Weboberfläche: erreichbar\n', result.stdout)
        self.assertIn(f'  http://10.0.0.5:{self.port}/\n  http://172.16.1.2:{self.port}/\n', result.stdout)
        for hidden in ('127.0.0.1', '172.17.0.1', '169.254.3.3'):
            self.assertNotIn(hidden, result.stdout)
        self.assertIn(f'Konfiguration: {self.config.parent}', result.stdout)
        self.assertIn(f'Veranstaltungsdaten: {self.config.parent / "data"}', result.stdout)
        self.assertNotIn('auth.yml', result.stdout)

    def test_stopped_service_is_not_an_error(self):
        self.service('inactive', 'disabled')
        result = self.status()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('Dienst:        gestoppt (Autostart aus)', result.stdout)
        self.assertIn('Weboberfläche: nicht erreichbar', result.stdout)

    def test_active_service_without_web_answer_is_an_error(self):
        result = self.status()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('Dienst:        läuft', result.stdout)
        self.assertIn('Weboberfläche: nicht erreichbar', result.stdout)
        self.assertIn(f'Hinweis: http://127.0.0.1:{self.port}/', result.stdout)

    def test_failed_service_is_an_error(self):
        self.service('failed', 'enabled')
        result = self.status()
        self.assertEqual(result.returncode, 1)
        self.assertIn('fehlgeschlagen (Autostart an)', result.stdout)
        self.assertIn('journalctl -u livescore.service', result.stdout)

    def test_loopback_binding_shows_no_lan_urls(self):
        self.write_config('127.0.0.1', self.port)
        self.serve()
        result = self.status()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f'  http://127.0.0.1:{self.port}/\n  (nur lokal erreichbar (bind_host 127.0.0.1))', result.stdout)
        self.assertNotIn('10.0.0.5', result.stdout)

    def test_running_older_version_needs_restart(self):
        self.serve(version='0.0.1')
        self.assertIn('erreichbar – läuft noch 0.0.1, Neustart nötig', self.status().stdout)

    def test_invalid_configuration(self):
        self.config.write_text('bind_host: 0.0.0.0\nport: kein-port\n')
        result = self.status()
        self.assertEqual(result.returncode, 2)
        self.assertIn('Konfiguration ungültig', result.stdout)

    @unittest.skipIf(os.geteuid() == 0, 'root liest jede Datei')
    def test_unreadable_configuration_uses_defaults_without_error(self):
        self.config.chmod(0)
        self.addCleanup(self.config.chmod, 0o644)
        result = self.status()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('ohne Leserecht; Standardwerte angenommen (Port 8730)', result.stdout)
        self.assertIn('  http://10.0.0.5:8730/', result.stdout)
        self.assertIn('Veranstaltungsdaten: /var/lib/livescore/data', result.stdout)

    def test_missing_installation(self):
        (self.runtime / 'installation.json').unlink()
        result = self.status()
        self.assertEqual(result.returncode, 1)
        self.assertIn('Keine Installation gefunden', result.stdout)

    def test_missing_unit(self):
        self.service('inactive', '', load='not-found')
        result = self.status()
        self.assertEqual(result.returncode, 1)
        self.assertIn('Dienst:        nicht eingerichtet', result.stdout)

    def test_status_writes_nothing(self):
        before = sorted(p for p in self.root.rglob('*') if '.venv' not in p.parts)
        self.serve()
        self.assertEqual(self.status().returncode, 0)
        self.assertEqual(sorted(p for p in self.root.rglob('*') if '.venv' not in p.parts), before)

    def test_unknown_argument(self):
        env = {**os.environ, 'PATH': f'{self.bin}:{os.environ["PATH"]}'}
        result = subprocess.run([str(self.runtime / 'bin/livescore'), '--status', '--extra'], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
