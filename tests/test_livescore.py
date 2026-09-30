import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError

from livescore.auth import AuthConfig
from livescore.app import create_app, Score
from livescore.config import load_config
from livescore.models import State
from livescore.service import Service
from livescore.storage import load, save, FileLease

ROOT = Path(__file__).resolve().parents[1]
(ROOT / '.test-artifacts').mkdir(exist_ok=True)


class APITest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / '.test-artifacts')
        self.path = Path(self.directory.name) / 'state.json'
        self.legacy_path = self.path
        self.app = create_app(auth_config=AuthConfig(enabled=False), data_file=self.legacy_path)
        self.client = TestClient(self.app).__enter__()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(lambda: self.client.__exit__(None, None, None))
        created = self.client.post('/api/v1/event-catalog/create', json=dict(
            request_id=str(uuid4()), catalog_session=self.state()['stream_id'],
            event=dict(name='Test', date_from='2026-10-03', date_to='2026-10-04'))).json()['created_event_id']
        self.client.post('/api/v1/event-catalog/select', json=dict(
            request_id=str(uuid4()), catalog_session=self.state()['stream_id'],
            selection_token=self.state()['selection_token'], event_id=created)).raise_for_status()
        self.path = Path(self.directory.name) / 'events' / f'{created}.json'
        self.configure('event', dict(name='Test', date_from='2026-10-03', date_to='2026-10-04'))
        self.configure('play-areas', dict(id='area', label='Court 1'))
        for pid in ('a','b','c'):
            self.configure('participants', dict(id=pid, name=pid.upper()))
        for mid in ('m1','m2'):
            self.configure('matches', dict(id=mid, date='2026-10-03', time='09:30', play_area_id='area', participant_1='a', participant_2='b'))

    def state(self):
        return self.client.get('/api/v1/tournament').json()

    def context(self):
        state = self.state()
        return dict(event_id=state['active_event_id'], selection_token=state['selection_token'])

    def request(self, operation, **fields):
        return self.client.post('/api/v1/' + operation, json=dict(request_id=str(uuid4()), expected_revision=self.state()['revision'], **self.context(), **fields))

    def configure(self, kind, data):
        response = self.request('config/' + kind, data=data)
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def action(self, operation, match_id='m1', **fields):
        response = self.request('live/' + operation, match_id=match_id, **fields)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def ready(self):
        self.action('select')
        return self.action('prepare',participant_1='a',participant_2='b',side_l='a',side_r='b')

    def start(self):
        self.ready()
        self.action('start')

    def score_payload(self, side='L', delta=1):
        state = self.state()
        match = next(m for m in state['matches'] if m['id'] == state['active_match_id'])
        return dict(request_id=str(uuid4()), **self.context(), match_id=match['id'], control_revision=match['control_revision'],
                    participant_id=state['live']['left' if side == 'L' else 'right']['id'], side=side, delta=delta)

    def score(self, side='L', delta=1):
        response = self.client.post('/api/v1/live/score', json=self.score_payload(side,delta))
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_configuration_creation_and_edit(self):
        state = self.state()
        self.assertEqual(state['event']['name'],'Test')
        self.assertEqual(len(state['participants']),3)
        self.assertEqual(len(state['matches']),2)
        self.configure('participants',dict(id='a',name='A new'))
        self.assertEqual(len(self.state()['participants']),3)
        self.assertEqual(self.state()['participants'][0]['name'],'A new')

    def test_unknown_pairing_and_correction(self):
        self.configure('matches',dict(id='m3',date='2026-10-03',time='11:30',play_area_id='area',placeholder_1='Finalist 1'))
        self.action('select',match_id='m3')
        self.action('prepare',match_id='m3',participant_1='c',participant_2='a',side_l='a',side_r='c')
        state = self.action('prepare',match_id='m3',participant_1='c',participant_2='b',side_l='b',side_r='c')
        self.assertEqual(state['live']['left']['id'],'b')
        self.action('unprepare',match_id='m3')
        self.action('select',match_id='m1')

    def test_side_switch_keeps_participant_scores_and_api_contract(self):
        self.start()
        self.score('L'); self.score('L'); self.score('R')
        before = self.client.get('/api/v1/live').json()
        self.assertEqual((before['left']['score'],before['right']['score']),(2,1))
        self.action('switch-sides')
        after = self.client.get('/api/v1/live').json()
        self.assertEqual(after['left'],dict(id='b',name='B',short_name='',country_code='',score=1,counters={},counter_states={}))
        self.assertEqual(after['right'],dict(id='a',name='A',short_name='',country_code='',score=2,counters={},counter_states={}))
        # Bestehende Felder bleiben erhalten; stage, round und period_info kommen additiv hinzu.
        self.assertEqual(set(after),{'status','revision','match_id','play_area','left','right','officials','period',
                                     'period_info','stage','round'})
        self.assertEqual((after['stage'],after['round']),(None,None))
        self.assertEqual(after['period_info'],dict(number=1,intermission=False,code='period_1',label_en=None))
        self.assertEqual(after['play_area'],{'id':'area','label':'Court 1'})
        self.assertEqual(self.state()['matches'][0]['scores'],{'a':2,'b':1})
        self.action('undo')
        self.assertEqual(self.state()['matches'][0]['scores'],{'a':2,'b':0})

    def test_decrement_undo_pause_resume_finish_next(self):
        self.start(); self.score(); self.score(); self.score(delta=-1)
        self.action('pause')
        self.assertEqual(self.state()['live']['status'],'paused')
        self.action('undo')
        self.assertEqual(self.state()['live']['left']['score'],2)
        self.action('resume'); self.action('finish')
        self.assertEqual(self.state()['live']['status'],'finished')
        state = self.action('select',match_id='m2')
        self.assertEqual(state['live']['status'],'scheduled')
        self.assertEqual(state['matches'][0]['scores']['a'],2)
        event_types = {e['type'] for e in self.client.get('/api/v1/events').json()}
        self.assertTrue({'match_started','score','pause','resume','match_finished','undo'} <= event_types)

    def test_reopen_after_accidental_finish_keeps_scores_sides_and_undo(self):
        self.start(); self.score('L'); self.score('L'); self.score('R')
        self.action('switch-sides'); self.action('finish')
        self.assertFalse(self.state()['can_undo'])
        state = self.action('reopen')
        self.assertEqual(state['live']['status'],'paused')
        self.assertEqual(state['matches'][0]['scores'],{'a':2,'b':1})
        self.assertEqual((state['live']['left']['id'],state['live']['left']['score']),('b',1))
        self.assertEqual((state['live']['right']['id'],state['live']['right']['score']),('a',2))
        self.assertTrue(state['can_undo'])
        # Nach einem Neustart bleibt der wieder geöffnete Zustand erhalten.
        self.client.__exit__(None,None,None)
        self.app = create_app(auth_config=AuthConfig(enabled=False), data_file=self.legacy_path); self.client = TestClient(self.app).__enter__()
        self.assertEqual(self.client.get('/api/v1/live').json()['status'],'paused')
        self.action('undo')
        self.assertEqual(self.state()['matches'][0]['scores'],{'a':2,'b':0})
        self.action('resume'); self.score('L')  # b steht nach dem Seitenwechsel links.
        self.action('finish')
        self.assertEqual(self.state()['matches'][0]['scores'],{'a':2,'b':1})
        event_types = [e['type'] for e in self.client.get('/api/v1/events').json()]
        self.assertEqual(event_types.count('match_finished'),2)
        self.assertIn('match_reopened',event_types)

    def test_reopen_only_for_selected_finished_match_and_after_selecting_it_again(self):
        before = self.state()
        self.assertEqual(self.request('live/reopen',match_id='m1').status_code,409)
        self.assertEqual(self.state(),before)
        self.ready()
        self.assertEqual(self.request('live/reopen',match_id='m1').status_code,409)
        self.action('start')
        self.assertEqual(self.request('live/reopen',match_id='m1').status_code,409)
        self.action('pause')
        self.assertEqual(self.request('live/reopen',match_id='m1').status_code,409)
        self.action('finish')
        stale = self.state()['revision']
        self.action('select',match_id='m2')
        before = self.state()
        self.assertEqual(self.request('live/reopen',match_id='m1').status_code,409)
        response = self.client.post('/api/v1/live/reopen',json=dict(request_id=str(uuid4()),expected_revision=stale,**self.context(),match_id='m1'))
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.state(),before)
        self.assertEqual(before['matches'][0]['status'],'finished')
        # Ein beendetes Spiel darf erneut ausgewählt und dann wieder geöffnet werden.
        state = self.action('select',match_id='m1')
        self.assertEqual((state['live']['status'],state['live']['match_id']),('finished','m1'))
        self.assertEqual(self.action('reopen')['live']['status'],'paused')
        self.assertEqual(self.request('live/select',match_id='m2').status_code,409)
        self.action('finish')
        self.action('select',match_id='m2'); self.action('prepare',match_id='m2',participant_1='a',participant_2='c',side_l='a',side_r='c')
        self.assertEqual(self.request('live/select',match_id='m1').status_code,409)
        self.action('start',match_id='m2')
        self.assertEqual(self.request('live/select',match_id='m1').status_code,409)

    def test_negative_and_zero_and_boolean_scores_rejected(self):
        self.start()
        for delta, code in ((-1,409),(0,422),(2,422),(True,422),('1',422)):
            with self.subTest(delta=delta):
                response = self.client.post('/api/v1/live/score',json=self.score_payload(delta=delta))
                self.assertEqual(response.status_code,code)
        self.assertEqual(self.state()['live']['left']['score'],0)

    def test_invalid_transitions_do_not_mutate(self):
        for operation in ('start','pause','resume','finish','undo','switch-sides'):
            before = self.state()
            response = self.request('live/'+operation,match_id='m1')
            self.assertEqual(response.status_code,409)
            self.assertEqual(self.state(),before)
        self.action('select')
        self.assertEqual(self.request('live/start',match_id='m1').status_code,409)
        self.action('prepare',participant_1='a',participant_2='b',side_l='a',side_r='b')
        self.action('switch-sides'); self.action('start')
        self.assertEqual(self.request('live/start',match_id='m1').status_code,409)
        self.assertEqual(self.request('live/select',match_id='m2').status_code,409)
        self.action('pause')
        self.assertEqual(self.request('live/pause',match_id='m1').status_code,409)
        self.action('finish')
        for operation in ('undo','switch-sides','resume','prepare','start','finish'):
            self.assertEqual(self.request('live/'+operation,match_id='m1').status_code,422 if operation == 'prepare' else 409)
        self.assertEqual(self.client.post('/api/v1/live/score',json=self.score_payload()).status_code,409)

    def test_validation_references_dates_pairing_and_extra_fields(self):
        invalid = [
            ('event',dict(name='Bad',date_from='2026-10-04',date_to='2026-10-03')),
            ('matches',dict(id='bad',date='2026-10-05',time='09:30',play_area_id='area')),
            ('matches',dict(id='bad',date='2026-10-03',time='09:30',play_area_id='missing')),
            ('participants',dict(id='a',name='   ')),
            ('participants',dict(id='a',name='A',unknown=1)),
        ]
        for kind,data in invalid:
            before = self.state()
            self.assertEqual(self.request('config/'+kind,data=data).status_code,422)
            self.assertEqual(self.state(),before)
        self.action('select')
        for pair in [('a','a','a','a'),('a','missing','a','missing'),('a','b','a','c')]:
            self.assertEqual(self.request('live/prepare',match_id='m1',**dict(zip(('participant_1','participant_2','side_l','side_r'),pair))).status_code,422)

    def test_stale_score_after_side_switch_pause_or_match_change(self):
        self.start()
        stale = self.score_payload()
        self.action('switch-sides')
        self.assertEqual(self.client.post('/api/v1/live/score',json=stale).status_code,409)
        stale = self.score_payload()
        self.action('pause'); self.action('resume')
        self.assertEqual(self.client.post('/api/v1/live/score',json=stale).status_code,409)
        self.action('finish'); self.action('select',match_id='m2')
        self.assertEqual(self.client.post('/api/v1/live/score',json=stale).status_code,409)

    def test_stale_finish_and_config_conflict(self):
        revision = self.state()['revision']
        self.configure('participants',dict(id='a',name='Changed'))
        response = self.client.post('/api/v1/config/participants',json=dict(request_id=str(uuid4()),expected_revision=revision,**self.context(),data=dict(id='a',name='Stale')))
        self.assertEqual(response.status_code,409)
        self.start(); revision = self.state()['revision']; self.score()
        response = self.client.post('/api/v1/live/finish',json=dict(request_id=str(uuid4()),expected_revision=revision,**self.context(),match_id='m1'))
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.request('config/participants',data=dict(id='a',name='Changed')).status_code,409)

    def test_two_rapid_scores_and_parallel_requests_no_lost_updates(self):
        self.start()
        payloads = [self.score_payload() for _ in range(30)]
        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(lambda p:self.client.post('/api/v1/live/score',json=p),payloads))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertEqual(self.state()['live']['left']['score'],30)
        self.assertEqual(load(self.path).matches[0].scores['a'],30)
        self.assertEqual(len({r.json()['revision'] for r in responses}),30)

    def test_idempotency_and_reused_id_with_different_payload(self):
        self.start(); payload = self.score_payload()
        first = self.client.post('/api/v1/live/score',json=payload)
        second = self.client.post('/api/v1/live/score',json=payload)
        self.assertEqual(first.json(),second.json())
        payload['delta'] = -1
        self.assertEqual(self.client.post('/api/v1/live/score',json=payload).status_code,409)
        self.assertEqual(self.state()['live']['left']['score'],1)

    def test_restart_restores_undo_and_request_deduplication(self):
        self.start(); payload = self.score_payload()
        self.client.post('/api/v1/live/score',json=payload)
        self.action('switch-sides'); self.action('pause')
        previous = self.state()
        self.client.__exit__(None,None,None)
        self.app = create_app(auth_config=AuthConfig(enabled=False), data_file=self.legacy_path); self.client = TestClient(self.app).__enter__()
        comparable = lambda state: {k:v for k,v in state.items() if k not in ('stream_id','stream_revision')}
        self.assertEqual(comparable(self.state()),comparable(previous))
        self.assertEqual(comparable(self.client.post('/api/v1/live/score',json=payload).json()),comparable(previous))
        self.action('undo')
        self.assertEqual(self.state()['live']['right']['score'],0)

    def test_storage_error_does_not_publish_or_change_memory(self):
        self.start(); before = self.state(); persisted = self.path.read_bytes()
        with patch('livescore.storage.os.replace',side_effect=OSError('disk error')):
            response = self.client.post('/api/v1/live/score',json=self.score_payload())
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.state(),before)
        self.assertEqual(self.path.read_bytes(),persisted)
        self.assertEqual(list(self.path.parent.glob('*.tmp')),[])

    def test_websocket_initial_broadcast_two_clients_and_reconnect(self):
        self.start()
        with self.client.websocket_connect('/api/v1/ws') as a, self.client.websocket_connect('/api/v1/ws') as b:
            self.assertEqual(a.receive_json(),self.state())
            self.assertEqual(b.receive_json(),self.state())
            updated = self.score()
            self.assertEqual(a.receive_json(),updated)
            self.assertEqual(b.receive_json(),updated)
        self.action('pause')
        with self.client.websocket_connect('/api/v1/ws') as c:
            self.assertEqual(c.receive_json(),self.state())

    def test_idle_and_static_pages(self):
        self.assertEqual(self.client.get('/api/v1/live').json()['status'],'idle')
        self.assertIsNone(self.client.get('/api/v1/live').json()['left'])
        for url in ('/','/config','/static/live.js','/docs'):
            self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.get('/api/v1/live').headers['cache-control'],'no-store')


class StorageTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT / '.test-artifacts')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'tournament.json'

    def test_atomic_replace_and_load(self):
        state = State(); save(self.path,state)
        with patch('livescore.storage.os.replace',wraps=__import__('os').replace) as replace:
            state.revision = 1; save(self.path,state)
        temporary, destination = replace.call_args.args
        self.assertEqual(temporary.parent,self.path.parent)
        self.assertEqual(destination,self.path)
        self.assertFalse(temporary.exists())
        self.assertEqual(load(self.path),state)
        self.assertEqual(json.loads(self.path.read_text())['revision'],1)

    def test_invalid_file_fails_without_overwrite(self):
        self.path.write_text('{broken')
        with self.assertRaises(ValidationError): load(self.path)
        self.assertEqual(self.path.read_text(),'{broken')
        self.path.write_text('{"schema_version": 2}')
        with self.assertRaises(ValidationError): load(self.path)

    def test_process_lease_excludes_second_owner_and_releases(self):
        first, second = FileLease(self.path), FileLease(self.path)
        first.acquire()
        try:
            with self.assertRaises(RuntimeError): second.acquire()
        finally: first.release()
        second.acquire(); second.release()

    def test_invalid_state_is_not_saved(self):
        save(self.path,State()); before = self.path.read_bytes()
        state = State(); state.active_match_id = 'missing'
        with self.assertRaises(ValidationError): save(self.path,state)
        self.assertEqual(self.path.read_bytes(),before)

    def test_config_relative_path_and_invalid_port(self):
        config = self.path.with_suffix('.yml')
        config.write_text('bind_host: 127.0.0.1\nport: 8730\ndata_file: nested/state.json\n')
        loaded = load_config(config)
        self.assertEqual(loaded.data_file, config.parent/'nested/state.json')
        config.write_text('bind_host: 127.0.0.1\nport: 70000\ndata_file: test.json\n')
        with self.assertRaises(ValidationError): load_config(config)

    def test_sample_is_valid(self):
        state = load(ROOT/'examples/prague-2026.json')
        self.assertEqual(len(state.participants),6)
        self.assertEqual(state.revision,0)

    def test_readme_api_example_matches_real_requests(self):
        examples = [json.loads(block) for block in re.findall(r'```json\n(.*?)\n```', (ROOT/'README.md').read_text(), re.S)]
        expected = next(item for item in examples if item.get('status') == 'live')
        sample = load(ROOT/'examples/prague-2026.json')
        save(self.path,sample)
        with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_file=self.path)) as client:
            for operation,fields in (
                ('select',{}),
                ('prepare',dict(participant_1='bsc-praha',participant_2='fc-ingolstadt-04',side_l='bsc-praha',side_r='fc-ingolstadt-04')),
                ('start',{}),
            ):
                state = client.get('/api/v1/tournament').json()
                response = client.post('/api/v1/live/'+operation,json=dict(request_id=str(uuid4()),expected_revision=state['revision'],event_id=state['active_event_id'],selection_token=state['selection_token'],match_id='match-001',**fields))
                self.assertEqual(response.status_code,200,response.text)
            score = next(item for item in examples if 'delta' in item)
            for side,pid in [('L','bsc-praha'),('L','bsc-praha'),('R','fc-ingolstadt-04')]:
                response = client.post('/api/v1/live/score',json={**score,'request_id':str(uuid4()),'side':side,'participant_id':pid,'event_id':state['active_event_id'],'selection_token':state['selection_token']})
                self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(client.get('/api/v1/live').json(),expected)


class QueueTest(unittest.IsolatedAsyncioTestCase):
    async def test_slow_subscriber_receives_latest_without_blocking(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts') as directory:
            path = Path(directory)/'state.json'
            state = load(ROOT/'examples/prague-2026.json')
            match = state.matches[0]; state.active_match_id = match.id
            match.status = 'live'; match.side_l = match.participant_1; match.side_r = match.participant_2
            match.scores = {match.participant_1:0,match.participant_2:0}
            save(path,state); service = Service(path); queue = service.subscribe()
            for _ in range(5):
                await service.apply('score',Score(request_id=uuid4(),match_id=match.id,control_revision=0,participant_id=match.side_l,side='L',delta=1))
            self.assertEqual(queue.qsize(),1)
            self.assertEqual((await queue.get())['live']['left']['score'],5)


if __name__ == '__main__': unittest.main()
