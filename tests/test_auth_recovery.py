"""Auth-only recovery transactions, concurrency, revocation and safe CLI dispatch."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import yaml

from livescore.auth import (Auth, AuthConfig, PasswordChange, credentials_lock,
                            hash_password, load_credentials, update_password, verify_password)
from livescore.config import load_config
from livescore.recovery import reset_admin_password, reload_running_service
from livescore.storage import atomic_write

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'New recovery password 2026!'
OPERATOR_PASSWORD = 'New operator password 2026!'


class RecoveryTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = {name:dict(role=name,password_hash=hash_password(name),default_password=True)
                        for name in ('admin','operator')}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root/'auth.yml'
        self.path.write_text(yaml.safe_dump(dict(users=self.original)))
        self.config_file=self.root/'server.yml'
        self.config_file.write_text('bind_host: 127.0.0.1\nport: 18730\ndata_dir: data\nauth:\n  file: auth.yml\n')
        self.config=load_config(self.config_file)
        self.auth=Auth(self.config.auth)
        self.admin=self.auth.new_session('admin')
        self.operator=self.auth.new_session('operator')

    async def test_recovery_and_reload_only_revoke_changed_account(self):
        operator=self.auth.credentials.users['operator'].model_dump()
        original_session=self.auth.session(self.operator)
        update_password(self.path,'admin',hash_password(PASSWORD))
        self.assertTrue(await self.auth.reload())
        self.assertIsNone(self.auth.session(self.admin))
        self.assertIs(self.auth.session(self.operator),original_session)
        self.assertEqual(self.auth.credentials.users['operator'].model_dump(),operator)
        self.assertFalse(self.auth.credentials.users['admin'].default_password)
        self.assertEqual((await self.auth.login('admin','admin'))[0],'invalid')
        result,sid=await self.auth.login('admin',PASSWORD)
        self.assertEqual(result,'ok')
        self.assertTrue(await self.auth.reload())
        self.assertIsNotNone(self.auth.session(sid)) # unchanged reload is not a logout

    async def test_bad_or_missing_file_preserves_credentials_sessions_and_logs_no_hash(self):
        credentials=self.auth.credentials
        sessions=dict(self.auth.sessions)
        for content in ('broken: [',yaml.safe_dump({'users':{'admin':self.original['admin']}}),
                        yaml.safe_dump({'users':{**self.original,'operator':dict(role='operator',password_hash='secret-invalid-hash')}})):
            self.path.write_text(content)
            with self.assertLogs(level='ERROR') as messages:
                self.assertFalse(await self.auth.reload())
            self.assertNotIn('secret-invalid-hash',' '.join(messages.output))
            self.assertNotIn(self.original['admin']['password_hash'],' '.join(messages.output))
            self.assertIs(self.auth.credentials,credentials)
            self.assertEqual(self.auth.sessions,sessions)
            self.assertEqual(self.path.read_text(),content)
        self.path.unlink()
        self.assertFalse(await self.auth.reload())
        self.assertIs(self.auth.credentials,credentials)
        self.assertFalse(self.path.exists())

    async def test_os_lock_wait_does_not_block_event_loop(self):
        entered=threading.Event();release=threading.Event()
        def writer():
            with credentials_lock(self.path):
                entered.set();release.wait(5)
        task=asyncio.create_task(asyncio.to_thread(writer))
        await asyncio.to_thread(entered.wait,5)
        reload=asyncio.create_task(self.auth.reload())
        try:
            await asyncio.sleep(.05)
            self.assertFalse(reload.done())
            self.assertIsNotNone(self.auth.session(self.operator))
        finally: release.set()
        await task
        self.assertTrue(await reload)

    async def test_parallel_web_operator_change_then_cli_admin_preserves_both(self):
        encoded=hash_password(PASSWORD)
        # Recover from default admin first so the web change is authorized.
        update_password(self.path,'admin',encoded)
        await self.auth.reload()
        self.admin=self.auth.new_session('admin')
        original_update=update_password
        started=threading.Event();recovered=threading.Event()
        next_password=hash_password('Another admin recovery password!')
        def recovery():
            started.wait(5)
            try: original_update(self.path,'admin',next_password)
            finally: recovered.set()
        def web_transaction(*args):
            result=original_update(*args)
            started.set()
            self.assertTrue(recovered.wait(5))
            return result
        cli=asyncio.create_task(asyncio.to_thread(recovery))
        with patch('livescore.auth.update_password',side_effect=web_transaction):
            failure=await self.auth.change_password(self.auth.session(self.admin),PasswordChange(
                username='operator',password=OPERATOR_PASSWORD,repeat=OPERATOR_PASSWORD))
        await cli
        self.assertIsNone(failure)
        await self.auth.reload()
        credentials=load_credentials(self.path)
        self.assertEqual(credentials.users['admin'].password_hash,next_password)
        self.assertTrue(verify_password(OPERATOR_PASSWORD,credentials.users['operator'].password_hash))
        self.assertIsNone(self.auth.session(self.admin))

    async def test_stale_web_request_cannot_overwrite_recovery_before_signal_arrives(self):
        update_password(self.path,'admin',hash_password(PASSWORD))
        await self.auth.reload()
        sid=self.auth.new_session('admin')
        encoded=hash_password('Second recovered admin password!')
        update_password(self.path,'admin',encoded) # RAM deliberately has not reloaded yet
        before=self.path.read_bytes()
        result=await self.auth.change_password(self.auth.session(sid),PasswordChange(
            username='admin',password=OPERATOR_PASSWORD,repeat=OPERATOR_PASSWORD))
        self.assertEqual(result,'auth_required')
        self.assertEqual(self.path.read_bytes(),before)
        self.assertIsNone(self.auth.session(sid))
        self.assertIsNotNone(self.auth.session(self.operator))

    async def test_parallel_cli_writers_serialize_and_preserve_operator(self):
        hashes=[hash_password(PASSWORD),hash_password('Second recovery password!')]
        def write(encoded):return update_password(self.path,'admin',encoded)
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(write,hashes))
        final=load_credentials(self.path)
        self.assertIn(final.users['admin'].password_hash,hashes)
        self.assertEqual(final.users['operator'].model_dump(),self.original['operator'])

    async def test_cli_getpass_confirmation_and_failure_leave_file_intact(self):
        before=self.path.read_bytes()
        for values in ([PASSWORD,'does not match'],['short','short']):
            with patch('livescore.recovery.getpass.getpass',side_effect=values),patch('livescore.recovery.reload_running_service') as reload:
                self.assertEqual(reset_admin_password(self.config_file,self.config),1)
                reload.assert_not_called()
            self.assertEqual(self.path.read_bytes(),before)
        with patch('livescore.recovery.getpass.getpass',side_effect=[PASSWORD,PASSWORD]),patch('livescore.recovery.reload_running_service',return_value=True) as reload:
            self.assertEqual(reset_admin_password(self.config_file,self.config),0)
            reload.assert_called_once_with(self.config_file)
        self.assertTrue(verify_password(PASSWORD,load_credentials(self.path).users['admin'].password_hash))
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        with patch('livescore.recovery.getpass.getpass',side_effect=[PASSWORD,PASSWORD]),patch('livescore.auth.atomic_write',side_effect=OSError('disk full')):
            before=self.path.read_bytes()
            self.assertEqual(reset_admin_password(self.config_file,self.config),1)
            self.assertEqual(self.path.read_bytes(),before)

    async def test_no_service_does_not_start_anything_and_extra_cli_password_is_rejected(self):
        with patch('livescore.recovery.shutil.which',return_value='/bin/systemctl'),patch('livescore.recovery.subprocess.run',return_value=subprocess.CompletedProcess([],0,'LoadState=not-found\n','')) as run,contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(reload_running_service(self.config_file))
            self.assertIn('standalone',output.getvalue())
            self.assertEqual(run.call_count,1)
            self.assertEqual(run.call_args.args[0][1],'show')
        before=self.path.read_bytes()
        result=subprocess.run([str(ROOT/'bin/livescore'),'--config',str(self.config_file),
            '--reset-admin-password','not-an-allowed-argument'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('New admin password:',result.stderr)
        self.assertNotIn('not-an-allowed-argument',result.stderr)
        self.assertEqual(self.path.read_bytes(),before)

    async def test_service_without_handler_or_with_restart_reload_is_never_signalled(self):
        info='LoadState=loaded\nActiveState=active\nMainPID=123\nFragmentPath=/test/livescore.service\nExecReload={ path=/bin/kill ; argv[]=/bin/kill -HUP $MAINPID ; }\n'
        argv=b'python\0-m\0livescore\0--config\0'+str(self.config_file).encode()+b'\0'
        for reported,caught in ((info,'0'),(info.replace('/bin/kill -HUP $MAINPID','/bin/systemctl restart livescore'),'1')):
            def read(path,*args,**kwargs):
                return '# Managed by the LiveScore installer;' if str(path).endswith('.service') else 'SigCgt:\t'+caught+'\n'
            with patch('livescore.recovery.shutil.which',return_value='/bin/systemctl'),patch('livescore.recovery.subprocess.run',return_value=subprocess.CompletedProcess([],0,reported,'')) as run,patch.object(Path,'read_bytes',return_value=argv),patch.object(Path,'read_text',autospec=True,side_effect=read):
                self.assertFalse(reload_running_service(self.config_file))
                self.assertEqual(run.call_count,1)

    async def test_cancelled_web_write_finishes_transaction_and_revokes_affected_sessions(self):
        entered=threading.Event();release=threading.Event()
        original=update_password
        def held(*args):
            entered.set();release.wait(5)
            return original(*args)
        with patch('livescore.auth.update_password',side_effect=held):
            task=asyncio.create_task(self.auth.change_password(self.auth.session(self.admin),PasswordChange(
                username='admin',password=PASSWORD,repeat=PASSWORD)))
            self.assertTrue(await asyncio.to_thread(entered.wait,5))
            task.cancel()
            await asyncio.sleep(.03)
            self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(verify_password(PASSWORD,load_credentials(self.path).users['admin'].password_hash))
        self.assertIsNone(self.auth.session(self.admin))
        self.assertIsNotNone(self.auth.session(self.operator))

    async def test_atomic_auth_write_preserves_service_owner_when_called_as_root(self):
        owner=self.path.stat()
        with patch('livescore.storage.os.fstat') as current,patch('livescore.storage.os.fchown') as chown:
            current.return_value.st_uid=owner.st_uid+1
            current.return_value.st_gid=owner.st_gid+1
            atomic_write(self.path,'test',preserve_owner=True)
            self.assertEqual(chown.call_args.args[1:],(owner.st_uid,owner.st_gid))
