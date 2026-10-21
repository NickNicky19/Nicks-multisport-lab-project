"""Offline inspection of retained ESPN NBA bytes; no HTTP, credentials or keys.

This is a partial-observation parser, not a collector or publication admission.
Source-use permission and source authenticity are not established by a checksum.
No source row is promoted to an executable contract by this inspector.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .integrity import (IntegrityError, _bounded_bytes, _decode, digest,
                        load_json, stamp, utc, write_receipt)
from .offer_import import REQUIRED_MARKETS

VERSION = "nba-espn-original-inspection-1"
ALL_CATEGORIES = (*REQUIRED_MARKETS, "PA")
MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 10000
# Primary labels from OFFER-PILOT-003's summary, plus the expected Total Turnovers
# label tested only synthetically (TOV was absent there). Milestones and quarters
# remain unmapped: a statistic match does not establish a variant.
ESPN_LABELS = {
    "Total Points": "PTS", "Total Points, Rebounds, and Assists": "PRA",
    "Total Rebounds": "REB", "Total 3-Point Field Goals": "3PM",
    "Total Assists": "AST", "Total Assists and Rebounds": "RA",
    "Total Points and Rebounds": "PR", "Total Turnovers": "TOV",
    "To Record a Triple Double": "TD", "To Record a Double Double": "DD",
    "Total Blocks": "BLK", "Total Steals": "STL",
    "Total Steals and Blocks": "BLK+STL", "Total Points and Assists": "PA",
}
ROOT = "/v2/sports/basketball/leagues/nba/"


def _path(url: str, *, transport: bool = False) -> str:
    if type(url) is not str:
        raise IntegrityError("Missing source URL/reference")
    parsed = urlsplit(url)
    if (parsed.scheme not in ({"https"} if transport else {"http", "https"})
            or parsed.netloc != "sports.core.api.espn.com" or parsed.fragment):
        raise IntegrityError("Expected exact ESPN core host and permitted scheme")
    return parsed.path


def _original(body: bytes, metadata: dict, imported_at: datetime) -> tuple[dict, dict]:
    if type(body) is not bytes or len(body) > MAX_BYTES or type(metadata) is not dict:
        raise IntegrityError("Expected bounded original bytes and capture metadata")
    fingerprint = hashlib.sha256(body).hexdigest()
    if (type(metadata.get("raw_bytes")) is not int or metadata["raw_bytes"] != len(body)
            or metadata.get("raw_sha256") != fingerprint):
        raise IntegrityError("Original byte count or SHA256 mismatch")
    source_path = _path(metadata.get("url"), transport=True)
    if _path(metadata.get("final_url"), transport=True) != source_path:
        raise IntegrityError("Capture redirected to a different resource")
    if (type(metadata.get("http_status")) is not int or metadata["http_status"] != 200
            or "json" not in str(metadata.get("content_type", "")).lower()):
        raise IntegrityError("Capture was not an HTTP200 JSON response; never treat as empty")
    started, observed, imported = (utc(metadata["request_started_at"]),
                                   utc(metadata["observed_at"]), utc(imported_at))
    if not started <= observed <= imported:
        raise IntegrityError("Capture/import clocks are inconsistent")
    data = _decode(body)
    if type(data) is not dict:
        raise IntegrityError("Expected ESPN JSON object")
    return data, {"source_url": metadata["url"], "final_url": metadata["final_url"],
                  "raw_sha256": fingerprint, "raw_bytes": len(body),
                  "capture_metadata_sha256": digest(metadata),
                  "request_started_at": stamp(started), "observed_at": stamp(observed),
                  "imported_at": stamp(imported), "upstream_authenticity_proven": False}


def _ref(row: dict, field: str) -> str | None:
    value = row.get(field)
    return value.get("$ref") if type(value) is dict else None


def _number(value) -> Decimal:
    if isinstance(value, bool) or type(value) not in (str, int, float):
        raise IntegrityError("Invalid threshold")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise IntegrityError("Invalid threshold") from error
    if not result.is_finite():
        raise IntegrityError("Nonfinite threshold")
    return result


def inspect_espn_original(body: bytes, metadata: dict, *, imported_at: datetime,
                          provider_body: bytes | None = None,
                          provider_metadata: dict | None = None) -> dict:
    """Return only source-backed partial observations; never collect or publish.

    Metadata clocks are retained capture assertions. Re-importing old bytes never
    refreshes observation time. A separately captured provider lookup can label
    its exact ID, but does not establish point-in-time identity for an old game.
    """
    data, original = _original(body, metadata, imported_at)
    route = re.fullmatch(ROOT + r"events/(\d+)/competitions/(\d+)/odds/(\d+)/propBets",
                         _path(original["source_url"]))
    if not route or route[1] != route[2]:
        raise IntegrityError("Expected exact inherited NBA event/competition/propBets route")
    event, provider = route[1], route[3]
    attribution = {"data_source": "ESPN", "provider_id": provider, "provider_name": None,
                   "provider_identity_observed_at": None, "point_in_time_identity_proven": False}
    if (provider_body is None) != (provider_metadata is None):
        raise IntegrityError("Provider original and metadata must be supplied together")
    if provider_body is not None:
        lookup, provider_original = _original(provider_body, provider_metadata, imported_at)
        expected = ROOT + "casinos/" + provider
        if (_path(provider_original["source_url"]) != expected
                or lookup.get("id") != provider or _path(lookup.get("$ref")) != expected
                or type(lookup.get("name")) is not str or not lookup["name"].strip()):
            raise IntegrityError("Provider lookup does not bind the captured provider")
        attribution.update(provider_name=lookup["name"],
                           provider_identity_observed_at=provider_original["observed_at"],
                           provider_original=provider_original)
    rows = data.get("items")
    if type(rows) is not list or len(rows) > MAX_ROWS:
        raise IntegrityError("Expected bounded items list")
    for field in ("count", "pageIndex", "pageSize", "pageCount"):
        if type(data.get(field)) is not int or data[field] < (0 if field == "count" else 1):
            raise IntegrityError("Invalid pagination metadata")
    if (data["pageIndex"] > data["pageCount"] or len(rows) > data["pageSize"]
            or len(rows) > data["count"]):
        raise IntegrityError("Inconsistent pagination")
    # The strict decoder above rejects duplicate keys/nonfinite numbers. Retain
    # original numeric lexemes separately: binary floats must not round a line
    # or price. The raw body hash remains the authoritative original reference.
    lexical_rows = json.loads(body, parse_float=str, parse_int=str)["items"]
    coverage = {key: {"observed_player_rows": 0, "parsed_partial_observations": 0,
                      "complete_contracts": 0, "sample_status": "UNOBSERVED_IN_SAMPLE",
                      "label_parser": "SUPPORTED_EXACT_PRIMARY_LABEL_ONLY",
                      "label_basis": "EXPECTED_SYNTHETIC_ONLY" if key == "TOV" else
                                     "HISTORICAL_SUMMARY_NOT_RAW_PLAYER_REPLAY"}
                for key in ALL_CATEGORIES}
    observations, diagnostics = [], []
    nonplayer = Counter()
    for index, row in enumerate(rows):
        try:
            if type(row) is not dict:
                raise IntegrityError("Expected object row")
            competition = ROOT + f"events/{event}/competitions/{event}"
            if (_path(_ref(row, "competition")) != competition
                    or _path(_ref(row, "provider")) != ROOT + "casinos/" + provider):
                raise IntegrityError("Row event/provider conflicts with capture route")
            label = row.get("type", {}).get("name")
            if type(label) is not str or not label:
                raise IntegrityError("Missing market label")
            athlete_ref, team_ref = _ref(row, "athlete"), _ref(row, "team")
            if athlete_ref is None:
                if "athlete" in row:
                    raise IntegrityError("Malformed athlete reference")
                # Missing identity alone is not proof of a nonplayer market.
                if label not in {"Team Total Points", "Will There Be Overtime?"}:
                    raise IntegrityError("Unresolved subject: missing athlete reference")
                if label == "Team Total Points" and not re.fullmatch(
                        ROOT + r"(?:seasons/\d+/)?teams/\d+", _path(team_ref)):
                    raise IntegrityError("Expected NBA team reference for team total")
                nonplayer[label] += 1
                continue
            if team_ref is not None:
                raise IntegrityError("Ambiguous athlete/team subject")
            athlete = re.fullmatch(ROOT + r"(?:seasons/\d+/)?athletes/(\d+)", _path(athlete_ref))
            if not athlete:
                raise IntegrityError("Expected NBA athlete identity")
            category = ESPN_LABELS.get(label)
            if category is not None:
                coverage[category]["observed_player_rows"] += 1
            reasons = ["player_name_unverified", "event_matchup_start_unverified",
                       "side_selection_identity_unverified", "period_unverified",
                       "overtime_unverified", "variant_unverified", "product_unverified",
                       "market_status_unverified", "settlement_rules_unverified"]
            if category is None:
                reasons.append("unsupported_market_label_or_variant")
            lexical_row = lexical_rows[index]
            current = lexical_row.get("current", {}).get("target", {}).get("value")
            total = lexical_row.get("odds", {}).get("total", {}).get("value")
            threshold = current if current is not None else total
            if threshold is None:
                reasons.append("threshold_unverified")
            else:
                _number(threshold)
                if current is not None and total is not None and _number(current) != _number(total):
                    reasons.append("contradictory_threshold_fields")
                    threshold = None
            prices = {kind: lexical_row.get("odds", {}).get(kind, {}).get("value")
                      for kind in ("american", "decimal", "fraction")}
            prices = {kind: value for kind, value in prices.items() if value is not None}
            updated = row.get("lastUpdated")
            if updated is not None:
                updated = stamp(utc(updated))
                if utc(updated) > utc(original["observed_at"]):
                    reasons.append("source_update_later_than_observation")
            else:
                reasons.append("source_update_clock_unavailable")
            observations.append({
                "row_index": index, "source_row_sha256": digest(row),
                "source_row_hash_format": "sha256-canonical-decoded-json-v1",
                "original_body_sha256": original["raw_sha256"],
                "league": "NBA", "player_id_namespace": "espn", "player_id": athlete[1],
                "player_name": None, "event_id_namespace": "espn", "event_id": event,
                "category": category, "source_market_label": label,
                "source_market_type_id": row.get("type", {}).get("id"),
                "threshold_source_value": threshold, "threshold_operator": None,
                "side": None, "period": None, "overtime": None, "variant": None,
                "venue": attribution["provider_name"], "product": None,
                "prices_as_supplied": prices,
                "numeric_representation": "original-json-number-lexemes-as-text",
                "price_status": "SUPPLIED_UNBOUND_TO_SIDE" if prices else "PRICE_UNAVAILABLE",
                "observed_at": original["observed_at"], "source_updated_at": updated,
                "unresolved": reasons, "contract": None, "quote": None,
                "qualified": False, "publication_admitted": False,
            })
            if category is not None:
                coverage[category]["parsed_partial_observations"] += 1
        except (IntegrityError, KeyError, TypeError, AttributeError, ValueError) as error:
            diagnostics.append({"row_index": index, "reason": str(error)})
    for counts in coverage.values():
        observed, parsed = counts["observed_player_rows"], counts["parsed_partial_observations"]
        counts["parse_rejected_rows"] = observed - parsed
        if observed:
            counts["sample_status"] = ("OBSERVED_PARSED_PARTIAL" if parsed == observed else
                                       "OBSERVED_WITH_PARSE_REJECTIONS" if parsed else
                                       "OBSERVED_PARSE_REJECTED")
    return {"schema_version": "nba-keyless-offer-inspection-v1", "parser_version": VERSION,
            "original": original, "attribution": attribution, "observations": observations,
            "diagnostics": diagnostics, "nonplayer_label_counts": dict(nonplayer),
            "category_coverage": coverage, "declared_items": data["count"],
            "page_index": data["pageIndex"], "declared_pages": data["pageCount"],
            "all_pages_present": data["pageCount"] == data["pageIndex"] == 1
                                 and len(rows) == data["count"],
            "complete_player_contracts": 0, "usable_quotes": 0,
            "rights_status": "NOT_ESTABLISHED_BY_PARSER",
            "public_offer_publication_performed": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--provider-raw")
    parser.add_argument("--provider-metadata")
    parser.add_argument("--receipt", required=True, help="Local, create-only; never a site export")
    args = parser.parse_args()
    report = inspect_espn_original(
        _bounded_bytes(Path(args.raw), MAX_BYTES), load_json(args.metadata),
        imported_at=datetime.now(timezone.utc),
        provider_body=_bounded_bytes(Path(args.provider_raw), MAX_BYTES) if args.provider_raw else None,
        provider_metadata=load_json(args.provider_metadata) if args.provider_metadata else None)
    created = write_receipt(args.receipt, report)
    print(f"{len(report['observations'])} player observations; "
          f"{sum(report['nonplayer_label_counts'].values())} nonplayer rows; "
          f"{len(report['diagnostics'])} diagnostics; complete_contracts=0; created={created}")


if __name__ == "__main__":
    main()
