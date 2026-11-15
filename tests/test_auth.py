"""Zugriffsschutz mit echten scrypt-Hashes und isolierter lokaler Auth-Datei."""
import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect
import yaml

from livescore.app import create_app
from livescore.auth import AuthConfig, COOKIE, hash_password, login_client, update_password, verify_password
from livescore.config import load_config
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

    def restart(self, **auth):
        if hasattr(self,'client'): self.client.__exit__(None,None,None)
        self.app = create_app(data_dir=self.root/'data',auth_config=AuthConfig(file=self.auth_path,**auth))
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

    def test_operator_can_reset_live_and_finished_match_with_csrf(self):
        self.login('operator')
        self.action('select')
        self.action('prepare', participant_1='bsc-praha', participant_2='fc-ingolstadt-04',
                    side_l='bsc-praha', side_r='fc-ingolstadt-04')
        self.action('start')
        state = self.client.get('/api/v1/tournament').json()
        payload = dict(request_id=str(uuid4()), expected_revision=state['revision'],
            event_id=state['active_event_id'], selection_token=state['selection_token'], match_id='match-001')
        self.assertEqual(self.client.post('/api/v1/live/reset', json=payload).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/tournament').json(), state)
        self.assertEqual(self.action('reset')['live']['status'], 'scheduled')
        self.action('prepare', participant_1='kairat-almaty', participant_2='fc-ingolstadt-04',
                    side_l='kairat-almaty', side_r='fc-ingolstadt-04')
        self.action('start'); self.action('finish')
        self.assertEqual(self.action('reset')['live']['status'], 'scheduled')
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/v1/live/reset', json=payload).status_code, 401)

    def assert_locked_but_live(self):
        """Fail closed nur für die Anmeldung; Live-API und Version bleiben (#18, #19)."""
        self.assertEqual(self.client.get('/api/v1/live').status_code,200)
        self.assertEqual(self.client.get('/api/version').status_code,200)
        self.assertEqual(self.client.get('/static/i18n.js').status_code,200)
        self.assertTrue(self.client.get('/api/auth/session').json()['locked'])
        self.login(password='admin',status=503)
        page=self.client.get('/',follow_redirects=False)
        self.assertEqual(page.status_code,503); self.assertIn('sudo livescore --reset-admin-password',page.text)
        self.assertEqual(self.client.get('/api/v1/tournament').json()['detail'],'auth_locked')
        self.assertEqual(self.client.post('/api/v1/live/start',json={}).status_code,503)

    def test_missing_file_creates_no_accounts_and_locks_only_login(self):
        self.client.__exit__(None,None,None)
        del self.client
        self.auth_path.unlink()
        with self.assertLogs(level='ERROR') as logs:
            self.restart()
        self.assertIn('auth.yml fehlt',' '.join(logs.output))
        self.assertFalse(self.auth_path.exists())
        self.assert_locked_but_live()
        # Reset legt die Datei an; der Reload hebt die Sperre ohne Neustart auf.
        update_password(self.auth_path,'admin',hash_password(NEW_PASSWORD),create=True)
        self.assertTrue(asyncio.run(self.app.state.auth.reload()))
        self.login(password=NEW_PASSWORD)
        users=self.client.get('/api/auth/users').json()['users']
        self.assertEqual([(u['username'],u['configured']) for u in users],[('admin',True),('operator',False)])
        self.change('operator')
        self.login('operator',password=NEW_PASSWORD)

    def test_broken_file_starts_service_without_rewriting_or_leaking_hash(self):
        self.client.__exit__(None,None,None)
        del self.client
        secret=self.initial['users']['admin']['password_hash']
        for content in ('','broken: [\n  '+secret,yaml.safe_dump({'users':{'admin':dict(role='admin',password_hash='scrypt$1$'+secret[-20:])}})):
            self.auth_path.write_text(content)
            with self.assertLogs(level='ERROR') as logs:
                self.restart()
            self.assertNotIn(secret[-20:],' '.join(logs.output))
            self.assertEqual(self.auth_path.read_text(),content)
            self.assert_locked_but_live()

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
        for password,repeat in [('abcd','abcd'),(NEW_PASSWORD,'different password'),('admin','admin')]:
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

    def test_both_roles_can_configure_existing_events_and_operate(self):
        self.admin()
        for role in ('operator','admin'):
            with self.subTest(role=role):
                self.login('admin',password=NEW_PASSWORD)
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
                self.login(role,password=NEW_PASSWORD if role == 'admin' else 'operator')
                event=state['event'];event['name']='Corrected name';event['location']='Corrected place'
                if role == 'admin': event['sport_profile']['ruleset']='Configured rules'
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
                self.action('switch-sides');self.action('intermission',intermission=True);self.action('period',period=2);self.action('finish')
                exported=self.client.get('/api/v1/event-catalog/'+imported+'/export')
                self.assertEqual(exported.status_code,200)
                self.assertEqual(exported.json()['event']['name'],'Corrected name')
                self.assertEqual(exported.json()['matches'][0]['scores']['bsc-praha'],1)
                # Nur der Admin darf eine Veranstaltung durch eine Importdatei ersetzen (Reset nach Tests).
                self.login('admin',password=NEW_PASSWORD)
                preview=self.client.post('/api/v1/event-catalog/import/preview',json=dict(json_text=raw,event_id=imported),headers=self.headers()).json()
                self.login(role,password=NEW_PASSWORD if role == 'admin' else 'operator')
                state=self.client.get('/api/v1/tournament').json()
                response=self.client.post('/api/v1/event-catalog/replace',json=dict(request_id=str(uuid4()),catalog_session=state['stream_id'],
                                          json_text=raw,event_id=imported,preview_token=preview['preview_token']),headers=self.headers())
                self.assertEqual(response.status_code,403 if role=='operator' else 200,response.text)
                self.assertEqual(self.client.get('/api/v1/tournament').json()['matches'][0]['status'],'finished' if role=='operator' else 'scheduled')
                state=self.client.get('/api/v1/tournament').json()
                response=self.client.post('/api/v1/event-catalog/reset',json=dict(request_id=str(uuid4()),catalog_session=state['stream_id'],event_id=imported),headers=self.headers())
                self.assertEqual(response.status_code,403 if role=='operator' else 200,response.text)
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

    def test_configured_limits_apply_to_the_web_change(self):
        """#12: Grenzen aus livescore.yml; ungültige Werte: Vorgabe mit Meldung, Dienst läuft."""
        self.admin()
        self.app.state.auth.limits=(8,10,None)
        self.assertEqual(self.client.get('/api/auth/session').json()['password_max_length'],10)
        for password,status in (('1234567',422),('12345678',200),('1234567890',200),('12345678901',422)):
            with self.subTest(password=password):
                response=self.client.post('/api/auth/password',json=dict(username='operator',password=password,repeat=password),headers=self.headers())
                self.assertEqual(response.status_code,status,response.text)
                if status==422: self.assertEqual(response.json()['detail'],'password_length')
        self.client.__exit__(None,None,None);del self.client
        with self.assertLogs(level='ERROR') as logs:
            self.app=create_app(data_dir=self.root/'data',auth_config=AuthConfig(file=self.auth_path,password_min_length=9,password_max_length=8))
            self.client=TestClient(self.app).__enter__()
        self.assertIn('Verwendet werden 5 bis 1024.',' '.join(logs.output))
        self.assertEqual(self.app.state.auth.limits[:2],(5,1024))
        self.assertEqual(self.client.get('/api/v1/live').status_code,200)

    def test_unknown_entries_are_kept_until_a_write_backs_them_up(self):
        self.client.__exit__(None,None,None);del self.client
        original=yaml.safe_load(self.auth_path.read_text())
        extended=json.loads(json.dumps(original))
        extended['users']['obsolete-account']=dict(role='obsolete',password_hash='discarded',default_password=True)
        extended['obsolete_setting']='discarded'
        self.auth_path.write_text(yaml.safe_dump(extended))
        before=self.auth_path.read_bytes()
        with self.assertLogs(level='WARNING') as logs:
            self.restart()
        self.assertIn('users.obsolete-account',' '.join(logs.output))
        self.assertEqual(self.auth_path.read_bytes(),before)  # Start schreibt nie neu
        self.assertEqual(set(self.app.state.auth.credentials.users),{'admin','operator'})
        self.login('obsolete-account',status=401)
        self.login('admin');self.change();self.login('admin',NEW_PASSWORD)
        backups=list(self.root.glob('auth.yml.defekt-*'))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),before)
        self.assertNotIn('obsolete',self.auth_path.read_text())
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
        self.app.state.auth.failures.extend([(time.monotonic(),'testclient')]*10)
        https.cookies.clear()
        self.assertEqual(self.login('operator',client=https,status=429).json(),{'detail':'login_limited'})
        https.close()

    def peer(self, address, **headers):
        """Eigener Client mit fester Gegenstelle, ohne Lifespan wie die übrigen Zweitclients."""
        client = TestClient(self.app,client=(address,50000),headers=headers)
        self.addCleanup(client.close)
        return client

    def fail(self, client, times):
        """Fehlversuche ohne je eine KDF-Prüfung (0,2 s) vormerken."""
        self.app.state.auth.failures.extend([(time.monotonic(),client)]*times)

    def test_failed_logins_lock_out_only_their_client(self):
        """#23: Fehlversuche eines Clients sperren nicht die übrigen Bediener."""
        attacker, operator = self.peer('192.0.2.10'), self.peer('192.0.2.20')
        self.fail('192.0.2.10',9)
        self.login(password='wrong secret',client=attacker,status=401)
        self.assertEqual(self.login('operator',client=attacker,status=429).json(),{'detail':'login_limited'})
        self.login('operator',password='wrong secret',client=operator,status=401)
        self.login('operator',client=operator)
        self.assertEqual(operator.get('/api/v1/tournament').status_code,200)
        self.login('operator',client=attacker,status=429)

    def test_successful_logins_are_not_counted_and_clear_client_failures(self):
        auth = self.app.state.auth
        operator, other = self.peer('192.0.2.20'), self.peer('192.0.2.30')
        self.login('operator',client=operator); self.login('operator',client=operator)
        self.assertEqual(list(auth.failures),[])
        self.fail('192.0.2.20',9); self.fail('192.0.2.30',3)
        self.login('operator',client=operator)
        # Nur die eigenen Fehlversuche sind gelöscht; das Gesamtlimit zählt sie weiter.
        self.assertEqual(sum(entry=='192.0.2.20' for _,entry in auth.failures),0)
        self.assertEqual(sum(entry=='192.0.2.30' for _,entry in auth.failures),3)
        self.assertEqual(len(auth.failures),12)
        self.fail('192.0.2.20',9)
        self.login('operator',client=operator)
        self.login('operator',client=other)

    def test_global_failure_cap_and_window(self):
        auth = self.app.state.auth
        late = self.peer('192.0.2.99')
        for host in range(1,21):
            self.fail(f'198.51.100.{host}',5)
        self.login('operator',client=late,status=429)
        # Gleiche Anzahl außerhalb des Fensters: Die Anmeldung geht wieder.
        auth.failures.clear()
        auth.failures.extend([(time.monotonic()-301,f'198.51.100.{host}') for host in range(1,101)])
        self.login('operator',client=late)
        self.assertEqual(list(auth.failures),[])
        # 99 Fehlversuche anderer und ein eigener erreichen das Gesamtlimit.
        for host in range(1,34):
            self.fail(f'198.51.100.{host}',3)
        self.login(password='wrong secret',client=late,status=401)
        self.login('operator',client=self.peer('192.0.2.98'),status=429)

    def test_trusted_proxy_forwarded_for_identifies_client(self):
        self.restart(trusted_proxies=['127.0.0.1'])
        auth = self.app.state.auth
        attacker = self.peer('127.0.0.1',**{'X-Forwarded-For':'192.0.2.10'})
        # Der Client darf links beliebige Einträge mitschicken; maßgeblich ist der vom Proxy angehängte.
        operator = self.peer('127.0.0.1',**{'X-Forwarded-For':'192.0.2.10, 192.0.2.20'})
        self.login(password='wrong secret',client=attacker,status=401)
        self.assertEqual([entry for _,entry in auth.failures],['192.0.2.10'])
        self.fail('192.0.2.10',9)
        self.login('operator',client=attacker,status=429)
        self.login('operator',client=operator)
        self.login('operator',client=self.peer('127.0.0.1'))  # ohne Header: der Proxy selbst

    def test_forwarded_for_from_untrusted_peer_is_ignored(self):
        for trusted in ([],['127.0.0.1']):
            with self.subTest(trusted=trusted):
                self.restart(trusted_proxies=trusted)
                auth = self.app.state.auth
                spoofing = self.peer('192.0.2.10',**{'X-Forwarded-For':'192.0.2.77'})
                self.login(password='wrong secret',client=spoofing,status=401)
                self.assertEqual([entry for _,entry in auth.failures],['192.0.2.10'])
                self.fail('192.0.2.10',9)
                for forwarded in ('192.0.2.78','127.0.0.1','192.0.2.78, 192.0.2.79'):
                    other = self.peer('192.0.2.10',**{'X-Forwarded-For':forwarded})
                    self.login('operator',client=other,status=429)

    def test_failed_password_save_preserves_sessions_and_hash(self):
        self.admin(); old=self.auth_path.read_bytes()
        with patch('livescore.auth.atomic_write',side_effect=OSError('simulated failure')):
            self.change('operator',status=503)
        self.assertEqual(self.auth_path.read_bytes(),old)
        self.assertTrue(self.app.state.auth.credentials.users['operator'].default_password)


