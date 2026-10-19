"""Optional real Chromium checks; requires existing Playwright and Chromium.

Runs a built artifact beneath the exact GitHub Pages repository prefix. This is
local browser evidence, never proof of deployment or forecast qualification.
"""
from __future__ import annotations

import argparse
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

PREFIX = "/Nicks-multisport-lab-project/"
ROUTES = {"overview": "Better questions.", "props": "Props", "value": "Value Research",
          "builder": "Paper Builder", "performance": "Performance",
          "sources": "Source Health", "specials": "Specials"}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith(PREFIX):
            self.send_error(404)
            return
        self.path = self.path[len(PREFIX) - 1:]
        super().do_GET()

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=Path("output"))
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    manifest = json.loads((root / "data/manifest.json").read_text())
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
    Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}{PREFIX}"
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            errors, failed_responses, requests = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failed_responses.append(response.url) if response.status >= 400 else None)
            page.on("request", lambda request: requests.append(request.url))
            for name, heading in ROUTES.items():
                page.goto(base + "#/" + name)
                page.get_by_role("heading", level=1).filter(has_text=heading).wait_for()
                assert page.get_by_role("alert").count() == 0, name
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
                page.reload()
                page.get_by_role("heading", level=1).filter(has_text=heading).wait_for()
            page.goto(base)
            page.get_by_role("heading", level=1).filter(has_text="Better questions.").wait_for()
            assert page.locator(".category-card").count() == 13
            if args.screenshots:
                page.screenshot(path=str(args.screenshots / "overview-desktop.png"), full_page=True)
            page.goto(base + "#/props")
            page.get_by_role("heading", name="Props", exact=True).wait_for()
            assert page.locator("tbody tr").count() == 14  # 13 required plus optional PA.
            page.get_by_role("button", name="Selected sports", exact=True).click()
            page.locator('input[name="sport"]').uncheck()
            assert "No sports selected" in page.locator("main").inner_text()
            assert page.locator("tbody tr").count() == 1
            page.get_by_role("link", name="Paper Builder", exact=True).click()
            page.get_by_role("heading", name="Paper Builder", exact=True).wait_for()
            assert "No sports selected" in page.locator(".request-summary").inner_text()
            page.locator('input[name="sport"]').check()
            page.get_by_role("button", name="All supported", exact=True).click()
            assert "All supported sports · NBA" in page.locator(".request-summary").inner_text()
            for legs, direction in [(2, "UNDER_ONLY"), (4, "OVER_ONLY"), (6, "MIXED")]:
                page.locator(f'input[name="legs"][value="{legs}"]').check()
                page.locator(f'input[name="direction"][value="{direction}"]').check()
                assert f"{legs} legs" in page.locator(".request-summary").inner_text()
                assert direction in page.locator(".request-summary").inner_text()
                page.get_by_role("button", name="Check paper readiness").click()
                assert "READINESS CHECK COMPLETE" in page.locator(".decision-box").inner_text()
                assert "NO_ACTION" in page.locator(".decision-box").inner_text()
                assert "Not issued" in page.locator(".request-summary").inner_text()
            for width in [390, 320]:
                page.set_viewport_size({"width": width, "height": 844})
                for name, heading in ROUTES.items():
                    page.goto(base + "#/" + name)
                    page.get_by_role("heading", level=1).filter(has_text=heading).wait_for()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Mobile overflow: {name} at {width}px"
                    if args.screenshots and width == 390 and name in ("overview", "props", "builder"):
                        page.screenshot(path=str(args.screenshots / f"{name}-mobile.png"), full_page=True)
            page.goto(base + "#/missing")
            page.get_by_role("heading", name="This route is not in the lab.").wait_for()
            assert not errors, errors
            assert not failed_responses, failed_responses
            assert all(url.startswith(base) for url in requests), requests

            # Negative fixtures are browser-only synthetic alterations, never publication data.
            page.route("**/data/manifest.json", lambda route: route.fulfill(json={**manifest, "schema_version": 999}))
            page.goto(base + "#/props")
            page.reload()
            page.get_by_role("alert").filter(has_text="Published snapshot unavailable").wait_for()
            page.unroute("**/data/manifest.json")
            page.route("**/data/nba.*.json", lambda route: route.fulfill(json={"corrupted": True}))
            page.reload()
            page.get_by_role("alert").filter(has_text="NBA snapshot unavailable").wait_for()
            page.unroute("**/data/nba.*.json")
            retained = json.loads(json.dumps(manifest))
            retained["sports"][0].update(retained=True, error="Synthetic browser retention failure")
            retained["errors"] = {"NBA": "Synthetic browser retention failure"}
            del retained["snapshot_id"]
            retained["snapshot_id"] = hashlib.sha256(json.dumps(retained, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            page.route("**/data/manifest.json", lambda route: route.fulfill(json=retained))
            page.goto(base + "#/sources")
            page.reload()
            page.get_by_text("NBA retains an earlier snapshot", exact=True).wait_for()
            assert "Generated" in page.locator(".notice.warning").inner_text()
            assert page.locator("tbody tr").count() == 0
            page.unroute("**/data/manifest.json")
            missing = json.loads(json.dumps(manifest))
            missing["errors"] = {"WNBA": "Synthetic first update rejected"}
            del missing["snapshot_id"]
            missing["snapshot_id"] = hashlib.sha256(json.dumps(missing, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            page.route("**/data/manifest.json", lambda route: route.fulfill(json=missing))
            page.goto(base + "#/props")
            page.reload()
            page.get_by_role("alert").filter(has_text="WNBA update unavailable").wait_for()
            assert page.locator('input[name="sport"]').count() == 1
            assert page.locator('input[name="sport"]').input_value() == "NBA"
            assert not errors, errors
            browser.close()
        print("PASS: Chromium desktop, 390px and 320px; seven routes and reloads; repository-prefix assets; all-13 inventory; shared scope and builder requests; NO_ACTION; unknown route; incompatible, corrupt, retained and first-failure snapshots. Local browser evidence only; no deployment/model/product claim.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
