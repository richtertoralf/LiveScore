import json
from pathlib import Path
import re
import subprocess
import shutil
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient
from livescore import __version__
from livescore.app import create_app
from livescore.auth import AuthConfig

ROOT = Path(__file__).resolve().parents[1]


class VersionTest(unittest.TestCase):
    def test_public_version_endpoint_and_protected_post(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.test-artifacts') as temp:
            root = Path(temp)
            with TestClient(create_app(data_dir=root / 'data', auth_config=AuthConfig(file=root / 'auth.yml'))) as client:
                response = client.get('/api/version')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'version': __version__})
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertEqual(client.post('/api/version').status_code, 401)

    def test_cli_and_python_use_changed_central_version(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.test-artifacts') as temp:
            root = Path(temp)
            shutil.copytree(ROOT / 'livescore', root / 'livescore', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(ROOT / 'bin', root / 'bin')
            (root / 'VERSION').write_text('9.8.7\n')
            result = subprocess.run([str(root / 'bin/livescore'), '--version'], cwd=root,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, 'LiveScore 9.8.7 (commit unbekannt)\n')
            result = subprocess.run([sys.executable, '-m', 'livescore', '--version'], cwd=root,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, 'LiveScore 9.8.7\n')
            (root / 'installation.json').write_text(json.dumps({
                'commit': '0123456789abcdef0123456789abcdef01234567', 'branch': 'main', 'dirty': False,
                'source': 'github main', 'installed_at': '2026-10-31T12:00:00+0100'}))
            result = subprocess.run([str(root / 'bin/livescore'), '--version'], cwd=root,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, 'LiveScore 9.8.7 (commit 0123456, branch main, '
                                            'github main 2026-10-31T12:00:00+0100)\n')

    def test_release_version(self):
        self.assertEqual((ROOT / 'VERSION').read_text(encoding='utf-8'), '0.2.3\n')
        self.assertEqual(__version__, '0.2.3')

    def test_readme_badge_matches_version_file(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertEqual(re.findall(r'img\.shields\.io/badge/version-([0-9.]+)-', readme), [__version__])

    def test_version_exits_without_loading_server_config(self):
        result = subprocess.run(
            [sys.executable, '-m', 'livescore', '--config',
             str(ROOT / '.test-artifacts' / 'nonexistent-version-config.yml'), '--version'],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'LiveScore {__version__}\n')
