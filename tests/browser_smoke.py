"""Zwei isolierte Chromium-Kontexte, eigener Server und Daten nur im Repository."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.test-artifacts'


async def run(executable):
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
        directory = Path(directory)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        config = directory/'server.yml'
        config.write_text(f'bind_host: 127.0.0.1\nport: {port}\ndata_dir: data\nauth:\n  enabled: false\n')
        environment = dict(os.environ, TMPDIR=str(directory), XDG_CACHE_HOME=str(directory/'cache'), XDG_CONFIG_HOME=str(directory/'config'))
        log = (ARTIFACTS/'browser-server.log').open('w')
        process = None

        def start():
            proc = subprocess.Popen([sys.executable,'-m','livescore','--config',str(config)],cwd=ROOT,env=environment,stdout=log,stderr=log)
            for _ in range(100):
                try:
                    with urlopen(url+'/api/v1/live',timeout=.2) as response:
                        if response.status == 200: return proc
                except OSError: pass
                if proc.poll() is not None: raise RuntimeError('Serverstart fehlgeschlagen; browser-server.log prüfen')
                time.sleep(.05)
            proc.terminate(); proc.wait(timeout=10)
            raise RuntimeError('Serverstart Timeout')

        try:
            process = start()
            async with async_playwright() as playwright:
                launch = dict(headless=True,env=environment)
                if executable: launch['executable_path'] = executable
                browser = await playwright.chromium.launch(**launch)
                a = await browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
                b = await browser.new_context(viewport={'width':768,'height':1024},has_touch=True)
                await a.add_init_script("localStorage.setItem('livescore-language','de')")
                await b.add_init_script("localStorage.setItem('livescore-language','de')")
                page_a, page_b = await a.new_page(), await b.new_page()
                errors = []
                for page in (page_a,page_b): page.on('pageerror',lambda error:errors.append(str(error)))
                await page_a.goto(url+'/events'); await page_b.goto(url)
                await expect(page_a.locator('#connection')).to_have_text('Verbunden')

                async def form(kind, fields):
                    target = page_a.locator(f'form[data-kind="{kind}"]')
                    for key,value in fields.items():
                        control = target.locator(f'[name="{key}"]')
                        if await control.evaluate('(node) => node.tagName') == 'SELECT':
                            await control.select_option(label=value)
                        else: await control.fill(value)
                    await target.locator('button[type=submit]').click()
                    await expect(page_a.locator('#message')).to_have_text('Gespeichert.')

                async def action(page, name):
                    target = page.locator(f'[data-action="{name}"]')
                    await expect(target).to_be_enabled(); await target.click()
                async def assert_officials(page):
                    live = await (await page.request.get(url+'/api/v1/live')).json()
                    expected = 'Officials: ' + ' · '.join(r['name'] + (f" ({r['country_code']})" if r['country_code'] else '') for r in live['officials'])
                    if live['officials']: await expect(page.locator('#officials')).to_have_text(expected)
                    else: await expect(page.locator('#officials')).to_have_count(0)

                async def scores(left,right):
                    for page in (page_a,page_b):
                        await expect(page.locator('#score-L')).to_have_text(str(left))
                        await expect(page.locator('#score-R')).to_have_text(str(right))
                        await assert_officials(page)

                async def foul(page, side='L', delta=1):
                    control = page.locator(f'[data-action="counter"][data-side="{side}"][data-counter="team_fouls"][data-delta="{delta}"]')
                    await expect(control).to_be_enabled(); await control.click()

                async def fouls(left, right, period=1):
                    for page in (page_a, page_b):
                        await expect(page.locator('#counter-L-team_fouls .counter-value')).to_have_text(str(left))
                        await expect(page.locator('#counter-R-team_fouls .counter-value')).to_have_text(str(right))
                        await expect(page.locator('#period-label')).to_contain_text(f'{period}. Halbzeit')
                        await assert_officials(page)

                async def choose(event_id):
                    await page_a.goto(url+'/events')
                    await expect(page_a.locator('#connection')).to_have_text('Verbunden')
                    await page_a.locator(f'[data-action="select-event"][data-id="{event_id}"]').click()
                    await expect(page_a.locator(f'[data-event-id="{event_id}"]')).to_have_class('panel active-event')

                # Event A manually; event B through a real file input and preview.
                await page_a.locator('#new-event summary').click()
                for key,value in dict(name='Browser Cup',date_from='2026-10-03',date_to='2026-10-04',location='Prag',score_label='Punkte').items():
                    await page_a.locator(f'#create-event [name="{key}"]').fill(value)
                await page_a.locator('#create-event button[type=submit]').click()
                await expect(page_a.locator('#catalog-list article')).to_have_count(1)
                catalog = await (await page_a.request.get(url+'/api/v1/event-catalog')).json()
                event_a = catalog['items'][0]['id']
                await page_a.locator('#json-import summary').click()
                await page_a.locator('#import-file').set_input_files(ROOT/'imports/prague-2026.json')
                await expect(page_a.locator('#import-preview')).to_be_visible()
                await expect(page_a.locator('#import-preview')).to_contain_text('6 Referees')
                await expect(page_a.locator('#import-preview')).to_contain_text('14 Spiele')
                assert len((await (await page_a.request.get(url+'/api/v1/event-catalog')).json())['items']) == 1
                await page_a.locator('[data-action="confirm-import"]').click()
                await expect(page_a.locator('#catalog-list article')).to_have_count(2)
                await expect(page_a.locator('#import-preview')).not_to_be_visible()
                await expect(page_a.locator('#import-file')).to_be_enabled()
                event_b = 'prague-2026'
                await page_a.locator('#import-file').set_input_files(ROOT/'imports/prague-2026.json')
                await expect(page_a.locator('[data-action="confirm-import"]')).to_have_text('Als neue Veranstaltung importieren')
                await page_a.locator('[data-action="cancel-import"]').click()
                await choose(event_a)
                await expect(page_b.locator('#active-event-name')).to_have_text('Browser Cup')
                await expect(page_a.locator('#active-event-name')).to_have_text('Browser Cup')
                # Open config draft must be discarded when another browser switches.
                await page_b.goto(url+'/config')
                await page_b.locator('#event-name').fill('Ungespeicherter alter Entwurf')
                await choose(event_b)
                await expect(page_b.locator('#event-name')).to_have_value('13th Cup of Central Europe Cities 2026')
                await expect(page_b.locator('#message')).to_contain_text('Ungespeicherte Formulare')
                await page_a.screenshot(path=str(ARTIFACTS/'mobile-events.png'),full_page=True)
                await page_b.screenshot(path=str(ARTIFACTS/'tablet-config.png'),full_page=True)
                await page_b.goto(url); await page_a.goto(url)
                await expect(page_b.locator('#active-event-name')).to_have_text('13th Cup of Central Europe Cities 2026')
                await page_a.locator('[data-action=select]').first.click()
                await action(page_a,'prepare'); await action(page_a,'start'); await action(page_a,'score-L-1')
                await scores(1,0)
                live = await (await page_a.request.get(url+'/api/v1/live')).json()
                assert live['left']['country_code'] == 'CZ' and live['right']['country_code'] == 'DE'
                for _ in range(4): await foul(page_a)
                await fouls(4,0)
                for page in (page_a,page_b):
                    await expect(page.locator('#counter-L-team_fouls')).to_have_class('counter warning')
                    await expect(page.locator('#counter-L-team_fouls')).to_contain_text('Nächstes Foul → Double Penalty')
                await foul(page_b); await fouls(5,0)
                for page in (page_a,page_b):
                    await expect(page.locator('#counter-L-team_fouls')).to_have_class('counter critical')
                    await expect(page.locator('#counter-L-team_fouls .counter-notice')).to_have_text('Double Penalty')
                await foul(page_a); await fouls(6,0)
                await page_a.screenshot(path=str(ARTIFACTS/'mobile-counters.png'),full_page=True)
                await page_b.screenshot(path=str(ARTIFACTS/'tablet-counters.png'),full_page=True)
                for page in (page_a,page_b):
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Counter-Überlauf'
                await foul(page_b,delta=-1); await fouls(5,0)
                await action(page_a,'switch-sides'); await fouls(0,5); await scores(0,1)
                await action(page_a,'switch-sides'); await fouls(5,0); await scores(1,0)
                await action(page_a,'period-dialog')
                await page_a.locator('#period-cancel').click(); await fouls(5,0)
                # Another operator's change invalidates a pending period confirmation.
                await action(page_a,'period-dialog'); await foul(page_b)
                await expect(page_a.locator('#period-dialog')).not_to_be_visible()
                await fouls(6,0)
                await action(page_a,'pause')
                await expect(page_b.locator('.status')).to_have_text('PAUSE')
                await action(page_a,'period-dialog')
                await page_a.locator('#period-confirm').click()
                await fouls(0,0,2); await scores(1,0)
                for page in (page_a,page_b):
                    await expect(page.locator('[data-action="period-dialog"]')).to_have_count(0)
                    await expect(page.locator('[data-action="counter"][data-side="L"][data-delta="-1"]')).to_be_disabled()
                await asyncio.gather(foul(page_a),foul(page_b))
                await fouls(2,0,2)
                await action(page_a,'resume')
                match = (await (await page_a.request.get(url+'/api/v1/tournament')).json())['matches'][0]
                assert match['counters']['team_fouls']['bsc-praha'] == {'1':6,'2':2}
                # Restart with both browsers still showing the active second period.
                process.terminate(); process.wait(timeout=10)
                await expect(page_a.locator('#connection')).to_have_text('Offline · Bedienung gesperrt')
                process = start()
                for page in (page_a,page_b):
                    await expect(page.locator('#connection')).to_have_text('Verbunden',timeout=15000)
                await fouls(2,0,2); await scores(1,0)
                await page_a.goto(url+'/events')
                await page_a.locator(f'[data-id="{event_a}"]').click()
                await expect(page_a.locator('#message')).to_contain_text('Aktuell ist ein Spiel vorbereitet oder aktiv')
                await expect(page_b.locator('.status')).to_have_text('LIVE')
                await action(page_b,'finish-dialog'); await page_b.locator('#finish-confirm').click()
                await expect(page_b.locator('.status')).to_have_text('BEENDET')
                await choose(event_a)
                await expect(page_b.locator('#active-event-name')).to_have_text('Browser Cup')
                assert (await (await page_b.request.get(url+'/api/v1/tournament')).json())['matches'] == []
                await choose(event_b)
                await expect(page_b.locator('#score-L')).to_have_text('1')
                async with page_a.expect_download() as download_info:
                    await page_a.locator(f'[data-event-id="{event_b}"] a[download]').click()
                download = await download_info.value
                await download.save_as(ARTIFACTS/'export-prague.json')
                exported = json.loads((ARTIFACTS/'export-prague.json').read_text())
                assert exported['matches'][0]['scores']['bsc-praha'] == 1
                assert 'active_event_id' not in exported
                assert len(exported['referees']) == 6 and len(exported['matches']) == 14
                assert all(len(match['officials']) == 3 for match in exported['matches'])
                assert exported['participants'][0]['country_code'] == 'CZ'
                assert exported['event']['sport_profile']['sport'] == 'blind_football'
                assert exported['matches'][0]['period'] == 2
                assert exported['matches'][0]['counters']['team_fouls']['bsc-praha'] == {'1':6,'2':2}
                # Reimport the exported portable state through the same file input.
                copy_file = directory/'prague-2026.json'
                copy_file.write_text(json.dumps(exported,ensure_ascii=False))
                await page_a.locator('#json-import summary').click()
                await page_a.locator('#import-file').set_input_files(copy_file)
                await expect(page_a.locator('[data-action="confirm-import"]')).to_have_text('Als neue Veranstaltung importieren')
                await page_a.locator('[data-action="confirm-import"]').click()
                await expect(page_a.locator('#import-preview')).not_to_be_visible()
                await expect(page_a.locator('#catalog-list article')).to_have_count(3)
                roundtrip = await (await page_a.request.get(url+'/api/v1/event-catalog/prague-2026-2/export')).json()
                assert roundtrip == exported

                await choose(event_a)
                await page_a.goto(url+'/config')
                await form('event',dict(name='Browser Cup',date_from='2026-10-03',date_to='2026-10-04',location='Prag',score_label='Punkte'))
                await form('play-areas',dict(label='Field 1'))
                await form('participants',dict(name='BSC Praha',short_name='BSC',country_code='cz'))
                await page_a.locator('#list-participants button').first.click()
                await expect(page_a.locator('#participants-country_code')).to_have_value('CZ')
                await form('participants',dict(name='BSC Praha',country_code='CZ'))
                await form('participants',dict(name='FC Ingolstadt 04',short_name='FCI'))
                await form('participants',dict(name='Kairat Almaty',short_name='KAI'))
                await form('referees',dict(name='Reviewer One',country_code='DE'))
                await page_a.locator('#list-referees button').first.click()
                await form('referees',dict(name='Reviewer One Edited'))
                await form('referees',dict(name='Reviewer Two'))
                await form('referees',dict(name='Reviewer Three',country_code='HU'))
                await form('matches',dict(date='2026-10-03',time='09:30',play_area_id='Field 1',round='Gruppe A',participant_1='BSC Praha',participant_2='FC Ingolstadt 04',official_slot_0='Reviewer One Edited (DE)',official_slot_1='Reviewer Two',official_slot_2='Reviewer Three (HU)'))
                await form('matches',dict(date='2026-10-04',time='08:30',play_area_id='Field 1',round='Finale',placeholder_1='Finalist 1',placeholder_2='Finalist 2'))
                await expect(page_b.locator('[data-action=select]')).to_have_count(2)
                await page_a.goto(url)
                await page_a.locator('[data-action=select]').first.click()
                await expect(page_b.locator('.status')).to_have_text('NÄCHSTES SPIEL')
                await action(page_a,'edit-pair')
                await page_a.locator('#pair-2').select_option(label='Kairat Almaty')
                await action(page_a,'prepare')
                await expect(page_b.locator('#name-R')).to_have_text('Kairat Almaty')
                await action(page_a,'unprepare'); await action(page_a,'edit-pair')
                await page_a.locator('#pair-2').select_option(label='FC Ingolstadt 04')
                await action(page_a,'prepare')
                await action(page_b,'switch-sides'); await expect(page_a.locator('#name-L')).to_have_text('FC Ingolstadt 04')
                await action(page_a,'switch-sides'); await action(page_a,'start')
                await expect(page_b.locator('.status')).to_have_text('LIVE')
                await action(page_a,'score-L-1'); await scores(1,0)
                await action(page_b,'score-L-1'); await scores(2,0)
                await action(page_b,'score-R-1'); await scores(2,1)
                await action(page_a,'switch-sides'); await scores(1,2)
                await expect(page_b.locator('#name-R')).to_have_text('BSC Praha')
                await action(page_b,'score-R--1'); await scores(1,1)
                await action(page_a,'undo'); await scores(1,2)
                await action(page_a,'pause'); await expect(page_b.locator('.status')).to_have_text('PAUSE')
                await action(page_b,'resume'); await expect(page_a.locator('.status')).to_have_text('LIVE')
                # Two browser contexts send scores from the same displayed state.
                await asyncio.gather(action(page_a,'score-L-1'),action(page_b,'score-L-1'))
                await scores(3,2)
                # Mobile double click must book once.
                await expect(page_a.locator('[data-action="score-R-1"]')).to_be_enabled()
                await page_a.locator('[data-action="score-R-1"]').dblclick(delay=30)
                await scores(3,3)
                await page_a.reload(); await scores(3,3)
                await b.set_offline(True)
                await expect(page_b.locator('#connection')).to_have_text('Offline · Bedienung gesperrt',timeout=20000)
                await expect(page_b.locator('[data-action="score-L-1"]')).to_be_disabled()
                await action(page_a,'score-R-1')
                await b.set_offline(False)
                await expect(page_b.locator('#connection')).to_have_text('Verbunden',timeout=15000)
                await scores(3,4)
                # A changed score invalidates the other browser's finish dialog.
                await action(page_b,'finish-dialog')
                await expect(page_b.locator('#finish-dialog')).to_be_visible()
                await action(page_a,'score-L-1')
                await expect(page_b.locator('#finish-dialog')).not_to_be_visible()
                await scores(4,4)
                await expect(page_a.locator('[data-action="score-L-1"]')).to_be_enabled()
                await page_a.screenshot(path=str(ARTIFACTS/'mobile-live.png'),full_page=True)
                await page_b.screenshot(path=str(ARTIFACTS/'tablet-live.png'),full_page=True)
                for page in (page_a,page_b):
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontaler Überlauf'
                curl = subprocess.check_output(['curl','--fail','--silent','--show-error',url+'/api/v1/live'],text=True)
                live = json.loads(curl)
                assert live['left']['score'] == live['right']['score'] == 4
                (ARTIFACTS/'curl-live.json').write_text(json.dumps(live,indent=2)+'\n')
                # Real server restart while both pages remain open.
                active = await (await page_a.request.get(url+'/api/v1/tournament')).json()
                persisted = json.loads((directory/'data'/'events'/f"{active['active_event_id']}.json").read_text())
                process.terminate(); process.wait(timeout=10)
                await expect(page_a.locator('#connection')).to_have_text('Offline · Bedienung gesperrt')
                process = start()
                await expect(page_a.locator('#connection')).to_have_text('Verbunden',timeout=15000)
                await expect(page_b.locator('#connection')).to_have_text('Verbunden',timeout=15000)
                await scores(4,4)
                restored = await (await page_a.request.get(url+'/api/v1/tournament')).json()
                assert restored['revision'] == persisted['revision']
                await action(page_a,'undo'); await scores(3,4)
                await action(page_a,'finish-dialog'); await page_a.locator('#finish-cancel').click()
                await expect(page_b.locator('.status')).to_have_text('LIVE')
                await action(page_a,'finish-dialog'); await page_a.locator('#finish-confirm').click()
                await expect(page_b.locator('.status')).to_have_text('BEENDET')
                await page_b.locator('[data-action=select]').click()
                await expect(page_a.locator('.status')).to_have_text('NÄCHSTES SPIEL')
                await page_a.locator('#pair-1').select_option(label='BSC Praha')
                await page_a.locator('#pair-2').select_option(label='Kairat Almaty')
                await action(page_a,'prepare'); await action(page_b,'start'); await scores(0,0)
                await action(page_a,'finish-dialog'); await page_a.locator('#finish-confirm').click()
                await expect(page_b.locator('.status')).to_have_text('BEENDET')
                await choose(event_b)
                await expect(page_b.locator('#score-L')).to_have_text('1')
                await assert_officials(page_b)
                await expect(page_b.locator('#period-label')).to_contain_text('2. Halbzeit')
                await expect(page_b.locator('#counter-L-team_fouls .counter-value')).to_have_text('2')
                assert len((await (await page_a.request.get(url+'/api/v1/event-catalog')).json())['items']) == 3
                assert not errors, errors
                await browser.close()
                print('PASS: Participant-Ländercodes, Prag-Profil, Counter +/−, Warnung bei 4, Critical bei 5/6, parallele Counter in zwei Browsern, Seitenwechsel, bestätigter/abgebrochener/veralteter Periodendialog, Periodenhistorie und echter Neustart in Periode 2; Prag-Datei (6 Referees, 14 Matches mit je 3 Officials), Referee-Anlage/Bearbeitung, Officials-Auswahl, Export/Reimport vollständig; Event-Neuanlage, Dateiimport mit Preview/Kollision/Abbruch, Event-Wechsel, Config-Entwurf verworfen, Isolation; Paarungskorrektur, parallele Scores, Doppelklick, Undo, Pause, Offline/Reconnect, Reload, Ergebnisbestätigung, nächstes Spiel, curl; keine JS-Fehler.')
        finally:
            if process and process.poll() is None:
                process.terminate(); process.wait(timeout=10)
            log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--chromium',help='Optionaler vorhandener Chromium-Pfad')
    asyncio.run(run(parser.parse_args().chromium))
