"""Real staged lifecycle with shared test venv; no systemd or host writes."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from livescore.app import create_app
from livescore.auth import Auth, PasswordChange, verify_password
from livescore.bootstrap import inspect_config, seed_if_empty
from livescore.config import load_config
from livescore.storage import load, save, FileLease
from tools.deploy import Deployment, MARKER, RUNTIME, FILES, atomic_text

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.test-artifacts'


class DeploymentTest(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.deployment = Deployment(self.root)
        self.addCleanup(patch.stopall)
        # Network/venv creation is separately exercised by the full staged smoke.
        # Everything after build (validation, seed, swap, backup, rollback) is real.
        patch.object(self.deployment, 'build', side_effect=self.build).start()

    def build(self, source):
        d = self.deployment
        d.mark(d.prefix)
        (d.prefix / 'releases').mkdir(exist_ok=True)
        target = Path(tempfile.mkdtemp(dir=d.prefix / 'releases'))
        for name in RUNTIME:
            shutil.copytree(ROOT / name, target / name, ignore=shutil.ignore_patterns('__pycache__'))
        for name in FILES:
            shutil.copy2(ROOT / name, target / name)
        (target / '.venv').symlink_to(ROOT / '.venv', target_is_directory=True)
        (target / 'installation.json').write_text(json.dumps(dict(config=str(d.config_file),staging_root=str(self.root))))
        return target

    def install(self):
        self.deployment.preflight()
        with self.deployment.lock():
            self.deployment.deploy(ROOT)
        return load_config(self.deployment.config_file)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for folder in (self.deployment.config, self.deployment.state / 'data')
                for p in folder.rglob('*') if p.is_file() and not p.name.endswith('.lock')}

    def test_fresh_seed_wrapper_and_server(self):
        config = self.install()
        expected = load(ROOT / 'imports/prague-2026.json')
        self.assertEqual(load(config.data_dir / 'events/prague-2026.json'), expected)
        self.assertEqual((len(expected.matches), len(expected.participants), len(expected.referees)), (14,6,6))
        result = subprocess.run([self.deployment.cli,'--version'], capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout, 'LiveScore 0.1.0\n')
        with TestClient(create_app(data_dir=config.data_dir,auth_config=config.auth)) as client:
            self.assertEqual(client.get('/api/version').json(), {'version':'0.1.0'})
            self.assertEqual(client.get('/api/v1/live').status_code,200)
            catalog = client.app.state.service
            self.assertEqual(catalog.selection.active_event_id,'prague-2026')
            self.assertEqual(len(catalog.state.matches),14)
            for name in ('admin','operator'):
                self.assertTrue(verify_password(name,client.app.state.auth.credentials.users[name].password_hash))
        self.assertTrue(config.auth.file.exists())

    def test_upgrade_preserves_config_passwords_active_event_and_scores(self):
        config = self.install()
        auth = Auth(config.auth)
        session = auth.session(auth.new_session('admin'))
        password = 'Changed deployment password!'
        self.assertIsNone(asyncio.run(auth.change_password(session,PasswordChange(
            username='admin',password=password,repeat=password))))
        state = load(config.data_dir / 'events/prague-2026.json')
        state.event.name = 'Edited tournament'
        # A second active event demonstrates that upgrades never reselect Prague.
        save(config.data_dir / 'events/other.json',state)
        selection = config.data_dir / 'active-event.json'
        data = json.loads(selection.read_text()); data['active_event_id']='other'
        selection.write_text(json.dumps(data))
        self.deployment.config_file.write_text(self.deployment.config_file.read_text().replace('8730','18730'))
        before = self.snapshot()
        old = self.deployment.current.resolve()
        with self.deployment.lock():
            self.deployment.deploy(ROOT,upgrade=True)
        self.assertNotEqual(self.deployment.current.resolve(),old)
        self.assertTrue(old.exists())
        self.assertEqual(self.snapshot(),before)
        auth = Auth(config.auth)
        self.assertTrue(verify_password(password,auth.credentials.users['admin'].password_hash))
        self.assertFalse(verify_password('admin',auth.credentials.users['admin'].password_hash))
        self.assertEqual(json.loads(selection.read_text())['active_event_id'],'other')
        self.assertEqual(len(list((self.deployment.state / 'backups').iterdir())),1)

    def test_reinstall_refuses_and_uninstall_retains_then_reinstall_preserves(self):
        config = self.install()
        Auth(config.auth)
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError,'Bereits installiert'):
            self.deployment.deploy(ROOT)
        self.deployment.uninstall()
        self.assertEqual(self.snapshot(),before)
        self.assertFalse(self.deployment.cli.exists())
        self.assertFalse(self.deployment.prefix.exists())
        self.install()
        self.assertEqual(self.snapshot(),before)
        self.deployment.uninstall(purge=True)
        self.assertFalse(self.deployment.config.exists())
        self.assertFalse(self.deployment.state.exists())

    def test_failure_after_swap_restores_code_unit_and_data(self):
        config=self.install(); Auth(config.auth)
        before=self.snapshot(); old=self.deployment.current.resolve()
        unit=self.deployment.unit.read_bytes()
        with patch.object(self.deployment,'health',side_effect=RuntimeError('simulated start failure')):
            with self.assertRaisesRegex(RuntimeError,'simulated'):
                self.deployment.deploy(ROOT,upgrade=True)
        self.assertEqual(self.deployment.current.resolve(),old)
        self.assertEqual(self.deployment.unit.read_bytes(),unit)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(len(list((self.deployment.prefix / 'releases').iterdir())),1)

    def test_build_failure_does_not_touch_runtime(self):
        self.install(); old=self.deployment.current.resolve(); before=self.snapshot()
        with patch.object(self.deployment,'build',side_effect=RuntimeError('dependency failure')):
            with self.assertRaises(RuntimeError): self.deployment.deploy(ROOT,upgrade=True)
        self.assertEqual(self.deployment.current.resolve(),old)
        self.assertEqual(self.snapshot(),before)

    def test_invalid_auth_upgrade_aborts_without_replacing_it(self):
        config=self.install(); config.auth.file.write_text('invalid: config')
        old=self.deployment.current.resolve(); before=self.snapshot()
        with self.assertRaises(subprocess.CalledProcessError): self.deployment.deploy(ROOT,upgrade=True)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.deployment.current.resolve(),old)

    def test_missing_auth_upgrade_never_generates_initial_passwords(self):
        config=self.install()
        self.assertFalse(config.auth.file.exists())
        old=self.deployment.current.resolve()
        with self.assertRaisesRegex(RuntimeError,'Auth-Datei fehlt'):
            self.deployment.deploy(ROOT,upgrade=True)
        self.assertFalse(config.auth.file.exists())
        self.assertEqual(self.deployment.current.resolve(),old)

    def test_service_stop_restart_and_rollback_sequence(self):
        config=self.install(); Auth(config.auth)
        old=self.deployment.current.resolve()
        calls=[]
        def control(*args):
            calls.append(args)
            if args[0]=='restart':raise RuntimeError('restart failed')
        with patch.object(self.deployment,'active',return_value=True), patch.object(self.deployment,'systemctl',side_effect=control):
            with self.assertRaisesRegex(RuntimeError,'restart failed'):
                self.deployment.deploy(ROOT,upgrade=True)
        self.assertEqual(calls,[('stop','livescore.service'),('daemon-reload',),('restart','livescore.service'),
                                ('stop','livescore.service'),('daemon-reload',),('start','livescore.service')])
        self.assertEqual(self.deployment.current.resolve(),old)

    def test_failed_service_control_during_rollback_still_restores_code(self):
        config=self.install(); Auth(config.auth)
        old=self.deployment.current.resolve()
        def control(*args):
            if args[0] in ('restart','stop'): raise RuntimeError('service control unavailable')
        with patch.object(self.deployment,'systemctl',side_effect=control):
            with self.assertRaisesRegex(RuntimeError,'service control unavailable'):
                self.deployment.deploy(ROOT,upgrade=True)
        self.assertEqual(self.deployment.current.resolve(),old)

    def test_foreign_paths_and_symlinks_refused(self):
        d=self.deployment
        d.config.mkdir(parents=True); (d.config/'foreign.yml').write_text('keep')
        with self.assertRaises(RuntimeError): d.preflight()
        shutil.rmtree(d.config); d.config.symlink_to(ROOT/'config',target_is_directory=True)
        with self.assertRaises(RuntimeError): d.preflight()

    def test_deploy_lock(self):
        with self.deployment.lock():
            with self.assertRaises(RuntimeError):
                with Deployment(self.root).lock(): pass


class SeedTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config=self.root/'server.yml'
        self.config.write_text('bind_host: 127.0.0.1\nport: 8730\ndata_dir: data\n')
        self.data=self.root/'data'
        self.seed=ROOT/'imports/prague-2026.json'

    def test_seed_only_when_no_state_exists_including_legacy_or_empty_catalog(self):
        for name,content in [('tournament.json',self.seed.read_text()),('active-event.json','{"active_event_id":null}'),('unknown.txt','keep')]:
            with self.subTest(name=name):
                self.data.mkdir(exist_ok=True)
                (self.data/name).write_text(content)
                self.assertFalse(seed_if_empty(self.config,self.seed))
                self.assertEqual((self.data/name).read_text(),content)
                shutil.rmtree(self.data)
        self.data.mkdir(); (self.data/'tournament.json.lock').touch()
        self.assertTrue(seed_if_empty(self.config,self.seed))
        self.assertFalse(seed_if_empty(self.config,self.seed))

    def test_seed_failure_cleans_its_partial_write_and_lock_excludes_server(self):
        with patch('livescore.bootstrap.save_selection',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): seed_if_empty(self.config,self.seed)
        self.assertFalse((self.data/'events/prague-2026.json').exists())
        lease=FileLease(self.data/'active-event.json');lease.acquire()
        try:
            with self.assertRaises(RuntimeError): seed_if_empty(self.config,self.seed)
        finally: lease.release()
        self.assertTrue(seed_if_empty(self.config,self.seed))
