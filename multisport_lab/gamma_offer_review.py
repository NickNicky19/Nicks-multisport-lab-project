"""Offline Gamma original replay and LOCAL_REVIEW_ONLY source observations.

No collection, trading, provider credentials, encryption keys or public admission.
Missing contract facts stay missing; this adapter cannot make an offer qualified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from .integrity import (IntegrityError, _bounded_bytes, _decode, canonical, digest,
                        load_json, stamp, utc, write_receipt)
from .offer_import import UNITS
from .offer_publication import SETTLEMENT_FIELDS

VERSION = "gamma-nba-local-review-1"
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_GETS = 12
MAX_PLAYER_ROWS = 32
TYPE_MAP = {"points": ("PTS", "Points"), "rebounds": ("REB", "Rebounds"),
            "assists": ("AST", "Assists")}
# These additional families actually occur in the captured official global
# market-type enum. Count a returned row even before its parser is implemented.
# This is a family inventory, not proof of an NBA contract's rules or coverage.
FAMILY_MAP = {**{key: value[0] for key, value in TYPE_MAP.items()},
              "threes": "3PM", "assists_points_rebounds": "PRA", "double_doubles": "DD"}
ID_GAP = "Provider response supplies no stable player entity ID."
CORRECTION_GAP = "NBA stat-correction and regrading treatment is not specified."
TOKEN_GAP = "Outcome-to-token mapping is not verified by retained API documentation."


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def original(directory: Path, label: str) -> tuple[dict, dict]:
    """Strict exact-byte recovery; metadata is capture evidence, not a signature."""
    raw = _bounded_bytes(directory / (label + ".body"), MAX_BODY_BYTES)
    metadata = load_json(directory / (label + ".metadata.json"))
    require(metadata.get("complete_body") is True and metadata.get("http_status") == 200,
            "Incomplete or unsuccessful original capture")
    require(type(metadata.get("raw_bytes")) is int and metadata["raw_bytes"] == len(raw)
            and metadata.get("raw_sha256") == hashlib.sha256(raw).hexdigest(),
            "Original response count/hash mismatch")
    for name in ("url", "final_url"):
        parsed = urlsplit(metadata[name])
        require(parsed.scheme == "https" and parsed.netloc in {
            "gamma-api.polymarket.com", "docs.polymarket.com", "www.wikidata.org"}
                and not parsed.username and not parsed.password and not parsed.fragment,
                "Original outside reviewed public source hosts")
    require(metadata["url"] == metadata["final_url"], "Redirect requires a separately counted receipt")
    require(utc(metadata["request_started_at"]) <= utc(metadata["observed_at"]), "Reversed capture clocks")
    decoded = _decode(raw)
    require(type(decoded) is dict, "Expected JSON object original")
    # Strict decoding first rejects duplicate keys and all nonfinite values.
    # Numeric fields then retain their original lexical precision as text.
    return json.loads(raw, parse_float=str, parse_int=str), metadata


def verify_request_ledger(directory: Path) -> dict:
    ledger = load_json(directory / "requests.json")
    entries = ledger.get("requests")
    require(ledger.get("limit") == MAX_GETS and type(entries) is list
            and 0 < len(entries) <= MAX_GETS, "Shared GET budget exceeded or missing")
    for ordinal, entry in enumerate(entries, 1):
        require(type(entry.get("label")) is str and re.fullmatch(r"[a-z][a-z0-9-]{0,80}", entry["label"]),
                "Unsafe original label")
        require(entry.get("ordinal") == ordinal and entry.get("retries") == 0
                and entry.get("automatic_redirects") is False, "Unaccounted attempt/redirect")
        raw = _bounded_bytes(directory / (entry["label"] + ".body"), MAX_BODY_BYTES)
        require(entry.get("complete_body") is True and len(raw) == entry["raw_bytes"]
                and hashlib.sha256(raw).hexdigest() == entry["raw_sha256"], "Request original changed")
        require(load_json(directory / (entry["label"] + ".metadata.json")) == entry,
                "Request ledger/sidecar mismatch")
    return ledger


def player_crosswalk(directory: Path) -> dict:
    """CC0 canonical identity; never reinterpret it as a Gamma player ID."""
    data, metadata = original(directory, "wikidata-edwards-entity")
    properties, property_meta = original(directory, "wikidata-identifier-properties")
    entities = data.get("entities", {})
    require(len(entities) == 1, "Ambiguous canonical identity response")
    entity_id, entity = next(iter(entities.items()))
    require(re.fullmatch(r"Q\d+", entity_id) and entity.get("id") == entity_id,
            "Invalid canonical entity identity")
    label = entity["labels"]["en"]["value"]
    require("basketball player" in entity["descriptions"]["en"]["value"],
            "Named entity is not independently identified as a basketball player")
    identity_url, property_url = urlsplit(metadata["url"]), urlsplit(property_meta["url"])
    require(identity_url.netloc == "www.wikidata.org"
            and identity_url.path == f"/wiki/Special:EntityData/{entity_id}.json",
            "Canonical response URL/entity mismatch")
    query = parse_qs(property_url.query)
    require(property_url.netloc == "www.wikidata.org" and property_url.path == "/w/api.php"
            and query.get("action") == ["wbgetentities"]
            and set(query.get("ids", [""])[0].split("|")) == {"P3647", "P3685"},
            "Property definitions are not bound to their Wikidata source")
    external = {}
    for property_id, expected_label, namespace in (
            ("P3647", "NBA.com player ID", "nba"),
            ("P3685", "ESPN.com NBA player ID", "espn")):
        require(properties["entities"][property_id]["labels"]["en"]["value"] == expected_label,
                "Unverified external identifier property meaning")
        claims = entity["claims"][property_id]
        require(len(claims) == 1 and claims[0]["mainsnak"]["datatype"] == "external-id",
                "Ambiguous canonical external identifier")
        value = claims[0]["mainsnak"]["datavalue"]["value"]
        require(type(value) is str and re.fullmatch(r"\d+", value), "Invalid external identifier")
        external[namespace] = value
    return {"player_name": label, "identity": {"namespace": "wikidata", "id": entity_id},
            "external_ids": external, "entity_revision": entity["lastrevid"],
            "raw_sha256": metadata["raw_sha256"], "observed_at": metadata["observed_at"],
            "gamma_player_entity_id": None, "current_team_affiliation_verified": False}


def _array(value, label):
    require(type(value) is str, "Expected source JSON-string " + label)
    result = _decode(value.encode())
    require(type(result) is list and len(result) == 2, "Invalid binary " + label)
    return result


def _price(value):
    require(type(value) is str and re.fullmatch(r"(?:0|1)(?:\.\d+)?", value)
            and Decimal(0) <= Decimal(value) <= Decimal(1), "Invalid literal binary price")
    return value


def inspect_bundle(directory: Path | str, *, now: datetime) -> tuple[dict, dict]:
    directory = Path(directory)
    ledger = verify_request_ledger(directory)
    require(all(utc(entry["request_started_at"]) <= utc(entry["observed_at"]) <= utc(now)
                for entry in ledger["requests"]), "Import precedes or reverses a required capture")
    event, meta = original(directory, "gamma-game-event")
    selected, selected_meta = original(directory, "gamma-edwards-market")
    crosswalk = player_crosswalk(directory)
    require(urlsplit(meta["url"]).netloc == "gamma-api.polymarket.com"
            and urlsplit(meta["url"]).path == "/events/" + event["id"], "Wrong linked event identity")
    require(urlsplit(selected_meta["url"]).netloc == "gamma-api.polymarket.com"
            and urlsplit(selected_meta["url"]).path == "/markets/" + selected["id"], "Wrong selected market identity")
    require(utc(meta["observed_at"]) <= utc(now) and utc(selected_meta["observed_at"]) <= utc(now)
            and utc(crosswalk["observed_at"]) <= utc(now), "Import precedes required capture")
    teams = event.get("teams")
    require(type(teams) is list and len(teams) == 2 and len({x["id"] for x in teams}) == 2
            and all(x.get("league") == "nba" for x in teams), "Unverified NBA matchup")
    require(type(event.get("title")) is str and event["title"], "Missing source matchup label")
    ordering = {team.get("ordering"): team.get("name") for team in teams}
    require(set(ordering) == {"away", "home"} and all(type(x) is str and x for x in ordering.values())
            and event["title"] == ordering["away"] + " vs. " + ordering["home"],
            "Matchup title conflicts with source team identities/order")
    markets = event.get("markets")
    require(type(markets) is list and len(markets) <= 128, "Event market inventory exceeds bound")
    matches = [row for row in markets if row.get("id") == selected["id"]]
    require(len(matches) == 1, "Selected market missing or duplicated in linked event")
    for field in ("id", "question", "conditionId", "description", "outcomes", "clobTokenIds",
                  "gameStartTime", "line", "sportsMarketType"):
        require(matches[0].get(field) == selected.get(field), "Selected/linked contract conflicts: " + field)
    coverage = {key: {"observed_rows": 0, "parsed_rows": 0, "status": "UNOBSERVED_IN_SAMPLE"}
                for key in UNITS}
    observations, diagnostics, source_fields = [], [], {}
    seen = set()
    for row in markets:
        market_type = row.get("sportsMarketType")
        if market_type not in FAMILY_MAP:
            continue
        category = FAMILY_MAP[market_type]
        coverage[category]["observed_rows"] += 1
        if market_type not in TYPE_MAP:
            coverage[category]["status"] = "UNSUPPORTED"
            diagnostics.append({"source_market_id": row.get("id"),
                                "reason": "Observed family parser not implemented: " + market_type})
            continue
        _, label = TYPE_MAP[market_type]
        try:
            require(row["id"] not in seen, "Duplicate source player market")
            seen.add(row["id"])
            match = re.fullmatch(r"(.+): " + label + r" O/U ((?:0|[1-9]\d*)(?:\.\d+)?)", row["question"])
            require(match is not None, "Unverified player/stat/threshold question")
            name, line = match.groups()
            require(Decimal(row["line"]) == Decimal(line), "Contradictory source thresholds")
            description = row["description"]
            noun = {"PTS": "points", "REB": "rebounds", "AST": "assists"}[category]
            require(re.search(r'"Yes" if ' + re.escape(name) + r' (?:scores|records) more than '
                              + re.escape(line) + r' (?:total )?' + noun + r' during the game\.', description),
                    "Explicit source YES predicate missing")
            require(re.search(r'"No" if ' + re.escape(name) + r' (?:scores|records) '
                              + re.escape(line) + ' ' + noun + r' or fewer during the game\.', description),
                    "Explicit source NO predicate missing")
            require(_array(row["outcomes"], "outcomes") == ["Yes", "No"], "Unverified source selections")
            tokens = _array(row["clobTokenIds"], "token identifiers")
            require(all(type(x) is str and re.fullmatch(r"\d+", x) for x in tokens)
                    and tokens[0] != tokens[1], "Invalid source token identifiers")
            require(utc(row["gameStartTime"]) == utc(event["startTime"]), "Contract/event start conflicts")
            prices = None if row.get("outcomePrices") is None else _array(row["outcomePrices"], "prices")
            if prices is not None:
                prices = [_price(x) for x in prices]
            gaps = [ID_GAP, CORRECTION_GAP, TOKEN_GAP]
            identity = crosswalk["identity"] if name == crosswalk["player_name"] else None
            if identity is None:
                gaps.append("Player name lacks independent stable-identity evidence.")
            if event.get("eventMetadata", {}).get("context_requires_regen") is True:
                gaps.append("The source event context flag requires explanation.")
            if row.get("restricted") is True or row.get("ready") is False or row.get("funded") is False:
                gaps.append("Source status flags do not establish an executable offer.")
            settlement = {}
            period = overtime = None
            if "The entire game including all overtime periods will be considered." in description:
                period, overtime = "full_game", "includes_overtime"
            else:
                gaps.append("Full-game period and overtime policy are unverified.")
            sentences = {
                "dnp": 'If the player is listed as inactive or otherwise does not take the court at any point, the market will resolve "No".',
                "postponement": "If the game is postponed, this market will remain open until the game has been completed. If the game is canceled entirely, with no make-up game, this market will resolve 50-50.",
                "official_stat_source": "The resolution source will be the official NBA box score as published on NBA.com.",
            }
            for field, sentence in sentences.items():
                if sentence in description:
                    settlement[field] = sentence
                else:
                    gaps.append("Source settlement meaning is unverified: " + field)
            if "dnp" in settlement:
                settlement["participation"] = settlement["dnp"]
            settlement["ties"] = 'The explicit No predicate includes ' + line + ' ' + noun + ' or fewer.'
            updated = stamp(utc(row["updatedAt"])) if row.get("updatedAt") else None
            if updated is not None and utc(updated) > utc(meta["observed_at"]):
                gaps.append("source_update_later_than_observation")
            observations.append({
                "source_market_id": row["id"], "source_event_id": event["id"],
                "player_name": name, "player_identity": identity, "event_label": event["title"],
                "event_starts_at": stamp(utc(event["startTime"])), "category": category,
                "threshold": line, "operator": ">", "selection": "Yes", "selection_id": None,
                "variant": "binary_player_stat_threshold", "period": period, "overtime": overtime,
                "observed_at": stamp(utc(meta["observed_at"])), "source_updated_at": updated,
                "prices_as_supplied": {"outcomes": ["Yes", "No"], "outcomePrices": prices,
                    "bestBid": _price(row["bestBid"]) if row.get("bestBid") is not None else None,
                    "bestAsk": _price(row["bestAsk"]) if row.get("bestAsk") is not None else None},
                "sportsbook_price_status": "PRICE_UNAVAILABLE", "settlement": settlement,
                "gaps": gaps, "complete": False, "normalized_offer_available": False,
                "raw_source_sha256": meta["raw_sha256"],
            })
            coverage[category]["parsed_rows"] += 1
            source_fields[row["id"]] = {key: row.get(key) for key in (
                "conditionId", "questionID", "clobTokenIds", "customLiveness", "restricted", "ready",
                "funded", "acceptingOrders", "fallbackResolutionType", "feeSchedule")}
        except (IntegrityError, KeyError, ValueError, TypeError) as error:
            diagnostics.append({"source_market_id": row.get("id"), "reason": str(error)})
    require(len(observations) <= MAX_PLAYER_ROWS, "Local player observation bound exceeded")
    for counts in coverage.values():
        if counts["observed_rows"] and counts["status"] != "UNSUPPORTED":
            counts["status"] = "OBSERVED_PARTIAL"
    # The independently identified selected subject is easy to find in preview.
    observations.sort(key=lambda x: (x["source_market_id"] != selected["id"], x["source_market_id"]))
    review = {"schema_version": "nba-local-offer-review-v1", "scope": "LOCAL_REVIEW_ONLY",
        "generated_at": stamp(utc(now)), "source": "Polymarket Gamma API", "venue": "Polymarket",
        "product": "binary_event_contract", "public_admission": False, "ticket_eligibility": False,
        "counts": {"player_rows_observed": sum(x["observed_rows"] for x in coverage.values()),
                   "rows_parsed": len(observations), "complete_contracts": 0},
        "category_coverage": coverage, "observations": observations}
    normalization = {"schema_version": "nba-local-normalization-readiness-v1",
        "target": "nba-player-offer-v1 / normalized_v1", "status": "BLOCKED_INCOMPLETE_CONTRACT",
        "required_settlement_fields": sorted(SETTLEMENT_FIELDS), "canonical_player_crosswalk": crosswalk,
        "normalized_capture": None, "diagnostics": diagnostics, "source_fields_as_supplied": source_fields,
        "request_count": len(ledger["requests"]), "standalone_market_original": selected_meta,
        "event_original": meta, "parser_version": VERSION,
        "source_event_identity": {key: event.get(key) for key in ("id", "gameId", "title", "startTime", "version", "teams", "eventMetadata", "active", "closed", "restricted")},
        "source_market_type_counts": {kind: sum(row.get("sportsMarketType") == kind for row in markets)
                                      for kind in sorted({str(row.get("sportsMarketType")) for row in markets})},
        "explanation": "Source facts are staged locally. Missing stable provider identity, selection binding and stat-correction meaning prevent entry into the existing complete normalized offer-only path. No field is invented to satisfy that validator."}
    return review, normalization


def build_preview(bundle: Path, destination: Path, *, now: datetime, source_root: Path) -> dict:
    source_root = source_root.resolve()
    destination = Path(os.path.abspath(destination))
    require(destination.is_relative_to(source_root / ".local-data")
            and destination != source_root / ".local-data",
            "Real-source preview must remain in ignored local storage")
    current = source_root
    for part in destination.relative_to(source_root).parts:
        current = current / part
        require(not current.is_symlink() and (not current.exists() or current.is_dir()),
                "Local preview parent must be a real directory")
    for name in ("review.receipt.json", "normalization.receipt.json", "review.json", "index.html",
                 "preview.mjs", "local-offer-review.mjs", "local-offer-review.css", "research.mjs"):
        path = destination / name
        require(not path.is_symlink() and (not path.exists() or path.is_file()),
                "Local preview asset must be a regular file")
    review, readiness = inspect_bundle(bundle, now=now)
    destination.mkdir(parents=True, exist_ok=True)
    write_receipt(destination / "review.receipt.json", review)
    write_receipt(destination / "normalization.receipt.json", readiness)
    assets = {"review.json": canonical(review), "local-offer-review.mjs": (source_root / "web/local-offer-review.mjs").read_bytes(),
              "local-offer-review.css": (source_root / "web/local-offer-review.css").read_bytes(),
              "research.mjs": (source_root / "web/research.mjs").read_bytes()}
    assets["index.html"] = b'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'"><title>NBA local source review</title><link rel="stylesheet" href="local-offer-review.css"><main id="review">Loading local review...</main><script type="module" src="preview.mjs"></script></html>'''
    assets["preview.mjs"] = b'''import {renderLocalOfferReview} from './local-offer-review.mjs';
try { const response=await fetch('./review.json',{cache:'no-store'}); if(!response.ok) throw new Error('Local review read failed'); const data=await response.json(); document.querySelector('#review').innerHTML=renderLocalOfferReview(data); }
catch(error) { document.querySelector('#review').textContent='Local review unavailable: '+error.message; }
'''
    for name, raw in assets.items():
        path = destination / name
        if path.exists():
            require(path.read_bytes() == raw, "Conflicting local preview asset; use a new destination")
        else:
            with path.open("xb") as handle:
                handle.write(raw)
    return {"preview": str(destination), "counts": review["counts"],
            "asset_sha256": {key: hashlib.sha256(raw).hexdigest() for key, raw in assets.items()},
            "public_admission": False, "ticket_eligibility": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_preview(args.bundle, args.preview, now=datetime.now(timezone.utc),
                                   source_root=Path(__file__).resolve().parents[1]), sort_keys=True))


if __name__ == "__main__":
    main()
