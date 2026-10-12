"""Opt-in: real venv/pip install, installed CLI, server restart, upgrade and uninstall.

Run with .venv/bin/python tests/deployment_smoke.py. All files stay in the repo;
only package downloads need a network. No system users/services are changed.
"""
import argparse
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ARTIFACTS = ROOT / '.test-artifacts'
PASSWORD = 'Deployment smoke password 2026!'


def run(remote_upgrade=False):
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='deployment-',dir=ARTIFACTS) as temp:
        root=Path(temp)
        environment=dict(os.environ,TMPDIR=str(root))
        cli=root/'usr/local/bin/livescore'
        config=root/'etc/livescore/livescore.yml'
        runtime=root/'opt/livescore/current'
        data=root/'var/lib/livescore/data'
        log=(ARTIFACTS/'deployment-smoke.log').open('w')
        process=None
        # A real published 0.1.2 runtime, not just a renamed version of the new code.
        initial_source=root/'initial-source'
        initial_source.mkdir()
        archive=subprocess.check_output(['git','archive','34643e5348aa386c9b65406741a1cc54f37a4e97'],cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
            contents.extractall(initial_source,filter='data')
        def command(*args, check=True):
            return subprocess.run([str(a) for a in args],cwd=ROOT,env=environment,
                                  stdout=log,stderr=log,check=check)
        def snapshot():
            return {str(p.relative_to(root)):p.read_bytes()
                    for directory in (root/'etc/livescore',data)
                    for p in directory.rglob('*') if p.is_file() and not p.name.endswith('.lock')}
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        def start(expected_version):
            proc=subprocess.Popen([str(cli)],cwd=ROOT,env=environment,stdout=log,stderr=log)
            for _ in range(100):
                try:
                    if httpx.get(url+'/api/version').json()=={'version':expected_version}:return proc
                except (httpx.HTTPError,ValueError):pass
                if proc.poll() is not None:raise RuntimeError('Installed server failed; see deployment-smoke.log')
                time.sleep(.1)
            proc.terminate();proc.wait(timeout=10);raise RuntimeError('Server timeout')
        def login(client,name,password):
            csrf=client.get('/api/auth/session').json()['csrf_token']
            response=client.post('/login',json={'username':name,'password':password},headers={'X-CSRF-Token':csrf})
            response.raise_for_status()
            return {'X-CSRF-Token':client.get('/api/auth/session').json()['csrf_token']}
        try:
            command(initial_source/'install.sh','--staging-root',root)
            assert subprocess.check_output([cli,'--version'],text=True)=='LiveScore 0.1.2\n'
            assert subprocess.check_output([runtime/'.venv/bin/python','-m','livescore','--version'],cwd=runtime,text=True)=='LiveScore 0.1.2\n'
            config.write_text(config.read_text().replace('0.0.0.0','127.0.0.1').replace('8730',str(port)))
            process=start('0.1.2')
            with httpx.Client(base_url=url) as client:
                headers=login(client,'admin','admin')
                response=client.post('/api/auth/password',json={'username':'admin','password':PASSWORD,'repeat':PASSWORD},headers=headers)
                response.raise_for_status()
                headers=login(client,'admin',PASSWORD)
                state=client.get('/api/v1/tournament').json()
                assert state['active_event_id']=='prague-2026'
                assert (len(state['matches']),len(state['participants']),len(state['referees']))==(14,6,6)
                # Apply real score/foul changes and preserve a running match across upgrade.
                from uuid import uuid4
                def action(operation, **fields):
                    state=client.get('/api/v1/tournament').json()
                    body=dict(request_id=str(uuid4()),expected_revision=state['revision'],event_id='prague-2026',selection_token=state['selection_token'],match_id='match-001',**fields)
                    response=client.post('/api/v1/live/'+operation,json=body,headers=headers)
                    response.raise_for_status()
                    return response.json()
                action('select'); action('prepare',participant_1='bsc-praha',participant_2='fc-ingolstadt-04',side_l='bsc-praha',side_r='fc-ingolstadt-04')
                state=action('start')
                body=dict(request_id=str(uuid4()),event_id='prague-2026',selection_token=state['selection_token'],match_id='match-001',control_revision=state['matches'][0]['control_revision'],participant_id='bsc-praha',delta=1)
                client.post('/api/v1/live/score',json=dict(**body,side='L'),headers=headers).raise_for_status()
                body['request_id']=str(uuid4())
                client.post('/api/v1/live/counter',json=dict(**body,counter_id='team_fouls',period=1),headers=headers).raise_for_status()
            process.terminate();process.wait(timeout=10)
            from livescore.profiles import ProfileEntry, ProfileLibrary, save_library
            from livescore.storage import load
            save_library(data/'sport-profiles.json',ProfileLibrary(revision=1,profiles=[
                ProfileEntry(id='prague',profile=load(data/'events/prague-2026.json').event.sport_profile)]))
            before=snapshot()
            old=runtime.resolve()
            if remote_upgrade:
                command(cli,'--upgrade')
            else:
                command(cli,'--upgrade','--source',ROOT)
            assert runtime.resolve()!=old and old.exists()
            assert snapshot()==before
            assert subprocess.check_output([cli,'--version'],text=True)=='LiveScore 0.2.0\n'
            process=start('0.2.0')
            with httpx.Client(base_url=url) as client:
                login(client,'admin',PASSWORD)
                assert client.get('/api/v1/sport-profiles').json()['profiles'][0]['id']=='prague'
                live=client.get('/api/v1/live').json()
                assert live['left']['score']==1 and live['left']['counters']['team_fouls']==1
                assert live['status']=='live' and len(live['officials'])==3
                assert client.get('/api/v1/tournament').json()['active_event_id']=='prague-2026'
            process.terminate();process.wait(timeout=10)
            assert snapshot()==before
            assert command(ROOT/'install.sh','--staging-root',root,check=False).returncode!=0
            assert snapshot()==before
            command(runtime/'uninstall.sh') # Installed metadata carries the safe staging root.
            assert snapshot()==before and not cli.exists() and not runtime.exists()
            command(ROOT/'uninstall.sh','--staging-root',root,'--purge')
            assert not data.exists() and not config.exists()
            print('PASS: published 0.1.2 install and real CLI upgrade to 0.2.0; venv/pip; profile library and event data preserved byte-for-byte; active Prague (14/6/6); config/auth/live score/fouls/officials; restart; repeated install refuses; uninstall retains data; explicit purge.')
        finally:
            if process and process.poll() is None:process.terminate();process.wait(timeout=10)
            log.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--remote-upgrade',action='store_true',help='Upgrade von GitHub/main statt lokal; nach Veröffentlichung prüfen')
    run(parser.parse_args().remote_upgrade)
