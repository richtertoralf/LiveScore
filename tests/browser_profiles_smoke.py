"""Admin-Profilpflege über die GUI, alle Sprachen, Operator und portable Kopien."""
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
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from livescore.auth import hash_password
ARTIFACTS = ROOT / '.test-artifacts'
PASSWORD = 'Profile browser password 2026!'


async def run(executable):
    with tempfile.TemporaryDirectory(dir=ARTIFACTS) as temp:
        directory=Path(temp)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        config=directory/'server.yml'
        config.write_text(f'bind_host: 127.0.0.1\nport: {port}\ndata_dir: data\nauth:\n  enabled: true\n  file: auth.yml\n')
        (directory/'auth.yml').write_text(yaml.safe_dump(dict(users={name:dict(role=name,password_hash=hash_password(PASSWORD),default_password=False) for name in ('admin','operator')})))
        environment=dict(os.environ,TMPDIR=str(directory),XDG_CACHE_HOME=str(directory/'cache'),XDG_CONFIG_HOME=str(directory/'config'))
        with (ARTIFACTS/'browser-profiles-server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','livescore','--config',str(config)],cwd=ROOT,env=environment,stdout=log,stderr=log)
            try:
                for _ in range(100):
                    try:
                        with urlopen(url+'/api/version',timeout=.2):break
                    except OSError:
                        if process.poll() is not None:raise RuntimeError('Server failed; see browser-profiles-server.log')
                        time.sleep(.05)
                else:raise RuntimeError('Server timeout')
                async with async_playwright() as playwright:
                    browser=await playwright.chromium.launch(headless=True,env=environment,**({'executable_path':executable} if executable else {}))
                    contexts=[await browser.new_context(viewport={'width':width,'height':1000}) for width in (900,390,768)]
                    admin,other,operator=[await c.new_page() for c in contexts]
                    errors=[]
                    for page in (admin,other,operator):page.on('pageerror',lambda error:errors.append(str(error)))
                    async def login(page,name):
                        await page.goto(url+'/login');await page.locator('#username').fill(name);await page.locator('#password').fill(PASSWORD)
                        await page.locator('#login-form button').click();await expect(page).to_have_url(url+'/')
                    async def connected(page):await expect(page.locator('#connection')).to_have_text('Connected')
                    async def click(page,selector):
                        button=page.locator(selector);await expect(button).to_be_enabled();await button.click()
                    async def state():return await (await admin.request.get(url+'/api/v1/tournament')).json()
                    async def library():return await (await admin.request.get(url+'/api/v1/sport-profiles')).json()
                    for page,name in ((admin,'admin'),(other,'admin'),(operator,'operator')):await login(page,name)
                    await admin.goto(url+'/config');await other.goto(url+'/config')
                    await expect(admin.locator('#profile-apply')).to_be_disabled()
                    await admin.locator('#profile-periods').fill('4')
                    names={'de':('Boxen','Runde','Rundenpause','Manuell erfassen'), 'en':('Boxing','Segment','Round break','Manual input'), 'cs':('Box','Část kola','Přestávka mezi koly','Ruční záznam')}
                    for lang,(name,period,pause,hint) in names.items():
                        for key,value in dict(name=name,period_label=period,break_label=pause,hint=hint).items():await admin.locator(f'#profile-{lang}-{key}').fill(value)
                    for index in range(2):
                        await click(admin,'[data-profile=add-counter]')
                        for lang in names:
                            for key,value in dict(label=f'{lang} Count {index+1}',warning_label=f'{lang} Check',critical_label=f'{lang} Critical').items():await admin.locator(f'#counter-{index}-{lang}-{key}').fill(value)
                        card=admin.locator('[data-counter-id]').nth(index)
                        await card.locator('[name=warning_at]').fill('1');await card.locator('[name=critical_at]').fill('2')
                        if index==1:await card.locator('[name=reset_each_period]').uncheck()
                    await click(admin,'[data-profile=save]')
                    await expect(admin.locator('#message')).to_contain_text('Library profile saved')
                    profiles=(await library())['profiles'];assert len(profiles)==1
                    profile_id=profiles[0]['id'];counter_ids=[c['id'] for c in profiles[0]['profile']['counters']]
                    # Edit conflict: an open admin draft must not overwrite another admin's changes.
                    await other.locator('#profile-source').select_option('library:'+profile_id)
                    await other.locator('#profile-en-name').fill('Stale draft')
                    await admin.locator('#profile-en-name').fill('Boxing revised');await click(admin,'[data-profile=save]')
                    await click(other,'[data-profile=save]')
                    await expect(other.locator('#message')).to_have_text('The profile library has changed. Reload the profile.')
                    other.on('dialog',lambda dialog:dialog.accept())
                    await click(other,'[data-profile=reload]');await expect(other.locator('#profile-en-name')).to_have_value('Boxing revised')
                    # All language fields remain editable regardless of the selected UI language.
                    for lang in ('de','cs','en'):
                        await other.locator(f'[data-lang={lang}]').click()
                        await expect(other.locator('#profile-source')).to_be_visible();await other.locator('#profile-source').select_option('library:'+profile_id)
                        for text_lang in names:await expect(other.locator(f'#profile-{text_lang}-name')).to_be_visible()
                        if lang=='cs':await other.screenshot(path=str(ARTIFACTS/'profiles-mobile-cs.png'),full_page=True)
                        assert await other.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    # Normal setup uses a file picker, never hand-written JSON/API calls.
                    await admin.goto(url+'/events');await connected(admin)
                    await admin.locator('#json-import summary').click();await admin.locator('#import-file').set_input_files(ROOT/'imports/prague-2026.json')
                    await click(admin,'[data-action=confirm-import]');await expect(admin.locator('#catalog-list article')).to_have_count(1)
                    await click(admin,'[data-action=select-event]')
                    await admin.goto(url+'/config');await expect(admin.locator('#profile-source')).to_be_visible()
                    await admin.locator('#profile-source').select_option('library:'+profile_id);await click(admin,'#profile-apply')
                    await expect(admin.locator('#message')).to_contain_text('Sport profile saved for this event')
                    snapshot=(await state())['event']['sport_profile'];assert snapshot['periods']==4
                    # Embedded profiles from other events are usable without library migration.
                    await admin.goto(url+'/events');await connected(admin)
                    await admin.locator('#json-import summary').click();await admin.locator('#import-file').set_input_files(ROOT/'imports/prague-2026.json')
                    await click(admin,'[data-action=confirm-import]');await expect(admin.locator('#catalog-list article')).to_have_count(2)
                    await admin.goto(url+'/config');await expect(admin.locator('#profile-source')).to_be_visible()
                    await admin.locator('#profile-source').select_option('event:prague-2026-2')
                    await expect(admin.locator('#profile-periods')).to_have_value('2')
                    await expect(admin.locator('#profile-cs-period_label')).to_have_value('Poločas')
                    assert (await state())['event']['sport_profile']['periods']==4
                    await operator.goto(url+'/events')
                    await expect(operator.locator('#new-event')).to_be_hidden();await expect(operator.locator('#json-import')).to_be_hidden()
                    await operator.goto(url+'/config');await expect(operator.locator('#profile-source')).to_have_count(0)
                    assert (await operator.request.get(url+'/api/v1/sport-profiles')).status==403
                    await operator.goto(url+'/');await click(operator,'[data-action=select]:first-of-type')
                    await click(operator,'[data-action=prepare]');await click(operator,'[data-action=start]')
                    for side in ('L','L','R'):await click(operator,f'[data-action="score-{side}-1"]')
                    for index,counter_id in enumerate(counter_ids):
                        for _ in range(3):await click(operator,f'[data-action=counter][data-side=L][data-counter="{counter_id}"][data-delta="1"]')
                    # Full translations, counters, hints and breaks on the operator's selected language.
                    for lang in ('de','cs','en'):
                        await operator.locator(f'[data-lang={lang}]').click()
                        await expect(operator.locator('#period-label')).to_contain_text('1. '+names[lang][1])
                        await expect(operator.locator('.profile-hint')).to_have_text(names[lang][3])
                        await expect(operator.locator(f'#counter-L-{counter_ids[0]} .counter-notice')).to_have_text(lang+' Critical')
                    await click(operator,'[data-action=intermission]')
                    await expect(operator.locator('.status')).to_have_text('Round break')
                    await click(operator,'[data-action=period-dialog]');await click(operator,'#period-confirm')
                    await expect(operator.locator('#period-label')).to_contain_text('2. Segment')
                    await expect(operator.locator(f'#counter-L-{counter_ids[0]} .counter-value')).to_have_text('0')
                    await expect(operator.locator(f'#counter-L-{counter_ids[1]} .counter-value')).to_have_text('3')
                    live=(await state())['live']
                    assert live['left']['counters']=={counter_ids[0]:0,counter_ids[1]:3}
                    assert (live['left']['score'],live['right']['score'])==(2,1)
                    assert live['period_info']['code']=='period_2' and live['period_info']['labels']['cs']=='2. Část kola'
                    # Used event structure is protected, texts remain editable even during live control.
                    await admin.goto(url+'/config');await expect(admin.locator('#profile-periods')).to_be_disabled()
                    await expect(admin.locator('[data-profile=remove-counter]').first).to_be_disabled()
                    before=(await state())['matches']
                    await admin.locator('#profile-en-period_label').fill('Name')
                    await click(admin,'#profile-apply')
                    await expect(operator.locator('#period-label')).to_contain_text('2. Name')
                    assert (await state())['matches']==before
                    # Editing/deleting the library leaves the event copy intact.
                    await admin.locator('#profile-source').select_option('library:'+profile_id);await admin.locator('#profile-periods').fill('8')
                    await click(admin,'[data-profile=save]');await expect(admin.locator('#message')).to_contain_text('Library profile saved')
                    assert (await state())['event']['sport_profile']['periods']==4
                    admin.on('dialog',lambda dialog:dialog.accept())
                    await click(admin,'[data-profile=delete]');await expect(admin.locator('#profile-source option')).to_have_count(4)
                    assert (await library())['profiles']==[]
                    assert (await state())['event']['sport_profile']['periods']==4
                    exported=await (await admin.request.get(url+'/api/v1/event-catalog/prague-2026/export')).json()
                    assert exported['event']['sport_profile']['translations']['en']['period_label']=='Name'
                    assert exported['matches'][0]['counters'][counter_ids[1]]['bsc-praha']=={'1':3,'2':3}
                    await click(operator,'[data-action=finish-dialog]');await click(operator,'#finish-confirm')
                    await click(operator,'[data-action=reopen-dialog]');await click(operator,'#reopen-confirm')
                    await click(operator,'[data-action="score-R-1"]')
                    assert (await state())['live']['status']=='live'
                    await admin.goto(url+'/config');await admin.screenshot(path=str(ARTIFACTS/'profiles-desktop-en.png'),full_page=True)
                    assert errors==[],errors
                    await browser.close()
                    print('PASS: profile CRUD without an event; concurrent admins; DE/EN/CS editing and display; GUI import/application; operator permissions; four periods; counter histories; immutable event copies; export and direct reopen.')
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--chromium')
    asyncio.run(run(parser.parse_args().chromium))
