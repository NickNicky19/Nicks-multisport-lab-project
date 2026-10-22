"""Nonempty synthetic offer renderer check; loopback only, no real admission."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import runpy
import sys
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from multisport_lab.integrity import IntegrityError, canonical


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    fixture = runpy.run_path(str(ROOT / "tests/test_offer_publication.py"))["asset_fixture"]()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(ROOT)))
    Thread(target=server.serve_forever, daemon=True).start()
    html = """<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/web/styles.css"></head>
    <body><main><h1>Synthetic offer renderer software check</h1><section class="panel"><div id="fixture" class="forecast-grid"></div></section></main>
    <script type="module">
    import {validateOfferAsset,verifyOfferAssetHashes,renderOffers} from '/web/offers.mjs';
    const asset=await (await fetch('/offer-fixture.json')).json();
    validateOfferAsset(asset,asset.generated_at,{allowSynthetic:true});
    await verifyOfferAssetHashes(asset,crypto);
    document.querySelector('#fixture').innerHTML=renderOffers(asset,{now:asset.generated_at});
    document.querySelector('details').open=true;
    document.documentElement.dataset.ready='true';
    </script></body></html>"""
    sizes = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
            for width, height in ((1440, 1000), (390, 844), (320, 760)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/offer-smoke.html", lambda route: route.fulfill(content_type="text/html", body=html))
                page.route("**/offer-fixture.json", lambda route: route.fulfill(content_type="application/json", body=canonical(fixture)))
                page.goto(f"http://127.0.0.1:{server.server_port}/offer-smoke.html")
                page.wait_for_function("document.documentElement.dataset.ready==='true'")
                card = page.locator(".offer-card")
                require(card.count() == 1, "Nonempty synthetic card missing")
                body = card.inner_text()
                require("Synthetic Player" in body and "OVER 12.5 PTS" in body, "Readable exact subject/side/line/category missing")
                require("Price unavailable" in body and "not a recommendation" in body, "Price/qualification distinction lost")
                require(fixture["offers"][0]["event_version"] in body and fixture["offers"][0]["source_evidence"][0]["raw_sha256"] in body,
                        "Exact source identities hidden")
                require(page.evaluate("document.documentElement.scrollWidth<=innerWidth"), "Offer details overflow viewport")
                require(not errors, "Offer browser errors: " + repr(errors))
                sizes.append({"width": width, "height": height, "overflow": False, "browser_errors": 0})
                page.close()
            browser.close()
        print(json.dumps({"status": "PASS", "synthetic_only": True, "admitted_actual_offers": 0, "viewports": sizes}))
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
