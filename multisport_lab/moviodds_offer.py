"""Offline, evidence-linked MoviOdds/bet365 NBA review, never public admission.

No HTTP client, polling, native player-ID invention, forecast issuance or price
qualification. The original public offer-v1 and Polymarket semantic-v2 contracts
are unchanged. Numeric ladder labels without an operator remain partial.
"""
from __future__ import annotations

from collections import Counter
import argparse
import csv
from datetime import datetime, timezone
from functools import wraps
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .integrity import IntegrityError, _bounded_bytes, _decode, canonical, digest, stamp, utc
from .offer_import import UNITS
from .source_evidence import _StaticText, _utf8, extract_source_text

SCHEMA = "nba-private-moviodds-offers-v1"
MAX_RAW_BYTES = 2 * 1024 * 1024
MAX_REVIEW_BYTES = 256 * 1024
MAX_QUOTES = 10000
MAX_DISPLAY = 8
URLS = {
    "catalog": "https://moviodds.com/catalog?sport=basketball",
    "snapshot": "https://moviodds.com/snapshot?fi=",  # exact fixture appended
    "api": "https://moviodds.com/doc",
    "sports": "https://moviodds.com/docs/sports/",
    "rules": "https://help.bet365.com/s/en/sportsrules/basketball",
    "roster": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_rosters/rosters_2027.csv",
    "schedule": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_schedules/nba_schedule_2027.csv",
}
GROUPS = {
    "181446": ("Points", "PTS"), "181447": ("Assists", "AST"),
    "181448": ("Rebounds", "REB"), "181449": ("Threes Made", "3PM"),
    "181463": ("Double Double", "DD"), "181464": ("Triple Double", "TD"),
    "182003": ("Points, Assists & Rebounds", "PRA"),
    "182004": ("Points & Rebounds", "PR"), "182005": ("Points & Assists", "PA"),
    "182006": ("Assists & Rebounds", "RA"), "182007": ("Steals & Blocks", "BLK+STL"),
    "182008": ("Blocks", "BLK"), "182009": ("Steals", "STL"),
}
QUARTERS = {"181551": ("1st Quarter Points", "PTS"),
            "181552": ("1st Quarter Rebounds", "REB"),
            "181553": ("1st Quarter Assists", "AST")}
RULE_PASSAGES = {
    "period_overtime": "All pre-game bets include overtime unless otherwise stated.",
    "player_overtime": "Overtime counts for any player props unless specified otherwise.",
    "participation": "Relevant players (all quoted players in a multi-player market) must be dressed and see court-time for bets to have action (unless specified otherwise).",
    "official_statistics_and_corrections": "Markets will be settled according to game stats from the respective official competition site published on the day of the game. Subsequent amendments do not affect settlement.",
    "double_triple_double": "Double/Double, player must record 10 or more in two of the following 5 statistical categories. Triple/Double, player must record 10 or more in 3 of the following 5 statistical categories: Points, Rebounds, Assists, Blocked Shots, Steals.",
    "push": "In 2-Way markets Push rules apply unless otherwise stated below. Stakes on single bets are returned, and in multiples/parlays the selection is treated as a non-runner.",
    "scheduled_date": "All games must start on the scheduled date (local stadium time) for bets to have action.",
    "interruption": "If a game is interrupted but subsequently resumed (from the point in the game at which it was interrupted) and played to a finish within 48 hours of the original scheduled game time, all bets will stand on the fixture.",
    "abandonment": "Otherwise if the game is resumed but not finished within 48 hours of the original scheduled game time, this will be treated as an abandonment and bets on the original fixture will be void, except for those bets the outcome of which had already been determined, prior to the initial interruption in fixture.",
    "minimum_duration": "There must be 5 minutes or less of scheduled game time left for bets to have action, unless the specific market outcome is already determined.",
    "replayed": "If a game is interrupted for any reason, and is replayed in full, this will be treated as an abandonment and bets on the original fixture will be void, except for those bets the outcome of which had already been determined, prior to the initial interruption in fixture.",
}


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _strict(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except IntegrityError:
            raise
        except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError) as error:
            raise IntegrityError("Malformed MoviOdds evidence: " + str(error)) from error
    return checked


