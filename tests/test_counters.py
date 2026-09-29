"""Generische Abschnitte/Counter, ohne sportartspezifische Service-Logik."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError

from livescore.auth import AuthConfig
from livescore.app import create_app
from livescore.models import Participant, State
from livescore.storage import load, save

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.test-artifacts'


class CounterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.directory = Path(self.temp.name)
        (self.directory / 'events').mkdir()
        self.path = self.directory / 'events' / 'prague.json'
        save(self.path, load(ROOT / 'imports/prague-2026.json'))
        self.restart()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.client.__exit__(None, None, None))
        state = self.state()
        self.client.post('/api/v1/event-catalog/select', json=dict(
            request_id=str(uuid4()), catalog_session=state['stream_id'],
            selection_token=state['selection_token'], event_id='prague')).raise_for_status()

    def restart(self):
        if hasattr(self, 'client'):
            self.client.__exit__(None, None, None)
        self.client = TestClient(create_app(auth_config=AuthConfig(enabled=False), data_dir=self.directory)).__enter__()

    def state(self):
        return self.client.get('/api/v1/tournament').json()

    def context(self):
        s = self.state()
        return dict(event_id=s['active_event_id'], selection_token=s['selection_token'])

    def request(self, operation, status=200, **fields):
        body = dict(request_id=str(uuid4()), expected_revision=self.state()['revision'], **self.context(), **fields)
        response = self.client.post('/api/v1/' + operation, json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def action(self, operation, status=200, **fields):
        return self.request('live/' + operation, status, match_id='match-001', **fields)

    def start(self):
        self.action('select')
        self.action('prepare', participant_1='bsc-praha', participant_2='fc-ingolstadt-04', side_l='bsc-praha', side_r='fc-ingolstadt-04')
        self.action('start')

    def payload(self, **fields):
        match = self.state()['matches'][0]
        return dict(request_id=str(uuid4()), **self.context(), match_id=match['id'],
                    control_revision=match['control_revision'], period=match['period'],
                    participant_id='bsc-praha', counter_id='team_fouls', delta=1, **fields)

    def counter(self, status=200, **changes):
        payload = self.payload(); payload.update(changes)
        response = self.client.post('/api/v1/live/counter', json=payload)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def test_country_config_and_live(self):
        self.request('config/participants', data=dict(id='bsc-praha', name='BSC Praha', country_code=' cz '))
        self.request('config/participants', data=dict(id='bsc-praha', name='BSC Praha'))
        self.assertEqual(self.state()['participants'][0]['country_code'], 'CZ')
        self.request('config/participants', status=422, data=dict(id='bsc-praha', name='BSC', country_code='CZE'))
        self.start()
        self.assertEqual(self.state()['live']['left']['country_code'], 'CZ')
        self.assertEqual(self.state()['live']['right']['country_code'], 'DE')
        self.assertEqual(Participant(id='a', name='A').country_code, '')

    def test_counter_thresholds_decrement_no_limit_and_independent_score(self):
        self.start(); self.counter(status=409, delta=-1)
        for value in range(1, 8):
            live = self.counter()['live']
            self.assertEqual(live['left']['counters']['team_fouls'], value)
            self.assertEqual(live['left']['counter_states']['team_fouls'], 'critical' if value >= 5 else 'warning' if value == 4 else 'normal')
            self.assertEqual(live['left']['score'], 0)
        self.counter(delta=-1)
        self.assertEqual(self.state()['live']['left']['counters']['team_fouls'], 6)
        for _ in range(6): self.counter(delta=-1)
        self.counter(status=409, delta=-1)
        self.counter(status=422, delta=0)
        self.counter(status=422, delta=True)
        self.counter(status=409, counter_id='unknown')
        self.counter(status=409, participant_id='kairat-almaty')

    def test_sides_periods_history_officials_restart(self):
        self.start()
        for _ in range(3): self.counter()
        self.counter(participant_id='fc-ingolstadt-04')
        m = self.state()['matches'][0]
        self.client.post('/api/v1/live/score', json=dict(request_id=str(uuid4()), **self.context(), match_id=m['id'], control_revision=m['control_revision'], participant_id='bsc-praha', side='L', delta=1)).raise_for_status()
        before = self.state()['matches'][0]
        self.action('switch-sides')
        live = self.state()['live']
        self.assertEqual(live['right']['id'], 'bsc-praha')
        self.assertEqual(live['right']['counters'], {'team_fouls': 3})
        self.assertEqual(live['left']['counters'], {'team_fouls': 1})
        self.action('pause')
        self.action('period', period=2)
        after = self.state()['matches'][0]
        self.assertEqual(after['status'], 'paused')
        self.assertEqual(after['side_l'], 'fc-ingolstadt-04')
        self.assertEqual(after['scores'], before['scores'])
        self.assertEqual(after['officials'], before['officials'])
        self.assertEqual(after['counters']['team_fouls']['bsc-praha'], {'1': 3, '2': 0})
        self.assertEqual(self.state()['live']['right']['counters'], {'team_fouls': 0})
        self.counter(); self.action('resume')
        expected = self.state()
        self.restart()
        restored = self.state()
        for key in ('matches', 'event', 'participants', 'referees', 'live'):
            self.assertEqual(restored[key], expected[key])
        self.assertEqual(load(self.path).matches[0].counters['team_fouls']['bsc-praha'], {'1': 3, '2': 1})
        log = self.client.get('/api/v1/events').json()
        self.assertTrue(any(e['type'] == 'counter' and e['period'] == 2 for e in log))
        self.assertTrue(any(e['type'] == 'period_changed' and e['period'] == 2 for e in log))

    def test_period_validation_dedup_and_stale_actions(self):
        self.action('select')
        self.action('period', status=409, period=2)
        self.counter(status=409)
        self.action('prepare', participant_1='bsc-praha', participant_2='fc-ingolstadt-04', side_l='bsc-praha', side_r='fc-ingolstadt-04')
        self.action('period', status=409, period=2)
        self.action('start')
        stale = self.payload()
        self.action('period', status=409, period=1)
        self.action('period', status=409, period=3)
        body = dict(request_id=str(uuid4()), expected_revision=self.state()['revision'], **self.context(), match_id='match-001', period=2)
        self.client.post('/api/v1/live/period', json=body).raise_for_status()
        self.client.post('/api/v1/live/period', json=body).raise_for_status()
        self.assertEqual(self.client.post('/api/v1/live/counter', json=stale).status_code, 409)
        self.action('period', status=409, period=2)
        self.action('period', status=409, period=3)
        self.action('finish')
        self.counter(status=409)
        self.action('period', status=409, period=2)

    def test_stale_counter_after_side_switch_pause_and_period(self):
        self.start()
        for operation, fields in [('switch-sides', {}), ('pause', {}), ('resume', {}), ('period', {'period':2})]:
            old = self.payload()
            self.action(operation, **fields)
            self.assertEqual(self.client.post('/api/v1/live/counter', json=old).status_code, 409)

    def test_parallel_counters_and_persistent_deduplication(self):
        self.start()
        requests = [self.payload() for _ in range(20)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda p: self.client.post('/api/v1/live/counter', json=p), requests))
        self.assertTrue(all(r.status_code == 200 for r in results))
        self.assertEqual(self.state()['live']['left']['counters']['team_fouls'], 20)
        self.restart()
        self.client.post('/api/v1/live/counter', json=requests[0]).raise_for_status()
        self.assertEqual(self.state()['live']['left']['counters']['team_fouls'], 20)
        requests[0]['delta'] = -1
        self.assertEqual(self.client.post('/api/v1/live/counter', json=requests[0]).status_code, 409)

    def test_two_websockets_counter_and_period(self):
        self.start()
        with self.client.websocket_connect('/api/v1/ws') as a, self.client.websocket_connect('/api/v1/ws') as b:
            a.receive_json(); b.receive_json()
            changed = self.counter()
            self.assertEqual(a.receive_json(), changed); self.assertEqual(b.receive_json(), changed)
            changed = self.action('period', period=2)
            self.assertEqual(a.receive_json(), changed); self.assertEqual(b.receive_json(), changed)

    def test_config_preserves_profile_and_rejects_changes_after_start(self):
        event = self.state()['event']; profile = event.pop('sport_profile')
        self.request('config/event', data=event)
        self.assertEqual(self.state()['event']['sport_profile'], profile)
        self.start(); self.action('finish')
        event['sport_profile'] = None
        self.request('config/event', status=409, data=event)
        self.assertEqual(self.state()['event']['sport_profile'], profile)

    def test_generic_nonreset_counter_carries_forward(self):
        event = self.state()['event']
        event['sport_profile']['sport'] = 'generic'
        event['sport_profile']['period_label'] = 'Runde'
        event['sport_profile']['periods'] = 3
        event['sport_profile']['counters'].append(dict(id='warnings', label='Hinweise', reset_each_period=False))
        self.request('config/event', data=event)
        self.start()
        for _ in range(2): self.counter(counter_id='warnings')
        self.action('period', period=2)
        self.assertEqual(self.state()['live']['left']['counters']['warnings'], 2)
        self.counter(counter_id='warnings', delta=-1)
        self.action('period', period=3)
        self.assertEqual(self.state()['matches'][0]['counters']['warnings']['bsc-praha'], {'1':2, '2':1, '3':1})

    def test_export_reimport_preserves_all_fields_and_history(self):
        self.start(); self.counter(); self.action('period', period=2); self.counter()
        exported = self.client.get('/api/v1/event-catalog/prague/export').json()
        self.assertEqual(exported['schema_version'], 1)
        self.assertEqual(len(exported['participants']), 6)
        self.assertEqual(len(exported['referees']), 6)
        self.assertEqual(len(exported['matches']), 14)
        self.assertTrue(all(len(m['officials']) == 3 for m in exported['matches']))
        self.assertEqual(exported['matches'][0]['counters']['team_fouls']['bsc-praha'], {'1':1, '2':1})
        raw = json.dumps(exported)
        preview = self.client.post('/api/v1/event-catalog/import/preview', json=dict(json_text=raw, event_id='copy')).json()
        response = self.client.post('/api/v1/event-catalog/import', json=dict(request_id=str(uuid4()), catalog_session=self.state()['stream_id'], json_text=raw, event_id='copy', preview_token=preview['preview_token']))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/api/v1/event-catalog/copy/export').json(), exported)

    def test_prepare_correct_pairing_and_officials_preserved(self):
        before = self.state()['matches'][0]['officials']
        self.action('select')
        for p2 in ('fc-ingolstadt-04', 'kairat-almaty'):
            self.action('prepare', participant_1='bsc-praha', participant_2=p2, side_l=p2, side_r='bsc-praha')
            match = self.state()['matches'][0]
            self.assertEqual(set(match['counters']['team_fouls']), {'bsc-praha', p2})
            self.assertEqual(match['officials'], before)
            self.action('unprepare')


class CounterModelTest(unittest.TestCase):
    def test_invalid_profiles_and_counter_states_rejected(self):
        original = json.loads((ROOT / 'imports/prague-2026.json').read_text())
        invalid = []
        for key, value in [('period', 3), ('period', True), ('period', 2), ('counters', {'unknown': {}}), ('counters', {'team_fouls': {'unknown': {'1': 0}}})]:
            data = deepcopy(original); data['matches'][0][key] = value; invalid.append(data)
        for period, value in [('0',0), ('01',0), ('3',0), ('1',-1), ('1',True), ('1',1), ('2',1)]:
            data = deepcopy(original); data['matches'][0]['counters']['team_fouls']['bsc-praha'] = {period:value}; invalid.append(data)
        for change in [dict(scope='global'), dict(warning_at=5,critical_at=4), dict(warning_at=-1)]:
            data = deepcopy(original); data['event']['sport_profile']['counters'][0].update(change); invalid.append(data)
        data = deepcopy(original); data['event']['sport_profile']['counters'] *= 2; invalid.append(data)
        for data in invalid:
            with self.subTest(data=data['matches'][0]['counters']):
                with self.assertRaises(ValidationError): State.model_validate(data)

    def test_optional_defaults_and_real_prague(self):
        self.assertIsNone(State().event)
        data = json.loads((ROOT / 'imports/prague-2026.json').read_text())
        self.assertEqual(data, json.loads((ROOT / 'examples/prague-2026.json').read_text()))
        self.assertEqual([p['country_code'] for p in data['participants']], ['CZ','DE','KZ','GR','DE','DE'])
        state = State.model_validate(data)
        self.assertEqual((len(state.participants),len(state.referees),len(state.matches)), (6,6,14))
        for m in state.matches:
            self.assertEqual(m.period, 1)
            self.assertEqual(len(m.officials), 3)
            self.assertTrue(all(v == 0 for h in m.counters['team_fouls'].values() for v in h.values()))
        data['event'].pop('sport_profile')
        for m in data['matches']:
            m.pop('period'); m.pop('counters')
        for p in data['participants']: p.pop('country_code')
        state = State.model_validate(data)
        self.assertIsNone(state.event.sport_profile)
        self.assertEqual(state.matches[0].period, 1)
        self.assertEqual(state.matches[0].counters, {})


if __name__ == '__main__':
    unittest.main()
