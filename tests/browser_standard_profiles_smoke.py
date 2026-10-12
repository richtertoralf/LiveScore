"""Alle sieben ausgelieferten Profile über Admin- und Operator-GUI prüfen."""
import argparse
import asyncio
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from playwright.async_api import async_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'.test-artifacts'

async def run(executable):
    with tempfile.TemporaryDirectory(dir=ARTIFACTS) as temporary:
        directory=Path(temporary)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        config=directory/'server.yml'
        config.write_text(f'bind_host: 127.0.0.1\nport: {port}\ndata_dir: data\nauth:\n  enabled: false\n')
        environment=dict(os.environ,TMPDIR=str(directory),XDG_CACHE_HOME=str(directory/'cache'),XDG_CONFIG_HOME=str(directory/'config'))
        with (ARTIFACTS/'browser-standard-profiles-server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','livescore','--config',str(config)],cwd=ROOT,env=environment,stdout=log,stderr=log)
            try:
                for _ in range(100):
                    try:
                        with urlopen(url+'/api/version',timeout=.2):break
                    except OSError:time.sleep(.05)
                else:raise RuntimeError('Server timeout')
                async with async_playwright() as p:
                    browser=await p.chromium.launch(headless=True,env=environment,**({'executable_path':executable} if executable else {}))
                    contexts=[await browser.new_context(viewport={'width':width,'height':1000}) for width in (900,390,768)]
                    admin,operator,observer=[await context.new_page() for context in contexts]
                    errors=[]
                    for page in (admin,operator,observer):page.on('pageerror',lambda error:errors.append(str(error)))
                    async def click(page,selector):
                        item=page.locator(selector);await expect(item).to_be_enabled();await item.click()
                    async def state():return await (await admin.request.get(url+'/api/v1/tournament')).json()
                    await admin.goto(url+'/config')
                    await expect(admin.locator('#profile-source option[value^="library:standard-"]')).to_have_count(7)
                    await admin.goto(url+'/events');await admin.locator('#json-import summary').click()
                    await admin.locator('#import-file').set_input_files(ROOT/'imports/prague-2026.json')
                    await click(admin,'[data-action=confirm-import]');await click(admin,'[data-action=select-event]')
                    profiles=(await (await admin.request.get(url+'/api/v1/sport-profiles')).json())['profiles']
                    for entry in profiles:
                        profile=entry['profile'];identifier=entry['id']
                        await admin.goto(url+'/config');await expect(admin.locator('#profile-source')).to_be_visible()
                        await admin.locator('#profile-source').select_option('library:'+identifier)
                        await expect(admin.locator('#profile-score-mode')).to_have_value(profile['score_mode'])
                        for lang in ('de','en','cs'):
                            for key in ('name','period_label','break_label','score_label','sets_label'):
                                await expect(admin.locator(f'#profile-{lang}-{key}')).to_be_visible()
                        if identifier=='standard-boxing':
                            for index in (0,1):
                                for lang in ('de','en','cs'):await expect(admin.locator(f'#role-{index}-{lang}-label')).to_be_visible()
                        await click(admin,'#profile-apply');await expect(admin.locator('#message')).to_contain_text('Sport profile saved for this event')
                        await operator.goto(url);await observer.goto(url)
                        await click(operator,'[data-action=select]:first-of-type')
                        await click(operator,'[data-action=prepare]');await click(operator,'[data-action=start]')
                        for lang in ('de','en','cs'):
                            await operator.locator(f'[data-lang={lang}]').click()
                            text=profile['translations'][lang]['period_label']
                            await expect(operator.locator('#period-label')).to_contain_text(text+' 1' if lang=='en' else '1. '+text)
                            if profile['score_mode']=='none':
                                await expect(operator.locator('.score')).to_have_count(0)
                                await expect(operator.locator('[data-action^="score-"]')).to_have_count(0)
                                await expect(operator.locator('.counter')).to_have_count(0)
                                await expect(operator.locator('#officials')).to_have_count(0)
                                await expect(operator.locator('[data-action=undo]')).to_have_count(0)
                                await expect(operator.locator('#role-L')).to_have_text(profile['roles']['participant_1']['labels'][lang])
                            else:await expect(operator.locator('#score-L')).to_have_text('0')
                            assert await operator.evaluate('document.documentElement.scrollWidth <= innerWidth')
                        await operator.locator('[data-lang=en]').click()
                        if profile['score_mode']!='none':
                            step=max(profile['score_steps'])
                            await click(operator,f'[data-action="score-L-{step}"]')
                            await expect(observer.locator('#score-L')).to_have_text(str(step))
                            await click(operator,'[data-action=undo]');await expect(operator.locator('#score-L')).to_have_text('0')
                            await click(operator,f'[data-action="score-L-{step}"]')
                            if profile['sets_enabled']:
                                await click(operator,'[data-action="sets-L-1"]');await expect(observer.locator('#sets-L')).to_have_text('1')
                        if profile['counters']:
                            await click(operator,'[data-action=counter][data-side=L][data-delta="1"]')
                        before=(await state())['live']
                        await click(operator,'[data-action=switch-sides]')
                        if profile['roles']:
                            await expect(operator.locator('#role-R')).to_have_text('Red corner')
                            await expect(observer.locator('#role-R')).to_have_text('Red corner')
                            after=(await state())['live'];assert after['right']['role']==before['left']['role']
                            assert after['right']['id']==before['left']['id']
                        await click(operator,'[data-action=intermission]')
                        await expect(operator.locator('.status')).to_have_text(profile['translations']['en']['break_label'])
                        await click(operator,'[data-action=period-dialog]');await click(operator,'#period-confirm')
                        if profile['score_mode']=='period':
                            await expect(operator.locator('#score-R')).to_have_text('0')
                            await expect(operator.locator('#sets-R')).to_have_text('1')
                            await expect(operator.locator('.period-history tbody tr')).to_have_count(2)
                            live=(await state())['live'];assert live['right']['period_scores']=={'1':step,'2':0}
                        elif profile['score_mode']=='total':await expect(operator.locator('#score-R')).to_have_text('1')
                        await click(operator,'[data-action=finish-dialog]');await click(operator,'#finish-confirm')
                        await click(operator,'[data-action=reopen-dialog]');await click(operator,'#reopen-confirm')
                        await expect(operator.locator('.status')).to_have_text('LIVE')
                        await expect(operator.locator('[data-action=switch-sides]')).to_be_enabled()
                        if identifier in ('standard-boxing','standard-showdown'):
                            await operator.screenshot(path=str(ARTIFACTS/(identifier+'-mobile.png')),full_page=True)
                        await click(operator,'[data-action=reset-dialog]');await click(operator,'#reset-confirm')
                        await expect(operator.locator('#pair-1')).to_be_visible()
                        match=(await state())['matches'][0]
                        assert match['period_scores']=={} and match['sets_won']=={} and match['scores']=={}
                    # All new configuration fields are editable, not just shipped presets.
                    await admin.goto(url+'/config');await expect(admin.locator('#profile-source')).to_be_visible()
                    await admin.locator('#profile-source').select_option('new')
                    await admin.locator('#profile-periods').fill('4')
                    await admin.locator('#profile-score-mode').select_option('period')
                    await admin.locator('#profile-score-steps').fill('1, 2')
                    await admin.locator('[name=sets_enabled]').check()
                    await admin.locator('[name=show_details]').uncheck();await admin.locator('[name=show_officials]').uncheck()
                    await admin.locator('[name=roles_enabled]').check()
                    for lang in ('de','en','cs'):
                        await admin.locator(f'#profile-{lang}-name').fill('Custom '+lang)
                        await admin.locator(f'#profile-{lang}-score_label').fill('Points '+lang)
                        await admin.locator(f'#profile-{lang}-sets_label').fill('Sets '+lang)
                        for index in (0,1):await admin.locator(f'#role-{index}-{lang}-label').fill(f'Role {index+1} {lang}')
                    await click(admin,'[data-profile=add-counter]')
                    for lang in ('de','en','cs'):
                        await admin.locator(f'#counter-0-{lang}-label').fill('Count '+lang)
                    await admin.locator('[data-counter-id] [name=enabled]').uncheck()
                    await admin.locator('[data-counter-id] [name=reset_each_period]').uncheck()
                    await click(admin,'[data-profile=save]');await expect(admin.locator('#message')).to_contain_text('Library profile saved')
                    stored=(await (await admin.request.get(url+'/api/v1/sport-profiles')).json())['profiles']
                    custom=next(entry['profile'] for entry in stored if entry['profile']['translations']['en']['name']=='Custom en')
                    assert custom['score_mode']=='period' and custom['score_steps']==[1,2] and custom['sets_enabled']
                    assert not custom['show_details'] and not custom['show_officials']
                    assert not custom['counters'][0]['enabled'] and not custom['counters'][0]['reset_each_period']
                    for lang in ('de','en','cs'):
                        assert custom['roles']['participant_1']['labels'][lang]=='Role 1 '+lang
                        assert custom['translations'][lang]['score_label']=='Points '+lang
                    await click(admin,'#profile-apply');await expect(admin.locator('#message')).to_contain_text('Sport profile saved for this event')
                    await operator.goto(url);await click(operator,'[data-action=prepare]');await click(operator,'[data-action=start]')
                    await expect(operator.locator('[data-action="score-L-2"]')).to_be_visible()
                    await expect(operator.locator('#sets-L')).to_have_text('0')
                    await expect(operator.locator('.counter')).to_have_count(0)
                    await expect(operator.locator('#officials')).to_have_count(0)
                    await expect(operator.locator('#role-L')).to_have_text('Role 1 en')
                    await click(operator,'[data-action="score-L-2"]');await click(operator,'[data-action="sets-L-1"]')
                    await expect(operator.locator('#sets-L')).to_have_text('1')
                    await expect(observer.locator('#sets-L')).to_have_text('1')
                    assert (await state())['live']['left']['score']==2
                    assert (await state())['live']['left']['sets_won']==1
                    assert not errors,errors
                    await browser.close()
                    print('PASS: seven automatic library profiles selected/applied in GUI; complete custom profile editing with all new fields and DE/EN/CS texts; mobile display; disabled functions; period points/history; manual sets; Undo; red/blue side switch; observer sync; reopen and reset.')
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=10)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--chromium')
    asyncio.run(run(parser.parse_args().chromium))
