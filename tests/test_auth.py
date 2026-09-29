"""Zugriffsschutz mit echten scrypt-Hashes und isolierter lokaler Auth-Datei."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import yaml

from livescore.app import create_app
from livescore.auth import AuthConfig, COOKIE, hash_password, verify_password
from livescore.storage import load, save

ROOT = Path(__file__).resolve().parents[1]
NEW_PASSWORD = 'A new local password 2026!'


class AuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = dict(users={name:dict(role=name,password_hash=hash_password(name),default_password=True) for name in ('admin','operator')})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts')
        self.root = Path(self.temp.name)
        self.auth_path = self.root/'auth.yml'
        self.auth_path.write_text(yaml.safe_dump(self.initial))
        save(self.root/'data/events/prague.json',load(ROOT/'imports/prague-2026.json'))
        (self.root/'data/active-event.json').write_text(json.dumps(dict(active_event_id='prague',selection_token=str(uuid4()))))
        self.restart()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda:self.client.__exit__(None,None,None))

    def restart(self):
        if hasattr(self,'client'): self.client.__exit__(None,None,None)
        self.app = create_app(data_dir=self.root/'data',auth_config=AuthConfig(file=self.auth_path))
        self.client = TestClient(self.app).__enter__()

    def login(self, name='admin', password=None, client=None, status=200):
        client = client or self.client
        client.cookies.clear()
        csrf = client.get('/api/auth/session').json()['csrf_token']
        response = client.post('/login',json=dict(username=name,password=password or name),headers={'X-CSRF-Token':csrf})
        self.assertEqual(response.status_code,status,response.text)
        return response

    def headers(self, client=None):
        return {'X-CSRF-Token':(client or self.client).get('/api/auth/session').json()['csrf_token']}

    def change(self, user='admin', password=NEW_PASSWORD, client=None, status=200):
        client = client or self.client
        response = client.post('/api/auth/password',json=dict(username=user,password=password,repeat=password),headers=self.headers(client))
        self.assertEqual(response.status_code,status,response.text)
        return response

    def admin(self):
        self.login(); self.change(); self.login(password=NEW_PASSWORD)

    def action(self, operation, **fields):
        state = self.client.get('/api/v1/tournament').json()
        body = dict(request_id=str(uuid4()),expected_revision=state['revision'],event_id=state['active_event_id'],selection_token=state['selection_token'],match_id='match-001',**fields)
        response = self.client.post('/api/v1/live/'+operation,json=body,headers=self.headers())
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_first_start_creates_only_two_hashed_users(self):
        self.client.__exit__(None,None,None)
        del self.client
        self.auth_path.unlink()
        self.restart()
        data = yaml.safe_load(self.auth_path.read_text())
        self.assertEqual(set(data['users']),{'admin','operator'})
        for name, user in data['users'].items():
            self.assertTrue(user['default_password'])
            self.assertTrue(verify_password(name,user['password_hash']))
            self.assertNotEqual(user['password_hash'],name)
            self.assertNotIn('password',user)
        self.assertEqual(self.auth_path.stat().st_mode & 0o777,0o600)

    def test_all_initial_logins_and_cookie_flags(self):
        for name in ('admin','operator'):
            self.client.cookies.clear()
            result = self.login(name)
            self.assertEqual(result.json()['redirect'],'/users' if name=='admin' else '/')
            session = self.client.get('/api/auth/session').json()
            self.assertEqual(session['role'],name)
            self.assertEqual(session['must_change_password'],name=='admin')
            cookie = result.headers['set-cookie']
            self.assertIn('HttpOnly',cookie); self.assertIn('SameSite=lax',cookie); self.assertIn('Max-Age=43200',cookie)

    def test_wrong_password_unknown_user_generic_no_echo(self):
        a = self.login(password='wrong secret',status=401)
        b = self.login('unknown',password='wrong secret',status=401)
        self.assertEqual(a.json(),b.json())
        self.assertNotIn('wrong secret',a.text)
        response = self.client.post('/login',json=dict(username='admin',password='z'*1025),headers=self.headers())
        self.assertEqual(response.status_code,422)
        self.assertNotIn('zzzz',response.text)

    def test_anonymous_ui_api_and_docs(self):
        for path in ('/','/events','/config','/users','/docs','/openapi.json','/static/index.html'):
            response = self.client.get(path,follow_redirects=False)
            self.assertEqual(response.status_code,303,path)
            self.assertEqual(response.headers['location'],'/login')
        self.assertEqual(self.client.get('/login').status_code,200)
        self.assertEqual(self.client.get('/static/i18n.js').status_code,200)
        self.assertEqual(self.client.get('/api/v1/tournament').status_code,401)
        self.assertEqual(self.client.post('/api/v1/live/start',json={}).status_code,401)

    def test_admin_forced_change_and_old_password_invalid(self):
        self.login()
        self.assertEqual(self.client.get('/',follow_redirects=False).headers['location'],'/users')
        self.assertEqual(self.client.get('/api/v1/tournament').status_code,403)
        self.assertEqual(self.client.post('/api/v1/config/event',json={},headers=self.headers()).status_code,403)
        self.change('operator',status=403)
        self.change()
        self.assertEqual(self.client.get('/api/v1/tournament').status_code,401)
        self.login(password='admin',status=401)
        self.login(password=NEW_PASSWORD)
        self.assertFalse(self.client.get('/api/auth/session').json()['must_change_password'])
        self.assertEqual(self.client.get('/config').status_code,200)
        self.assertEqual(self.client.get('/docs').status_code,200)
        self.assertEqual(self.client.get('/openapi.json').status_code,200)

    def test_password_resets_revoke_sessions_and_persist(self):
        self.admin()
        other = TestClient(self.app)
        self.login('operator',client=other)
        sid = other.cookies.get(COOKIE)
        self.change('operator')
        self.assertNotIn(sid,self.app.state.auth.sessions)
        self.assertEqual(other.get('/api/v1/tournament').status_code,401)
        self.login('operator',client=other,status=401)
        self.login('operator',password=NEW_PASSWORD,client=other)
        self.assertEqual(self.client.get('/api/auth/session').json()['defaults'],[])
        stored = self.auth_path.read_bytes()
        self.restart()
        self.assertEqual(self.auth_path.read_bytes(),stored)
        self.login('admin',password=NEW_PASSWORD)
        for user in self.client.get('/api/auth/users').json()['users']:
            self.assertFalse(user['default_password']); self.assertNotIn('password_hash',user)
        self.login('operator',password=NEW_PASSWORD)
        other.close()

    def test_password_mismatch_and_invalid_input_dont_change_file(self):
        self.admin(); before=self.auth_path.read_bytes()
        for password,repeat in [('short','short'),(NEW_PASSWORD,'different password'),('admin','admin')]:
            response=self.client.post('/api/auth/password',json=dict(username='operator',password=password,repeat=repeat),headers=self.headers())
            self.assertEqual(response.status_code,422)
        self.assertEqual(self.auth_path.read_bytes(),before)

    def business_request(self, path, **fields):
        state=self.client.get('/api/v1/tournament').json()
        body=dict(request_id=str(uuid4()), **fields)
        if path.startswith('event-catalog/'):
            body['catalog_session']=state['stream_id']
        else:
            body.update(expected_revision=state['revision'],event_id=state['active_event_id'],selection_token=state['selection_token'])
        response=self.client.post('/api/v1/'+path,json=body,headers=self.headers())
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_both_roles_have_full_event_and_live_permissions(self):
        for role in ('operator','admin'):
            with self.subTest(role=role):
                if role=='admin': self.admin()
                else: self.login(role)
                for path in ('/','/events','/config','/api/v1/tournament','/api/v1/matches'):
                    self.assertEqual(self.client.get(path).status_code,200,path)
                created=self.business_request('event-catalog/create',event=dict(name=role+' cup',date_from='2026-10-03',date_to='2026-10-04'))['created_event_id']
                state=self.client.get('/api/v1/tournament').json()
                self.business_request('event-catalog/select',event_id=created,selection_token=state['selection_token'])
                # Import a fresh event for each role, then exercise all editing paths.
                raw=(ROOT/'imports/prague-2026.json').read_text()
                preview=self.client.post('/api/v1/event-catalog/import/preview',json=dict(json_text=raw,event_id=role+'-prague'),headers=self.headers())
                self.assertEqual(preview.status_code,200)
                preview=preview.json()
                imported=self.business_request('event-catalog/import',json_text=raw,event_id=preview['event_id'],preview_token=preview['preview_token'])['created_event_id']
                state=self.client.get('/api/v1/tournament').json()
                self.business_request('event-catalog/select',event_id=imported,selection_token=state['selection_token'])
                state=self.client.get('/api/v1/tournament').json()
                event=state['event'];event['name']='Corrected name';event['location']='Corrected place'
                event['sport_profile']['ruleset']='Configured rules'
                self.business_request('config/event',data=event)
                self.business_request('config/participants',data=dict(id='bsc-praha',name='Corrected participant'))
                self.business_request('config/participants',data=dict(id='extra',name='Extra participant'))
                self.business_request('config/referees',data=dict(id=state['referees'][0]['id'],name='Corrected referee'))
                self.business_request('config/referees',data=dict(id='extra-ref',name='Extra referee'))
                self.business_request('config/matches',data=dict(id='match-001',date='2026-10-03',time='09:30',play_area_id='field-1',participant_1='bsc-praha',participant_2='fc-ingolstadt-04',round='Corrected round'))
                self.business_request('config/matches',data=dict(id='extra-match',date='2026-10-03',time='18:00',play_area_id='field-1'))
                self.action('select')
                self.action('prepare',participant_1='bsc-praha',participant_2='fc-ingolstadt-04',side_l='bsc-praha',side_r='fc-ingolstadt-04')
                self.action('start')
                state=self.client.get('/api/v1/tournament').json();match=state['matches'][0]
                body=dict(request_id=str(uuid4()),event_id=imported,selection_token=state['selection_token'],match_id=match['id'],control_revision=match['control_revision'],participant_id='bsc-praha',delta=1)
                self.assertEqual(self.client.post('/api/v1/live/score',json=dict(**body,side='L'),headers=self.headers()).status_code,200)
                body['request_id']=str(uuid4())
                self.assertEqual(self.client.post('/api/v1/live/counter',json=dict(**body,counter_id='team_fouls',period=1),headers=self.headers()).status_code,200)
                self.action('switch-sides');self.action('pause');self.action('period',period=2);self.action('resume');self.action('finish')
                exported=self.client.get('/api/v1/event-catalog/'+imported+'/export')
                self.assertEqual(exported.status_code,200)
                self.assertEqual(exported.json()['event']['name'],'Corrected name')
                self.assertEqual(exported.json()['matches'][0]['scores']['bsc-praha'],1)
                if role=='operator':
                    for path in ('/users','/api/auth/users','/docs','/openapi.json','/static/users.html'):
                        self.assertEqual(self.client.get(path).status_code,403,path)
                    self.change('admin',status=403);self.change('operator',status=403)
                else:
                    self.assertEqual(self.client.get('/users').status_code,200)
                    self.change('operator')

    def test_csrf_login_logout_and_mutations(self):
        self.assertEqual(self.client.post('/login',json=dict(username='admin',password='admin')).status_code,403)
        self.login('operator')
        for headers in ({},{'X-CSRF-Token':'invalid'},{**self.headers(),'Origin':'https://evil.example'}):
            self.assertEqual(self.client.post('/logout',headers=headers).status_code,403)
            self.assertEqual(self.client.post('/api/v1/live/start',json={},headers=headers).status_code,403)
        self.assertEqual(self.client.post('/logout',headers=self.headers()).status_code,200)
        self.assertEqual(self.client.get('/api/v1/tournament').status_code,401)

    def test_restart_and_expiration_end_sessions(self):
        self.login('operator'); cookie=self.client.cookies.get(COOKIE)
        self.restart(); self.client.cookies.set(COOKIE,cookie)
        self.assertEqual(self.client.get('/api/v1/tournament').status_code,401)
        self.client.cookies.clear(); self.login('operator')
        session=self.app.state.auth.session(self.client.cookies.get(COOKIE)); session.expires=time.monotonic()-1
        self.assertEqual(self.client.get('/api/v1/tournament').status_code,401)

    def test_only_live_get_is_public(self):
        response=self.client.get('/api/v1/live')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['status'],'idle')
        self.assertNotIn('set-cookie',response.headers)
        for path in ('/api/v1/tournament','/api/v1/matches','/api/v1/events','/api/v1/event-catalog','/api/auth/users'):
            self.assertEqual(self.client.get(path).status_code,401,path)
        for path in ('/api/v1/live','/api/v1/live/start','/api/v1/config/event','/api/v1/event-catalog/create','/api/v1/event-catalog/import/preview','/api/auth/password'):
            self.assertEqual(self.client.post(path,json={}).status_code,401,path)
        self.login('operator');self.action('select')
        self.action('prepare',participant_1='bsc-praha',participant_2='fc-ingolstadt-04',side_l='bsc-praha',side_r='fc-ingolstadt-04')
        self.action('start')
        expected=self.client.get('/api/v1/live').json()
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/v1/live').json(),expected)
        self.assertEqual(expected['status'],'live')

    def test_existing_file_reduction_preserves_supported_accounts(self):
        self.client.__exit__(None,None,None);del self.client
        original=yaml.safe_load(self.auth_path.read_text())
        extended=json.loads(json.dumps(original))
        extended['users']['obsolete-account']=dict(role='obsolete',password_hash='discarded',default_password=True)
        extended['obsolete_setting']='discarded'
        self.auth_path.write_text(yaml.safe_dump(extended))
        self.restart()
        self.assertEqual(yaml.safe_load(self.auth_path.read_text()),original)
        self.assertEqual(set(self.app.state.auth.credentials.users),{'admin','operator'})
        self.login('obsolete-account',status=401)
        self.login('admin');self.change();self.login('admin',NEW_PASSWORD)
        before=self.auth_path.read_bytes()
        self.restart()
        self.assertEqual(self.auth_path.read_bytes(),before)

    def test_websocket_auth_origin_and_password_revocation(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/api/v1/ws',headers={'Origin':'http://testserver'}): pass
        self.login('operator')
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/api/v1/ws',headers={'Origin':'https://evil.example'}): pass
        with self.client.websocket_connect('/api/v1/ws',headers={'Origin':'http://testserver'}) as ws:
            self.assertEqual(ws.receive_json()['event']['name'],'13th Cup of Central Europe Cities 2026')
            admin=TestClient(self.app)
            self.login('admin',client=admin); self.change(client=admin); self.login('admin',NEW_PASSWORD,client=admin)
            self.change('operator',client=admin)
            with self.assertRaises(WebSocketDisconnect): ws.receive_json()
            admin.close()

    def test_secure_cookie_and_login_throttle(self):
        self.app.state.auth.config.secure_cookie=True
        https=TestClient(self.app,base_url='https://testserver')
        response=self.login('operator',client=https)
        self.assertIn('Secure',response.headers['set-cookie'])
        self.app.state.auth.attempts.extend([time.monotonic()]*30)
        https.cookies.clear()
        self.login('operator',client=https,status=429)
        https.close()

    def test_failed_password_save_preserves_sessions_and_hash(self):
        self.admin(); old=self.auth_path.read_bytes()
        with patch('livescore.auth.atomic_write',side_effect=OSError('simulated failure')):
            self.change('operator',status=503)
        self.assertEqual(self.auth_path.read_bytes(),old)
        self.assertTrue(self.app.state.auth.credentials.users['operator'].default_password)


if __name__ == '__main__': unittest.main()
