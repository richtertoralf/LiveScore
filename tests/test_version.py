from pathlib import Path
import subprocess
import sys
import unittest

from livescore import __version__

ROOT = Path(__file__).resolve().parents[1]


class VersionTest(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual((ROOT / 'VERSION').read_text(encoding='utf-8'), '0.1.0\n')
        self.assertEqual(__version__, '0.1.0')

    def test_version_exits_without_loading_server_config(self):
        result = subprocess.run(
            [sys.executable, '-m', 'livescore', '--config',
             str(ROOT / '.test-artifacts' / 'nonexistent-version-config.yml'), '--version'],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'LiveScore 0.1.0\n')
