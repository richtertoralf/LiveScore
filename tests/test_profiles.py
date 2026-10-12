"""Profilbibliothek, Sprachpflege, Veranstaltungs-Kopien und Rechte."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
import yaml

from livescore.app import create_app
from livescore.auth import AuthConfig, hash_password
from livescore.models import SportProfile, State
from livescore.profiles import ProfileEntry, ProfileLibrary, display_profile, save_library
from livescore.storage import load, save

ROOT = Path(__file__).resolve().parents[1]


def boxing():
    return SportProfile(sport='boxing', ruleset='Nur eine Beschreibung', periods=3, period_label='Runde',
        translations={lang: dict(name=name,period_label=period,break_label=pause,hint=hint)
                      for lang,name,period,pause,hint in (
                          ('de','Boxen','Runde','Rundenpause','Manuelle Erfassung'),
                          ('en','Boxing','Round','Round break','Manual scoring'),
                          ('cs','Box','Kolo','Přestávka mezi koly','Ruční záznam'))},
        counters=[dict(id='notices',label='Hinweise',reset_each_period=False,warning_at=2,critical_at=4,
            translations={lang: dict(label=label,warning_label=warning,critical_label=critical)
                          for lang,label,warning,critical in (
                              ('de','Hinweise','Bitte prüfen','Kritisch'),
                              ('en','Notices','Please check','Critical'),
                              ('cs','Upozornění','Zkontrolujte','Kritické'))})])


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.test-artifacts')
        self.directory = Path(self.temp.name)
        save(self.directory / 'events/prague.json', load(ROOT / 'imports/prague-2026.json'))
        self.restart()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.client.__exit__(None,None,None))
        state = self.state()
        self.client.post('/api/v1/event-catalog/select',json=dict(request_id=str(uuid4()),
            catalog_session=state['stream_id'],selection_token=state['selection_token'],event_id='prague')).raise_for_status()

    def restart(self):
        if hasattr(self,'client'): self.client.__exit__(None,None,None)
        self.app = create_app(data_dir=self.directory,auth_config=AuthConfig(enabled=False))
        self.client = TestClient(self.app).__enter__()

    def state(self):
        return self.client.get('/api/v1/tournament').json()

    def request(self, path, status=200, **fields):
        s = self.state()
        if path.startswith('sport-profiles/'):
            context = dict(catalog_session=s['stream_id'],expected_revision=self.app.state.service.profiles.revision)
        else:
            context = dict(event_id=s['active_event_id'],selection_token=s['selection_token'],expected_revision=s['revision'])
        response = self.client.post('/api/v1/'+path,json=dict(request_id=str(uuid4()),**context,**fields))
        self.assertEqual(response.status_code,status,response.text)
        return response.json()

    def apply_profile(self, profile, status=200):
        return self.request('config/sport-profile',status,data=dict(sport_profile=profile.model_dump(mode='json') if profile else None))

    def action(self, action, **fields):
        return self.request('live/'+action,match_id='match-001',**fields)

    def start(self):
        self.action('select')
        self.action('prepare',participant_1='bsc-praha',participant_2='fc-ingolstadt-04',side_l='bsc-praha',side_r='fc-ingolstadt-04')
        self.action('start')

    def test_library_crud_revision_dedup_failure_and_restart(self):
        self.assertTrue((self.directory/'sport-profiles.json').exists())
        listing=self.client.get('/api/v1/sport-profiles').json()
        self.assertEqual(len(listing['profiles']),7)
        self.assertEqual(listing['event_profiles'][0]['id'],'prague')
        original=self.state()['event']
        self.request('sport-profiles/save',id='boxing',profile=boxing().model_dump())
        stored=(self.directory/'sport-profiles.json').read_bytes()
        self.assertEqual(self.state()['event'],original)
        s=self.state()
        payload=dict(request_id=str(uuid4()),catalog_session=s['stream_id'],expected_revision=self.app.state.service.profiles.revision,id='boxing',profile=boxing().model_dump())
        payload['profile']['periods']=5
        response=self.client.post('/api/v1/sport-profiles/save',json=payload)
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.post('/api/v1/sport-profiles/save',json=payload).status_code,200)
        stale=deepcopy(payload);stale['request_id']=str(uuid4())
        self.assertEqual(self.client.post('/api/v1/sport-profiles/save',json=stale).status_code,409)
        altered=deepcopy(payload);altered['profile']['periods']=4
        self.assertEqual(self.client.post('/api/v1/sport-profiles/save',json=altered).status_code,409)
        before=self.client.get('/api/v1/sport-profiles').json()
        with patch('livescore.catalog.save_library',side_effect=OSError('disk full')):
            self.request('sport-profiles/delete',503,id='boxing')
        self.assertEqual(self.client.get('/api/v1/sport-profiles').json(),before)
        self.restart()
        self.assertEqual(self.client.get('/api/v1/sport-profiles').json(),before)
        self.assertNotEqual((self.directory/'sport-profiles.json').read_bytes(),stored)
        self.request('sport-profiles/delete',id='boxing')
        self.assertEqual(len(self.client.get('/api/v1/sport-profiles').json()['profiles']),7)
        self.assertEqual(self.state()['event'],original)
        self.request('sport-profiles/delete',409,id='boxing')

    def test_prague_format_transfers_to_boxing_and_exports_without_library(self):
        before=self.state()
        self.apply_profile(boxing())
        after=self.state()
        for key in ('participants','referees','play_areas'):
            self.assertEqual(after[key],before[key])
        for old,new in zip(before['matches'],after['matches']):
            self.assertEqual({k:v for k,v in old.items() if k!='counters'}, {k:v for k,v in new.items() if k!='counters'})
            self.assertEqual(set(new['counters']),{'notices'} if new['participant_1'] or new['participant_2'] else set())
        self.request('sport-profiles/save',id='boxing',profile=boxing().model_dump())
        self.start()
        s=self.state();m=s['matches'][0]
        self.client.post('/api/v1/live/counter',json=dict(request_id=str(uuid4()),event_id='prague',selection_token=s['selection_token'],
            match_id=m['id'],control_revision=m['control_revision'],period=1,participant_id='bsc-praha',counter_id='notices',delta=1)).raise_for_status()
        self.action('intermission',intermission=True);self.action('period',period=2)
        expected=self.state()['event']['sport_profile']
        changed=boxing();changed.periods=8;changed.counters=[]
        self.request('sport-profiles/save',id='boxing',profile=changed.model_dump())
        self.request('sport-profiles/delete',id='boxing')
        self.assertEqual(self.state()['event']['sport_profile'],expected)
        exported=self.client.get('/api/v1/event-catalog/prague/export').json()
        self.assertNotIn('profile_library',exported)
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts') as temp:
            path=Path(temp);save(path/'events/archive.json',State.model_validate(exported))
            with TestClient(create_app(data_dir=path,auth_config=AuthConfig(enabled=False))) as other:
                self.assertEqual(other.get('/api/v1/event-catalog/archive/export').json(),exported)
                self.assertTrue((path/'sport-profiles.json').exists())
        self.assertEqual(exported['matches'][0]['counters']['notices']['bsc-praha'],{'1':1,'2':1})

    def test_used_structure_locked_but_texts_thresholds_and_order_remain_editable(self):
        self.apply_profile(boxing());self.start()
        original=self.state()
        profile=boxing();profile.translations['cs'].period_label='Díl';profile.counters[0].warning_at=1
        with self.client.websocket_connect('/api/v1/ws') as ws:
            ws.receive_json();changed=self.apply_profile(profile)
            self.assertEqual(ws.receive_json(),changed)
        self.assertEqual(self.state()['matches'],original['matches'])
        self.assertEqual(changed['live']['period_info']['labels']['cs'],'1. Díl')
        self.assertEqual(changed['live'],self.client.get('/api/v1/live').json())
        for change in ('periods','add','remove','reset'):
            variant=profile.model_copy(deep=True)
            if change=='periods':variant.periods=4
            elif change=='add':variant.counters.append(variant.counters[0].model_copy(update={'id':'extra'}))
            elif change=='remove':variant.counters=[]
            else:variant.counters[0].reset_each_period=True
            self.apply_profile(variant,409)
        self.action('finish');self.apply_profile(boxing())
        self.apply_profile(None,409)
        self.assertEqual(self.state()['matches'][0]['scores'],original['matches'][0]['scores'])

    def test_prepare_can_be_cancelled_before_restructuring(self):
        self.action('select');self.action('prepare',participant_1='bsc-praha',participant_2='fc-ingolstadt-04',side_l='bsc-praha',side_r='fc-ingolstadt-04')
        self.apply_profile(boxing(),409)
        self.action('unprepare');self.apply_profile(boxing())
        self.apply_profile(None)
        self.assertEqual(self.state()['matches'][0]['counters'],{})

    def test_labels_and_legacy_files_are_read_without_migration_or_sport_logic(self):
        original=(ROOT/'imports/prague-2026.json').read_bytes()
        old=load(ROOT/'imports/prague-2026.json').event.sport_profile
        labels=display_profile(old)
        self.assertEqual(labels['translations']['cs']['period_label'],'Poločas')
        self.assertEqual(labels['counters'][0]['translations']['en']['label'],'Fouls')
        self.assertEqual((ROOT/'imports/prague-2026.json').read_bytes(),original)
        profile=boxing();profile.sport='showdown';profile.ruleset='football';profile.translations['en'].period_label='Name'
        self.apply_profile(profile);self.start()
        self.assertEqual(self.state()['live']['period_info']['code'],'period_1')
        self.assertEqual(self.state()['live']['period_info']['labels']['en'],'Name 1')
        with self.assertRaises(ValidationError):SportProfile.model_validate(dict(profile.model_dump(),translations={'fr':{}}))
        with self.assertRaises(ValidationError):ProfileLibrary(profiles=[ProfileEntry(id='x',profile=profile)]*2)


class ProfilePermissionsTest(unittest.TestCase):
    def test_invalid_library_aborts_before_creating_selection_or_migrating_events(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts') as temp:
            root=Path(temp)
            library=root/'sport-profiles.json'
            library.write_text('{"schema_version": 99, "profiles": []}')
            original=library.read_bytes()
            with self.assertRaises(ValidationError):
                with TestClient(create_app(data_dir=root,auth_config=AuthConfig(enabled=False))):pass
            self.assertEqual(library.read_bytes(),original)
            self.assertFalse((root/'active-event.json').exists())

    def test_admin_only_including_event_edit_and_import_bypasses(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-artifacts') as temp:
            root=Path(temp)
            auth_file=root/'auth.yml'
            password='Safe test password 2026!'
            auth_file.write_text(yaml.safe_dump(dict(users={name:dict(role=name,password_hash=hash_password(password),default_password=False) for name in ('admin','operator')})))
            save(root/'events/prague.json',load(ROOT/'imports/prague-2026.json'))
            with TestClient(create_app(data_dir=root,auth_config=AuthConfig(file=auth_file))) as client:
                def login(name):
                    csrf=client.get('/api/auth/session').json()['csrf_token']
                    client.post('/login',json=dict(username=name,password=password),headers={'X-CSRF-Token':csrf}).raise_for_status()
                    return {'X-CSRF-Token':client.get('/api/auth/session').json()['csrf_token']}
                self.assertEqual(client.get('/api/v1/sport-profiles').status_code,401)
                headers=login('operator')
                self.assertEqual(client.get('/api/v1/sport-profiles').status_code,403)
                for route in ('sport-profiles/save','sport-profiles/delete','config/sport-profile','event-catalog/create','event-catalog/import','event-catalog/import/preview'):
                    self.assertEqual(client.post('/api/v1/'+route,json={},headers=headers).status_code,403,route)
                s=client.get('/api/v1/tournament').json()
                client.post('/api/v1/event-catalog/select',json=dict(request_id=str(uuid4()),catalog_session=s['stream_id'],selection_token=s['selection_token'],event_id='prague'),headers=headers).raise_for_status()
                s=client.get('/api/v1/tournament').json();event=s['event']
                def edit(event):
                    return client.post('/api/v1/config/event',json=dict(request_id=str(uuid4()),event_id='prague',selection_token=s['selection_token'],expected_revision=s['revision'],data=event),headers=headers)
                changed=deepcopy(event);changed['sport_profile']=boxing().model_dump()
                self.assertEqual(edit(changed).status_code,403)
                event.pop('sport_profile');event['name']='Operator correction'
                self.assertEqual(edit(event).status_code,200)
                client.cookies.clear();headers=login('admin')
                self.assertEqual(client.get('/api/v1/sport-profiles').status_code,200)
                s=client.get('/api/v1/tournament').json()
                payload=dict(request_id=str(uuid4()),catalog_session=s['stream_id'],expected_revision=client.app.state.service.profiles.revision,id='boxing',profile=boxing().model_dump())
                self.assertEqual(client.post('/api/v1/sport-profiles/save',json=payload).status_code,403)
                self.assertEqual(client.post('/api/v1/sport-profiles/save',json=payload,headers=headers).status_code,200)
