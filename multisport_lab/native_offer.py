"""Native-event Boolean NBA offers, separate from publication and forecast joins.

This bounded, offline representation does not change offer-v1 or the external
market-v2 contract. A source's complete DD/TD selection need not invent a 0.5
line or an exact cross-provider event match. Original-byte replay is a separate
mandatory evidence check; a digest alone is never source authentication.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from functools import wraps
import re

from .integrity import IntegrityError, canonical, digest, stamp, utc
from .moviodds_offer import (RULE_PASSAGES, SCHEMA as REVIEW_SCHEMA, URLS,
    _clock, _id, _schedule_clock, _text, build_review, replay_review)
from .offer_import import UNITS
from .native_offer_admissions import REVIEWED_OFFERS as _PUBLIC_REVIEWED_OFFER_IDS

SCHEMA = "nba-native-player-offer-v2"
MAX_OFFER_BYTES = 32 * 1024
MAX_ASSET_BYTES = 256 * 1024
MAX_OFFERS = 32
# An explicit reviewed code change is required to admit exact source records.
# This package admits none; caller-supplied flags/registries cannot grant access.
_TOP = set("schema_version offer_id evidence_lane league source venue product original_review_id review_observation_index review_normalized_at normalized_at observed_at knowledge_observed_at publisher_server_time event category units player_name native_player_id canonical_player source_team_label selection predicate period overtime variant price price_changed_at market_polled_at source_pointer evidence rules category_inventory semantic_status availability public_admission ticket_eligible qualification".split())
_EVENT = set("id_namespace id event_version version_kind home away starts_at in_play source_pointer canonical_candidate start_difference_seconds forecast_match_status".split())
_EVIDENCE = set("url raw_sha256 raw_bytes metadata_sha256 request_started_at observed_at content_type retrieval_basis".split())
_RULE_SCOPE = "MoviOdds declares exclusively bet365 prices; ordinary full-game NBA DD/TD Yes/No, no quarter/first-basket/promotion exception applied."


def _require(condition, message):
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
            raise IntegrityError("Malformed native NBA offer: " + str(error)) from error
    return checked


def _fields(value, names):
    return type(value) is dict and set(value) == set(names)


def _sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _count(value, maximum=10000):
    return type(value) is int and 0 <= value <= maximum


def _pointer(value, kind, maximum):
    return (type(value) is str and re.fullmatch("/" + kind + r"/(?:0|[1-9][0-9]*)", value)
            is not None and int(value.rsplit("/", 1)[1]) < maximum)


def _now(now):
    value = now if type(now) is str else stamp(utc(now))
    _clock(value)
    return value


def _validate_body(offer, now):
    _require(_fields(offer, _TOP) and offer["schema_version"] == SCHEMA
        and offer["evidence_lane"] in {"ACTUAL_SOURCE_REPLAY", "SYNTHETIC_TEST"}
        and offer["league"] == "NBA" and offer["source"] == "MoviOdds"
        and offer["venue"] == "bet365" and offer["product"] == "standard basketball player markets"
        and _sha(offer["original_review_id"]) and _sha(offer["offer_id"])
        and _count(offer["review_observation_index"], 7)
        and offer["semantic_status"] == "COMPLETE_NATIVE_SOURCE_CONTRACT"
        and offer["availability"] == "OBSERVED_SNAPSHOT_NOT_CURRENT"
        and offer["public_admission"] is False and offer["ticket_eligible"] is False
        and offer["qualification"] == "UNAVAILABLE", "Unsupported native offer or self-granted eligibility")
    observed, knowledge, server = (_clock(offer[k]) for k in
        ["observed_at", "knowledge_observed_at", "publisher_server_time"])
    _require(server <= observed <= knowledge <= _clock(offer["review_normalized_at"])
        <= _clock(offer["normalized_at"]) <= _clock(_now(now)), "Native offer clocks disagree")
    event = offer["event"]
    _require(_fields(event, _EVENT) and event["id_namespace"] == "moviodds" and _id(event["id"])
        and _sha(event["event_version"]) and event["version_kind"] == "OBSERVED_CATALOG_OBJECT_SHA256"
        and _text(event["home"]) and _text(event["away"]) and event["home"] != event["away"]
        and event["in_play"] is False and _pointer(event["source_pointer"], "fixtures", 5000)
        and observed < _clock(event["starts_at"]), "Native event is missing or was not pregame at capture")
    candidate = event["canonical_candidate"]
    _require(_fields(candidate, "namespace id starts_at home_id away_id roster_season source_pointer".split())
        and candidate["namespace"] == "espn" and all(_id(candidate[k]) for k in ["id", "home_id", "away_id"])
        and candidate["home_id"] != candidate["away_id"]
        and type(candidate["roster_season"]) is str and re.fullmatch(r"20[0-9]{2}", candidate["roster_season"])
        and _pointer(candidate["source_pointer"], "csv/rows", 5000), "Invalid separate canonical event candidate")
    delta_ns = _clock(event["starts_at"]) - _schedule_clock(candidate["starts_at"])
    delta = delta_ns // 10**9 if delta_ns % 10**9 == 0 else format(Decimal(delta_ns) / Decimal(10**9), "f")
    _require(type(event["start_difference_seconds"]) is type(delta)
        and event["start_difference_seconds"] == delta
        and candidate["starts_at"][:10] == event["starts_at"][:10]
        and event["forecast_match_status"] == ("CANONICAL_CANDIDATE_ONLY" if delta_ns == 0 else "BLOCKED_EVENT_START_DISAGREEMENT"),
        "A native source contract cannot erase or resolve the canonical event conflict")
    player = offer["canonical_player"]
    _require(offer["native_player_id"] is None and _text(offer["player_name"])
        and _fields(player, "namespace id name team_id opponent_id source_pointer".split())
        and player["namespace"] == "espn" and player["name"] == offer["player_name"]
        and all(_id(player[k]) for k in ["id", "team_id", "opponent_id"])
        and player["team_id"] != player["opponent_id"]
        and {player["team_id"], player["opponent_id"]} == {candidate["home_id"], candidate["away_id"]}
        and _pointer(player["source_pointer"], "csv/rows", 5000)
        and offer["source_team_label"] == (event["home"] if player["team_id"] == candidate["home_id"] else event["away"]),
        "Player identity/affiliation must retain its external canonical crosswalk")
    category, selection = offer["category"], offer["selection"]
    _require(category in {"DD", "TD"} and offer["units"] == UNITS[category]
        and _fields(selection, "group_id market_id selection_id label".split())
        and all(_id(selection[k]) for k in ["group_id", "market_id", "selection_id"])
        and selection["group_id"] == ("181463" if category == "DD" else "181464")
        and selection["label"] in {"Yes", "No"}
        and offer["predicate"] == {"kind": "BOOLEAN_STAT_ACHIEVEMENT", "selection": selection["label"],
            "at_least_ten_in_categories": 2 if category == "DD" else 3,
            "primitive_categories": ["PTS", "REB", "AST", "BLK", "STL"]}
        and type(offer["predicate"]["at_least_ten_in_categories"]) is int
        and offer["period"] == "full_game" and offer["overtime"] == "includes_overtime"
        and offer["variant"] == "standard_binary_player_achievement"
        and _pointer(offer["source_pointer"], "quotes", 10000), "A native Boolean offer must not invent a numerical line or side")
    changed, confirmed = _clock(offer["price_changed_at"]), _clock(offer["market_polled_at"])
    _require(changed <= server and confirmed <= server and server - confirmed <= 1800 * 10**9,
        "Future or stale exact-market source clocks")
    price = offer["price"]
    _require(_fields(price, "kind value fractional_as_supplied status".split())
        and price["kind"] == "sportsbook_decimal"
        and (price["fractional_as_supplied"] is None or _text(price["fractional_as_supplied"], 128)), "Invalid supplied price representation")
    value = price["value"]
    _require(value is None or (type(value) is str and len(value) <= 128
        and re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is not None
        and Decimal(value) <= 1000000), "Invalid supplied decimal price; missing is not zero")
    _require(price["status"] == ("PRICE_UNAVAILABLE" if value is None else
        "OBSERVED_PRICE_NOT_QUALIFIED" if Decimal(value) > 1 else "UNAVAILABLE_AT_CAPTURE"), "Source price status is not qualification")
    evidence = offer["evidence"]
    _require(_fields(evidence, URLS), "Exact seven original evidence references required")
    latest = 0
    for role, item in evidence.items():
        media = {"catalog": {"application/json"}, "snapshot": {"application/json"},
            "api": {"text/html"}, "sports": {"text/html"}, "rules": {"text/html"},
            "roster": {"text/csv", "application/octet-stream"}, "schedule": {"text/csv", "application/octet-stream"}}[role]
        _require(_fields(item, _EVIDENCE) and item["url"] == URLS[role] + (event["id"] if role == "snapshot" else "")
            and _sha(item["raw_sha256"]) and _sha(item["metadata_sha256"])
            and _count(item["raw_bytes"], 2 * 1024 * 1024) and item["raw_bytes"] > 0
            and item["content_type"] in media and item["retrieval_basis"] == (
                "RETAINED_RELEASE_REDIRECT_CHAIN" if role in {"roster", "schedule"} else "DIRECT_COMPLETE_HTTP_RESPONSE"), "Invalid original source binding")
        capture = _clock(item["observed_at"])
        _require(_clock(item["request_started_at"]) <= capture <= _clock(offer["review_normalized_at"]), "Original evidence clocks disagree")
        latest = max(latest, capture)
    _require(latest == knowledge and evidence["snapshot"]["observed_at"] == offer["observed_at"], "Later supporting evidence cannot refresh capture")
    rules = offer["rules"]
    _require(_fields(rules, "extractor text_sha256 text_bytes passages applicability jurisdiction financial_settlement".split())
        and rules["extractor"] == "bet365-static-rules-text-v1" and _sha(rules["text_sha256"])
        and _count(rules["text_bytes"], 512 * 1024) and rules["text_bytes"] > 0
        and rules["applicability"] == _RULE_SCOPE and rules["jurisdiction"] == "NOT_SUPPLIED_BY_FEED"
        and rules["financial_settlement"] == "NOT_IMPLEMENTED_OR_QUALIFIED"
        and _fields(rules["passages"], RULE_PASSAGES), "Incomplete or inapplicable rule set")
    spans = []
    for role, quote in RULE_PASSAGES.items():
        passage = rules["passages"][role]
        _require(_fields(passage, ["start", "end", "source_value"])
            and _count(passage["start"], rules["text_bytes"]) and _count(passage["end"], rules["text_bytes"])
            and passage["source_value"] == quote and passage["end"] - passage["start"] == len(quote.encode()), "Invalid exact rule passage binding")
        spans.append((passage["start"], passage["end"]))
    spans.sort()
    _require(all(spans[i - 1][1] <= spans[i][0] for i in range(1, len(spans))), "Rule passages overlap")
    inventory = offer["category_inventory"]
    _require(_fields(inventory, UNITS), "All thirteen categories plus PA must remain inventoried")
    for code, item in inventory.items():
        _require(_fields(item, "observed parsed complete status".split()) and all(_count(item[k]) for k in ["observed", "parsed", "complete"])
            and item["observed"] == item["parsed"] >= item["complete"]
            and (code in {"DD", "TD"} or item["complete"] == 0)
            and item["status"] == ("OBSERVED_IN_SAMPLE" if item["observed"] else "UNOBSERVED_IN_SAMPLE"), "Invalid full-category source inventory")
    _require(sum(item["observed"] for item in inventory.values()) <= 10000 and inventory[category]["complete"] > 0,
        "Source inventory cannot support this complete selection")
    _require(len(canonical(offer)) <= MAX_OFFER_BYTES, "Native offer exceeds 32-KiB encoded ceiling")
    return offer


@_strict
def validate_native_offer(offer, *, now):
    """Validate meaning and decoded-JSON identity; does not authenticate a source."""
    _validate_body(offer, now)
    _require(offer["offer_id"] == digest({k: v for k, v in offer.items() if k != "offer_id"}), "Native offer digest mismatch")
    return offer


@_strict
def build_native_offer(review, index, *, now):
    """Create a separately versioned semantic record from a complete local row.

    This does not promote the original private review or authenticate raw bytes.
    Use replay_native_offer against exact originals before acknowledging recovery.
    """
    _require(type(review) is dict and review.get("schema_version") == REVIEW_SCHEMA
        and review.get("scope") == "LOCAL_REVIEW_ONLY" and review.get("public_admission") is False
        and review.get("ticket_eligibility") is False and review.get("qualification") == "UNAVAILABLE"
        and _sha(review.get("review_id"))
        and review["review_id"] == digest({k: v for k, v in review.items() if k != "review_id"})
        and len(canonical(review)) <= 256 * 1024 and type(review.get("observations")) is list
        and 1 <= len(review["observations"]) <= 8 and _count(index, len(review["observations"]) - 1), "Invalid sealed source review or observation index")
    row = review["observations"][index]
    _require(type(row) is dict and row.get("semantic_status") == "COMPLETE_LOCAL"
        and row.get("gaps") == [] and row.get("available_at_capture") is True and row.get("ticket_eligible") is False,
        "Only complete, pregame source semantic observations can be normalized")
    offer = {"schema_version": SCHEMA, "offer_id": "0" * 64,
        "evidence_lane": review["evidence_lane"], "league": "NBA", "source": review["source"],
        "venue": review["venue_as_declared_by_source"], "product": review["product"],
        "original_review_id": review["review_id"], "review_observation_index": index,
        "review_normalized_at": review["normalized_at"], "normalized_at": _now(now),
        "observed_at": review["observed_at"], "knowledge_observed_at": review["knowledge_observed_at"],
        "publisher_server_time": review["publisher_server_time"], "event": deepcopy(review["event"]),
        "category": row["category"], "units": row["units"], "player_name": row["player_label"],
        "native_player_id": row["native_player_id"], "canonical_player": deepcopy(row["canonical_player"]),
        "source_team_label": row["source_team_label"], "selection": deepcopy(row["source_selection"]),
        **{k: deepcopy(row[k]) for k in ["predicate", "period", "overtime", "variant", "price", "price_changed_at", "market_polled_at", "source_pointer"]},
        "evidence": deepcopy(review["evidence"]), "rules": deepcopy(review["rules"]),
        "category_inventory": deepcopy(review["category_inventory"]),
        "semantic_status": "COMPLETE_NATIVE_SOURCE_CONTRACT", "availability": "OBSERVED_SNAPSHOT_NOT_CURRENT",
        "public_admission": False, "ticket_eligible": False, "qualification": "UNAVAILABLE"}
    _validate_body(offer, now)
    offer["offer_id"] = digest({k: v for k, v in offer.items() if k != "offer_id"})
    return validate_native_offer(offer, now=now)


@_strict
def replay_native_offer(offer, assets, *, now, allow_synthetic=False):
    """Rebuild the original review and this derivation without mutating either."""
    validate_native_offer(offer, now=now)
    review = build_review(assets, fixture=offer["event"]["id"], normalized_at=offer["review_normalized_at"],
        evidence_lane=offer["evidence_lane"])
    replay_review(review, assets, now=now, allow_synthetic=allow_synthetic)
    expected = build_native_offer(review, offer["review_observation_index"], now=offer["normalized_at"])
    _require(canonical(offer) == canonical(expected), "Native offer differs from exact original source replay")
    return {"schema_version": "nba-native-offer-replay-v1", "offer_id": offer["offer_id"],
        "original_review_id": review["review_id"], "verified_at": _now(now), "originals_replayed": len(assets),
        "durable_remote_archive_verified": False, "public_admission": False, "ticket_eligible": False}


@_strict
def validate_native_offers(offers, *, now):
    _require(type(offers) is list and len(offers) <= MAX_OFFERS
        and len(canonical(offers)) <= MAX_ASSET_BYTES, "Native offer asset exceeds unchanged 32-offer/256-KiB limits")
    for offer in offers:
        validate_native_offer(offer, now=now)
    _require(len({offer["offer_id"] for offer in offers}) == len(offers), "Duplicate native offer IDs")
    identities = [(o["source"], o["event"]["id"], *(o["selection"][k] for k in ["group_id", "market_id", "selection_id"])) for o in offers]
    _require(len(set(identities)) == len(identities), "Duplicate native selection identities")
    return offers


def native_offer_publicly_admitted(offer):
    """Only an internally reviewed exact-record registry can grant publication."""
    return (type(offer) is dict and offer.get("evidence_lane") == "ACTUAL_SOURCE_REPLAY"
        and offer.get("offer_id") in _PUBLIC_REVIEWED_OFFER_IDS)
