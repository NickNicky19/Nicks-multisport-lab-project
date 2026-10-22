"""Local display/metadata browser verification; no source requests or deployment.

Requires an already built artifact and existing Playwright/Chromium. Explicit
IntegrityError checks stay enabled under python -O. Only loopback is served.
"""
from __future__ import annotations
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from multisport_lab.integrity import IntegrityError,digest

PREFIX='/Nicks-multisport-lab-project/'


def require(ok,message):
    if not ok:raise IntegrityError(message)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith(PREFIX):self.send_error(404);return
        self.path=self.path[len(PREFIX)-1:]
        super().do_GET()
    def log_message(self,*_args):pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args();root=args.output.resolve()
    manifest=json.loads((root/'data/manifest.json').read_text())
    require(manifest['schema_version'] in {4,5,6} and manifest['display'] is not None,'Readable metadata artifact required')
    sport=json.loads((root/'data'/next(r['path'] for r in manifest['sports'] if r['league']=='NBA')).read_text())
    metadata=json.loads((root/'data'/manifest['display']['path']).read_text())
    names={r['player_id']:r['display_name'] for r in metadata['catalog']['players']}
    selected=[f for f in sport['forecasts'] if f['player_id'] in names and f['league']=='NBA' and f['id_namespace']=='espn']
    expected={names[f['player_id']] for f in selected}
    require(len(expected)==6,'All six reviewed source-backed names required')
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(root)))
    Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}{PREFIX}'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            for width,height in ((1440,1000),(390,844),(320,760)):
                page=browser.new_page(viewport={'width':width,'height':height});errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'#/props/upcoming')
                page.get_by_role('heading',level=1,name='Props',exact=True).wait_for()
                page.locator('.research-availability').wait_for()
                require(page.get_by_role('alert').count()==0,'Valid display asset raised an alert')
                if manifest['schema_version'] in {5,6}:
                    require(page.get_by_role('heading',level=2,name='Paired operational research',exact=True).count()==1,'Valid paired channel did not render')
                    require('Paired operational research unavailable' not in page.locator('main').inner_text() and 'Offer publication unavailable' not in page.locator('main').inner_text(),'Independent paired/offer channel failed browser recovery')
                if manifest['schema_version'] in {5,6}:
                    require(page.get_by_role('heading',level=2,name='Paired operational research',exact=True).count()==1,'Valid paired channel did not render')
                    require('Paired operational research unavailable' not in page.locator('main').inner_text() and 'Offer publication unavailable' not in page.locator('main').inner_text(),'Independent paired/offer channel failed browser recovery')
                status=page.locator('.research-availability').inner_text()
                require('0 published player contracts' in status and '0 qualified · NO_ACTION' in status,'Offer/ticket state not independently visible')
                require(('No complete player contract with reviewed source permission' in status) if manifest['schema_version'] in {5,6} else ('Complete player contracts and permission to publish them are still unverified' in status and 'no checked offer export yet' in status),'Offer summary hides contract/permission or export blocker')
                require('admitted offer-only record may show “price unavailable”' in status and 'quotes, value estimates and tickets have separate checks' in status,'Offer-only pricing was confused with quote/ticket gates')
                offers=page.locator('section.panel').filter(has=page.get_by_role('heading',level=2,name='Published offers',exact=True)).inner_text()
                require(('reviewed source permission' in offers and 'Retained source observations are not admitted published offers' in offers) if manifest['schema_version'] in {5,6} else ('checked offer export is not implemented' in offers and 'permission to publish them remain unverified' in offers),'Published-offer empty state hides its next export/contract requirement')
                require(('An admitted offer can display “price unavailable”' in offers) if manifest['schema_version'] in {5,6} else ('Some source prices have been observed' in offers and 'otherwise complete, admitted offer can be displayed with “price unavailable”' in offers),'Empty state implies all source prices are missing or every offer needs a price')
                require('Source access, exact contract mapping and price evidence are still under review' not in offers and 'Missing lines and prices remain unknown' not in status,'Ambiguous old price-dependent publication explanation returned')
                require('Last retained NBA forecast-input preparation' in status and 'Preparation only' in status and 'None recorded in the published forecasts' in status,'Clocks were conflated or historical issue promoted')
                history=page.locator('.research-availability .history-shortcut');history.focus();page.keyboard.press('Enter')
                page.wait_for_function("document.querySelector('[data-filter=\"view\"]')?.value==='history'")
                page.locator('[data-filter="category"]').select_option('REB')
                headings=set(page.locator('.forecast-card h3').all_inner_texts())
                require(expected<=headings,'Readable player names missing from History')
                royce=page.locator('.forecast-card').filter(has=page.get_by_role('heading',name="Royce O'Neale",exact=True))
                require('Phoenix Suns' in royce.inner_text() and 'San Antonio Spurs @ Phoenix Suns' in royce.inner_text(),'Historical matchup not readable')
                require('24 Nov 2025' in royce.inner_text(),'Historical event date missing')
                royce.locator('summary').click()
                original=next(f for f in selected if f['player_id']=='2583632')
                require(original['issued_at'] in royce.inner_text() and original['forecast_id'] in royce.inner_text() and original['player_label'] in royce.inner_text(),'Original issue/identity details changed')
                require(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'History overflows viewport')
                page.locator('[data-filter="category"]').select_option('ALL')
                while page.locator('#more-forecasts').count():page.locator('#more-forecasts').click()
                require(set(page.locator('.forecast-card').evaluate_all('cards=>cards.map(card=>card.dataset.market)'))=={'PTS','PRA','REB','3PM','AST','RA','PR','TOV','TD','DD','BLK','STL','BLK+STL','PA'},'Fourteen-category coverage lost')
                page.get_by_role('link',name='Performance',exact=True).click()
                page.get_by_role('heading',level=1,name='Performance',exact=True).wait_for()
                require(expected<=set(page.locator('.performance-targets strong').all_inner_texts()),'Performance hides readable player identities')
                require(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Performance overflows viewport')
                page.get_by_role('link',name='Paper Builder',exact=True).click()
                page.get_by_role('heading',level=1,name='Paper Builder',exact=True).wait_for()
                for size in range(2,7):
                    page.locator(f'input[name="legs"][value="{size}"]').check()
                    require('NO_ACTION' in page.locator('main').inner_text(),'Builder admission relaxed')
                for mode in ('OVER_ONLY','UNDER_ONLY','MIXED'):
                    page.locator(f'input[name="direction"][value="{mode}"]').check()
                    require('0 admitted candidates' in page.locator('main').inner_text(),'Metadata became builder candidates')
                page.get_by_role('button',name='Selected sports',exact=True).click();page.locator('input[name="sport"]').uncheck()
                require('No sports selected' in page.locator('main').inner_text(),'Empty sport scope expanded')
                page.get_by_role('button',name='All supported',exact=True).click()
                require('0 admitted candidates' in page.locator('main').inner_text(),'All-supported scope manufactured candidates')
                require(not errors,'Browser errors: '+str(errors));page.close()
            retained={**manifest,'display':{**manifest['display'],'retained':True,'error':'Synthetic failed update; earlier verified names retained'},'display_error':'Synthetic failed update; earlier verified names retained'}
            retained['snapshot_id']=digest({k:v for k,v in retained.items() if k!='snapshot_id'})
            page=browser.new_page(viewport={'width':390,'height':844})
            page.route('**/data/manifest.json',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(retained)))
            page.goto(base+'#/props/history');page.get_by_text('Earlier verified display metadata retained',exact=True).wait_for()
            page.locator('[data-filter="category"]').select_option('REB')
            require('The failed update did not refresh these clocks' in page.locator('main').inner_text(),'Retained metadata appeared freshly verified')
            require(page.get_by_role('heading',name="Royce O'Neale",exact=True).count()>0,'Retained valid display names disappeared')
            require(page.get_by_text('Readable names unavailable',exact=True).count()==0,'Retained metadata was falsely labelled unavailable')
            page.close()
            page=browser.new_page(viewport={'width':390,'height':844})
            page.route('**/data/display.*.json',lambda route:route.fulfill(status=404,body=''))
            page.goto(base+'#/props/history');page.get_by_text('Readable names unavailable',exact=True).wait_for()
            page.locator('[data-filter="category"]').select_option('REB')
            require(page.locator('.forecast-card').count()==len(sport['forecasts']),'Display failure removed valid distributions')
            require(any('name unavailable' in name for name in page.locator('.forecast-card h3').all_inner_texts()),'Display failure guessed readable names')
            require(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Fallback overflows mobile viewport')
            browser.close()
    finally:server.shutdown();server.server_close()
    print('PASS local display browser: desktop1440/mobile390/320; six names, historical matchups/date,14categories,separate clocks,keyboard History,retained metadata clocks,metadata404 fallback,scopes,2–6/directions/NO_ACTION. No deployment or issuance.')


if __name__=='__main__':main()
