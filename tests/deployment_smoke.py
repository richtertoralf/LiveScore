"""Opt-in: real venv/pip install, installed CLI, server restart, upgrade and uninstall.

Run with .venv/bin/python tests/deployment_smoke.py. All files stay in the repo;
only package downloads need a network. No system users/services are changed.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
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
        def start():
            proc=subprocess.Popen([str(cli)],cwd=ROOT,env=environment,stdout=log,stderr=log)
            for _ in range(100):
                try:
                    if httpx.get(url+'/api/version').json()=={'version':'0.1.0'}:return proc
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
            command(ROOT/'install.sh','--staging-root',root)
            assert subprocess.check_output([cli,'--version'],text=True)=='LiveScore 0.1.0\n'
            assert subprocess.check_output([runtime/'.venv/bin/python','-m','livescore','--version'],cwd=runtime,text=True)=='LiveScore 0.1.0\n'
            config.write_text(config.read_text().replace('0.0.0.0','127.0.0.1').replace('8730',str(port)))
            process=start()
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
            before=snapshot()
            old=runtime.resolve()
            if remote_upgrade:
                command(cli,'--upgrade')
            else:
                command(cli,'--upgrade','--source',ROOT)
            assert runtime.resolve()!=old and old.exists()
            assert snapshot()==before
            process=start()
            with httpx.Client(base_url=url) as client:
                login(client,'admin',PASSWORD)
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
            print('PASS: real venv/pip fresh install; seeded Prague active (14/6/6); CLI/version; installed server; changed admin password; upgrade preserves config/auth/active event/live score/fouls/officials; restart; repeated install refuses; uninstall retains data; explicit purge.')
        finally:
            if process and process.poll() is None:process.terminate();process.wait(timeout=10)
            log.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--remote-upgrade',action='store_true',help='Upgrade von GitHub/main statt lokal; nach Veröffentlichung prüfen')
    run(parser.parse_args().remote_upgrade)