class _RulesText(_StaticText):
    """Versioned extension: ignore self-closing drawing leaves inside hidden SVG.

    The existing html-static-text-v1 contract and its consumers are unchanged.
    Active/self-closing HTML outside an excluded SVG still fails closed.
    """
    def handle_startendtag(self, tag, attrs):
        if tag in {"path", "polygon", "line", "ellipse"} and any(
                name == "svg" and hidden for name, hidden in self.stack):
            self._node()
            return
        super().handle_startendtag(tag, attrs)


def rules_text(raw):
    parser = _RulesText()
    parser.feed(_utf8(raw))
    result = parser.result()
    require(0 < len(result) <= 512 * 1024, "Rules text exceeds bound")
    return result


def _text(value, limit=300):
    return type(value) is str and 0 < len(value) <= limit and value.strip() == value


def _id(value):
    return _text(value) and value.isascii() and value.isdecimal()


def _clock(value):
    require(type(value) is str and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z", value),
        "An actual UTC clock is required")
    # datetime truncates nanoseconds. Preserve source ordering exactly even for
    # a one-nanosecond future quote, confirmation or server clock.
    whole = utc(value[:19] + "Z") - datetime(1970, 1, 1, tzinfo=timezone.utc)
    fraction = value[20:-1] if len(value) > 20 else ""
    return (whole.days * 86400 + whole.seconds) * 10**9 + int(fraction.ljust(9, "0") or "0")


def _schedule_clock(value):
    require(type(value) is str, "Missing canonical schedule clock")
    # The retained CSV uses minute-resolution UTC. This is an exact conversion
    # for comparison only; retain that source literal unchanged in the record.
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z", value):
        value = value[:-1] + ":00Z"
    return _clock(value)


def _asset(key, assets, fixture, normalized_at):
    require(key in assets and type(assets[key]) is dict
            and set(assets[key]) == {"raw", "metadata_raw"}, "Missing original/metadata pair")
    raw, metadata_raw = assets[key]["raw"], assets[key]["metadata_raw"]
    require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW_BYTES
            and type(metadata_raw) is bytes and 0 < len(metadata_raw) <= 256 * 1024,
            "Original or metadata exceeds unchanged byte ceiling")
    metadata = _decode(metadata_raw)
    url = URLS[key] + fixture if key == "snapshot" else URLS[key]
    if key in {"roster", "schedule"}:
        # Replay the old, actual redirect/request inventory; do not manufacture
        # a 200 response at its stable GitHub URL or refresh its old clocks.
        require(type(metadata) is list, "Retained release request inventory required")
        redirects = [r for r in metadata if r.get("url") == url and r.get("status") == 302]
        require(len(redirects) == 1, "Publisher asset redirect is ambiguous")
        replies = [r for r in metadata if r.get("url") == redirects[0].get("location") and r.get("status") == 200]
        require(len(replies) == 1 and urlsplit(replies[0]["url"]).hostname == "release-assets.githubusercontent.com",
                "Original release redirect chain differs")
        response = replies[0]
        require(type(response["bytes"]) is int and response["bytes"] == len(raw)
                and response["sha256"] == hashlib.sha256(raw).hexdigest()
                and _clock(redirects[0]["request_started_at"]) <= _clock(redirects[0]["observed_at"])
                <= _clock(response["request_started_at"]),
                "Retained release original differs")
        meta = {"complete_body": True, "http_status": response["status"], "url": url, "final_url": url,
            "raw_bytes": response["bytes"], "raw_sha256": response["sha256"],
            "request_started_at": response["request_started_at"], "observed_at": response["observed_at"],
            "content_type": response["content_type"]}
    else:
        require(type(metadata) is dict, "Original response metadata required")
        meta = metadata
    require(meta.get("complete_body") is True and meta.get("http_status") == 200
            and meta.get("url") == meta.get("final_url") == url
            and type(meta.get("raw_bytes")) is int and meta["raw_bytes"] == len(raw)
            and meta.get("raw_sha256") == hashlib.sha256(raw).hexdigest(),
            "Incomplete, misrouted or changed original")
    require(_clock(meta["request_started_at"]) <= _clock(meta["observed_at"])
            <= _clock(normalized_at), "Original source clocks disagree")
    content_type = meta.get("content_type", "").split(";", 1)[0].lower()
    expected = {"catalog": {"application/json"}, "snapshot": {"application/json"},
                "api": {"text/html"}, "sports": {"text/html"}, "rules": {"text/html"},
                "roster": {"text/csv", "application/octet-stream"},
                "schedule": {"text/csv", "application/octet-stream"}}[key]
    require(content_type in expected, "Original media type differs")
    return raw, {"url": url, "raw_sha256": meta["raw_sha256"], "raw_bytes": len(raw),
        "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
        "request_started_at": meta["request_started_at"], "observed_at": meta["observed_at"],
        "content_type": content_type, "retrieval_basis": "RETAINED_RELEASE_REDIRECT_CHAIN" if key in {"roster", "schedule"} else "DIRECT_COMPLETE_HTTP_RESPONSE"}


