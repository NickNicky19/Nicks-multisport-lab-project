"""Optional real Chromium checks; requires existing Playwright and Chromium.

Runs a built artifact beneath the exact GitHub Pages repository prefix. This is
local browser evidence, never proof of deployment or forecast qualification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
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


def screenshot(page, path):
    # Full-page captures otherwise place fixed navigation at the current scroll offset.
    page.evaluate("document.activeElement?.blur(); window.scrollTo(0, 0)")
    page.screenshot(path=str(path), full_page=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=Path("output"))
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    manifest = json.loads((root / "data/manifest.json").read_text())
    nba_snapshot = json.loads((root / "data" / manifest["sports"][0]["path"]).read_text())
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
                screenshot(page, args.screenshots / "overview-desktop.png")
            page.goto(base + "#/props")
            page.get_by_role("heading", name="Props", exact=True).wait_for()
            assert page.locator(".inventory-table tbody tr").count() == 14  # 13 required plus optional PA.
            checked_now = datetime.now(timezone.utc)
            history = [row for row in nba_snapshot["forecasts"] if row["evidence_lane"] == "RECONSTRUCTED_RESEARCH"
                       or datetime.fromisoformat(row["event_starts_at"].replace("Z", "+00:00")) <= checked_now]
            upcoming = [row for row in nba_snapshot["forecasts"] if row not in history]
            if upcoming:
                assert page.locator(".forecast-card").count() == min(28, len(upcoming)*14)
                assert "Captured research" in page.locator(".forecast-card").first.inner_text()
            else:
                assert page.locator(".forecast-card").count() == 0
                page.get_by_text("No upcoming research forecasts", exact=True).wait_for()
            page.locator('[data-filter="view"]').select_option("history")
            if history:
                assert page.locator(".forecast-card").count() >= 14
                assert ("Historical reconstruction" if history[0]["evidence_lane"] == "RECONSTRUCTED_RESEARCH" else "Captured research") in page.locator(".forecast-card").first.inner_text()
                assert len(set(page.locator(".forecast-card").evaluate_all("cards => cards.map(card => card.dataset.market)"))) == 14
                assert len(json.dumps(nba_snapshot, ensure_ascii=False).encode()) <= 512 * 1024
                while page.locator("#more-forecasts").count():
                    page.locator("#more-forecasts").click()
                assert page.locator(".forecast-card").count() == len(history) * 14
                first = page.locator(".forecast-card").first
                first.locator("summary").click()
                actual = history[0]
                assert first.locator("time").get_attribute("datetime") == actual["event_starts_at"]
                assert actual["issued_at"] in first.locator(".forecast-provenance").inner_text()
                assert actual["cutoff_at"] in first.locator(".forecast-provenance").inner_text()
                assert actual["forecast_id"] in first.locator(".forecast-provenance").inner_text()
                page.locator('[data-filter="category"]').select_option("REB")
                assert page.locator(".forecast-card").count() == len(history)
                if args.screenshots:
                    screenshot(page, args.screenshots / "real-reb-history-desktop.png")
                    page.set_viewport_size({"width": 390, "height": 844})
                    screenshot(page, args.screenshots / "real-reb-history-mobile.png")
                    page.locator(".forecast-card").first.screenshot(path=str(args.screenshots / "real-reb-card-mobile.png"))
                    page.set_viewport_size({"width": 1440, "height": 1000})
                page.get_by_role("link", name="Performance", exact=True).click()
                scored = [row for row in nba_snapshot["performance"] if row["status"] == "SCORED"]
                by_forecast = {row["forecast_id"]: row for row in nba_snapshot["forecasts"]}
                groups = {tuple(by_forecast[row["forecast_id"]][key] for key in ("league", "evidence_lane", "model_version", "model_commit", "model_code_sha256", "conditioning", "period", "extra_time_policy")) for row in scored}
                assert page.locator(".grade-summary tbody tr").count() == len(groups)*14
                assert f'{len(nba_snapshot["performance"])} typed grade records published' in page.locator("main").inner_text()
                if nba_snapshot["performance"]:
                    page.locator(".grade-receipts>summary").click()
                    assert page.locator(".grade-receipt").count() == len(nba_snapshot["performance"])
                    assert "Financial settlement: NOT_EVALUATED" in page.locator(".grade-receipt").first.inner_text()
                assert "No settled paper tickets published" in page.locator("main").inner_text()
                page.get_by_role("link", name="Props", exact=True).click()
                page.locator('[data-filter="category"]').select_option("ALL")
            page.get_by_role("button", name="Selected sports", exact=True).click()
            page.locator('input[name="sport"]').uncheck()
            assert "No sports selected" in page.locator("main").inner_text()
            assert page.locator(".inventory-table tbody tr").count() == 1
            assert page.locator(".forecast-card").count() == 0
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
                        screenshot(page, args.screenshots / f"{name}-mobile.png")
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

            # Explicitly synthetic typed-v2 browser fixtures; never written to the artifact.
            page.unroute("**/data/manifest.json")
            repo = Path(__file__).resolve().parents[2]
            synthetic = json.loads(subprocess.run(["node", "--input-type=module", "-e", "import {typedFixture} from './web/tests/fixtures.mjs'; console.log(JSON.stringify(typedFixture()));"], cwd=repo, text=True, capture_output=True, check=True).stdout)
            canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            page.route("**/data/manifest.json", lambda route: route.fulfill(body=canonical(synthetic["manifest"]), content_type="application/json"))
            page.route("**/data/nba.*.json", lambda route: route.fulfill(body=canonical(synthetic["sport"]), content_type="application/json"))
            page.goto(base + "#/props")
            page.reload()
            page.get_by_text("No upcoming research forecasts", exact=True).wait_for()
            assert page.get_by_role("alert").count() == 0
            page.locator('[data-filter="view"]').select_option("history")
            assert page.locator(".forecast-card").count() == 14
            assert page.locator('.forecast-card[data-market="PA"]').count() == 1
            page.locator('[data-filter="category"]').select_option("REB")
            assert page.locator(".forecast-card").count() == 1
            page.locator(".forecast-details summary").click()
            assert "Actual issued time" in page.locator(".forecast-provenance").inner_text()
            assert "not a pregame receipt" in page.locator(".forecast-details").inner_text()
            assert "Synthetic fixture player" in page.locator(".forecast-card").inner_text()
            assert page.get_by_text("No offers published in this scope", exact=True).count() == 1
            if args.screenshots:
                screenshot(page, args.screenshots / "synthetic-history-mobile.png")
            page.get_by_role("link", name="Performance", exact=True).click()
            page.get_by_role("heading", name="Performance", exact=True).wait_for()
            page.locator(".grade-summary tbody tr").first.wait_for()
            assert page.locator(".grade-summary tbody tr").count() == 14
            assert "No settled paper tickets published" in page.locator("main").inner_text()
            page.locator(".grade-receipts>summary").click()
            assert "Financial settlement: NOT_EVALUATED" in page.locator(".grade-receipt").inner_text()
            if args.screenshots:
                screenshot(page, args.screenshots / "synthetic-performance-mobile.png")
            page.get_by_role("link", name="Props", exact=True).click()
            page.locator('[data-filter="view"]').select_option("upcoming")
            assert page.locator(".forecast-card").count() == 0
            page.get_by_role("link", name="Paper Builder", exact=True).click()
            assert "0 admitted candidates" in page.locator(".request-summary").inner_text()
            assert "NO_ACTION" in page.locator(".decision-box").inner_text()

            # Synthetic past captures exercise display grouping, not a real-time producer.
            page.unroute("**/data/manifest.json")
            page.unroute("**/data/nba.*.json")
            mixed = json.loads(subprocess.run(["node", "--input-type=module", "-e", "import {mixedEvidenceFixture} from './web/tests/fixtures.mjs'; console.log(JSON.stringify(mixedEvidenceFixture()));"], cwd=repo, text=True, capture_output=True, check=True).stdout)
            page.route("**/data/manifest.json", lambda route: route.fulfill(body=canonical(mixed["manifest"]), content_type="application/json"))
            page.route("**/data/nba.*.json", lambda route: route.fulfill(body=canonical(mixed["sport"]), content_type="application/json"))
            page.goto(base + "#/props")
            page.reload()
            page.get_by_text("No upcoming research forecasts", exact=True).wait_for()
            assert not page.get_by_role("alert").count()
            history_link = page.get_by_role("link", name="Explore 4 forecast records in History", exact=False)
            history_link.wait_for()
            history_link.click()
            page.locator('.forecast-card').first.wait_for()
            while page.locator("#more-forecasts").count():
                page.locator("#more-forecasts").click()
            assert page.locator(".forecast-card").count() == 56
            assert page.locator(".historical-notice strong").inner_text() == "Past-event forecasts and reconstructed research"
            assert "does not establish completion" in page.locator(".historical-notice").inner_text()
            page.locator('[data-filter="category"]').select_option("REB")
            assert page.locator(".forecast-card").count() == 4
            captured = page.locator(".forecast-card").filter(has_text="Synthetic captured-a")
            assert captured.locator(".forecast-card-heading>.pill").inner_text() == "Captured research"
            captured.locator("summary").click()
            assert "REAL_TIME_CAPTURED" in captured.locator(".forecast-details").inner_text()
            assert "not a pregame receipt" not in captured.locator(".forecast-details").inner_text()
            page.get_by_role("link", name="Performance", exact=True).click()
            page.get_by_role("heading", name="Performance", exact=True).wait_for()
            page.locator(".grade-group").first.wait_for()
            assert page.locator(".grade-group").count() == 3
            assert page.locator(".grade-summary tbody tr").count() == 42
            reconstructed = page.locator('.grade-group[data-evidence-lane="RECONSTRUCTED_RESEARCH"]')
            captured = page.locator('.grade-group[data-evidence-lane="REAL_TIME_CAPTURED"][data-model-commit="' + "a" * 40 + '"]')
            revision = page.locator('.grade-group[data-model-commit="' + "f" * 40 + '"]')
            assert reconstructed.locator(".grade-summary tbody tr").first.locator("td").all_inner_texts()[:4] == ["2", "3", "0.69315", "0"]
            assert captured.locator(".grade-summary tbody tr").first.locator("td").all_inner_texts()[:4] == ["1", "4", "∞ · zero support", "1"]
            assert revision.locator(".grade-summary tbody tr").first.locator("td").all_inner_texts()[:4] == ["1", "3", "0.69315", "0"]
            for width in [1440, 390, 320]:
                page.set_viewport_size({"width": width, "height": 1000 if width == 1440 else 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Mixed group overflow at {width}px"
                if args.screenshots and width != 320:
                    screenshot(page, args.screenshots / f"synthetic-mixed-groups-{width}.png")
            page.get_by_role("link", name="Props", exact=True).click()
            page.get_by_role("button", name="Selected sports", exact=True).click()
            page.locator('input[name="sport"]').uncheck()
            assert page.locator(".forecast-card").count() == 0
            page.get_by_role("link", name="Performance", exact=True).click()
            assert page.locator(".grade-group").count() == 0
            page.get_by_role("link", name="Paper Builder", exact=True).click()
            assert "0 admitted candidates" in page.locator(".request-summary").inner_text()
            assert "NO_ACTION" in page.locator(".decision-box").inner_text()
            # Invented v2 prospective contract with a fixed browser clock only.
            # It proves rendering/timing validation, never actual capture or issuance.
            prospective = json.loads(subprocess.run(["node", "--input-type=module", "-e", "import {prospectiveFixture} from './web/tests/fixtures.mjs'; console.log(JSON.stringify(prospectiveFixture()));"], cwd=repo, text=True, capture_output=True, check=True).stdout)
            prospective_page = context.new_page()
            prospective_page.on("pageerror", lambda error: errors.append(str(error)))
            prospective_page.clock.install(time=datetime(2000, 1, 1, tzinfo=timezone.utc))
            prospective_page.route("**/data/manifest.json", lambda route: route.fulfill(body=canonical(prospective["manifest"]), content_type="application/json"))
            prospective_page.route("**/data/nba.*.json", lambda route: route.fulfill(body=canonical(prospective["sport"]), content_type="application/json"))
            prospective_page.goto(base + "#/props")
            prospective_page.get_by_role("heading", name="Props", exact=True).wait_for()
            assert prospective_page.locator(".forecast-card").count() == 14
            assert prospective_page.get_by_role("alert").count() == 0
            assert "Captured research" in prospective_page.locator(".forecast-card").first.inner_text()
            assert "Statistical grade: pending" in prospective_page.locator(".forecast-card").first.inner_text()
            prospective_page.locator('[data-filter="category"]').select_option("REB")
            prospective_page.locator(".forecast-details summary").click()
            provenance = prospective_page.locator(".forecast-provenance").inner_text()
            for field in ("event_version", "source_pack_record_id", "generation_started_at", "generation_completed_at", "source_observed_min_at", "source_observed_max_at", "imported_at"):
                assert prospective["sport"]["forecasts"][0]["prospective"][field] in provenance
            for width in [1440, 390, 320]:
                prospective_page.set_viewport_size({"width": width, "height": 1000 if width == 1440 else 844})
                assert prospective_page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Prospective card overflow at {width}px"
                if args.screenshots and width != 320:
                    screenshot(prospective_page, args.screenshots / f"synthetic-prospective-{width}.png")
            prospective_page.get_by_role("link", name="Performance", exact=True).click()
            assert prospective_page.locator(".grade-group").count() == 0
            assert "1 forecast records pending a verified grade" in prospective_page.locator("main").inner_text()
            prospective_page.get_by_role("link", name="Paper Builder", exact=True).click()
            assert "0 admitted candidates" in prospective_page.locator(".request-summary").inner_text()
            assert "NO_ACTION" in prospective_page.locator(".decision-box").inner_text()
            prospective_page.close()
            assert not errors, errors
            browser.close()
        if nba_snapshot["forecasts"]:
            print(f'PASS real retained research: {len(nba_snapshot["events"])} events, {len(nba_snapshot["forecasts"])} bundles, {len(nba_snapshot["forecasts"]) * 14} category PMFs and {len(nba_snapshot["performance"])} forecast grades; actual event/cutoff/issue/record IDs, all-category load-more, REB filter, finite support and separate NOT_EVALUATED financial state checked.')
        print("PASS: Chromium desktop, 390px and 320px; seven routes and reloads; repository-prefix assets; all-13 inventory; shared scope and builder requests; NO_ACTION; unknown route; incompatible, corrupt, retained and first-failure snapshots; synthetic typed-v2 fourteen-category history, future exclusion, provenance, separate forecast grades mixed-lane/model summaries and prospective-v2 pending-grade provenance. Local browser/software evidence only; no deployment/model/product claim.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
