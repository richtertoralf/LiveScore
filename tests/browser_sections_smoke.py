"""Sportprofile, Abschnittspausen und Wiederöffnen in EN/DE/CS mit zwei Browsern."""
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

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.test-artifacts'


async def run(executable, language_filter=None):
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ARTIFACTS) as temporary:
        directory = Path(temporary)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        config = directory / 'server.yml'
        config.write_text(f'bind_host: 127.0.0.1\nport: {port}\ndata_dir: data\nauth:\n  enabled: false\n')
        environment = dict(os.environ, TMPDIR=str(directory), XDG_CACHE_HOME=str(directory / 'cache'),
                           XDG_CONFIG_HOME=str(directory / 'config'))
        with (ARTIFACTS / 'browser-sections-server.log').open('w') as log:
            process = subprocess.Popen([sys.executable, '-m', 'livescore', '--config', str(config)],
                                       cwd=ROOT, env=environment, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        with urlopen(url + '/api/v1/live', timeout=.2):
                            break
                    except OSError:
                        if process.poll() is not None:
                            raise RuntimeError('Server failed; see browser-sections-server.log')
                        time.sleep(.05)
                else:
                    raise RuntimeError('Server timeout')
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=True, env=environment,
                                                               **({'executable_path': executable} if executable else {}))
                    sample = json.loads((ROOT / 'examples/prague-2026.json').read_text())
                    profiles = [('blind_football', 'Halbzeit', 2, 'half'), ('football', 'Half', 2, 'half'),
                                ('handball', 'Poločas', 2, 'half'), ('boxing', 'Runde', 3, 'round'),
                                ('showdown', 'Satz', 5, 'set'), ('other', 'Durchgang', 4, 'custom'),
                                ('many_halves', 'Halbzeit', 3, 'half'), ('single', 'Abschnitt', 1, 'period'),
                                ('no_profile', None, 1, 'period')]
                    vocabulary = {
                        'en': {'half': ('Half', 'Half-time'), 'round': ('Round', 'Round break'),
                               'set': ('Set', 'Set break'), 'custom': ('Durchgang', 'Break between periods'), 'period': ('Period', 'Break between periods')},
                        'de': {'half': ('Halbzeit', 'Halbzeitpause'), 'round': ('Runde', 'Rundenpause'),
                               'set': ('Satz', 'Satzpause'), 'custom': ('Durchgang', 'Pause zwischen Abschnitten'), 'period': ('Abschnitt', 'Pause zwischen Abschnitten')},
                        'cs': {'half': ('Poločas', 'Poločasová přestávka'), 'round': ('Kolo', 'Přestávka mezi koly'),
                               'set': ('Set', 'Přestávka mezi sety'), 'custom': ('Durchgang', 'Přestávka mezi částmi'), 'period': ('Část', 'Přestávka mezi částmi')},
                    }
                    errors = []
                    for language in vocabulary:
                        if language_filter and language != language_filter:
                            continue
                        contexts = [await browser.new_context(viewport={'width': width, 'height': 1000}) for width in (390, 768)]
                        for context in contexts:
                            await context.add_init_script(f"localStorage.setItem('livescore-language','{language}')")
                        a, b = [await context.new_page() for context in contexts]
                        for page in (a, b):
                            page.on('pageerror', lambda error: errors.append(str(error)))
                        for index, (sport, label, count, term) in enumerate(profiles):
                            data = deepcopy(sample)
                            data['event']['name'] = f'{sport} {language}'
                            data['event']['score_label'] = 'Score'
                            data['event']['sport_profile'] = dict(sport=sport, periods=count, period_label=label,
                                counters=[dict(id='count', label='Counter', reset_each_period=True)]) if label else None
                            for match in data['matches']:
                                match['counters'] = {}
                            text = json.dumps(data)
                            event_id = f'sections-{language}-{index}'

                            async def post(route, **fields):
                                response = await a.request.post(url + '/api/v1/' + route, data=fields)
                                assert response.ok, await response.text()
                                return await response.json()

                            preview = await post('event-catalog/import/preview', json_text=text, event_id=event_id)
                            state = await (await a.request.get(url + '/api/v1/tournament')).json()
                            state = await post('event-catalog/import', json_text=text, event_id=event_id,
                                preview_token=preview['preview_token'], request_id=str(uuid4()), catalog_session=state['stream_id'])
                            await post('event-catalog/select', event_id=event_id, selection_token=state['selection_token'],
                                       request_id=str(uuid4()), catalog_session=state['stream_id'])
                            await a.goto(url); await b.goto(url)

                            async def click(page, action):
                                button = page.locator(f'[data-action="{action}"]')
                                await expect(button).to_be_enabled(); await button.click()

                            async def live():
                                return await (await a.request.get(url + '/api/v1/live')).json()

                            await a.locator('[data-action=select]').first.click()
                            await click(a, 'prepare')
                            word, pause = vocabulary[language][term]
                            def start_label(number):
                                return f'{number}. {word} starten' if language == 'de' else f'Zahájit {number}. {word}' if language == 'cs' else f'Start {word} {number}'
                            if label:
                                await expect(a.locator('[data-action=start]')).to_have_text(start_label(1))
                                # A custom label must not accidentally become another UI translation.
                                assert await a.evaluate("async () => (await import('/static/i18n.js')).profileText({translations:{en:{period_label:'Name'},de:{period_label:'Name'},cs:{period_label:'Name'}}},'period_label')") == 'Name'
                            await click(a, 'start')
                            await expect(b.locator('.status')).to_have_text('LIVE' if language != 'cs' else 'ŽIVĚ')
                            if sport == 'boxing':
                                # An old client can still create paused; new GUI/API agree on live.
                                state = await (await a.request.get(url + '/api/v1/tournament')).json()
                                legacy = await post('live/pause', request_id=str(uuid4()), match_id='match-001',
                                    event_id=event_id, selection_token=state['selection_token'], expected_revision=state['revision'])
                                assert legacy['matches'][0]['status'] == 'paused' and legacy['live']['status'] == 'live'
                                await a.reload(); await b.reload()
                                await expect(b.locator('.status')).to_have_text('LIVE' if language != 'cs' else 'ŽIVĚ')
                            for page in (a, b):
                                await expect(page.locator('[data-action=pause], [data-action=resume]')).to_have_count(0)
                            for period in range(1, count + 1):
                                await expect(b.locator('[data-action=period-dialog]')).to_have_count(0)
                                if period < count:
                                    await expect(a.locator('[data-action=intermission]')).to_have_text(pause)
                                    await click(a, 'intermission')
                                    for page in (a, b):
                                        await expect(page.locator('.status')).to_have_text(pause)
                                        await expect(page.locator('[data-action=period-dialog]')).to_have_text(start_label(period + 1))
                                    assert (await live())['period_info']['intermission'] is True
                                    assert await a.locator('[data-action=period-dialog]').evaluate("node => Boolean(node.compareDocumentPosition(document.querySelector('[data-action=finish-dialog]')) & Node.DOCUMENT_POSITION_FOLLOWING)")
                                    await click(b, 'intermission')  # Korrektur ohne Abschnittswechsel.
                                    await expect(a.locator('.status')).to_have_text('LIVE' if language != 'cs' else 'ŽIVĚ')
                                    assert (await live())['period'] == period
                                    await click(a, 'intermission')
                                    await click(a, 'period-dialog'); await a.locator('#period-cancel').click()
                                    assert (await live())['period'] == period
                                    # Concurrent change invalidates the pending confirmation.
                                    await click(a, 'period-dialog'); await click(b, 'score-L-1')
                                    await expect(a.locator('#period-dialog')).not_to_be_visible()
                                    if sport in ('boxing', 'showdown') and period == 1:
                                        await a.screenshot(path=str(ARTIFACTS / f'sections-{sport}-{language}.png'), full_page=True)
                                    await click(b, 'period-dialog'); await b.locator('#period-confirm').click()
                                    await expect(a.locator('#period-label')).to_contain_text(f'{period + 1}. {word}')
                                    assert (await live())['period_info']['intermission'] is False
                                else:
                                    await expect(a.locator('[data-action=intermission]')).to_have_count(0)
                            before = await live()
                            await click(a, 'finish-dialog'); await a.locator('#finish-confirm').click()
                            await click(b, 'reopen-dialog'); await b.locator('#reopen-confirm').click()
                            await expect(a.locator('.status')).to_have_text('LIVE' if language != 'cs' else 'ŽIVĚ')
                            reopened = await live()
                            assert reopened['status'] == 'live'
                            assert (reopened['period'], reopened['left'], reopened['right']) == (before['period'], before['left'], before['right'])
                            await click(a, 'score-R-1')  # No resume step.
                            if label:
                                counter = a.locator('[data-action=counter][data-side=R][data-delta="1"]')
                                await expect(counter).to_be_enabled(); await counter.click()
                                await expect(b.locator('#counter-R-count .counter-value')).to_have_text('1')
                            await click(b, 'finish-dialog'); await b.locator('#finish-confirm').click()
                            await expect(a.locator('.status')).to_have_text({'en': 'FINISHED', 'de': 'BEENDET', 'cs': 'UKONČENO'}[language])
                            assert await a.evaluate('document.documentElement.scrollWidth <= innerWidth')
                        for context in contexts:
                            await context.close()
                    assert errors == [], errors
                    await browser.close()
                    print(f'PASS: 9 profiles × {language_filter or "EN/DE/CS"}, two browsers, all section boundaries, legacy paused and direct reopen.')
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--chromium')
    parser.add_argument('--language', choices=('en', 'de', 'cs'))
    args = parser.parse_args()
    asyncio.run(run(args.chromium, args.language))
