"""Korrektur mit zwei echten Operator-Logins, DE/EN/CS, Profilen und Neustart."""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from uuid import uuid4

from playwright.async_api import async_playwright, expect
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from livescore.auth import hash_password

ARTIFACTS = ROOT / '.test-artifacts'
PASSWORD = 'Operator reset smoke 2026!'


async def run(executable):
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ARTIFACTS) as temporary:
        directory = Path(temporary)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        config = directory / 'server.yml'
        config.write_text(f'bind_host: 127.0.0.1\nport: {port}\ndata_dir: data\nauth:\n  enabled: true\n  file: auth.yml\n')
        directory.joinpath('auth.yml').write_text(yaml.safe_dump(dict(users={
            name: dict(role=name, password_hash=hash_password(PASSWORD), default_password=False)
            for name in ('admin', 'operator')})))
        sample = json.loads((ROOT / 'examples/prague-2026.json').read_text())
        events = directory / 'data/events'; events.mkdir(parents=True)
        for lang in ('de', 'en', 'cs'):
            for sport, count, word in (('boxing', 4, 'Runde'), ('showdown', 5, 'Satz'), ('none', 1, 'Abschnitt')):
                data = deepcopy(sample)
                data['event']['name'] = f'{sport} {lang}'
                data['event']['sport_profile'] = None if sport == 'none' else dict(periods=count,
                    period_label=word, counters=[dict(id='count', label='Counter', reset_each_period=True)])
                for match in data['matches']: match['counters'] = {}
                other = data['matches'][1]
                other.update(status='finished', side_l=other['participant_1'], side_r=other['participant_2'],
                    scores={other['participant_1']: 2, other['participant_2']: 1})
                (events / f'{sport}-{lang}.json').write_text(json.dumps(data))
        environment = dict(os.environ, TMPDIR=str(directory), XDG_CACHE_HOME=str(directory/'cache'),
                           XDG_CONFIG_HOME=str(directory/'config'))
        with (ARTIFACTS / 'browser-reset-server.log').open('w') as log:
            process = None
            def start():
                proc = subprocess.Popen([sys.executable, '-m', 'livescore', '--config', str(config)],
                                        cwd=ROOT, env=environment, stdout=log, stderr=log)
                for _ in range(100):
                    try:
                        with urlopen(url+'/api/v1/live', timeout=.2): return proc
                    except OSError:
                        if proc.poll() is not None: raise RuntimeError('Server failed; see browser-reset-server.log')
                        time.sleep(.05)
                proc.terminate(); proc.wait(timeout=10); raise RuntimeError('Server timeout')
            try:
                process = start()
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, env=environment,
                        **({'executable_path': executable} if executable else {}))
                    errors = []
                    for lang in ('de', 'en', 'cs'):
                        contexts = [await browser.new_context(viewport={'width':w, 'height':900}) for w in (390, 1024)]
                        a, b = [await c.new_page() for c in contexts]
                        async def login(page):
                            await page.goto(url+'/login')
                            await page.locator('#username').fill('operator'); await page.locator('#password').fill(PASSWORD)
                            await page.locator('#login-form button').click()
                            await expect(page.locator('#connection')).to_contain_text({'de':'Verbunden', 'en':'Connected', 'cs':'Připojeno'}[lang])
                        for c, page in zip(contexts, (a,b)):
                            await c.add_init_script(f"localStorage.setItem('livescore-language','{lang}')")
                            page.on('pageerror', lambda e: errors.append(str(e)))
                            await login(page)
                        async def click(page, action):
                            button = page.locator(f'[data-action="{action}"]')
                            await expect(button).to_be_enabled(); await button.click()
                        async def state(): return await (await a.request.get(url+'/api/v1/tournament')).json()
                        async def live(): return await (await a.request.get(url+'/api/v1/live')).json()
                        async def confirm_reset(page):
                            await click(page, 'reset-dialog'); await expect(page.locator('#reset-confirm')).to_be_enabled()
                            await page.locator('#reset-confirm').click()
                            await expect(page.locator('#pair-1')).to_be_visible()
                        for sport in ('boxing', 'showdown', 'none'):
                            await a.goto(url+'/events')
                            await a.locator(f'[data-event-id="{sport}-{lang}"] [data-action=select-event]').click()
                            await a.goto(url+'/'); await b.reload()
                            await expect(a.locator('#active-event-name')).to_have_text(f'{sport} {lang}')
                            before = await state()
                            await a.locator('[data-action=select][data-id=match-001]').click()
                            await click(a, 'prepare')
                            await confirm_reset(a)  # same action while ready
                            await click(a, 'prepare'); await click(a, 'start')
                            await click(a, 'score-L-1'); await click(b, 'score-R-1')
                            if sport != 'none':
                                await a.locator('[data-action=counter][data-side=L][data-delta="1"]').click()
                                await click(a, 'intermission'); await click(a, 'period-dialog')
                                await a.locator('#period-confirm').click()
                                await click(a, 'intermission')
                            await click(a, 'reset-dialog')
                            await expect(a.locator('#reset-result')).to_contain_text('1 : 1')
                            await expect(a.locator('#reset-dialog h2')).to_have_text({
                                'de':'Dieses Spiel zurücksetzen?', 'en':'Reset this match?', 'cs':'Resetovat tento zápas?'}[lang])
                            await a.locator('#reset-cancel').click()
                            assert (await live())['status'] == 'live'
                            await click(a, 'reset-dialog'); await click(b, 'score-L-1')
                            await expect(a.locator('#reset-dialog')).not_to_be_visible()
                            assert (await live())['left']['score'] == 2
                            if sport == 'boxing' and lang == 'cs':
                                s = await state()
                                session = await (await a.request.get(url+'/api/auth/session')).json()
                                response = await a.request.post(url+'/api/v1/live/pause', data=dict(
                                    request_id=str(uuid4()), expected_revision=s['revision'], event_id=s['active_event_id'],
                                    selection_token=s['selection_token'], match_id='match-001'),
                                    headers={'X-CSRF-Token': session['csrf_token']})
                                assert response.ok, await response.text()
                            await click(a, 'reset-dialog')
                            await a.screenshot(path=str(ARTIFACTS/f'reset-{sport}-{lang}.png'), full_page=True)
                            await expect(a.locator('#reset-confirm')).to_be_enabled(); await a.locator('#reset-confirm').click()
                            await expect(a.locator('#pair-1')).to_be_visible()
                            for page in (a,b):
                                await expect(page.locator('[data-action=score-L-1]')).to_have_count(0)
                            reset = await state()
                            assert reset['matches'][1:] == before['matches'][1:]
                            assert reset['event'] == before['event']
                            assert reset['matches'][0]['counters'] == {} and reset['live']['left'] is None
                            await a.locator('#pair-1').select_option('kairat-almaty')
                            await a.locator('#pair-2').select_option('blista-marburg')
                            await click(a, 'prepare'); await click(a, 'start')
                            await expect(b.locator('#name-L')).to_have_text('Kairat Almaty')
                            await expect(b.locator('[data-action=undo]')).to_be_disabled()
                            await click(b, 'score-L-1'); await click(a, 'undo')
                            await expect(b.locator('#score-L')).to_have_text('0')
                            await expect(b.locator('[data-action=undo]')).to_be_disabled()
                            if sport == 'boxing' and lang == 'cs':
                                process.terminate(); process.wait(timeout=10); process = start()
                                await login(a); await login(b)
                                await expect(b.locator('#name-L')).to_have_text('Kairat Almaty')
                                await expect(b.locator('[data-action=undo]')).to_be_disabled()
                            await click(a, 'finish-dialog'); await a.locator('#finish-confirm').click()
                            await a.locator('[data-action=select][data-id=match-003]').click()
                            await click(a, 'toggle-finished')
                            await a.locator('[data-action=select][data-id=match-001]').click()
                            await expect(b.locator('[data-action=reopen-dialog]')).to_be_enabled()
                            await confirm_reset(b)  # finished, reselected, operator B
                            await expect(a.locator('[data-action=prepare]')).to_be_enabled()
                            assert (await state())['matches'][1:] == before['matches'][1:]
                            assert not await b.locator('[data-action=pause], [data-action=resume]').count()
                            assert await b.evaluate('document.documentElement.scrollWidth <= innerWidth')
                            exported = await a.request.get(url+f'/api/v1/event-catalog/{sport}-{lang}/export')
                            exported_data = await exported.json()
                            assert len([e for e in exported_data['events'] if e['type']=='match_reset']) == 3
                        for c in contexts: await c.close()
                    assert errors == [], errors
                    await browser.close()
                    print('PASS: two operator logins; ready/live/intermission/legacy paused/finished; DE/EN/CS; boxing/showdown/no profile; dialogs/cancel/conflict; corrected pairing and Undo; isolation/export/restart; mobile/desktop.')
            finally:
                if process and process.poll() is None: process.terminate(); process.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--chromium')
    asyncio.run(run(parser.parse_args().chromium))