def _csv(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)),
            "CSV header is ambiguous")
    rows = []
    for row in reader:
        require(None not in row and None not in row.values(), "CSV row is incomplete")
        rows.append(row)
        require(len(rows) <= 5000, "Identity CSV exceeds row ceiling")
    return rows


def _price(quote):
    value = quote.get("odds_dec")
    if value is None:
        return None
    require(type(value) in {str, int} and not isinstance(value, bool), "Invalid decimal price")
    value = str(value)
    require(len(value) <= 128 and re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value),
            "Unsupported price decimal lexeme")
    number = Decimal(value)
    require(number.is_finite() and 0 <= number <= 1000000, "Invalid bounded decimal price")
    return value


@_strict
def build_review(assets, *, fixture, normalized_at, evidence_lane="ACTUAL_SOURCE_REPLAY"):
    """Replay complete original bodies; no collection, late binding or issuance."""
    require(_text(fixture) and fixture.isascii() and fixture.isdecimal(), "Invalid native fixture")
    _clock(normalized_at)
    require(evidence_lane in {"ACTUAL_SOURCE_REPLAY", "SYNTHETIC_TEST"}, "Unknown private evidence lane")
    require(set(assets) == set(URLS), "Exact seven evidence roles required")
    raw, evidence = {}, {}
    for key in URLS:
        raw[key], evidence[key] = _asset(key, assets, fixture, normalized_at)
    api = extract_source_text(raw["api"], "text/html").decode()
    sports = extract_source_text(raw["sports"], "text/html").decode()
    require("No API key" in api or "no API key" in api or "no key" in api,
            "Retained API allowance no longer matches reviewed version")
    require("bet365" in api and "player props" in sports and "basketball" in sports,
            "Source/venue/category scope lacks original evidence")
    text = rules_text(raw["rules"])
    passages = {}
    for key, quote in RULE_PASSAGES.items():
        needle = quote.encode(); start = text.find(needle)
        require(start >= 0, "Exact reviewed basketball rule missing: " + key)
        passages[key] = {"start": start, "end": start + len(needle), "source_value": quote}
    catalog, snapshot = _decode(raw["catalog"]), _decode(raw["snapshot"])
    require(type(catalog) is dict and type(catalog.get("fixtures")) is list
            and type(catalog.get("count")) is int and catalog["count"] == len(catalog["fixtures"])
            and len(catalog["fixtures"]) <= 5000, "Malformed complete catalog")
    require(all(type(row) is dict and _id(row.get("id")) for row in catalog["fixtures"]),
            "Catalog identity missing")
    require(len({row["id"] for row in catalog["fixtures"]}) == len(catalog["fixtures"]),
            "Duplicate catalog fixture")
    matches = [row for row in catalog["fixtures"] if row["id"] == fixture]
    require(len(matches) == 1, "Selected fixture absent or ambiguous")
    event = matches[0]
    require(event.get("sport") == "basketball" and event.get("league") == "NBA"
            and type(event.get("in_play")) is bool
            and all(_text(event.get(k)) for k in ["home", "away", "kickoff_utc"])
            and event["home"] != event["away"], "Unsupported NBA event identity")
    _clock(event["kickoff_utc"])
    require(type(snapshot) is dict and snapshot.get("fixture") == fixture
            and type(snapshot.get("quotes")) is list
            and type(snapshot.get("count")) is int and 0 <= snapshot["count"] <= MAX_QUOTES
            and len(snapshot["quotes"]) == snapshot["count"], "Incomplete bounded fixture snapshot")
    require(type(snapshot.get("group_status")) is dict, "Per-market status required")
    require(_clock(snapshot["server_time"]) <= _clock(evidence["snapshot"]["observed_at"]),
            "Publisher clock is later than receipt")
    # Strict decode above rejects duplicates/non-finites; this preserves price lexemes.
    lexical = json.loads(raw["snapshot"], parse_float=str)
    roster, schedule = _csv(raw["roster"]), _csv(raw["schedule"])
    require(len({row["athlete_id"] for row in roster}) == len(roster), "Ambiguous canonical roster IDs")
    candidates = [row for row in schedule if row["home_abbreviation"] + " " + row["home_name"] == event["home"]
        and row["away_abbreviation"] + " " + row["away_name"] == event["away"]
        and row["date"][:10] == event["kickoff_utc"][:10]]
    require(len(candidates) <= 1, "Ambiguous canonical event candidate")
    candidate = candidates[0] if candidates else None
    if candidate is not None:
        require(all(_id(candidate[k]) for k in ["id", "home_id", "away_id"])
                and candidate["home_id"] != candidate["away_id"]
                and re.fullmatch(r"20[0-9]{2}", candidate["season"]), "Invalid canonical event candidate IDs/season")
    delta_ns = _clock(event["kickoff_utc"]) - _schedule_clock(candidate["date"]) if candidate else None
    delta = None if delta_ns is None else (delta_ns // 10**9 if delta_ns % 10**9 == 0
        else format(Decimal(delta_ns) / Decimal(10**9), "f"))
    event_view = {"id_namespace": "moviodds", "id": fixture,
        "event_version": digest(event), "version_kind": "OBSERVED_CATALOG_OBJECT_SHA256",
        "home": event["home"], "away": event["away"], "starts_at": event["kickoff_utc"],
        "in_play": event["in_play"], "source_pointer": "/fixtures/" + str(catalog["fixtures"].index(event)),
        "canonical_candidate": None if candidate is None else {"namespace": "espn", "id": candidate["id"],
            "starts_at": candidate["date"], "home_id": candidate["home_id"], "away_id": candidate["away_id"],
            "roster_season": candidate["season"], "source_pointer": "/csv/rows/" + str(schedule.index(candidate))},
        "start_difference_seconds": delta,
        "forecast_match_status": "NOT_MATCHED" if candidate is None else
            ("CANONICAL_CANDIDATE_ONLY" if delta == 0 else "BLOCKED_EVENT_START_DISAGREEMENT")}
    seen, observed, quarter, parsed, rows, diagnostics, games = set(), Counter(), Counter(), Counter(), [], Counter(), []
    for index, q in enumerate(lexical["quotes"]):
        require(type(q) is dict and q.get("fixture_id") == fixture
                and all(_id(q.get(k)) for k in ["group_id", "market_id", "sel_id"])
                and _text(q.get("group_name")),
                "Quote lacks exact fixture/selection identity")
        identity = tuple(q[k] for k in ["group_id", "market_id", "sel_id"])
        require(identity not in seen, "Duplicate native selection tuple"); seen.add(identity)
        price = _price(q)
        require(_clock(q["ts"]) <= _clock(snapshot["server_time"]), "Future price change")
        require(type(q.get("suspended", False)) is bool, "Invalid suspension status")
        group = snapshot["group_status"].get(q["group_id"])
        require(type(group) is dict and type(group.get("stale", False)) is bool
                and _clock(group["polled_at"]) <= _clock(snapshot["server_time"]),
                "Missing, future or invalid exact-market confirmation")
        group_age = (_clock(snapshot["server_time"]) - _clock(group["polled_at"])) / 10**9
        available = not q.get("suspended", False) and not group.get("stale", False) and group_age <= 1800
        g = GROUPS.get(q["group_id"])
        if g is None:
            if q["group_id"] in QUARTERS:
                expected, code = QUARTERS[q["group_id"]]
                require(q["group_name"] == expected, "Conflicting quarter market name")
                quarter[code] += 1
            elif q["group_id"] == "1453":
                require(q["group_name"] == "Game", "Conflicting game market name")
                games.append({"selection_id": q["sel_id"], "market_id": q["market_id"],
                    "market": q.get("line"), "side": q.get("side"), "label": q.get("label"),
                    "handicap": q.get("handicap"), "odds_decimal_as_supplied": price,
                    "source_pointer": "/quotes/" + str(index), "market_polled_at": group["polled_at"],
                    "available_at_capture": available})
            else:
                diagnostics["OTHER_MARKET_GROUP"] += 1
            continue
        expected, category = g
        require(q["group_name"] == expected and "period" not in q,
                "Group identity/period contradicts reviewed full-game market")
        observed[category] += 1
        require(_text(q.get("line")) and _text(q.get("side")), "Player label/selection missing")
        require(q.get("n2") is None or _text(q["n2"]), "Invalid literal player-team label")
        affiliations = [] if candidate is None else [r for r in roster
            if r["display_name"] == q["line"] and r["season"] == candidate["season"]
            and r["team_id"] in {candidate["home_id"], candidate["away_id"]}
            and r["team_abbreviation"] + " " + (candidate["home_name"] if r["team_id"] == candidate["home_id"] else candidate["away_name"]) == q.get("n2")]
        if len(affiliations) == 1:
            require(_id(affiliations[0]["athlete_id"]), "Missing canonical player identity")
        canonical_player = None if len(affiliations) != 1 else {
            "namespace": "espn", "id": affiliations[0]["athlete_id"], "name": affiliations[0]["display_name"],
            "team_id": affiliations[0]["team_id"],
            "opponent_id": candidate["away_id"] if affiliations[0]["team_id"] == candidate["home_id"] else candidate["home_id"],
            "source_pointer": "/csv/rows/" + str(roster.index(affiliations[0]))}
        binary = category in {"DD", "TD"} and q["side"] in {"Yes", "No"}
        gaps = ([] if canonical_player else ["CANONICAL_PLAYER_AFFILIATION_UNVERIFIED"])
        if event["in_play"] or _clock(evidence["snapshot"]["observed_at"]) >= _clock(event["kickoff_utc"]):
            gaps.append("NOT_A_VERIFIED_PREGAME_CAPTURE")
        if not binary:
            gaps.append("NUMERIC_SELECTION_OPERATOR_UNVERIFIED")
        if not available:
            gaps.append("SUSPENDED_OR_UNCONFIRMED_MARKET")
        parsed[category] += 1
        rows.append({"category": category, "units": UNITS[category], "player_label": q["line"],
            "canonical_player": canonical_player, "native_player_id": None,
            "source_team_label": q.get("n2"), "source_selection": {"group_id": q["group_id"],
                "market_id": q["market_id"], "selection_id": q["sel_id"], "label": q["side"]},
            "predicate": None if not binary else {"kind": "BOOLEAN_STAT_ACHIEVEMENT", "selection": q["side"],
                "at_least_ten_in_categories": 2 if category == "DD" else 3,
                "primitive_categories": ["PTS", "REB", "AST", "BLK", "STL"]},
            "period": "full_game", "overtime": "includes_overtime",
            "variant": "standard_binary_player_achievement" if binary else "numeric_ladder_operator_unverified",
            "price": {"kind": "sportsbook_decimal", "value": price, "fractional_as_supplied": q.get("odds_frac"),
                "status": "PRICE_UNAVAILABLE" if price is None else
                    ("OBSERVED_PRICE_NOT_QUALIFIED" if available and Decimal(price) > 1 else "UNAVAILABLE_AT_CAPTURE")},
            "source_pointer": "/quotes/" + str(index), "price_changed_at": q["ts"],
            "market_polled_at": group["polled_at"], "available_at_capture": available,
            "gaps": gaps, "semantic_status": "COMPLETE_LOCAL" if not gaps else "INCOMPLETE",
            "ticket_eligible": False})
    # Full inventory is measured before a declared, bounded preview selection.
    # Prefer complete examples; retain original order among equal status.
    display = sorted(enumerate(rows), key=lambda item: (bool(item[1]["gaps"]), item[0]))[:MAX_DISPLAY]
    body = {"schema_version": SCHEMA, "scope": "LOCAL_REVIEW_ONLY", "evidence_lane": evidence_lane,
        "source": "MoviOdds", "venue_as_declared_by_source": "bet365", "product": "standard basketball player markets",
        "normalized_at": normalized_at, "observed_at": evidence["snapshot"]["observed_at"],
        "knowledge_observed_at": max((e["observed_at"] for e in evidence.values()), key=_clock),
        "publisher_server_time": snapshot["server_time"], "event": event_view, "evidence": evidence,
        "rules": {"extractor": "bet365-static-rules-text-v1", "text_sha256": hashlib.sha256(text).hexdigest(),
            "text_bytes": len(text), "passages": passages,
            "applicability": "MoviOdds declares exclusively bet365 prices; ordinary full-game NBA DD/TD Yes/No, no quarter/first-basket/promotion exception applied.",
            "jurisdiction": "NOT_SUPPLIED_BY_FEED", "financial_settlement": "NOT_IMPLEMENTED_OR_QUALIFIED"},
        "counts": {"source_selections": len(snapshot["quotes"]), "full_game_player_selections": sum(observed.values()),
            "parsed_player_selections": len(rows), "verified_player_selections": sum(r["canonical_player"] is not None for r in rows),
            "complete_local_contracts": sum(not r["gaps"] for r in rows), "displayed": len(display),
            "game_selections": len(games), "quarter_player_selections": sum(quarter.values()),
            "other_selections": sum(diagnostics.values())},
        "category_inventory": {c: {"observed": observed[c], "parsed": parsed[c], "complete": sum(r["category"] == c and not r["gaps"] for r in rows),
            "status": "OBSERVED_IN_SAMPLE" if observed[c] else "UNOBSERVED_IN_SAMPLE"} for c in UNITS},
        "quarter_category_inventory": dict(quarter), "diagnostics": dict(diagnostics),
        "selection": {"limit": MAX_DISPLAY, "ordering": "COMPLETE_FIRST_THEN_ORIGINAL_SOURCE_ORDER"},
        "observations": [row for _, row in display], "game_lines": games,
        "limitations": ["Snapshot only; not a current live board or installed collector.",
            "No native permanent player ID is supplied; canonical crosswalk uses retained SportsDataverse ESPN-derived roster.",
            "Numeric ladder labels alone do not establish >=, >, over/under or push semantics.",
            "Canonical schedule candidate and provider start remain separate; no fuzzy forecast match.",
            "Publisher invitation covers bounded private read/cache/replay; public derived-offer admission is separate.",
            "No executable quote, EV, minutes estimate, blowout probability or qualified ticket is created."],
        "public_admission": False, "ticket_eligibility": False, "qualification": "UNAVAILABLE"}
    require(body["counts"]["source_selections"] == sum(observed.values()) + sum(quarter.values()) + len(games) + sum(diagnostics.values()),
            "Inventory silently loses source selections")
    body["review_id"] = digest(body)
    require(len(canonical(body)) <= MAX_REVIEW_BYTES, "Private review exceeds existing encoded ceiling")
    return body


