"""Abschnittspausen ohne Sportregeln; Wiederöffnen und Legacy-Status."""
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from livescore.app import create_app
from livescore.auth import AuthConfig
from livescore.models import SportProfile
from livescore.storage import load, save

ROOT = Path(__file__).resolve().parents[1]


class SectionsTest(unittest.TestCase):
    def test_profiles_breaks_reopen_restart_and_participant_binding(self):
        profiles = [('blind_football', 'Halbzeit', 2), ('football', 'Half', 2),
                    ('handball', 'Poločas', 2), ('boxing', 'Runde', 3),
                    ('showdown', 'Satz', 5), ('other', 'Durchgang', 4),
                    ('single', 'Abschnitt', 1), ('no_profile', None, 1)]
        for sport, label, count in profiles:
            with self.subTest(sport=sport), tempfile.TemporaryDirectory(dir=ROOT / '.test-artifacts') as directory:
                path = Path(directory) / 'state.json'
                state = load(ROOT / 'examples/prague-2026.json')
                state.event.sport_profile = SportProfile(sport=sport, period_label=label, periods=count,
                    counters=[dict(id='per_period', label='Counter', reset_each_period=True),
                              dict(id='total', label='Total', reset_each_period=False)]) if label else None
                for match in state.matches:
                    match.counters = {}
                save(path, state)

                def app():
                    return create_app(data_file=path, auth_config=AuthConfig(enabled=False))

                with TestClient(app()) as client:
                    def snapshot():
                        return client.get('/api/v1/tournament').json()

                    def action(operation, expected=200, **fields):
                        s = snapshot()
                        match = next((m for m in s['matches'] if m['id'] == s['active_match_id']), None)
                        payload = dict(request_id=str(uuid4()), event_id=s['active_event_id'],
                                       selection_token=s['selection_token'], match_id='match-001', **fields)
                        if operation in ('score', 'counter'):
                            payload['control_revision'] = match['control_revision']
                        else:
                            payload['expected_revision'] = s['revision']
                        response = client.post('/api/v1/live/' + operation, json=payload)
                        self.assertEqual(response.status_code, expected, response.text)
                        return response.json()

                    action('select')
                    action('prepare', participant_1='bsc-praha', participant_2='fc-ingolstadt-04',
                           side_l='bsc-praha', side_r='fc-ingolstadt-04')
                    action('start')
                    for side, pid in [('L', 'bsc-praha'), ('L', 'bsc-praha'), ('R', 'fc-ingolstadt-04')]:
                        action('score', side=side, participant_id=pid, delta=1)
                    action('switch-sides')

                    for period in range(1, count + 1):
                        if label:
                            for counter in ('per_period', 'total'):
                                action('counter', participant_id='bsc-praha', counter_id=counter,
                                       period=period, delta=1)
                        before = client.get('/api/v1/live').json()
                        action('period', expected=409, period=period)
                        if period < count:
                            with client.websocket_connect('/api/v1/ws') as a, client.websocket_connect('/api/v1/ws') as b:
                                a.receive_json(); b.receive_json()
                                changed = action('intermission', intermission=True)
                                for ws in (a, b):
                                    self.assertEqual(ws.receive_json(), changed)
                            live = changed['live']
                            self.assertEqual(live['status'], 'live')
                            self.assertTrue(live['period_info']['intermission'])
                            self.assertEqual(live['right'], before['right'])
                            action('intermission', intermission=False)
                            self.assertFalse(snapshot()['live']['period_info']['intermission'])
                            action('intermission', intermission=True)
                            action('period', expected=409, period=period + 2)
                            action('period', period=period + 1)
                            live = snapshot()['live']
                            self.assertFalse(live['period_info']['intermission'])
                            self.assertEqual(live['right']['counters'], {'per_period': 0, 'total': period})
                        else:
                            action('intermission', expected=409, intermission=True)
                            action('period', expected=409, period=period + 1)

                    before = snapshot()['live']
                    action('finish')
                    reopened = action('reopen')
                    self.assertEqual(reopened['matches'][0]['status'], 'live')
                    self.assertEqual(reopened['live']['status'], 'live')
                    for key in ('left', 'right', 'officials', 'period', 'period_info'):
                        self.assertEqual(reopened['live'][key], before[key])
                    self.assertTrue(reopened['can_undo'])
                    action('undo')
                    self.assertEqual(snapshot()['live']['left']['score'], 0)
                    action('score', side='L', participant_id='fc-ingolstadt-04', delta=1)
                    expected = snapshot()['live']
                    # Export remains schema-v1 and contains a directly usable live match.
                    event_id = snapshot()['active_event_id']
                    exported = client.get(f'/api/v1/event-catalog/{event_id}/export').json()
                    self.assertEqual(exported['schema_version'], 1)
                    self.assertEqual(exported['matches'][0]['status'], 'live')
                with TestClient(app()) as client:
                    actual=client.get('/api/v1/live').json()
                    self.assertNotEqual(actual['source']['instance_id'],expected['source']['instance_id'])
                    expected['source']=actual['source']
                    self.assertEqual(actual,expected)

    def test_legacy_pause_is_preserved_but_live_projection_is_consistent(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.test-artifacts') as directory:
            path = Path(directory) / 'state.json'
            state = load(ROOT / 'examples/prague-2026.json')
            state.active_match_id = 'match-001'
            match = state.matches[0]
            match.status = 'paused'
            match.side_l, match.side_r = match.participant_1, match.participant_2
            match.scores = {match.participant_1: 2, match.participant_2: 1}
            save(path, state)
            original = path.read_bytes()
            with TestClient(create_app(data_file=path, auth_config=AuthConfig(enabled=False))) as client:
                snapshot = client.get('/api/v1/tournament').json()
                live = client.get('/api/v1/live').json()
                self.assertEqual(snapshot['matches'][0]['status'], 'paused')
                self.assertEqual(live['status'], 'live')
                self.assertEqual(snapshot['live'], live)
                with client.websocket_connect('/api/v1/ws') as ws:
                    self.assertEqual(ws.receive_json()['live'], live)
                self.assertEqual((live['left']['score'], live['right']['score']), (2, 1))
                schema = client.get('/openapi.json').json()
                for route in ('pause', 'resume'):
                    self.assertNotIn('/api/v1/live/'+route,schema['paths'])
            self.assertEqual(path.read_bytes(), original)
