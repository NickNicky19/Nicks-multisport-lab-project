"""Optional local Chromium verification; never contacts a sports-data source.

Source facts and screenshots stay in ignored local storage, not Git or Pages.
Integrity checks use explicit exceptions and remain active under python -O.
"""
from __future__ import annotations

import argparse
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from multisport_lab.integrity import IntegrityError, canonical, read_receipt, write_receipt
from playwright.sync_api import sync_playwright


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preview", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    source_root = Path(__file__).resolve().parents[2]
    preview = args.preview.resolve()
    evidence = args.evidence.resolve()
    require(preview.is_relative_to(source_root / ".local-data")
            and evidence.is_relative_to(source_root / ".local-data"), "Private local artifacts required")
    report = read_receipt(preview / "review.receipt.json")
    require(canonical(report) == (preview / "review.json").read_bytes(), "Preview JSON changed after receipt")
    first = report["observations"][0]
    evidence.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(preview)))
    Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    checks, forbidden, failures = [], [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
            try:
                for width, height in ((1440, 1000), (390, 844), (320, 800)):
                    context = browser.new_context(viewport={"width": width, "height": height})
                    def bounded_route(route):
                        if urlsplit(route.request.url).netloc == f"127.0.0.1:{server.server_port}":
                            route.continue_()
                        else:
                            forbidden.append(route.request.url)
                            route.abort()
                    context.route("**/*", bounded_route)
                    page = context.new_page()
                    page.on("pageerror", lambda error: failures.append(str(error)))
                    for name in ("standalone.html", "index.html"):
                        response = page.goto(base + "/" + name, wait_until="networkidle")
                        require(response.status == 200, "Local preview route failed")
                        cards = page.locator("article.local-observation")
                        require(cards.count() == report["counts"]["rows_parsed"], "Actual row count changed in browser")
                        selected = cards.first
                        require(first["player_name"] in selected.locator("h2").inner_text()
                                and first["threshold"] in selected.locator("h2").inner_text(), "Readable source heading missing")
                        text = selected.inner_text()
                        require(first["event_label"] in text and "Polymarket Gamma API" in text,
                                "Source or matchup attribution missing")
                        require("partial source observation" in text.casefold() and "unavailable" in text
                                and "Outcome-to-token mapping" in text, "Contract gaps or missing price status hidden")
                        require(page.locator("tbody tr").count() == 14, "Full category inventory missing")
                        require("NO_ACTION" in page.locator("body").inner_text(), "No-action guard missing")
                        selected.locator("summary").click()
                        text = selected.inner_text()
                        require(first["raw_source_sha256"] in text and first["source_market_id"] in text
                                and "selection/token mapping unverified" in text, "Original source IDs or mapping gap hidden")
                        if first["player_identity"] is not None:
                            require(first["player_identity"]["id"] in text, "Canonical player identity missing")
                        require(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile horizontal overflow")
                        checks.append({"width": width, "route": name, "rows": cards.count(),
                                       "category_rows": 14, "no_horizontal_overflow": True})
                    page.evaluate("scrollTo(0,0)")
                    image = evidence / f"local-review-{width}.png"
                    page.screenshot(path=str(image))
                    context.close()
                require(not forbidden and not failures, "Unexpected network access or browser error")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    receipt = {"schema_version": "nba-local-offer-browser-check-v1", "checks": checks,
        "source_gets": 0, "external_requests": forbidden, "page_errors": failures,
        "counts": report["counts"], "public_deployment": False,
        "screenshots": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in evidence.glob("local-review-*.png")}}
    write_receipt(evidence / "browser.receipt.json", receipt)
    print(json.dumps({"status": "PASS", "viewports": 3, "routes": 2,
                      "counts": report["counts"], "external_requests": 0,
                      "evidence": str(evidence)}, sort_keys=True))


if __name__ == "__main__":
    main()
