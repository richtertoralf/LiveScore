"""EN/DE/CS, Erstlogin, Admin-Passwörter und zwei angemeldete Operatoren."""
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

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'.test-artifacts'
PASSWORD='Local test password 2026!'


async def run(executable):
    with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
        directory=Path(directory)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        config=directory/'server.yml'
        config.write_text(f'bind_host: 127.0.0.1\nport: {port}\ndata_dir: data\nauth:\n  enabled: true\n  file: auth.yml\n')
        environment=dict(os.environ,TMPDIR=str(directory),XDG_CACHE_HOME=str(directory/'cache'),XDG_CONFIG_HOME=str(directory/'config'))
        log=(ARTIFACTS/'browser-auth-server.log').open('w')
        process=None
        def start():
            proc=subprocess.Popen([sys.executable,'-m','livescore','--config',str(config)],cwd=ROOT,env=environment,stdout=log,stderr=log)
            for _ in range(150):
                try:
                    with urlopen(url+'/api/auth/session',timeout=.2) as r:
                        if r.status==200: return proc
                except OSError: pass
                if proc.poll() is not None: raise RuntimeError('Server failed; see browser-auth-server.log')
                time.sleep(.05)
            proc.terminate();proc.wait(timeout=10);raise RuntimeError('Server timeout')
        try:
            process=start()
            public=json.loads(subprocess.check_output(['curl','--fail','--silent','--show-error',url+'/api/v1/live'],text=True))
            assert public['status']=='idle'
            async with async_playwright() as p:
                kwargs=dict(headless=True,env=environment)
                if executable: kwargs['executable_path']=executable
                browser=await p.chromium.launch(**kwargs)
                contexts=[await browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True),await browser.new_context(viewport={'width':768,'height':1024}),await browser.new_context()]
                admin,a,b=[await c.new_page() for c in contexts]
                errors=[]
                for page in (admin,a,b): page.on('pageerror',lambda err:errors.append(str(err)))
                async def language(page,code):
                    await page.locator(f'[data-lang="{code}"]').click()
                    await expect(page.locator('html')).to_have_attribute('lang',code)
                    await expect(page.locator('.app-version')).to_have_text('LiveScore v' + (ROOT/'VERSION').read_text().strip())
                async def login(page,name,password=PASSWORD):
                    await page.goto(url+'/login')
                    await page.locator('#username').fill(name)
                    await page.locator('#password').fill(password)
                    await page.locator('#login-form button').click()
                async def password(user):
                    await admin.locator(f'[data-user="{user}"]').click()
                    await admin.locator('#new-password').fill(PASSWORD)
                    await admin.locator('#repeat-password').fill(PASSWORD)
                    async with admin.expect_navigation(wait_until='domcontentloaded'):
                        await admin.locator('#password-form button').click()
                await admin.goto(url+'/config')
                await expect(admin).to_have_url(url+'/login')
                await expect(admin.locator('html')).to_have_attribute('lang','en')
                await expect(admin.locator('h1')).to_have_text('Sign in')
                await expect(admin.locator('.app-version')).to_have_text('LiveScore v0.1.2')
                await language(admin,'de'); await expect(admin.locator('h1')).to_have_text('Anmelden')
                await language(admin,'cs'); await expect(admin.locator('h1')).to_have_text('Přihlásit se')
                # Explicit English fallback without changing the selected language.
                fallback=await admin.evaluate("async () => { const m=await import('/static/i18n.js'); const old=m.translations.cs['Speichern']; delete m.translations.cs['Speichern']; const result=m.t('Speichern'); m.translations.cs['Speichern']=old; return result; }")
                assert fallback=='Save'
                await language(admin,'en')
                await login(admin,'admin','wrong password')
                await expect(admin.locator('#message')).to_have_text('Invalid username or password.')
                await login(admin,'admin','admin')
                await expect(admin).to_have_url(url+'/users')
                await expect(admin.locator('.app-version')).to_have_text('LiveScore v0.1.2')
                await expect(admin.locator('#default-warning')).to_contain_text('Default password is still active')
                await expect(admin.locator('[data-user="operator"]')).to_be_disabled()
                await password('admin'); await expect(admin).to_have_url(url+'/login')
                await login(admin,'admin')
                await expect(admin).to_have_url(url+'/')
                await expect(admin.locator('.app-version')).to_have_text('LiveScore v0.1.2')
                await admin.goto(url+'/users')
                await password('operator')
                await expect(admin.locator('#default-warning')).to_have_count(0)
                await admin.goto(url+'/events')
                await expect(admin.locator('.app-version')).to_have_text('LiveScore v0.1.2')
                await expect(admin.locator('#connection')).to_have_text('Connected')
                await admin.locator('#json-import summary').click()
                await admin.locator('#import-file').set_input_files(ROOT/'imports/prague-2026.json')
                await expect(admin.locator('#import-preview')).to_contain_text('14 matches')
                await admin.locator('[data-action="confirm-import"]').click()
                await expect(admin.locator('#catalog-list article')).to_have_count(1)
                await admin.locator('[data-action="select-event"]').click()
                await expect(admin.locator('.active-event')).to_have_count(1)
                # Admin sieht „Zurücksetzen“; der Dialog liegt in allen drei Sprachen vor.
                for code,title,confirm in [('cs','Obnovit událost?','Obnovit'),('de','Veranstaltung zurücksetzen?','Zurücksetzen'),('en','Reset event?','Reset')]:
                    await language(admin,code)
                    await expect(admin.locator('[data-action="reset-event"]')).to_be_enabled()
                    await admin.locator('[data-action="reset-event"]').click()
                    await expect(admin.locator('#reset-dialog h2')).to_have_text(title)
                    await expect(admin.locator('#reset-confirm')).to_have_text(confirm)
                    await admin.locator('#reset-cancel').click()
                for code,heading in [('en','Configure event'),('de','Veranstaltung einrichten'),('cs','Nastavit událost')]:
                    await admin.goto(url+'/config'); await language(admin,code)
                    await expect(admin.locator('h1')).to_have_text(heading)
                    await expect(admin.locator('form[data-kind="participants"]')).to_be_visible()
                    assert '${' not in await admin.locator('main').inner_text()
                await admin.screenshot(path=str(ARTIFACTS/'auth-config-cs.png'),full_page=True)
                await language(admin,'en')
                await login(a,'operator'); await login(b,'operator')
                for page in (a,b):
                    await expect(page.locator('#connection')).to_have_text('Connected')
                    await expect(page.locator('a[href="/config"]')).to_be_visible()
                await a.goto(url+'/events')
                await expect(a.locator('#new-event')).to_be_visible()
                await expect(a.locator('#json-import')).to_be_visible()
                await expect(a.locator('a[download]')).to_be_visible()
                await expect(a.locator('[data-action="reset-event"]')).to_have_count(0)
                assert (await a.request.get(url+'/config')).status==200
                assert (await a.request.get(url+'/users')).status==403
                assert (await a.request.get(url+'/api/v1/event-catalog/prague-2026/export')).status==200
                # Operator performs creation, import/export and configuration through the GUI.
                await a.locator('#new-event summary').click()
                for key,value in dict(name='Operator Cup',date_from='2026-10-03',date_to='2026-10-04').items():
                    await a.locator(f'#create-event [name="{key}"]').fill(value)
                await a.locator('#create-event button[type=submit]').click()
                await expect(a.locator('#catalog-list article')).to_have_count(2)
                await a.locator('#json-import summary').click()
                await a.locator('#import-file').set_input_files(ROOT/'imports/prague-2026.json')
                await expect(a.locator('[data-action="confirm-import"]')).to_have_text('Import as new event')
                await expect(a.locator('[data-action="replace-import"]')).to_have_count(0)
                await a.locator('[data-action="confirm-import"]').click()
                await expect(a.locator('#catalog-list article')).to_have_count(3)
                async with a.expect_download() as exported:
                    await a.locator('[data-event-id="prague-2026"] a[download]').click()
                download=await exported.value
                await download.save_as(directory/'operator-export.json')
                assert len(json.loads((directory/'operator-export.json').read_text())['matches'])==14
                await a.goto(url+'/config')
                await a.locator('#event-name').fill('Operator corrected Prague')
                await a.locator('form[data-kind="event"] button[type=submit]').click()
                await expect(a.locator('#message')).to_have_text('Saved.')
                await expect(b.locator('#active-event-name')).to_have_text('Operator corrected Prague')
                await a.goto(url+'/')
                await a.locator('[data-action="select"]').first.click()
                await a.locator('[data-action="prepare"]').click()
                await a.locator('[data-action="start"]').click()
                await expect(b.locator('.status')).to_have_text('LIVE')
                await a.locator('[data-action="score-L-1"]').click()
                await expect(b.locator('#score-L')).to_have_text('1')
                await b.locator('[data-action="counter"][data-side="L"][data-delta="1"]').click()
                for page in (a,b): await expect(page.locator('#counter-L-team_fouls .counter-value')).to_have_text('1')
                await language(a,'de'); await expect(a.locator('#period-label')).to_contain_text('Halbzeit')
                await language(b,'cs'); await expect(b.locator('#period-label')).to_contain_text('Poločas')
                await b.locator('[data-action="period-dialog"]').click(); await b.locator('#period-confirm').click()
                await expect(a.locator('#period-label')).to_contain_text('2. Halbzeit')
                await expect(a.locator('#counter-L-team_fouls .counter-value')).to_have_text('0')
                await a.screenshot(path=str(ARTIFACTS/'auth-live-de.png'),full_page=True)
                await b.screenshot(path=str(ARTIFACTS/'auth-live-cs.png'),full_page=True)
                for page in (a,b,admin): assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await admin.goto(url+'/users'); await password('operator')
                await expect(a).to_have_url(url+'/login',timeout=15000)
                await expect(b).to_have_url(url+'/login',timeout=15000)
                await login(a,'operator'); await expect(a.locator('html')).to_have_attribute('lang','de')
                await expect(a.locator('#score-L')).to_have_text('1')
                await a.locator('#logout').click(); await expect(a).to_have_url(url+'/login')
                # Let the login page finish its session fetch before deliberately
                # stopping the test server; a URL change alone is not page readiness.
                await a.wait_for_load_state('networkidle')
                process.terminate();process.wait(timeout=10)
                process=start()
                await admin.goto(url+'/users'); await expect(admin).to_have_url(url+'/login')
                await login(admin,'admin'); await expect(admin).to_have_url(url+'/')
                await expect(admin.locator('#score-L')).to_have_text('1')
                assert not errors,errors
                await browser.close()
                print('PASS: EN default, DE/CS switch and persistence, EN fallback, login errors, forced admin change, all password resets/default warnings, admin import/config, admin-only reset/replace (reset dialog EN/DE/CS), operator full event permissions and admin-only password management; anonymous curl live GET, two logged-in operators synchronize score/counter/period, session invalidation incl. WebSockets/logout/restart; no JS errors, no viewport overflow.')
        finally:
            if process and process.poll() is None: process.terminate();process.wait(timeout=10)
            log.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--chromium');asyncio.run(run(parser.parse_args().chromium))
