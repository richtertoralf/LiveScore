"""Veranstaltungskatalog: Isolation, Import, atomare Auswahl und Migration."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError

from livescore.auth import AuthConfig
from livescore.app import create_app
from livescore.config import load_config
from livescore.models import State
from livescore.storage import load, save

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.test-artifacts'
ARTIFACTS.mkdir(exist_ok=True)
SAMPLE = (ROOT / 'examples/prague-2026.json').read_text()


def context(state):
    return dict(event_id=state['active_event_id'], selection_token=state['selection_token'])


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.directory = Path(self.temp.name)
        self.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.client.__exit__(None, None, None))

    def start(self):
        self.app = create_app(auth_config=AuthConfig(enabled=False), data_dir=self.directory)
        self.client = TestClient(self.app).__enter__()

    def snapshot(self):
        return self.client.get('/api/v1/tournament').json()

    def catalog(self):
        return self.client.get('/api/v1/event-catalog').json()

    def post(self, operation, **fields):
        state = self.snapshot()
        return self.client.post('/api/v1/event-catalog/' + operation, json=dict(
            request_id=str(uuid4()), catalog_session=state['stream_id'], **fields))

    def create(self, name='Cup 2026'):
        response = self.post('create', event=dict(name=name, date_from='2026-10-03',date_to='2026-10-04'))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['created_event_id']

    def select(self, event_id, status=200):
        response = self.post('select', event_id=event_id, selection_token=self.snapshot()['selection_token'])
        self.assertEqual(response.status_code, status, response.text)
        return response

    def preview(self, text=SAMPLE, event_id=None):
        response = self.client.post('/api/v1/event-catalog/import/preview', json=dict(json_text=text, event_id=event_id))
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def imported(self, event_id='prague-2026', as_new=False):
        preview = self.preview(event_id=event_id)
        response = self.post('import', json_text=SAMPLE, event_id=preview['event_id'], preview_token=preview['preview_token'], as_new=as_new)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['created_event_id']

    def action(self, action, **fields):
        state = self.snapshot()
        payload = dict(request_id=str(uuid4()), **context(state), match_id='match-001', **fields)
        if action == 'score':
            match = state['matches'][0]
            payload.update(control_revision=match['control_revision'],participant_id=match['side_l'],side='L',delta=1)
        else: payload['expected_revision'] = state['revision']
        response = self.client.post('/api/v1/live/'+action,json=payload)
        self.assertEqual(response.status_code,200,response.text)
        return response

    def prepare(self):
        self.action('select')
        self.action('prepare',participant_1='bsc-praha',participant_2='fc-ingolstadt-04',side_l='bsc-praha',side_r='fc-ingolstadt-04')

    def test_empty_create_two_and_restart_selection(self):
        self.assertEqual(self.catalog()['items'],[])
        self.assertIsNone(self.snapshot()['active_event_id'])
        self.assertEqual(self.client.get('/api/v1/live').json()['status'],'idle')
        a, b = self.create(), self.create()
        self.assertNotEqual(a,b)
        self.assertEqual(len(self.catalog()['items']),2)
        self.assertIsNone(self.snapshot()['active_event_id'])
        self.select(b)
        token = self.snapshot()['selection_token']
        self.client.__exit__(None,None,None); self.start()
        self.assertEqual(self.snapshot()['active_event_id'],b)
        self.assertEqual(self.snapshot()['selection_token'],token)
        self.assertEqual(len(self.catalog()['items']),2)

    def test_preview_is_read_only_and_confirmation_preserves_state(self):
        before = {p.relative_to(self.directory):p.read_bytes() for p in self.directory.rglob('*') if p.is_file()}
        preview = self.preview(event_id='prague-2026')
        after = {p.relative_to(self.directory):p.read_bytes() for p in self.directory.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.assertEqual(preview['participants'],6)
        event_id = self.imported()
        self.assertEqual(load(self.directory/'events'/f'{event_id}.json'),State.model_validate_json(SAMPLE))
        export = self.client.get(f'/api/v1/event-catalog/{event_id}/export')
        self.assertEqual(State.model_validate_json(export.text),State.model_validate_json(SAMPLE))
        self.assertIn(f'{event_id}.json',export.headers['content-disposition'])

    def test_invalid_import_syntax_model_and_invariants(self):
        invalid = ['{broken','[]','{}',SAMPLE.replace('"schema_version": 1','"schema_version": 2'), SAMPLE.replace('"participant_2": "fc-ingolstadt-04"','"participant_2": "bsc-praha"')]
        for raw in invalid:
            response = self.client.post('/api/v1/event-catalog/import/preview',json={'json_text':raw})
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.catalog()['items'],[])
        preview = self.preview()
        response = self.post('import',json_text=SAMPLE.replace('BSC Praha','Altered'),event_id=preview['event_id'],preview_token=preview['preview_token'],as_new=False)
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.catalog()['items'],[])

    def test_collision_never_overwrites_and_copy_gets_unique_id(self):
        first = self.imported()
        original = (self.directory/'events'/f'{first}.json').read_bytes()
        preview = self.preview(event_id=first)
        self.assertTrue(preview['collision'])
        response = self.post('import',json_text=SAMPLE,event_id=first,preview_token=preview['preview_token'],as_new=False)
        self.assertEqual(response.status_code,409)
        second = self.imported(as_new=True)
        self.assertNotEqual(first,second)
        self.assertEqual((self.directory/'events'/f'{first}.json').read_bytes(),original)
        self.assertEqual(len(self.catalog()['items']),2)

    def test_switch_rules_isolation_and_restore(self):
        a,b = self.create('Empty'),self.imported()
        self.select(a); self.select(b)
        self.action('select'); self.select(a); self.select(b)  # scheduled
        self.action('prepare',participant_1='bsc-praha',participant_2='fc-ingolstadt-04',side_l='bsc-praha',side_r='fc-ingolstadt-04')
        self.select(a,409)  # ready
        self.action('start'); self.action('score'); self.select(a,409)
        self.action('pause'); self.select(a,409)
        self.action('finish'); self.select(a)
        self.assertEqual(self.snapshot()['matches'],[])
        self.select(b)
        self.assertEqual(self.client.get('/api/v1/live').json()['left']['score'],1)
        self.client.__exit__(None,None,None); self.start()
        self.assertEqual(self.snapshot()['active_event_id'],b)
        self.assertEqual(self.snapshot()['matches'][0]['status'],'finished')
        self.assertEqual(self.snapshot()['matches'][0]['scores']['bsc-praha'],1)

    def test_stale_config_and_score_context_rejected_even_after_roundtrip(self):
        a,b = self.imported(),self.imported(as_new=True)
        self.select(a); old = self.snapshot()
        payload = dict(request_id=str(uuid4()),expected_revision=old['revision'],**context(old),data={'id':'new','name':'Must not leak'})
        self.select(b)
        self.assertEqual(self.client.post('/api/v1/config/participants',json=payload).status_code,409)
        self.select(a)
        self.assertEqual(self.client.post('/api/v1/config/participants',json=payload).status_code,409)
        self.prepare(); self.action('start')
        score = dict(request_id=str(uuid4()),**context(old),match_id='match-001',control_revision=2,participant_id='bsc-praha',side='L',delta=1)
        self.assertEqual(self.client.post('/api/v1/live/score',json=score).status_code,409)

    def test_websocket_broadcasts_switch_with_lower_state_revision(self):
        a,b = self.imported(),self.create('Empty')
        self.select(a); self.action('select')
        with self.client.websocket_connect('/api/v1/ws') as first, self.client.websocket_connect('/api/v1/ws') as second:
            initial = first.receive_json(); second.receive_json()
            self.select(b)
            left,right = first.receive_json(),second.receive_json()
            self.assertEqual(left,right)
            self.assertEqual(left['active_event_id'],b)
            self.assertLess(left['revision'],initial['revision'])
            self.assertGreater(left['stream_revision'],initial['stream_revision'])

    def test_failed_selection_or_create_does_not_publish_or_change_disk(self):
        a,b = self.create(),self.create(); self.select(a)
        before = self.snapshot(); pointer = (self.directory/'active-event.json').read_bytes()
        with patch('livescore.storage.os.replace',side_effect=OSError('write failed')):
            self.select(b,503)
            response = self.post('create',event=dict(name='Fail',date_from='2026-10-03',date_to='2026-10-04'))
            self.assertEqual(response.status_code,503)
        self.assertEqual(before,self.snapshot())
        self.assertEqual(pointer,(self.directory/'active-event.json').read_bytes())
        self.assertEqual(len(self.catalog()['items']),2)

    def test_concurrent_create_unique_and_request_retry(self):
        state = self.snapshot()
        payload = dict(request_id=str(uuid4()),catalog_session=state['stream_id'],event=dict(name='Cup',date_from='2026-10-03',date_to='2026-10-04'))
        first = self.client.post('/api/v1/event-catalog/create',json=payload)
        again = self.client.post('/api/v1/event-catalog/create',json=payload)
        self.assertEqual(first.json()['created_event_id'],again.json()['created_event_id'])
        def create(_):
            return self.client.post('/api/v1/event-catalog/create',json={**payload,'request_id':str(uuid4())})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(create,range(4)))
        self.assertTrue(all(r.status_code == 200 for r in results))
        self.assertEqual(len(self.catalog()['items']),5)
        self.client.__exit__(None,None,None); self.start()
        self.assertEqual(self.client.post('/api/v1/event-catalog/create',json=payload).status_code,409)
        self.assertEqual(len(self.catalog()['items']),5)

    def test_path_traversal_is_rejected(self):
        self.assertEqual(self.post('select',event_id='../escape',selection_token=self.snapshot()['selection_token']).status_code,422)
        self.assertEqual(self.client.post('/api/v1/event-catalog/import/preview',json=dict(json_text=SAMPLE,event_id='../escape')).status_code,422)

    def test_import_rejects_broken_undo_history(self):
        event_id = self.imported(); self.select(event_id); self.prepare(); self.action('start'); self.action('score')
        state = load(self.directory/'events'/f'{event_id}.json').model_dump(mode='json')
        state['events'][-1]['participant_id'] = 'missing'
        response = self.client.post('/api/v1/event-catalog/import/preview',json=dict(json_text=json.dumps(state)))
        self.assertEqual(response.status_code,422)
        state['events'][-1]['participant_id'] = 'bsc-praha'
        state['matches'][0]['scores']['bsc-praha'] = 0
        response = self.client.post('/api/v1/event-catalog/import/preview',json=dict(json_text=json.dumps(state)))
        self.assertEqual(response.status_code,422)

    def test_catalogue_process_lease_blocks_second_server(self):
        with self.assertRaises(RuntimeError):
            with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_dir=self.directory)): pass

    def test_selection_and_start_are_serialized(self):
        a,b = self.imported(),self.create('Other'); self.select(a); self.prepare()
        with ThreadPoolExecutor(max_workers=2) as pool:
            start = pool.submit(self.action,'start')
            switch = pool.submit(self.select,b,409)
            start.result(); switch.result()
        self.assertEqual(self.snapshot()['active_event_id'],a)
        self.assertEqual(self.snapshot()['live']['status'],'live')

    def test_failed_import_keeps_catalogue_and_active_event(self):
        self.select(self.create())
        before = self.snapshot(); preview = self.preview()
        with patch('livescore.storage.os.replace',side_effect=OSError('disk full')):
            response = self.post('import',json_text=SAMPLE,event_id=preview['event_id'],preview_token=preview['preview_token'])
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(len(list((self.directory/'events').glob('*.json'))),1)

    def configure(self, kind, data, status=200):
        state = self.snapshot()
        response = self.client.post('/api/v1/config/'+kind,json=dict(
            request_id=str(uuid4()),expected_revision=state['revision'],**context(state),data=data))
        self.assertEqual(response.status_code,status,response.text)
        return response

    def match_plan(self):
        from livescore.models import MatchPlan
        return {key:value for key,value in self.snapshot()['matches'][0].items() if key in MatchPlan.model_fields}

    def test_referee_create_edit_and_read(self):
        self.select(self.create())
        self.configure('referees',dict(id='philipp-eilers',name='Philipp Eilers',country_code='de'))
        self.assertEqual(self.snapshot()['referees'],[dict(id='philipp-eilers',name='Philipp Eilers',country_code='DE')])
        self.configure('referees',dict(id='philipp-eilers',name='Philipp Eilers (Official)'))
        self.assertEqual(len(self.snapshot()['referees']),1)
        self.assertEqual(self.snapshot()['referees'][0]['country_code'],'')
        self.configure('referees',dict(id='invalid',name='Bad',country_code='DEU'),422)
        self.assertEqual(self.client.get('/api/v1/live').json()['officials'],[])

    def test_official_assignment_validation_and_omitted_field_preserved(self):
        self.select(self.imported())
        plan = self.match_plan(); original = plan['officials']
        for officials in (['missing'],[original[0],original[0]]):
            before = self.snapshot()
            self.configure('matches',{**plan,'officials':officials},422)
            self.assertEqual(self.snapshot(),before)
        del plan['officials']
        self.configure('matches',{**plan,'round':'Korrigierte Runde'})
        self.assertEqual(self.snapshot()['matches'][0]['officials'],original)
        self.configure('matches',{**plan,'officials':[]})
        self.action('select')
        self.assertEqual(self.client.get('/api/v1/live').json()['officials'],[])

    def test_officials_survive_all_live_actions_and_restart(self):
        event_id = self.imported(); self.select(event_id)
        original = self.snapshot()['matches'][0]['officials']
        referees = self.snapshot()['referees']
        # Bisherige Felder unverändert, Funktion und Reihenfolge additiv.
        expected = [{**next(r for r in referees if r['id']==rid),'position':index,'role':'referee','role_label_en':'Referee'}
                    for index,rid in enumerate(original,start=1)]
        def check():
            self.assertEqual(self.snapshot()['matches'][0]['officials'],original)
            self.assertEqual(self.client.get('/api/v1/matches').json()[0]['officials'],original)
            self.assertEqual(self.client.get('/api/v1/live').json()['officials'],expected)
        self.action('select'); check()
        self.action('prepare',participant_1='bsc-praha',participant_2='kairat-almaty',side_l='kairat-almaty',side_r='bsc-praha'); check()
        self.action('unprepare'); check()
        self.prepare(); check()
        for operation in ('switch-sides','start','score','score','pause','switch-sides','resume','undo'):
            self.action(operation); check()
        before = self.snapshot()['matches']
        self.client.__exit__(None,None,None); self.start()
        check()
        self.assertEqual(self.snapshot()['matches'],before)
        self.assertEqual(self.snapshot()['referees'],referees)
        self.action('finish'); check()

    def test_prague_import_export_reimport_preserves_referees_and_order(self):
        self.assertEqual((ROOT/'imports/prague-2026.json').read_bytes(),(ROOT/'examples/prague-2026.json').read_bytes())
        preview = self.preview()
        self.assertEqual((preview['participants'],preview['referees'],preview['matches']),(6,6,14))
        first = self.imported()
        exported = self.client.get(f'/api/v1/event-catalog/{first}/export').text
        self.assertEqual(State.model_validate_json(exported),State.model_validate_json(SAMPLE))
        preview = self.preview(text=exported,event_id=first)
        response = self.post('import',json_text=exported,event_id=first,preview_token=preview['preview_token'],as_new=True)
        self.assertEqual(response.status_code,200,response.text)
        second = response.json()['created_event_id']
        self.assertNotEqual(first,second)
        self.assertEqual(load(self.directory/'events'/f'{first}.json'),load(self.directory/'events'/f'{second}.json'))

    def test_two_websockets_receive_official_assignments_and_names(self):
        self.select(self.imported()); self.action('select')
        plan = self.match_plan(); plan['officials'].reverse()
        with self.client.websocket_connect('/api/v1/ws') as a, self.client.websocket_connect('/api/v1/ws') as b:
            a.receive_json(); b.receive_json()
            self.configure('matches',plan)
            first,second = a.receive_json(),b.receive_json()
            self.assertEqual(first,second)
            self.assertEqual([r['id'] for r in first['live']['officials']],plan['officials'])
            person = {key:first['live']['officials'][0][key] for key in ('id','name','country_code')}
            self.configure('referees',{**person,'name':'Updated Official'})
            first,second = a.receive_json(),b.receive_json()
            self.assertEqual(first,second)
            self.assertEqual(first['live']['officials'][0]['name'],'Updated Official')


class MigrationTest(unittest.TestCase):
    def test_data_dir_config_and_custom_legacy_file(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory=Path(directory); config=directory/'server.yml'
            config.write_text('bind_host: 127.0.0.1\nport: 8730\ndata_file: custom.json\n')
            (directory/'custom.json').write_text(SAMPLE)
            loaded = load_config(config)
            self.assertEqual(loaded.data_dir,directory.resolve())
            with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_file=loaded.data_file,data_dir=loaded.data_dir)) as client:
                self.assertEqual(len(client.get('/api/v1/event-catalog').json()['items']),1)
            self.assertEqual((directory/'custom.json').read_text(),SAMPLE)
            config.write_text('bind_host: 127.0.0.1\nport: 8730\ndata_dir: separate\n')
            self.assertEqual(load_config(config).data_dir,(directory/'separate').resolve())
            config.write_text(config.read_text()+'data_file: custom.json\n')
            with self.assertRaises(ValidationError): load_config(config)

    def test_existing_conflicting_event_and_missing_active_file_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory=Path(directory); legacy=directory/'tournament.json'; legacy.write_text(SAMPLE)
            save(directory/'events'/'other.json',State())
            original = (directory/'events'/'other.json').read_bytes()
            with self.assertRaises(ValueError):
                with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_dir=directory)): pass
            self.assertEqual((directory/'events'/'other.json').read_bytes(),original)
            self.assertEqual(legacy.read_text(),SAMPLE)
            (directory/'active-event.json').write_text(json.dumps({'active_event_id':'missing','selection_token':str(uuid4())}))
            with self.assertRaises(ValueError):
                with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_dir=directory)): pass

    def test_legacy_copy_restores_live_state_without_touching_original(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory = Path(directory); legacy = directory/'tournament.json'
            state = State.model_validate_json(SAMPLE)
            match = state.matches[0]; state.active_match_id = match.id
            match.status='paused'; match.side_l=match.participant_1; match.side_r=match.participant_2
            match.scores={match.participant_1:2,match.participant_2:1}
            save(legacy,state); original = legacy.read_bytes()
            for _ in range(2):
                with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_dir=directory)) as client:
                    snap = client.get('/api/v1/tournament').json()
                    self.assertEqual(snap['live']['left']['score'],2)
                    self.assertEqual(snap['live']['status'],'paused')
                    self.assertEqual(len(client.get('/api/v1/event-catalog').json()['items']),1)
                    self.assertEqual(load(directory/'events'/f"{snap['active_event_id']}.json"),state)
                self.assertEqual(legacy.read_bytes(),original)

    def test_lock_without_legacy_is_empty(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory=Path(directory); (directory/'tournament.json.lock').touch()
            with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_dir=directory)) as client:
                self.assertEqual(client.get('/api/v1/event-catalog').json()['items'],[])

    def test_invalid_legacy_never_replaced(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory=Path(directory); legacy=directory/'tournament.json'; legacy.write_text('{broken')
            with self.assertRaises(ValidationError):
                with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_dir=directory)): pass
            self.assertEqual(legacy.read_text(),'{broken')
            self.assertFalse((directory/'active-event.json').exists())

    def test_interrupted_migration_reuses_identical_copy(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory=Path(directory); legacy=directory/'tournament.json'; legacy.write_text(SAMPLE)
            from livescore import storage
            real = storage.atomic_write
            def fail_pointer(path, text):
                if path.name == 'active-event.json': raise OSError('interrupted')
                real(path,text)
            with patch('livescore.storage.atomic_write',side_effect=fail_pointer):
                with self.assertRaises(OSError):
                    with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_dir=directory)): pass
            self.assertEqual(len(list((directory/'events').glob('*.json'))),1)
            with TestClient(create_app(auth_config=AuthConfig(enabled=False), data_dir=directory)) as client:
                self.assertEqual(len(client.get('/api/v1/event-catalog').json()['items']),1)
            self.assertEqual(legacy.read_text(),SAMPLE)


class OfficialModelTest(unittest.TestCase):
    def test_zero_one_three_and_more_than_three_preserve_order(self):
        from livescore.service import live_view
        sample = json.loads(SAMPLE)
        ids = [r['id'] for r in sample['referees']][::-1]
        for count in (0,1,3,6):
            with self.subTest(count=count):
                sample['matches'][0]['officials'] = ids[:count]
                sample['active_match_id'] = 'match-001'
                state = State.model_validate(sample)
                self.assertEqual(state.matches[0].officials,ids[:count])
                self.assertEqual([r['id'] for r in live_view(state)['officials']],ids[:count])

    def test_duplicate_referee_or_unknown_duplicate_official_rejected(self):
        for kind in ('referee','duplicate','unknown'):
            sample = json.loads(SAMPLE)
            if kind == 'referee': sample['referees'].append(sample['referees'][0])
            elif kind == 'duplicate': sample['matches'][0]['officials'] *= 2
            else: sample['matches'][0]['officials'] = ['missing']
            with self.subTest(kind=kind), self.assertRaises(ValidationError): State.model_validate(sample)

    def test_optional_fields_without_schema_migration(self):
        sample = json.loads(SAMPLE); del sample['referees']
        for match in sample['matches']: del match['officials']
        state = State.model_validate(sample)
        self.assertEqual(state.schema_version,1)
        self.assertEqual(state.referees,[])
        self.assertTrue(all(m.officials == [] for m in state.matches))

    def test_real_prague_fixture(self):
        sample = State.model_validate_json((ROOT/'imports/prague-2026.json').read_text())
        self.assertEqual((len(sample.participants),len(sample.referees),len(sample.matches)),(6,6,14))
        self.assertTrue(all(len(match.officials)==3 for match in sample.matches))
        self.assertEqual(next(r.name for r in sample.referees if r.id=='luis-ramon-perez-macias'),'Luis Ramon Pérez Macias')
        self.assertNotIn('Peréz',sample.model_dump_json())
