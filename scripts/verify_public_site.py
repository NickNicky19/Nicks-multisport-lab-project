#!/usr/bin/env python3
"""One-off, read-only verification of the actual public PR24 Pages deployment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import urllib.request
from urllib.parse import unquote, urlsplit

REPOSITORY = "NickNicky19/Nicks-multisport-lab-project"
OWNER = "NickNicky19"
BASE = "https://nicknicky19.github.io/Nicks-multisport-lab-project/"
EXPECTED_BUILD = "ceacbef7e4b8ac3b6da19eaa946b83af74887aee"
EXPECTED_REF = "refs/heads/verification/pr24-public-ceac-20261024"
PAGES_RUN = 40086049201
PAGES_WORKFLOW = 389957636
MAX_BODY = 4 * 1024 * 1024
MAX_NETWORK = 64 * 1024 * 1024
MAX_RESPONSES = 512
MAX_SHOT = 4 * 1024 * 1024
MAX_SHOTS = 32 * 1024 * 1024
EXPECTED_NAMES = {"Jerami Grant", "Alex Caruso", "Kelly Olynyk",
                  "Royce O'Neale", "LeBron James", "Maxi Kleber"}
CATEGORIES = {"PTS", "PRA", "REB", "3PM", "AST", "RA", "PR", "TOV",
              "TD", "DD", "BLK", "STL", "BLK+STL", "PA"}


class VerificationError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise VerificationError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def object_or_empty(value):
    return value if isinstance(value, dict) else {}


def identity():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_ACTOR") == OWNER
            and os.environ.get("GITHUB_REF") == EXPECTED_REF
            and os.environ.get("GITHUB_WORKFLOW_REF") ==
                REPOSITORY + "/.github/workflows/public-site-verification.yml@" + EXPECTED_REF,
            "Requires the exact owner-only, GitHub-hosted verification push")
    require(object_or_empty(event.get("sender")).get("login") == OWNER
            and object_or_empty(event.get("repository")).get("full_name") == REPOSITORY
            and event.get("forced") is False and event.get("deleted") is False
            and event.get("ref") == EXPECTED_REF
            and event.get("after") == os.environ.get("GITHUB_SHA")
            and object_or_empty(event.get("head_commit")).get("id") == os.environ.get("GITHUB_SHA"),
            "Push identity or ordinary-update evidence differs")
    require(re.fullmatch(r"[a-f0-9]{40}", os.environ.get("GITHUB_SHA", "")) is not None,
            "Missing exact verifier execution identity")
    return {"execution_sha": os.environ["GITHUB_SHA"],
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *unused):
        raise VerificationError("Unexpected redirect in GitHub deployment evidence")


def github_json(path):
    url = "https://api.github.com/repos/" + REPOSITORY + "/" + path
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "NML-public-site-verification"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    started = now()
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=25) as response:
        require(response.status == 200 and response.geturl() == url, "GitHub evidence response differs")
        encoded = response.read(MAX_BODY + 1)
    require(len(encoded) <= MAX_BODY, "GitHub evidence exceeds its bound")
    value = json.loads(encoded)
    require(isinstance(value, dict), "GitHub evidence is not an object")
    return value, {"url": url, "started_at": started, "completed_at": now(),
                   "bytes": len(encoded), "sha256": sha(encoded)}


def deployment_evidence():
    run, run_receipt = github_json("actions/runs/" + str(PAGES_RUN))
    require(run.get("id") == PAGES_RUN and run.get("workflow_id") == PAGES_WORKFLOW
            and run.get("path") == ".github/workflows/pages.yml"
            and run.get("head_sha") == EXPECTED_BUILD and run.get("head_branch") == "main"
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and object_or_empty(run.get("repository")).get("full_name") == REPOSITORY,
            "The exact main Pages run is not successfully complete; do not infer deployment")
    jobs, jobs_receipt = github_json("actions/runs/" + str(PAGES_RUN) + "/jobs?per_page=100")
    rows = jobs.get("jobs")
    require(isinstance(rows, list) and type(jobs.get("total_count")) is int
            and jobs["total_count"] == len(rows) <= 100, "Incomplete Pages job inventory")
    deploy = [row for row in rows if row.get("name") == "deploy"]
    require(len(deploy) == 1 and deploy[0].get("status") == "completed"
            and deploy[0].get("conclusion") == "success", "Successful deploy job not observed")
    return {"run": PAGES_RUN, "head": EXPECTED_BUILD, "deploy_job": deploy[0]["id"],
            "deploy_completed_at": deploy[0].get("completed_at"),
            "responses": [run_receipt, jobs_receipt]}


SNAPSHOT = """async () => {
  const {loadSnapshot} = await import('./snapshot.mjs');
  const {displayTarget} = await import('./display.mjs');
  const s = await loadSnapshot();
  const failures = (s.errors || []).map(x=>x.message);
  for (const k of ['pros004Error','displayError','offersError','pairedResearchError',
                   'dailyResearchError','productionResearchError']) if(s[k]) failures.push(k+': '+s[k]);
  if(failures.length) throw new Error(failures.join('; '));
  const nba=s.sports.find(x=>x.league==='NBA');
  if(!nba || !s.display) throw new Error('Missing verified NBA/display channel');
  const historical=nba.forecasts.filter(x=>x.evidence_lane==='RECONSTRUCTED_RESEARCH');
  return {manifest:s.manifest, historical:historical.map(f=>({
    player_id:f.player_id,event_id:f.event_id,event_starts_at:f.event_starts_at,
    player_label:f.player_label,forecast_id:f.forecast_id,issued_at:f.issued_at,
    cutoff_at:f.cutoff_at,target:displayTarget(f,s.display)})),
    legacy_counts:Object.fromEntries(['forecasts','performance','offers','candidates','tickets'].map(k=>[k,nba[k].length])),
    clocks:s.display.status,
    channel_counts:Object.fromEntries(['pros004','offers','pairedResearch','dailyResearch','productionResearch'].map(k=>[k,
      s[k]?.counts ?? s[k]?.index?.counts ?? null])),
    production_loaded_game_date:s.productionResearch?.loaded_game_date ?? null};
}"""


def safe_static(root, relative):
    parts = PurePosixPath(relative).parts
    require(parts and not relative.startswith("/") and not any(p in {".", ".."} for p in parts),
            "Unsafe public asset path")
    target = root / "web"
    for part in parts:
        target = target / part
        require(not target.is_symlink(), "Static source path traverses a symlink")
    require(target.is_file(), "Public static asset is absent from the exact deployed source: " + relative)
    return target


class NetworkProof:
    def __init__(self, root):
        self.root, self.total, self.response_count = root, 0, 0
        self.records, self.responses, self.blocked = {}, [], []

    def guard(self, route):
        request = route.request
        if request.url == "https://nicknicky19.github.io/favicon.ico":
            route.abort()  # Browser chrome, not a project request.
            return
        if request.method != "GET" or not request.url.startswith(BASE):
            self.blocked.append({"url": request.url, "method": request.method})
            route.abort()
            return
        route.continue_()

    def receive(self, response):
        self.response_count += 1
        require(self.response_count <= MAX_RESPONSES, "Browser response budget exceeded")
        self.responses.append(response)

    def consume(self):
        for response in self.responses:
            url = response.url
            require(url.startswith(BASE) and response.status == 200, "Public response failed: " + url)
            length = response.headers.get("content-length")
            require(length is None or int(length) <= MAX_BODY, "Public response exceeds its advertised bound")
            encoded = response.body()
            require(len(encoded) <= MAX_BODY, "Public response exceeds its body bound")
            self.total += len(encoded)
            require(self.total <= MAX_NETWORK, "Public response budget exceeds 64 MiB")
            relative = unquote(urlsplit(url).path[len(urlsplit(BASE).path):]) or "index.html"
            checksum = sha(encoded)
            existing = self.records.get(url)
            require(existing is None or existing["sha256"] == checksum,
                    "Public bytes changed during verification: " + url)
            if relative == "data/manifest.json":
                body = json.loads(encoded)
                require(body.get("build_commit") == EXPECTED_BUILD, "Public manifest serves a different build")
                kind = "manifest"
            elif relative.startswith("data/") and relative.endswith(".json"):
                match = re.search(r"\.([a-f0-9]{64})\.json$", relative)
                require(match is not None and checksum == match.group(1),
                        "Public data filename does not match its raw bytes: " + relative)
                kind = "hash_named_data"
            else:
                require(safe_static(self.root, relative).read_bytes() == encoded,
                        "Served static bytes differ from deployed source: " + relative)
                kind = "exact_deployed_static"
            self.records[url] = {"url": url, "path": relative, "bytes": len(encoded),
                                 "sha256": checksum, "verification": kind, "observed_at": now()}
        self.responses.clear()
        require(not self.blocked, "Unexpected external or non-GET browser request")


def verify_browser(root, output):
    from playwright.sync_api import sync_playwright
    proof = NetworkProof(root)
    screenshots, views = [], []
    total_shots = 0
    canonical_snapshot = None
    builder_cases = 0

    def capture(page, name, width):
        nonlocal total_shots
        page.evaluate("document.activeElement?.blur(); window.scrollTo(0,0)")
        path = output / (name + "-" + str(width) + ".png")
        encoded = page.screenshot(full_page=False)
        require(len(encoded) <= MAX_SHOT, "Screenshot exceeds 4 MiB")
        total_shots += len(encoded)
        require(total_shots <= MAX_SHOTS, "Screenshots exceed 32 MiB")
        path.write_bytes(encoded)
        screenshots.append({"path": path.name, "bytes": len(encoded), "sha256": sha(encoded),
                            "url": page.url, "viewport": width, "captured_at": now()})
        require(page.evaluate("document.documentElement.scrollWidth<=innerWidth"), "Viewport overflows")
        views.append({"route": page.url, "width": width, "checked_at": now()})
        # Chromium may discard prior-document bodies on the next navigation.
        # Verify actual received bytes while their document is still live.
        proof.consume()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        version = browser.version
        for width, height in ((1440, 1000), (390, 844), (320, 760)):
            context = browser.new_context(viewport={"width": width, "height": height},
                                          service_workers="block")
            context.route("**/*", proof.guard)  # Allowlist only; never fulfill, mock or rewrite a response.
            context.on("response", proof.receive)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE + "#/overview", wait_until="networkidle", timeout=30000)
            page.get_by_role("heading", level=1).wait_for()
            capture(page, "overview", width)
            page.goto(BASE + "#/props/upcoming")
            page.get_by_role("heading", level=1, name="Props", exact=True).wait_for()
            page.locator(".research-availability").wait_for()
            snapshot = page.evaluate(SNAPSHOT)
            require(snapshot["manifest"]["build_commit"] == EXPECTED_BUILD, "Native validator found the wrong build")
            if canonical_snapshot is None:
                canonical_snapshot = snapshot
            require(snapshot["manifest"]["snapshot_id"] == canonical_snapshot["manifest"]["snapshot_id"],
                    "Published snapshot changed between viewports")
            records = snapshot["historical"]
            require(len(records) == 6 and {f["target"]["playerName"] for f in records} == EXPECTED_NAMES
                    and all(f["target"]["nameBasis"] == "SOURCE_VERIFIED_DISPLAY" for f in records),
                    "Six source-backed historical identities are not preserved")
            require(snapshot["legacy_counts"]["performance"] == 6, "Six original statistical grades are missing")
            availability = page.locator(".research-availability")
            labels = availability.locator(".publication-clocks dt").all_inner_texts()
            require({"Site publication", "Last retained NBA forecast-input preparation",
                     "Last genuine pregame issuance"} <= set(labels), "Publication/capture/issuance clocks conflated")
            publication = availability.locator(".publication-clocks>div").filter(
                has=page.get_by_text("Site publication", exact=True)).locator("dd")
            expected_publication = page.evaluate("(value)=>new Intl.DateTimeFormat(\'en-GB\', "
                "{dateStyle:\'medium\',timeStyle:\'short\',timeZone:\'UTC\'}).format(new Date(value))+\' UTC\'",
                snapshot["manifest"]["published_at"])
            require(publication.inner_text() == expected_publication,
                    "Displayed publication clock differs from the manifest")
            text = availability.inner_text()
            require("0 qualified · NO_ACTION" in text, "Website claims a qualified paper ticket")
            require("price unavailable" in text and "quotes, value estimates and tickets have separate checks" in text,
                    "Offer-only evidence was conflated with prices or tickets")
            require(page.get_by_role("alert").count() == 0, "Published channels raised a recovery alert")
            capture(page, "upcoming", width)
            page.goto(BASE + "#/props/history")
            page.wait_for_function("document.querySelector('[data-filter=\"view\"]')?.value==='history'")
            proof.consume()
            page.reload(wait_until="networkidle")
            page.wait_for_function("document.querySelector('[data-filter=\"view\"]')?.value==='history'")
            page.locator('[data-filter="category"]').select_option("REB")
            for record in records:
                target = record["target"]
                card = page.locator(".forecast-card").filter(
                    has=page.get_by_role("heading", name=target["playerName"], exact=True))
                require(card.count() == 1, "Readable historical player heading is missing or duplicated")
                require(target["matchup"] in card.inner_text() and target["teamName"] in card.inner_text(),
                        "Historical matchup/team names changed")
                require(card.locator("time").first.get_attribute("datetime") == record["event_starts_at"],
                        "Historical event date differs from the original")
                card.locator("summary").first.click()
                detail = card.inner_text()
                require(all(str(record[k]) in detail for k in
                            ("player_id", "event_id", "player_label", "forecast_id", "issued_at", "cutoff_at")),
                        "Accessible original source IDs, clocks or forecast identity are missing")
                card.locator("summary").first.click()
            capture(page, "history", width)
            page.locator('[data-filter="category"]').select_option("ALL")
            while page.locator("#more-forecasts").count():
                page.locator("#more-forecasts").click()
            require(set(page.locator(".forecast-card").evaluate_all(
                "cards=>cards.map(card=>card.dataset.market)")) == CATEGORIES, "Fourteen category coverage changed")
            page.get_by_role("link", name="Performance", exact=True).click()
            page.get_by_role("heading", level=1, name="Performance", exact=True).wait_for()
            require(EXPECTED_NAMES <= set(page.locator(".performance-targets strong").all_inner_texts()),
                    "Performance hides verified player names")
            capture(page, "performance", width)
            page.get_by_role("link", name="Paper Builder", exact=True).click()
            page.get_by_role("heading", level=1, name="Paper Builder", exact=True).wait_for()
            for scope in ("One sport", "Selected sports", "All supported"):
                page.get_by_role("button", name=scope, exact=True).click()
                if scope != "All supported":
                    page.locator('input[name="sport"][value="NBA"]').check()
                for legs in range(2, 7):
                    page.locator('input[name="legs"][value="' + str(legs) + '"]').check()
                    for direction in ("OVER_ONLY", "UNDER_ONLY", "MIXED"):
                        page.locator('input[name="direction"][value="' + direction + '"]').check()
                        page.get_by_role("button", name="Check paper readiness", exact=True).click()
                        summary = page.locator(".request-summary").inner_text()
                        require(str(legs) + " legs" in summary and direction in summary
                                and "0 admitted candidates" in summary, "Builder request/scope changed")
                        require("NO_ACTION" in page.locator(".decision-box").inner_text(),
                                "Unsupported ticket escaped NO_ACTION")
                        builder_cases += 1
            page.get_by_role("button", name="Selected sports", exact=True).click()
            page.locator('input[name="sport"][value="NBA"]').uncheck()
            require("No sports selected" in page.locator("main").inner_text(), "Empty sport scope expanded")
            page.get_by_role("link", name="Props", exact=True).click()
            require(page.locator(".forecast-card").count() == 0, "Empty scope displays legacy opportunities")
            page.get_by_role("link", name="Paper Builder", exact=True).click()
            page.get_by_role("button", name="All supported", exact=True).click()
            capture(page, "builder", width)
            page.goto(BASE + "#/sources")
            page.get_by_role("heading", level=1, name="Source Health", exact=True).wait_for()
            capture(page, "sources", width)
            require(not errors, "Public browser runtime errors: " + "; ".join(errors)[:1024])
            page.wait_for_load_state("networkidle")
            proof.consume()
            context.close()
        browser.close()
    require(builder_cases == 135, "Incomplete builder matrix")
    require(any(x["verification"] == "manifest" for x in proof.records.values()), "No public manifest response")
    require(any(x["path"] == "snapshot.mjs" for x in proof.records.values()), "Served validator bytes were not checked")
    return {"browser_version": version, "viewports": [1440, 390, 320], "views": views,
            "builder_cases": builder_cases, "screenshots": screenshots,
            "network_bytes_including_repeats": proof.total, "response_count": proof.response_count,
            "responses": sorted(proof.records.values(), key=lambda x: x["url"]),
            "snapshot": canonical_snapshot}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "nml-public-pages-verification-v1", "started_at": now(),
              "expected_build": EXPECTED_BUILD, "pages_run": PAGES_RUN, "public_url": BASE,
              "status": "BLOCKED", "public_verified": False, "provider_requests": 0,
              "forecasts_generated": 0, "model_evaluation": False, "merge_mutations": 0,
              "verifier_sha256": sha(Path(__file__).read_bytes()),
              "static_scope": "All browser-loaded project static assets and native selected publication pages; not an exhaustive crawl."}
    try:
        report["execution"] = identity()
        root = args.source_root.resolve()
        require((root / ".git/HEAD").read_text().strip() == EXPECTED_BUILD,
                "Static comparison checkout is not the exact deployed commit")
        report["deployment"] = deployment_evidence()
        report["browser"] = verify_browser(root, output)
        report.update(status="PASS", public_verified=True)
        code = 0
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error)[:2048])
        code = 1
    report["completed_at"] = now()
    encoded = json.dumps(report, sort_keys=True, indent=2).encode() + b"\n"
    require(len(encoded) <= 1024 * 1024, "Public verification report exceeds 1 MiB")
    (output / "public-verification.json").write_bytes(encoded)
    summary = {k:report[k] for k in ("status", "expected_build", "pages_run",
                                   "public_verified", "started_at", "completed_at")}
    summary.update(error_type=report.get("error_type"), error=report.get("error"),
                   verifier_sha256=report["verifier_sha256"])
    if report.get("browser"):
        proof = report["browser"]
        summary.update(browser_version=proof["browser_version"], views=len(proof["views"]),
            screenshots=len(proof["screenshots"]), builder_cases=proof["builder_cases"],
            public_snapshot_id=proof["snapshot"]["manifest"]["snapshot_id"],
            historical_counts=proof["snapshot"]["legacy_counts"],
            public_channel_counts=proof["snapshot"]["channel_counts"],
            served_assets=len(proof["responses"]), rendered_names=sorted(EXPECTED_NAMES))
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
