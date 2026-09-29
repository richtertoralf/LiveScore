"""Real SIGHUP/PTY recovery against a live server, with an isolated systemctl stub.

The stub executes the shipped ExecReload command on our own PID only. It never
contacts the host systemd. All test files stay below .test-artifacts.
"""
import json
import os
from pathlib import Path
import pty
import select
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

import httpx
import yaml
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.test-artifacts'
PASSWORD = 'Recovered administrator password 2026!'
ORIGINAL_PASSWORD = 'Original administrator password 2026!'


def interactive_reset(config, environment):
    master, slave = pty.openpty()
    process = subprocess.Popen([str(ROOT/'bin/livescore'),'--config',str(config),'--reset-admin-password'],
        cwd=ROOT,env=environment,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
    os.close(slave)
    output=b''; answered=0; deadline=time.monotonic()+20
    try:
        while time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: chunk=os.read(master,4096)
                except OSError: break
                if not chunk:break
                output+=chunk
            prompt=(b'New admin password: ',b'Repeat new admin password: ')
            if answered<2 and prompt[answered] in output:
                os.write(master,(PASSWORD+'\n').encode());answered+=1
            if process.poll() is not None:break
        process.wait(timeout=2)
        assert process.returncode==0,output.decode()
        assert answered==2 and PASSWORD.encode() not in output, 'Hidden getpass input required'
        assert b'Admin password updated.' in output and b'No restart was required.' in output
        return output.decode()
    finally:
        os.close(master)
        if process.poll() is None:process.kill();process.wait(timeout=5)


def run():
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='recovery-',dir=ARTIFACTS) as directory:
        directory=Path(directory)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        config=directory/'server.yml'
        config.write_text(f'bind_host: 127.0.0.1\nport: {port}\ndata_dir: data\nauth:\n  file: auth.yml\n')
        subprocess.run([sys.executable,'-m','livescore.bootstrap','--config',str(config),
                        '--seed',str(ROOT/'imports/prague-2026.json')],cwd=ROOT,check=True,capture_output=True)
        environment=dict(os.environ,TMPDIR=str(directory))
        log=(ARTIFACTS/'auth-recovery-server.log').open('w')
        process=subprocess.Popen([sys.executable,'-m','livescore','--config',str(config)],cwd=ROOT,env=environment,stdout=log,stderr=log)
        stop=threading.Event();observations=[];errors=[];poller=None
        def login(client,username,password,expected=200):
            client.cookies.clear()
            csrf=client.get('/api/auth/session').json()['csrf_token']
            response=client.post('/login',json=dict(username=username,password=password),headers={'X-CSRF-Token':csrf})
            assert response.status_code==expected,response.text
            if expected==200:return {'X-CSRF-Token':client.get('/api/auth/session').json()['csrf_token']}
        try:
            for _ in range(100):
                try:
                    if httpx.get(url+'/api/version',timeout=.3).status_code==200:break
                except httpx.HTTPError:pass
                assert process.poll() is None,'Server exited'
                time.sleep(.05)
            else:raise AssertionError('Startup timeout')
            with httpx.Client(base_url=url) as admin,httpx.Client(base_url=url) as operator,httpx.Client(base_url=url) as fresh:
                headers=login(admin,'admin','admin')
                admin.post('/api/auth/password',json=dict(username='admin',password=ORIGINAL_PASSWORD,repeat=ORIGINAL_PASSWORD),headers=headers).raise_for_status()
                login(admin,'admin',ORIGINAL_PASSWORD)
                opheaders=login(operator,'operator','operator')
                def action(operation, **fields):
                    state=operator.get('/api/v1/tournament').json()
                    payload=dict(request_id=str(uuid4()),expected_revision=state['revision'],event_id=state['active_event_id'],selection_token=state['selection_token'],match_id='match-001',**fields)
                    response=operator.post('/api/v1/live/'+operation,json=payload,headers=opheaders)
                    response.raise_for_status()
                    return response.json()
                action('select');action('prepare',participant_1='bsc-praha',participant_2='fc-ingolstadt-04',side_l='bsc-praha',side_r='fc-ingolstadt-04')
                action('start')
                def point(counter=False):
                    state=operator.get('/api/v1/tournament').json()
                    payload=dict(request_id=str(uuid4()),event_id=state['active_event_id'],selection_token=state['selection_token'],match_id='match-001',control_revision=state['matches'][0]['control_revision'],participant_id='bsc-praha',delta=1)
                    payload.update(dict(counter_id='team_fouls',period=state['live']['period']) if counter else dict(side='L'))
                    operator.post('/api/v1/live/'+('counter' if counter else 'score'),json=payload,headers=opheaders).raise_for_status()
                point();point();point(counter=True);action('period',period=2);point(counter=True)
                before=operator.get('/api/v1/tournament').json()
                before_live=operator.get('/api/v1/live').json()
                auth_file=directory/'auth.yml'
                before_owner=(auth_file.stat().st_uid,auth_file.stat().st_gid)
                operator_record=yaml.safe_load(auth_file.read_text())['users']['operator']
                event_bytes={p.name:p.read_bytes() for p in (directory/'data').rglob('*.json')}
                cookies='; '.join(f'{k}={v}' for k,v in operator.cookies.items())
                def poll():
                    with httpx.Client(base_url=url,timeout=2) as client:
                        while not stop.is_set():
                            try:
                                response=client.get('/api/v1/live')
                                observations.append((response.status_code,response.json()))
                            except Exception as exc:errors.append(type(exc).__name__)
                            stop.wait(.03)
                poller=threading.Thread(target=poll);poller.start()
                # The isolated service controller reports the real running process,
                # and executes only ExecReload from the repository's service file.
                fakebin=directory/'bin';fakebin.mkdir()
                controller=fakebin/'systemctl'
                unit=ROOT/'systemd/livescore.service'
                controller.write_text('#!'+sys.executable+'\n'+'''import json,os,subprocess,sys
from pathlib import Path
pid=os.environ['RECOVERY_TEST_PID']
unit=Path(os.environ['RECOVERY_TEST_UNIT'])
with Path(os.environ['RECOVERY_TEST_CALLS']).open('a') as log:log.write(json.dumps(sys.argv[1:])+'\\n')
if sys.argv[1]=='show':
 if '--value' in sys.argv:print(pid)
 else:print('LoadState=loaded\\nActiveState=active\\nMainPID='+pid+'\\nFragmentPath='+str(unit)+'\\nExecReload={ path=/bin/kill ; argv[]=/bin/kill -HUP $MAINPID ; }')
elif sys.argv[1]=='reload':
 command=next(line.split('=',1)[1] for line in unit.read_text().splitlines() if line.startswith('ExecReload='))
 subprocess.run(command.replace('$MAINPID',pid).split(),check=True)
else:raise SystemExit('Unexpected service operation')
''')
                controller.chmod(0o755)
                environment.update(PATH=str(fakebin)+os.pathsep+os.environ['PATH'],RECOVERY_TEST_PID=str(process.pid),RECOVERY_TEST_UNIT=str(unit),RECOVERY_TEST_CALLS=str(directory/'service-calls.jsonl'))
                with connect(url.replace('http:','ws:')+'/api/v1/ws',origin=url,additional_headers={'Cookie':cookies},proxy=None) as ws:
                    assert json.loads(ws.recv(timeout=3))==before
                    output=interactive_reset(config,environment)
                    # Wait for asynchronous reload without issuing another login/KDF.
                    for _ in range(100):
                        if admin.get('/api/v1/tournament').status_code==401:break
                        time.sleep(.03)
                    else:raise AssertionError('Old admin session not revoked')
                    assert process.poll() is None
                    assert operator.get('/api/v1/tournament').json()==before
                    assert json.loads(ws.recv(timeout=7))=={'heartbeat':True}
                    login(fresh,'admin',ORIGINAL_PASSWORD,expected=401)
                    login(fresh,'admin',PASSWORD)
                    assert yaml.safe_load(auth_file.read_text())['users']['operator']==operator_record
                    assert (auth_file.stat().st_uid,auth_file.stat().st_gid)==before_owner
                    valid=auth_file.read_bytes()
                    auth_file.write_text('users: [invalid secret contents')
                    subprocess.run([controller,'reload','livescore.service'],env=environment,check=True)
                    for _ in range(100):
                        if 'Auth reload rejected' in (ARTIFACTS/'auth-recovery-server.log').read_text():break
                        time.sleep(.03)
                    else:raise AssertionError('Invalid reload not logged')
                    assert fresh.get('/api/v1/tournament').status_code==200
                    assert operator.get('/api/v1/tournament').json()==before
                    assert json.loads(ws.recv(timeout=7))=={'heartbeat':True}
                    auth_file.write_bytes(valid)
                    subprocess.run([controller,'reload','livescore.service'],env=environment,check=True)
                    assert process.poll() is None
                    stop.set();poller.join(timeout=5)
                    assert observations and not errors,errors
                    assert all(status==200 and body==before_live for status,body in observations)
                    assert {p.name:p.read_bytes() for p in (directory/'data').rglob('*.json')}==event_bytes
                    point()
                    assert json.loads(ws.recv(timeout=3))['live']['left']['score']==3
                calls=[json.loads(line) for line in (directory/'service-calls.jsonl').read_text().splitlines()]
                assert all(call[0] in ('show','reload') for call in calls),calls
                server_log=(ARTIFACTS/'auth-recovery-server.log').read_text()
                assert server_log.count('Started server process')==1
                assert PASSWORD not in server_log and 'invalid secret contents' not in server_log
                print(f'PASS: recovery through real hidden PTY/getpass; ExecReload SIGHUP; PID {process.pid} unchanged; '
                      f'{len(observations)} uninterrupted live GETs; admin sessions revoked/new password accepted; '
                      'operator session/WebSocket and active live event/score/fouls/period/history unchanged; '
                      'invalid auth rejected without downtime; no stop/start/restart commands. Host systemd untouched.')
        finally:
            stop.set()
            if poller:poller.join(timeout=5)
            if process.poll() is None:process.terminate();process.wait(timeout=10)
            log.close()


if __name__=='__main__':run()
