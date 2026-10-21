"""Explicit local static-v2 preview check; no source requests or publication."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from multisport_lab.integrity import IntegrityError, _bounded_bytes, write_receipt


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def local_path(value):
    root = Path.cwd().resolve()
    local = root / ".local-data"
    path = Path(os.path.abspath(value))
    require(path.is_relative_to(local) and path != local,
            "Actual local preview artifacts must remain under cwd/.local-data")
    cursor = root
    for part in path.relative_to(root).parts:
        cursor /= part
        require(not cursor.is_symlink(), "Local preview path must not traverse a symlink")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("output", type=Path, help="New ignored local directory; never overwritten")
    args = parser.parse_args()
    source, output = local_path(args.html), local_path(args.output)
    info = source.lstat()
    require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 2 * 1024 * 1024,
            "Static preview must be a bounded regular file")
    source_raw = _bounded_bytes(source, 2 * 1024 * 1024)
    require(not output.exists(), "Use a new local browser-evidence directory")
    output.mkdir(parents=True, mode=0o700)
    viewports = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        try:
            for width, height in ((1440, 1000), (390, 844), (320, 760)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors, requests = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: requests.append(request.url)
                        if request.url.startswith(("http:", "https:")) else None)
                page.route("http://**/*", lambda route: route.abort())
                page.route("https://**/*", lambda route: route.abort())
                # Render already-authorized bytes through the supported DOM API.
                # Do not navigate the managed browser to its blocked file scheme.
                page.set_content(source_raw.decode("utf-8"), wait_until="load")
                require(page.locator("script").count() == 0, "Static review must contain no scripts")
                require(page.locator(".local-observation").count() == 1, "Exactly one selected contract is required")
                status = page.locator(".local-observation").get_attribute("data-semantic-status")
                require(status in {"INCOMPLETE", "COMPLETE_LOCAL"}, "Semantic status is not explicit")
                body = page.locator("body").inner_text()
                require("LOCAL REVIEW ONLY" in body and "PRICE_UNAVAILABLE" in body
                        and "Paper Builder: NO_ACTION" in body, "Local price/qualification boundaries missing")
                require(page.locator("tbody th[scope='row']").count() == 14, "Full category inventory missing")
                page.evaluate("document.querySelectorAll('details').forEach(item => {item.open=true})")
                require(page.evaluate("document.documentElement.scrollWidth<=innerWidth"),
                        "Semantic evidence details overflow the viewport")
                require(not errors and not requests, "Browser errors or HTTP requests occurred")
                screenshot = output / f"semantic-{width}.png"
                page.screenshot(path=str(screenshot), full_page=True)
                viewports.append({"width": width, "height": height, "semantic_status": status,
                    "overflow": False, "browser_errors": 0, "http_requests": 0,
                    "screenshot": str(screenshot),
                    "screenshot_sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest()})
                page.close()
        finally:
            browser.close()
    report = {"schema_version": "nba-semantic-local-browser-check-v1", "status": "PASS",
              "source_html": str(source), "source_html_sha256": hashlib.sha256(source_raw).hexdigest(),
              "rendering_mode": "PROVIDED_LOCAL_HTML_BYTES", "file_url_navigation_verified": False,
              "scope": "LOCAL_REVIEW_ONLY", "public_admission": False,
              "ticket_eligibility": False, "network_requests": 0, "viewports": viewports}
    write_receipt(output / "browser-check.json", report)
    print(json.dumps({"status": "PASS", "viewports": len(viewports), "network_requests": 0,
                      "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