@_strict
def replay_review(review, assets, *, now, allow_synthetic=False):
    """Recovery acknowledges original bytes AND meaning; never repairs a record."""
    require(type(review) is dict and review.get("schema_version") == SCHEMA, "Unsupported review")
    require(review.get("evidence_lane") == "ACTUAL_SOURCE_REPLAY" or
            (allow_synthetic and review.get("evidence_lane") == "SYNTHETIC_TEST"), "Unadmitted synthetic review")
    require(_clock(review["normalized_at"]) <= _clock(stamp(utc(now))), "Future review clock")
    expected = build_review(assets, fixture=review["event"]["id"], normalized_at=review["normalized_at"],
                            evidence_lane=review["evidence_lane"])
    require(canonical(review) == canonical(expected), "Review differs from original source replay")
    return {"schema_version": "nba-moviodds-replay-v1", "review_id": review["review_id"],
            "verified_at": stamp(utc(now)), "originals_replayed": len(assets),
            "durable_remote_archive_verified": False, "public_admission": False}


def load_assets(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "Invalid original directory")
    from .player_line_review import MAX_PACKAGE_BYTES, MAX_PACKAGE_FILES
    entries = list(directory.iterdir())
    require(len(entries) <= MAX_PACKAGE_FILES
            and all(p.is_file() and not p.is_symlink() for p in entries)
            and sum(p.stat().st_size for p in entries) <= MAX_PACKAGE_BYTES,
            "Original package exceeds unchanged file/byte ceilings or contains unsafe entries")
    return {key: {"raw": _bounded_bytes(directory / (key + ".body"), MAX_RAW_BYTES),
                  "metadata_raw": _bounded_bytes(directory / (key + ".metadata.json"), 256 * 1024)} for key in URLS}


