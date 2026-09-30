"""Öffentliche Live-API: Spielperiode/Halbzeitpause, Turnierphase, Runde, Officials, Nationen."""
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
from livescore.models import State
from livescore.storage import load

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.test-artifacts'
ARTIFACTS.mkdir(exist_ok=True)
PRAGUE = json.loads((ROOT / 'imports/prague-2026.json').read_text())
# Felder und Typen des LiveScore-0.1.0-Vertrags, wie sie bestehende Clients (GFX) prüfen.
OLD_TOP = {'status', 'revision', 'match_id', 'play_area', 'left', 'right', 'officials', 'period'}
OLD_SIDE = {'id': str, 'name': str, 'short_name': str, 'country_code': str, 'score': int,
            'counters': dict, 'counter_states': dict}
OLD_OFFICIAL = {'id': str, 'name': str, 'country_code': str}


class LiveMetadataTest(unittest.TestCase):
    def setUp(self, data=PRAGUE):
        self.temp = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.directory = Path(self.temp.name)
        (self.directory / 'events').mkdir()
        self.path = self.directory / 'events' / 'prague.json'
        # Rohes JSON: Bestandsdateien ohne neue Felder werden so geladen, wie sie auf Platte liegen.
        self.path.write_text(json.dumps(data, ensure_ascii=False))
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

    def live(self):
        return self.client.get('/api/v1/live').json()

    def request(self, operation, status=200, **fields):
        s = self.state()
        body = dict(request_id=str(uuid4()), expected_revision=s['revision'], event_id=s['active_event_id'],
                    selection_token=s['selection_token'], **fields)
        response = self.client.post('/api/v1/' + operation, json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def action(self, operation, status=200, match_id='match-001', **fields):
        return self.request('live/' + operation, status, match_id=match_id, **fields)

    def start(self, match_id='match-001', p1='bsc-praha', p2='fc-ingolstadt-04'):
        self.action('select', match_id=match_id)
        self.action('prepare', match_id=match_id, participant_1=p1, participant_2=p2, side_l=p1, side_r=p2)
        self.action('start', match_id=match_id)

    def score(self, side, participant_id):
        s = self.state(); m = next(m for m in s['matches'] if m['id'] == s['active_match_id'])
        self.client.post('/api/v1/live/score', json=dict(
            request_id=str(uuid4()), event_id=s['active_event_id'], selection_token=s['selection_token'],
            match_id=m['id'], control_revision=m['control_revision'], participant_id=participant_id,
            side=side, delta=1)).raise_for_status()

    def foul(self, participant_id):
        s = self.state(); m = next(m for m in s['matches'] if m['id'] == s['active_match_id'])
        self.client.post('/api/v1/live/counter', json=dict(
            request_id=str(uuid4()), event_id=s['active_event_id'], selection_token=s['selection_token'],
            match_id=m['id'], control_revision=m['control_revision'], period=m['period'],
            participant_id=participant_id, counter_id='team_fouls', delta=1)).raise_for_status()

    def phase(self):
        info = self.live()['period_info']
        return info['code'], info['label_en'], info['number'], info['intermission']

    def assert_compatible(self, live):
        """Alle bisherigen Felder bleiben mit unverändertem Typ vorhanden."""
        self.assertLessEqual(OLD_TOP, set(live))
        self.assertIsInstance(live['period'], int)
        for side in ('left', 'right'):
            for key, kind in OLD_SIDE.items():
                self.assertIsInstance(live[side][key], kind, key)
        for official in live['officials']:
            for key, kind in OLD_OFFICIAL.items():
                self.assertIsInstance(official[key], kind, key)

    def test_stored_metadata_stage_round_officials_before_start(self):
        self.action('select')
        live = self.live()
        self.assertEqual(live['status'], 'scheduled')
        self.assertEqual(live['stage'], dict(code='group_stage', name='Gruppenphase', label_en='Group stage'))
        self.assertEqual(live['round'], dict(code='group_a', name='Gruppe A', label_en='Group A'))
        self.assertEqual(live['period_info'], dict(number=1, intermission=False, code='not_started', label_en='Not started'))
        self.assertEqual(live['officials'], [
            dict(id='luis-ramon-perez-macias', name='Luis Ramon Pérez Macias', country_code='ES', position=1, role='referee', role_label_en='Referee'),
            dict(id='bennet-kruekemeier', name='Bennet Krükemeier', country_code='DE', position=2, role='referee', role_label_en='Referee'),
            dict(id='juan-carlos-paule', name='Juan Carlos Paule', country_code='ES', position=3, role='referee', role_label_en='Referee'),
        ])
        self.assertIsNone(live['left'])

    def test_all_known_stage_and_round_labels(self):
        expected = {
            'match-003': (('group_stage', 'Group stage'), ('group_a', 'Group A')),
            'match-010': (('play_offs', 'Play-offs'), ('semi_final_1', 'Semi-final 1')),
            'match-011': (('play_offs', 'Play-offs'), ('semi_final_2', 'Semi-final 2')),
            'match-012': (('play_offs', 'Play-offs'), ('fifth_place_match', '5th-place match')),
            'match-013': (('play_offs', 'Play-offs'), ('bronze_medal_match', 'Bronze medal match')),
            'match-014': (('play_offs', 'Play-offs'), ('gold_medal_match', 'Gold medal match')),
        }
        for match_id, (stage, round_) in expected.items():
            with self.subTest(match_id):
                self.action('select', match_id=match_id)
                live = self.live()
                self.assertEqual((live['stage']['code'], live['stage']['label_en']), stage)
                self.assertEqual((live['round']['code'], live['round']['label_en']), round_)
                self.assertNotEqual(live['stage']['name'], live['round']['name'])
        # Officials mit Sonderzeichen in Spielreihenfolge (Match 12: Pérez, Raschke, Jeszo).
        self.action('select', match_id='match-012')
        self.assertEqual([(o['position'], o['name']) for o in self.live()['officials']],
                         [(1, 'Luis Ramon Pérez Macias'), (2, 'Carsten Raschke'), (3, 'Tamás Jeszo')])

    def test_unknown_labels_override_empty_values_and_editor_compatibility(self):
        plan = {k: v for k, v in self.state()['matches'][1].items() if k in (
            'id', 'date', 'time', 'play_area_id', 'participant_1', 'participant_2', 'officials')}
        self.request('config/matches', data=dict(plan, stage='Hauptrunde', round='Gruppe b'))
        self.action('select', match_id='match-002')
        live = self.live()
        self.assertEqual(live['stage'], dict(code=None, name='Hauptrunde', label_en=None))
        self.assertEqual(live['round'], dict(code='group_b', name='Gruppe b', label_en='Group B'))
        self.request('config/matches', data=dict(plan, stage='Hauptrunde', stage_label='Main round', round='Viertelfinale'))
        live = self.live()
        self.assertEqual(live['stage'], dict(code=None, name='Hauptrunde', label_en='Main round'))
        self.assertEqual(live['round'], dict(code=None, name='Viertelfinale', label_en=None))
        # Ein älterer Client ohne die neuen Felder löscht sie nicht.
        self.request('config/matches', data=dict(plan, round='Viertelfinale'))
        self.assertEqual(self.live()['stage']['label_en'], 'Main round')
        self.request('config/matches', data=dict(plan, stage='', stage_label='', round='', officials=[]))
        live = self.live()
        self.assertEqual((live['stage'], live['round'], live['officials']), (None, None, []))

    def test_nations_present_missing_and_bound_to_participant(self):
        self.start(match_id='match-002', p1='kairat-almaty', p2='asamea-keravnos')
        live = self.live()
        self.assertEqual((live['left']['country_code'], live['right']['country_code']), ('KZ', 'GR'))
        self.action('finish', match_id='match-002')
        # Nation fehlt: bleibt gemäß bestehendem Vertrag "", nichts wird aus Name/Ort geraten.
        self.request('config/participants', data=dict(id='fc-schalke-04', name='FC Schalke 04', short_name='S04', country_code=''))
        self.action('select', match_id='match-003')
        self.action('prepare', match_id='match-003', participant_1='blista-marburg', participant_2='fc-schalke-04',
                    side_l='blista-marburg', side_r='fc-schalke-04')
        live = self.live()
        self.assertEqual((live['left']['country_code'], live['right']['country_code']), ('DE', ''))
        # Korrigierte Paarung: die Nation des neuen Teilnehmers, keine Übernahme vom vorherigen Platz.
        self.action('prepare', match_id='match-003', participant_1='blista-marburg', participant_2='bsc-praha',
                    side_l='bsc-praha', side_r='blista-marburg')
        live = self.live()
        self.assertEqual((live['left']['id'], live['left']['country_code']), ('bsc-praha', 'CZ'))
        self.assertEqual((live['right']['id'], live['right']['country_code']), ('blista-marburg', 'DE'))

    def test_side_switch_keeps_name_nation_score_fouls_and_period(self):
        self.start()
        self.score('L', 'bsc-praha'); self.score('L', 'bsc-praha'); self.score('R', 'fc-ingolstadt-04')
        self.foul('bsc-praha')
        self.action('intermission', intermission=True)
        before = self.live()
        self.action('switch-sides')
        after = self.live()
        self.assertEqual(after['left'], before['right'])
        self.assertEqual(after['right'], before['left'])
        self.assertEqual((after['right']['name'], after['right']['country_code'], after['right']['score'],
                          after['right']['counters']['team_fouls']), ('BSC Praha', 'CZ', 2, 1))
        self.assertEqual((after['left']['name'], after['left']['country_code'], after['left']['score'],
                          after['left']['counters']['team_fouls']), ('FC Ingolstadt 04', 'DE', 1, 0))
        # Seitenwechsel ändert weder Periode noch Halbzeitpause.
        self.assertEqual(after['period_info'], before['period_info'])
        self.assertEqual(self.phase(), ('half_time', 'Half-time', 1, True))
        self.assert_compatible(after)

    def test_first_half_pause_half_time_second_half_full_time(self):
        self.action('select'); self.action('prepare', participant_1='bsc-praha', participant_2='fc-ingolstadt-04',
                                            side_l='bsc-praha', side_r='fc-ingolstadt-04')
        self.assertEqual(self.phase(), ('not_started', 'Not started', 1, False))
        self.action('intermission', status=409, intermission=True)
        self.action('start')
        self.assertEqual(self.phase(), ('first_half', '1st half', 1, False))
        self.action('pause')
        self.assertEqual(self.live()['status'], 'paused')
        self.assertEqual(self.phase(), ('first_half', '1st half', 1, False))  # normale Pause ≠ Halbzeit
        self.action('resume')
        self.action('intermission', intermission=True)
        self.assertEqual((self.live()['status'], *self.phase()), ('live', 'half_time', 'Half-time', 1, True))
        self.action('intermission', status=409, intermission=True)
        self.action('intermission', intermission=False)  # Korrektur
        self.assertEqual(self.phase(), ('first_half', '1st half', 1, False))
        self.action('intermission', intermission=True); self.action('pause')
        self.assertEqual((self.live()['status'], *self.phase()), ('paused', 'half_time', 'Half-time', 1, True))
        self.foul('bsc-praha')  # zählt weiter zur ersten Halbzeit
        self.action('period', period=2)
        self.assertEqual((self.live()['status'], *self.phase()), ('paused', 'second_half', '2nd half', 2, False))
        self.assertEqual(self.state()['matches'][0]['counters']['team_fouls']['bsc-praha'], {'1': 1, '2': 0})
        self.action('intermission', status=409, intermission=True)  # kein Abschnitt mehr danach
        self.action('resume'); self.action('finish')
        self.assertEqual(self.phase(), ('full_time', 'Full-time', 2, False))
        types = [e['type'] for e in self.client.get('/api/v1/events').json()]
        self.assertEqual(types.count('intermission_started'), 2)
        self.assertEqual(types.count('intermission_ended'), 1)
        # Nächstes Spiel beginnt neu, ohne Periode/Pause des vorherigen.
        self.action('select', match_id='match-002')
        self.assertEqual(self.phase(), ('not_started', 'Not started', 1, False))

    def test_finish_during_half_time_and_validation(self):
        self.start()
        self.action('intermission', intermission=True)
        self.action('intermission', status=422, intermission='yes')
        self.action('intermission', status=422)
        self.action('finish')
        self.assertEqual(self.phase(), ('full_time', 'Full-time', 1, False))
        self.action('intermission', status=409, intermission=False)

        def variant(status, period=1, intermission=False):
            data = deepcopy(PRAGUE); match = data['matches'][0]
            if status != 'scheduled':
                data['active_match_id'] = 'match-001'
                match.update(side_l='bsc-praha', side_r='fc-ingolstadt-04', scores={'bsc-praha': 0, 'fc-ingolstadt-04': 0})
            match.update(status=status, period=period, intermission=intermission)
            return data
        State.model_validate(variant('live', intermission=True))
        for args in (('scheduled',), ('ready',), ('live', 2), ('paused', 2), ('finished',)):
            with self.subTest(args):
                State.model_validate(variant(*args))  # gültige Basis
                with self.assertRaises(ValidationError):
                    State.model_validate(variant(*args, intermission=True))
        with self.assertRaises(ValidationError):
            State.model_validate(dict(variant('live'), matches=[dict(variant('live')['matches'][0], intermission=1)] + PRAGUE['matches'][1:]))

    def test_metadata_change_reaches_websocket_and_poll_without_score_change(self):
        self.start()
        before = self.live()
        with self.client.websocket_connect('/api/v1/ws') as a, self.client.websocket_connect('/api/v1/ws') as b:
            a.receive_json(); b.receive_json()
            changed = self.action('intermission', intermission=True)
            for ws in (a, b):
                self.assertEqual(ws.receive_json(), changed)
        after = self.live()
        self.assertEqual(changed['live'], after)
        self.assertGreater(after['revision'], before['revision'])
        self.assertEqual((after['left']['score'], after['right']['score']), (before['left']['score'], before['right']['score']))
        self.assertEqual(after['period_info']['code'], 'half_time')

    def test_restart_restores_half_time_and_metadata(self):
        self.start()
        self.foul('fc-ingolstadt-04')
        self.action('intermission', intermission=True)
        expected = self.live()
        self.restart()
        self.assertEqual(self.live(), expected)
        stored = load(self.path).matches[0]
        self.assertEqual((stored.intermission, stored.stage, stored.round), (True, 'Gruppenphase', 'Gruppe A'))
        self.assertEqual(expected['right']['counters'], {'team_fouls': 1})
        self.assertEqual(expected['left']['counters'], {'team_fouls': 0})  # echte 0, nicht fehlend

    def test_generic_profile_has_neutral_codes_without_football_labels(self):
        event = self.state()['event']
        event['sport_profile'].update(sport='showdown', period_label='Satz', periods=3)
        self.request('config/event', data=event)
        self.start()
        self.assertEqual(self.phase(), ('period_1', None, 1, False))
        self.action('intermission', intermission=True)
        self.assertEqual(self.phase(), ('intermission_after_1', None, 1, True))
        self.action('period', period=2)
        self.assertEqual(self.phase(), ('period_2', None, 2, False))
        self.action('finish')
        self.assertEqual(self.phase(), ('finished', None, 2, False))

    def test_without_profile_no_intermission_and_no_counters(self):
        data = json.loads(self.path.read_text())
        data['event'].pop('sport_profile')
        for match in data['matches']:
            match.pop('counters')
        self.path.write_text(json.dumps(data, ensure_ascii=False))
        self.restart()
        self.start()
        live = self.live()
        self.assertEqual(live['period_info'], dict(number=1, intermission=False, code='period_1', label_en=None))
        self.assertEqual((live['left']['counters'], live['left']['counter_states']), ({}, {}))  # nicht unterstützt
        self.action('intermission', status=409, intermission=True)

    def test_idle_has_null_metadata(self):
        live = self.live()
        self.assertEqual(live['status'], 'idle')
        self.assertEqual((live['period_info'], live['stage'], live['round'], live['officials']), (None, None, None, []))


class LegacyDataTest(LiveMetadataTest):
    """Bestandsdaten ohne stage/*_label/intermission bleiben ladbar und erfinden keine Angaben."""

    def setUp(self):
        data = deepcopy(PRAGUE)
        for match in data['matches']:
            match.pop('stage')
        super().setUp(data)

    def test_stored_metadata_stage_round_officials_before_start(self):
        self.action('select')
        live = self.live()
        self.assertIsNone(live['stage'])
        self.assertEqual(live['round']['label_en'], 'Group A')
        self.assertEqual(live['period_info']['code'], 'not_started')
        self.start_legacy_live()

    def start_legacy_live(self):
        self.action('prepare', participant_1='bsc-praha', participant_2='fc-ingolstadt-04',
                    side_l='bsc-praha', side_r='fc-ingolstadt-04')
        self.action('start')
        self.assertEqual(self.phase(), ('first_half', '1st half', 1, False))
        self.assertNotIn('intermission', json.loads(json.dumps(PRAGUE['matches'][0])))
        self.assert_compatible(self.live())

    # Die übrigen Szenarien setzen die Turnierphase aus der aktuellen Beispieldatei voraus.
    test_all_known_stage_and_round_labels = None
    test_restart_restores_half_time_and_metadata = None


if __name__ == '__main__':
    unittest.main()
