"""Local synthetic typed-asset browser smoke; never publish or issue these fixtures.

Every new verifier check raises IntegrityError explicitly under Python -O too.
Only a temporary static copy is served over loopback; no provider route is used.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Thread

from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from multisport_lab.integrity import IntegrityError


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    root=Path(__file__).resolve().parents[2]
    code="import {pairedCollection} from './web/tests/pros004-fixtures.mjs'; console.log(JSON.stringify(pairedCollection().assets));"
    result=subprocess.run(['node','--input-type=module','-e',code],cwd=root,capture_output=True,text=True,check=True)
    assets=json.loads(result.stdout)
    with tempfile.TemporaryDirectory(prefix='nml-pros004-public-synthetic-') as directory:
        output=Path(directory)
        for source in (root/'web').iterdir():
            if source.is_file() and source.suffix in {'.html','.css','.js','.mjs','.svg','.webmanifest'}:
                shutil.copyfile(source,output/source.name)
        (output/'data').mkdir()
        for name,raw in assets.items():
            require('/' not in name and '\\' not in name,'Unsafe synthetic asset name')
            (output/'data'/name).write_text(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=directory))
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
                for width,height in ((1440,1000),(390,844)):
                    page=browser.new_page(viewport={'width':width,'height':height});errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{server.server_port}/#/props')
                    study=page.locator('.pros004-research');study.get_by_role('heading',name='No upcoming PROS004 research forecasts').wait_for()
                    require(page.get_by_role('alert').count()==0,'Synthetic typed publication raised an alert')
                    require(study.locator('.forecast-card').count()==0,'Inactive originals entered Upcoming')
                    page.locator('[data-filter="view"]').select_option('history')
                    require(study.locator('.forecast-card').count()==28,'Paired History lost fourteen-category originals')
                    require(study.locator('[data-pros004-model="R0"]').count()==14 and study.locator('[data-pros004-model="K0"]').count()==14,'Model identities blended')
                    page.locator('[data-filter="category"]').select_option('PA')
                    require(study.locator('.forecast-card').count()==2,'Optional PA did not follow selected category')
                    require('Retained original · unadmitted' in study.inner_text(),'Missing completion proof was hidden')
                    require(page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Typed History overflows viewport')
                    page.get_by_role('button',name='Selected sports',exact=True).click()
                    page.locator('input[name="sport"]').uncheck()
                    require(page.locator('.pros004-research').count()==0,'Unselected NBA records leaked into scope')
                    page.get_by_role('button',name='All supported',exact=True).click()
                    require(page.locator('.pros004-research .forecast-card').count()==28,'All-supported scope did not restore exact NBA coverage')
                    page.get_by_role('link',name='Performance',exact=True).click()
                    # Hash changes precede this SPA's asynchronous render event.
                    # Wait for the destination view before reading its records.
                    page.get_by_role('heading',level=1,name='Performance',exact=True).wait_for()
                    study=page.locator('.pros004-research')
                    require(study.locator('.forecast-card').count()==2,'Individual paired grade states missing')
                    require('DNP_NOT_SCORED' in study.inner_text(),'DNP state lost')
                    require('Mean CRPS' not in study.inner_text() and study.locator('.grade-summary').count()==0,'Reserved comparison aggregates exposed')
                    require(page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Typed Performance overflows viewport')
                    page.get_by_role('link',name='Paper Builder',exact=True).click()
                    page.get_by_role('heading',level=1,name='Paper Builder',exact=True).wait_for()
                    for legs in range(2,7):
                        page.locator(f'input[name="legs"][value="{legs}"]').check()
                        require('NO_ACTION' in page.locator('main').inner_text(),'Research originals entered builder')
                    for direction in ('OVER_ONLY','UNDER_ONLY','MIXED'):
                        page.locator(f'input[name="direction"][value="{direction}"]').check()
                        require('NO_ACTION' in page.locator('main').inner_text(),'Direction relaxed builder admission')
                    require(not errors,'Browser JavaScript error: '+str(errors))
                    page.close()
                browser.close()
        finally:
            server.shutdown();server.server_close()
    print('SYNTHETIC ONLY: desktop1440/mobile390 typed paired History/Upcoming/individual grades/scope/builder passed; no issuance or deployment')


if __name__=='__main__':
    main()
