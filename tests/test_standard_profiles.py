"""Sieben Ausgangsprofile, Erfassungsmodi und atomare Bereitstellung."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
from livescore.models import SportProfile, State
from livescore.profiles import ProfileLibrary, provision_profiles, save_library, standard_profiles
from livescore.storage import load
import test_livescore as fixture

ROOT = Path(__file__).resolve().parents[1]


class ProvisionTest(unittest.TestCase):
    def test_no_event_has_unknown_display_and_automatic_library(self):
        from livescore.app import create_app
        from livescore.auth import AuthConfig
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts') as directory:
            with TestClient(create_app(data_dir=Path(directory),auth_config=AuthConfig(enabled=False))) as client:
                view=client.get('/api/v1/live').json()
                self.assertEqual(view['status'],'idle')
                self.assertIsNone(view['display']);self.assertIsNone(view['sport_profile'])
                self.assertIsNone(view['source']['event_id'])
                self.assertTrue(view['source']['available']);self.assertFalse(view['pairing_confirmed'])
                self.assertEqual(len(client.get('/api/v1/sport-profiles').json()['profiles']),7)

    def test_new_library_repeat_edits_collisions_and_deleted_defaults(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts') as directory:
            path=Path(directory)/'sport-profiles.json'
            library=provision_profiles(path)
            self.assertEqual(len(library.profiles),7)
            self.assertEqual(len(set(library.bundled_profiles)),7)
            original=path.read_bytes()
            provision_profiles(path)
            self.assertEqual(path.read_bytes(),original)
            library.profiles[0].profile.periods=4
            library.profiles.pop(1)
            library.profiles.append(library.profiles[0].model_copy(deep=True,update={'id':'custom'}))
            save_library(path,library)
            edited=path.read_bytes()
            provision_profiles(path)
            self.assertEqual(path.read_bytes(),edited)
            self.assertNotIn('standard-showdown',{p.id for p in provision_profiles(path).profiles})
            # An existing administrator profile with a bundled ID is not overwritten either.
            save_library(path,ProfileLibrary(profiles=[library.profiles[0]]))
            upgraded=provision_profiles(path)
            self.assertEqual(upgraded.profiles[0].profile.periods,4)
            self.assertEqual(len(upgraded.profiles),7)

    def test_atomic_failures_and_invalid_library_preserve_existing_bytes(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts') as directory:
            path=Path(directory)/'sport-profiles.json'
            save_library(path,ProfileLibrary())
            before=path.read_bytes()
            with patch('livescore.storage.os.replace',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):provision_profiles(path)
            self.assertEqual(path.read_bytes(),before)
            self.assertFalse(list(path.parent.glob('*.tmp')))
            path.write_text('{"schema_version":99}')
            before=path.read_bytes()
            with self.assertRaises(ValidationError):provision_profiles(path)
            self.assertEqual(path.read_bytes(),before)

    def test_legacy_prague_import_needs_no_event_migration(self):
        for name in ('imports/prague-2026.json','examples/prague-2026.json'):
            path=ROOT/name;before=path.read_bytes();state=load(path)
            self.assertEqual(state.event.sport_profile.score_mode,'total')
            self.assertFalse(state.event.sport_profile.sets_enabled)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(State.model_validate_json(state.model_dump_json()),state)

    def test_generic_profile_validation(self):
        for fields in (dict(score_steps=[0]),dict(score_steps=[1,1]),dict(score_steps=[True]),
                       dict(score_mode='boxing'),dict(sets_enabled=1),
                       dict(roles={'participant_1':dict(de='Rot',en='Red',cs='Červený')})):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):SportProfile(**fields)
        self.assertEqual(len(standard_profiles()),7)
        for entry in standard_profiles():
            for language in ('de','en','cs'):
                text=entry.profile.translations[language]
                self.assertTrue(text.name and text.period_label and text.break_label)


class StandardAPITest(unittest.TestCase):
    setUp=fixture.APITest.setUp
    state=fixture.APITest.state
    context=fixture.APITest.context
    request=fixture.APITest.request
    configure=fixture.APITest.configure
    action=fixture.APITest.action
    ready=fixture.APITest.ready
    start=fixture.APITest.start
    score_payload=fixture.APITest.score_payload
    score=fixture.APITest.score

    def profile(self, identifier, **changes):
        profile=next(p.profile for p in standard_profiles() if p.id=='standard-'+identifier)
        for key,value in changes.items():setattr(profile,key,value)
        response=self.request('config/sport-profile',data={'sport_profile':profile.model_dump(mode='json')})
        self.assertEqual(response.status_code,200,response.text)
        return profile

    def sets(self, side='L', delta=1):
        response=self.client.post('/api/v1/live/sets',json=self.score_payload(side,delta))
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_all_seven_profiles_api_contract_and_manual_periods(self):
        other=deepcopy(self.state()['matches'][1])
        for entry in standard_profiles():
            with self.subTest(profile=entry.id):
                p=self.profile(entry.id.removeprefix('standard-'));self.start()
                view=self.state()['live']
                self.assertEqual(view['display']['score'],p.score_mode!='none')
                self.assertEqual(view['display']['sets'],p.sets_enabled)
                self.assertEqual(view['display']['counters'],[c.id for c in p.counters if c.enabled])
                self.assertIsNone(view['left']['score']) if p.score_mode=='none' else self.assertIsInstance(view['left']['score'],int)
                if p.score_mode=='none':
                    self.assertEqual(self.client.post('/api/v1/live/score',json=self.score_payload()).status_code,422)
                    self.assertFalse(view['display']['officials']);self.assertFalse(view['display']['details'])
                else:self.score()
                if p.sets_enabled:self.sets()
                else:self.assertEqual(self.client.post('/api/v1/live/sets',json=self.score_payload()).status_code,409)
                for number in range(2,p.periods+1):
                    self.action('intermission',intermission=True)
                    self.action('period',period=number)
                    self.assertEqual(self.state()['live']['period'],number)
                    self.assertEqual(self.state()['live']['left']['score'],None if p.score_mode=='none' else 0 if p.score_mode=='period' else 1)
                self.assertEqual(self.request('live/period',match_id='m1',period=p.periods+1).status_code,409)
                self.assertEqual(self.state()['live']['status'],'live')
                self.action('finish');self.action('reset')
                # Profile counter initialization is allowed; unrelated scores/status remain unchanged.
                actual=self.state()['matches'][1]
                for key in ('scores','period_scores','sets_won','status','control_revision'):
                    self.assertEqual(actual[key],other[key])

    def test_period_points_sets_correction_undo_and_persistence(self):
        self.profile('showdown');self.start()
        self.score(delta=2);self.score(delta=1);self.score(delta=-2);self.action('undo')
        self.score('R',2);self.sets();self.action('undo')
        self.assertEqual(self.state()['live']['left']['sets_won'],0)
        self.sets();self.action('intermission',intermission=True);self.action('period',period=2)
        self.assertEqual(self.state()['live']['left']['score'],0)
        self.assertEqual(self.state()['live']['left']['period_scores'],{'1':3,'2':0})
        # Undo can correct an earlier set after moving on; it never changes current set points.
        self.action('undo');self.action('undo')
        self.assertEqual(self.state()['live']['right']['period_scores'],{'1':0,'2':0})
        self.score('R',2);self.sets('R');self.sets('R',-1);self.action('undo')
        self.action('switch-sides')
        self.assertEqual(self.state()['live']['left']['id'],'b')
        self.assertEqual(self.state()['live']['left']['sets_won'],1)
        self.assertEqual(self.state()['live']['left']['score'],2)
        persisted=load(self.path)
        self.assertEqual(persisted.matches[0].period_scores,{'1':{'a':3,'b':0},'2':{'a':0,'b':2}})
        self.assertEqual(persisted.matches[0].sets_won,{'a':0,'b':1})
        self.action('finish');before=self.state()['matches'][0]
        self.action('reopen');after=self.state()['matches'][0]
        for key in ('scores','period_scores','sets_won'):self.assertEqual(after[key],before[key])
        self.client.__exit__(None,None,None)
        self.client=TestClient(self.app).__enter__()
        self.assertEqual(self.state()['matches'][0]['period_scores'],before['period_scores'])
        self.action('reset')
        m=self.state()['matches'][0]
        self.assertEqual((m['scores'],m['period_scores'],m['sets_won']),({},{},{}))
        self.ready();self.action('start')
        self.assertFalse(self.state()['can_undo'])

    def test_fixed_roles_remain_with_participant_across_screen_switch(self):
        self.profile('boxing');self.start()
        left=self.state()['live']['left'];self.assertEqual(left['role']['labels']['de'],'Rote Ecke')
        self.action('switch-sides')
        right=self.state()['live']['right']
        self.assertEqual(right['id'],left['id']);self.assertEqual(right['role'],left['role'])
        self.assertEqual(self.state()['live']['left']['role']['labels']['en'],'Blue corner')
        self.assertFalse(self.state()['can_undo'])

    def test_manual_points_and_sets_never_decide_winners_or_end_sections(self):
        self.profile('showdown');self.start()
        for _ in range(6):self.score(delta=2)
        for _ in range(4):self.sets()
        view=self.state()['live']
        self.assertEqual(view['status'],'live');self.assertEqual(view['period'],1)
        self.assertEqual(view['left']['score'],12);self.assertEqual(view['left']['sets_won'],4)
        self.assertEqual(view['right']['sets_won'],0)
        self.action('intermission',intermission=True);self.action('period',period=2)
        self.assertEqual(self.state()['live']['left']['sets_won'],4)

    def test_concurrent_points_and_sets_dedupe_and_stale_period_controls(self):
        self.profile('showdown');self.start()
        score=self.score_payload(delta=2);sets=self.score_payload('R')
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda args:self.client.post(*args[:1],json=args[1]),
                [('/api/v1/live/score',score),('/api/v1/live/sets',sets)]))
        self.assertEqual([r.status_code for r in responses],[200,200])
        self.assertEqual(self.client.post('/api/v1/live/sets',json=sets).status_code,200)
        self.assertEqual(self.state()['live']['right']['sets_won'],1)
        stale=self.score_payload();self.action('intermission',intermission=True);self.action('period',period=2)
        self.assertEqual(self.client.post('/api/v1/live/score',json=stale).status_code,409)
        self.assertEqual(self.state()['live']['left']['score'],0)
        self.assertEqual(self.client.post('/api/v1/live/sets',json=dict(stale,request_id=str(uuid4()),delta=2)).status_code,422)

    def test_disabled_counter_and_display_updates_preserve_history(self):
        p=self.profile('blind-football');self.start();s=self.state();m=s['matches'][0]
        payload=dict(request_id=str(uuid4()),**self.context(),match_id='m1',control_revision=m['control_revision'],
                     period=1,participant_id='a',counter_id='team_fouls',delta=1)
        for _ in range(5):
            payload['request_id']=str(uuid4())
            self.assertEqual(self.client.post('/api/v1/live/counter',json=payload).status_code,200)
        self.assertEqual(self.state()['live']['left']['counter_states']['team_fouls'],'critical')
        p.counters[0].enabled=False;p.show_details=False;p.show_officials=False
        self.assertEqual(self.request('config/sport-profile',data={'sport_profile':p.model_dump()}).status_code,200)
        self.assertEqual(self.state()['live']['display']['counters'],[])
        self.assertEqual(self.state()['matches'][0]['counters']['team_fouls']['a'],{'1':5})
        payload['request_id']=str(uuid4())
        self.assertEqual(self.client.post('/api/v1/live/counter',json=payload).status_code,409)

    def test_invalid_histories_rejected_and_structural_changes_guarded(self):
        self.profile('table-tennis');self.start();self.score();self.sets()
        raw=load(self.path).model_dump(mode='json')
        variants=[]
        for key,value in [('period_scores',{'1':{'a':0,'b':0}}),('period_scores',{'2':{'a':1,'b':0}}),
                          ('sets_won',{'c':1,'b':0})]:
            variant=deepcopy(raw);variant['matches'][0][key]=value;variants.append(variant)
        variant=deepcopy(raw);variant['event']['sport_profile']['score_mode']='none';variants.append(variant)
        for variant in variants:
            with self.assertRaises(ValidationError):State.model_validate(variant)
        p=SportProfile.model_validate(raw['event']['sport_profile']);p.score_mode='total'
        self.assertEqual(self.request('config/sport-profile',data={'sport_profile':p.model_dump()}).status_code,409)
        p.score_mode='period';p.score_steps=[1,2];p.translations['cs'].score_label='Body'
        self.assertEqual(self.request('config/sport-profile',data={'sport_profile':p.model_dump()}).status_code,200)

    def test_public_availability_null_zero_and_unconfirmed_pairing(self):
        for route in ('pause','resume'):
            self.assertEqual(self.client.post('/api/v1/live/'+route,json={}).status_code,404)
        self.profile('boxing')
        idle=self.client.get('/api/v1/live').json()
        self.assertTrue(idle['source']['available'])
        self.assertEqual(idle['status'],'idle');self.assertFalse(idle['pairing_confirmed'])
        self.action('select')
        scheduled=self.client.get('/api/v1/live').json()
        self.assertEqual(scheduled['status'],'scheduled')
        self.assertFalse(scheduled['pairing_confirmed']);self.assertIsNone(scheduled['left'])
        self.action('prepare',participant_1='a',participant_2='b',side_l='a',side_r='b')
        ready=self.client.get('/api/v1/live').json()
        self.assertTrue(ready['pairing_confirmed']);self.assertIsNone(ready['left']['score'])
        self.assertIsNone(ready['left']['sets_won']);self.assertIsNone(ready['left']['period_scores'])
        self.assertIsNone(ready['officials']);self.assertIsNone(ready['stage']);self.assertIsNone(ready['round'])
        self.assertEqual(ready['left']['role']['id'],'red')
        self.action('reset');self.profile('football');self.ready()
        football=self.client.get('/api/v1/live').json()
        self.assertTrue(football['display']['score']);self.assertEqual(football['left']['score'],0)
        self.assertEqual(football['right']['score'],0)

    def test_source_context_changes_on_event_switch_restart_reset_and_profile_edit(self):
        initial=self.client.get('/api/v1/live').json()['source']
        self.profile('football');edited=self.client.get('/api/v1/live').json()['source']
        self.assertGreater(edited['revision'],initial['revision'])
        self.start();self.action('finish');self.action('reopen');self.action('reset')
        reset=self.client.get('/api/v1/live').json()
        self.assertFalse(reset['pairing_confirmed']);self.assertGreater(reset['source']['revision'],edited['revision'])
        self.client.__exit__(None,None,None);self.client=TestClient(self.app).__enter__()
        restarted=self.client.get('/api/v1/live').json()
        self.assertNotEqual(restarted['source']['instance_id'],reset['source']['instance_id'])
        self.assertEqual(restarted['source']['event_id'],initial['event_id'])
        state=self.state()
        created=self.client.post('/api/v1/event-catalog/create',json=dict(request_id=str(uuid4()),catalog_session=state['stream_id'],
            event=dict(name='Other',date_from='2026-10-03',date_to='2026-10-04'))).json()['created_event_id']
        self.client.post('/api/v1/event-catalog/select',json=dict(request_id=str(uuid4()),catalog_session=state['stream_id'],
            selection_token=state['selection_token'],event_id=created)).raise_for_status()
        changed=self.client.get('/api/v1/live').json()
        self.assertEqual(changed['source']['event_id'],created)
        self.assertNotEqual(changed['source']['selection_token'],restarted['source']['selection_token'])
        self.assertIsNone(changed['left']);self.assertEqual(changed['status'],'idle')
        self.assertEqual(changed,self.state()['live'])

    def test_enabled_sets_without_imported_values_are_not_fabricated_zero(self):
        self.profile('showdown');self.start()
        state=load(self.path);state.matches[0].sets_won={}
        from livescore.storage import save
        save(self.path,state)
        self.client.__exit__(None,None,None);self.client=TestClient(self.app).__enter__()
        view=self.client.get('/api/v1/live').json()
        self.assertTrue(view['display']['sets']);self.assertIsNone(view['left']['sets_won'])
        self.sets();self.assertEqual(self.state()['live']['left']['sets_won'],1)

    def test_all_six_documented_snapshots_match_live_serialization(self):
        import re
        from livescore.service import live_view
        examples=[json.loads(block) for block in re.findall(r'```json\n(.*?)\n```',(ROOT/'docs/API.md').read_text(),re.S)]
        snapshots=[e for e in examples if 'source' in e]
        self.assertEqual(len(snapshots),6)
        for expected in snapshots:
            with self.subTest(profile=expected['sport_profile']['sport'],status=expected['status']):
                state=load(ROOT/'examples/prague-2026.json')
                state.event.sport_profile=SportProfile.model_validate(expected['sport_profile'])
                area=next(area for area in state.play_areas if area.id==expected['play_area']['id'])
                area.label=expected['play_area']['label']
                for match in state.matches:match.counters={}
                state.active_match_id=expected['match_id'];state.revision=expected['revision']
                match=state.matches[0];match.status=expected['status'];match.period=expected['period']
                match.intermission=expected['period_info']['intermission']
                if expected['pairing_confirmed']:
                    left=expected['left'];right=expected['right']
                    from livescore.models import Participant
                    for side in (left,right):
                        if side['id'] not in {p.id for p in state.participants}:
                            state.participants.append(Participant(**{k:side[k] for k in ('id','name','short_name','country_code')}))
                    match.participant_1=left['id'];match.participant_2=right['id']
                    match.side_l=left['id'];match.side_r=right['id']
                    match.scores={left['id']:left['score'] or 0,right['id']:right['score'] or 0}
                    if expected['display']['sets']:match.sets_won={left['id']:left['sets_won'],right['id']:right['sets_won']}
                    if expected['display']['score_mode']=='period':
                        match.period_scores={p:{left['id']:value,right['id']:right['period_scores'][p]} for p,value in left['period_scores'].items()}
                    match.counters={c.id:{side['id']:{str(match.period):side['counters'][c.id]} for side in (left,right)}
                                    for c in state.event.sport_profile.counters if c.enabled}
                actual=live_view(State.model_validate(state.model_dump()))
                self.assertEqual(actual,{key:value for key,value in expected.items() if key!='source'})