class LoginClientTest(unittest.TestCase):
    """#23: X-Forwarded-For nur von eingetragenen Proxys, rechter Eintrag zuerst."""

    def test_client_from_peer_and_trusted_forwarded_for(self):
        trusted = AuthConfig(trusted_proxies=['127.0.0.1','10.0.0.2','::1']).trusted_proxies
        for peer,forwarded,proxies,expected in (
                ('192.0.2.10','192.0.2.77',[],'192.0.2.10'),
                ('127.0.0.1','192.0.2.77',[],'127.0.0.1'),
                ('192.0.2.10','192.0.2.77',trusted,'192.0.2.10'),
                ('127.0.0.1','192.0.2.77',trusted,'192.0.2.77'),
                ('127.0.0.1','spoofed, 192.0.2.66, 192.0.2.77',trusted,'192.0.2.77'),
                ('127.0.0.1','192.0.2.66, 192.0.2.77, 10.0.0.2',trusted,'192.0.2.77'),
                ('::1','2001:DB8::1',trusted,'2001:db8::1'),
                ('127.0.0.1','',trusted,'127.0.0.1'),
                ('127.0.0.1','10.0.0.2, 127.0.0.1',trusted,'127.0.0.1'),
                ('127.0.0.1','192.0.2.66, unknown',trusted,'127.0.0.1'),
                ('','192.0.2.77',trusted,'')):
            with self.subTest(peer=peer,forwarded=forwarded,proxies=bool(proxies)):
                self.assertEqual(login_client(peer,forwarded,proxies),expected)

    def test_trusted_proxies_config_validation(self):
        self.assertEqual(AuthConfig().trusted_proxies,[])
        for invalid in (['10.0.0.0/8'],['proxy.local'],['127.0.0.1:8080'],'127.0.0.1'):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                AuthConfig(trusted_proxies=invalid)
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts') as temp:
            path = Path(temp)/'livescore.yml'
            base = 'bind_host: 127.0.0.1\nport: 8730\ndata_dir: data\nauth:\n  trusted_proxies: '
            path.write_text(base+'[127.0.0.1, "::1"]\n')
            self.assertEqual([str(item) for item in load_config(path).auth.trusted_proxies],['127.0.0.1','::1'])
            path.write_text(base+'[192.0.2.300]\n')
            with self.assertRaises(ValidationError): load_config(path)


if __name__ == '__main__': unittest.main()