def prepare_review(source, destination, *, fixture, now, evidence_lane="ACTUAL_SOURCE_REPLAY"):
    # Use the existing bounded, fsynced, create-only private package helpers.
    from .player_line_review import _create, _private_directory
    assets = load_assets(source)
    destination = _private_directory(Path(destination), Path(__file__).resolve().parents[1])
    signature = {key: {k: hashlib.sha256(v).hexdigest() for k, v in value.items()} for key, value in assets.items()}
    intent_path = destination / "review-intent.json"
    if intent_path.exists():
        intent = _decode(_bounded_bytes(intent_path, MAX_REVIEW_BYTES))
        require(type(intent) is dict and set(intent) == {"fixture", "originals", "normalized_at"}
                and intent["fixture"] == fixture and intent["originals"] == signature
                and _clock(intent["normalized_at"]) <= _clock(stamp(utc(now))), "Retry cannot rebind inputs or original clocks")
    else:
        intent = {"fixture": fixture, "originals": signature, "normalized_at": stamp(utc(now))}
    review = build_review(assets, fixture=fixture, normalized_at=intent["normalized_at"], evidence_lane=evidence_lane)
    _create(destination, intent_path.name, canonical(intent), maximum=MAX_REVIEW_BYTES)
    for key, asset in assets.items():
        _create(destination, key + ".body", asset["raw"], maximum=MAX_RAW_BYTES)
        _create(destination, key + ".metadata.json", asset["metadata_raw"], maximum=256 * 1024)
    _create(destination, "review.json", canonical(review), maximum=MAX_REVIEW_BYTES)
    return {"review_id": review["review_id"], "counts": review["counts"], "source_http_requests": 0,
            "public_admission": False, "durable_remote_archive_verified": False}


def verify_package(directory, *, now, allow_synthetic=False):
    directory = Path(directory)
    assets = load_assets(directory)
    review = _decode(_bounded_bytes(directory / "review.json", MAX_REVIEW_BYTES))
    intent = _decode(_bounded_bytes(directory / "review-intent.json", MAX_REVIEW_BYTES))
    signature = {key: {k: hashlib.sha256(v).hexdigest() for k, v in value.items()} for key, value in assets.items()}
    require(intent == {"fixture": review["event"]["id"], "originals": signature,
                       "normalized_at": review["normalized_at"]}, "Recovery intent, bytes or original normalization clock differ")
    return replay_review(review, assets, now=now, allow_synthetic=allow_synthetic)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--originals", type=Path)
    choice.add_argument("--verify", type=Path)
    parser.add_argument("--fixture")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(); now = datetime.now(timezone.utc)
    if args.verify:
        require(args.output is None and args.fixture is None, "Read-only recovery cannot override identity/output")
        result = verify_package(args.verify, now=now)
    else:
        require(args.fixture is not None and args.output is not None, "Fixture and private output required")
        result = prepare_review(args.originals, args.output, fixture=args.fixture, now=now)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
