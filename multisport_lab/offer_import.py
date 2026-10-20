"""Bounded, offline NBA offer-capture import. This module never contacts a source.

An importer's permission statement and capture clocks are caller assertions, not
independently verified source rights or prospective publication. Complete records
can yield kernel contracts/quotes; neither construction qualifies a product.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .contracts import PropContract, QuoteObservation
from .integrity import canonical, digest, load_json, stamp, utc, write_receipt

CAPTURE_SCHEMA = "nba-offer-capture-v1"
REPORT_SCHEMA = "nba-offer-import-v1"
PARSER_VERSION = "nba-offer-import-0.3"
MAX_ROWS = 10000
REQUIRED_MARKETS = ("PTS", "PRA", "REB", "3PM", "AST", "RA", "PR", "TOV",
                    "TD", "DD", "BLK", "STL", "BLK+STL")
UNITS = {
    "PTS": "points", "PRA": "stat_sum", "REB": "rebounds",
    "3PM": "made_three_point_field_goals", "AST": "assists", "RA": "stat_sum",
    "PR": "stat_sum", "TOV": "turnovers", "TD": "indicator_0_or_1",
    "DD": "indicator_0_or_1", "BLK": "blocks", "STL": "steals",
    "BLK+STL": "stat_sum", "PA": "stat_sum",
}
# Labels observed in the bounded NBA samples, including OFFER-PILOT-003's four
# sum families. A recognized statistic does not establish period, OT or terms.
# Quarter and other unsupported labels remain diagnostics rather than aliases.
SLEEPER_LABELS = {
    "points": "PTS", "pts_reb_ast": "PRA", "rebounds": "REB",
    "threes_made": "3PM", "assists": "AST", "turnovers": "TOV",
    "double_double": "DD", "blocks": "BLK", "steals": "STL",
    "points_and_assists": "PA", "points_and_rebounds": "PR",
    "rebounds_and_assists": "RA", "blocks_and_steals": "BLK+STL",
}
LANES = {"SYNTHETIC_TEST", "RECONSTRUCTED_RESEARCH", "VERIFIED_ASOF_REPLAY",
         "REAL_TIME_CAPTURED"}


class _SubjectTypeError(ValueError):
    def __init__(self, reason: str, *, option_index: int | None = None):
        super().__init__(reason)
        self.option_index = option_index


def _sleeper_subject_type(row: dict, options: list) -> str:
    """Check every subject type before constructing even one player identity."""
    subject_type = row.get("subject_type")
    if subject_type is None or subject_type == "":
        raise _SubjectTypeError("missing_row_subject_type")
    if type(subject_type) is not str or subject_type not in {"player", "team"}:
        raise _SubjectTypeError("unrecognized_row_subject_type")
    for index, option in enumerate(options):
        if type(option) is not dict:
            raise ValueError("option must be an object")
        option_type = option.get("subject_type")
        if option_type is None or option_type == "":
            raise _SubjectTypeError("missing_option_subject_type", option_index=index)
        if option_type != subject_type:
            raise _SubjectTypeError("row_option_subject_type_mismatch", option_index=index)
    return subject_type


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a nonempty trimmed string")
    return value


def _decimal_text(value: Any, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{name} must be finite numeric text or a number")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{name} must be finite") from None
    if not number.is_finite():
        raise ValueError(f"{name} must be finite")
    return str(number)


def _metadata(capture: dict, imported_at: datetime) -> dict:
    if type(capture) is not dict or capture.get("schema_version") != CAPTURE_SCHEMA:
        raise ValueError("unsupported capture schema")
    observed_at = utc(capture["observed_at"])
    if observed_at > imported_at:
        raise ValueError("capture observation cannot be later than import")
    source = _text(capture["source"], "source")
    source_url = _text(capture["source_url"], "source_url")
    if not source_url.startswith(("https://", "file:")):
        raise ValueError("source_url must identify an HTTPS or local file source")
    authorization = capture.get("authorization")
    if (type(authorization) is not dict
            or authorization.get("scope") != "local_research"
            or authorization.get("public_redistribution") is not False):
        raise ValueError("explicit local research authorization with no public redistribution is required")
    _text(authorization.get("basis"), "authorization basis")
    lane = capture.get("evidence_lane")
    if lane not in LANES:
        raise ValueError("unknown evidence lane")
    pagination = capture.get("pagination")
    if (type(pagination) is not dict or type(pagination.get("complete")) is not bool
            or type(pagination.get("pages_observed")) is not int
            or pagination["pages_observed"] < 1):
        raise ValueError("explicit pagination completeness and positive page count are required")
    status = capture.get("http_status")
    if type(status) is not int or not 100 <= status <= 599:
        raise ValueError("http_status must be an actual HTTP status code")
    _text(capture.get("content_type"), "content_type")
    _text(capture.get("format"), "format")
    canonical(capture)  # Also reject nonfinite values and non-JSON input from Python callers.
    return {
        "source": source, "source_url": source_url,
        "observed_at": stamp(observed_at), "imported_at": stamp(imported_at),
        "evidence_lane": lane, "authorization_assertion": authorization,
        "pagination": pagination, "http_status": status,
        "source_payload_sha256": digest(capture["data"]),
        "hash_format": "sha256-canonical-decoded-json-v1",
        "capture_sha256": digest(capture),
        "capture_assertions_independently_verified": False,
    }


def _sleeper(row: dict, metadata: dict, index: int) -> list[dict]:
    _text(row.get("sport"), "sport")
    if row.get("sport") != "nba":
        return []
    row_id = f"row:{index}"
    options = row.get("options")
    if type(options) is not list or not options:
        raise ValueError("NBA board row requires a nonempty options list")
    if _sleeper_subject_type(row, options) == "team":
        return []  # Recognized nonplayer subject; import_capture records why it is ignored.
    for name in ("game_id", "subject_id", "market_type", "wager_type", "line_type"):
        _text(row.get(name), name)
    updated = row.get("updated_at")
    if updated is not None:
        if type(updated) is not int or updated < 0:
            raise ValueError("updated_at must be Unix milliseconds or null")
        updated = stamp(datetime.fromtimestamp(updated / 1000, timezone.utc))
        if utc(updated) > utc(metadata["observed_at"]):
            raise ValueError("source update is later than capture")
    observations = []
    for option_index, option in enumerate(options):
        if type(option) is not dict:
            raise ValueError("option must be an object")
        # Never splice a line or multiplier from a different event/player/variant.
        for name in ("sport", "game_id", "subject_id", "subject_type", "market_type", "wager_type",
                     "outcome_type", "line_type", "season", "season_type", "game_status"):
            if name not in row or name not in option or option[name] != row[name]:
                raise ValueError(f"row/option identity mismatch: {name}")
        selection_id = _text(option.get("line_id"), "line_id")
        side = option.get("outcome")
        category = SLEEPER_LABELS.get(row["wager_type"])
        reasons = ["period_unverified", "overtime_unverified", "event_start_unknown",
                   "settlement_rules_unverified", "entry_terms_unverified",
                   "provider_identity_crosswalk_unverified"]
        if row.get("status") != "active" or option.get("status") != "active":
            reasons.append("market_not_active")
        if option.get("game_status") != "pre_game":
            reasons.append("not_pregame")
        if category is None:
            reasons.append("unmapped_statistic")
        if side not in {"over", "under"} or row.get("outcome_type") != "over_under":
            reasons.append("unmapped_outcome_type")
        line = _decimal_text(option.get("outcome_value"), "outcome_value")
        multiplier = option.get("payout_multiplier")
        price = None
        if multiplier is not None:
            multiplier = _decimal_text(multiplier, "payout_multiplier")
            if Decimal(multiplier) <= 0:
                raise ValueError("payout_multiplier must exceed zero")
            price = {"value": multiplier, "kind": "pickem_multiplier"}
        else:
            reasons.append("price_missing")
        observations.append({
            "row_id": f"{row_id}/option:{option_index}", "provider": "sleeper",
            "provider_event_id": row["game_id"], "provider_player_id": row["subject_id"],
            "subject_type": "player",
            "provider_market_id": row["market_type"], "provider_selection_id": selection_id,
            "event_id": f"sleeper:nba:event:{row['game_id']}",
            "player_id": f"sleeper:nba:player:{row['subject_id']}",
            "league": "NBA", "stat": category, "raw_stat_label": row["wager_type"],
            "units": UNITS.get(category), "line": line, "side": side,
            "variant": row["line_type"], "venue": "Sleeper", "product": "picks_unverified_variant",
            "period": None, "extra_time_policy": None, "settlement_version": None,
            "event_starts_at": None, "source_updated_at": updated,
            "board_status": row.get("status"), "selection_status": option.get("status"),
            "game_status": option.get("game_status"), "price": price,
            "line_price_evidence_id": metadata["source_payload_sha256"],
            "contract": None, "quote": None, "qualified": False,
            "unavailable_reasons": reasons,
        })
    return observations


def _normalized(row: dict, metadata: dict, index: int) -> list[dict]:
    if type(row["contract"]) is not dict or type(row["contract"].get("line")) is not str:
        raise ValueError("normalized contract line must use exact decimal text")
    contract = PropContract(**row["contract"])
    if contract.sport != "basketball" or contract.league != "NBA":
        raise ValueError("normalized initial import supports basketball / NBA only")
    if contract.stat not in UNITS or contract.units != UNITS[contract.stat]:
        raise ValueError("unknown NBA statistic or incompatible units")
    if contract.period != "full_game" or contract.extra_time_policy not in {
            "includes_overtime", "regulation_only"}:
        raise ValueError("normalized initial import requires explicit full-game/OT semantics")
    for name in ("provider_event_id", "provider_player_id", "provider_market_id",
                 "provider_selection_id", "semantic_evidence_reference"):
        _text(row.get(name), name)
    if row.get("status") not in {"pre_game", "live", "closed", "suspended"}:
        raise ValueError("explicit recognized status required")
    starts_at = stamp(utc(row["event_starts_at"]))
    updated = row.get("source_updated_at")
    if updated is not None:
        updated = stamp(utc(updated))
        if utc(updated) > utc(metadata["observed_at"]):
            raise ValueError("source update is later than capture")
    quote = None
    price = row.get("price")
    if price is not None:
        if type(price) is not dict or set(price) != {"value", "kind"}:
            raise ValueError("price requires only an explicit value and kind")
        if type(price["value"]) is not str:
            raise ValueError("normalized price must use exact decimal text")
        quote = QuoteObservation(
            contract, price["value"], price["kind"], metadata["source"],
            utc(metadata["observed_at"]), utc(starts_at),
            metadata["source_payload_sha256"], metadata["source_payload_sha256"],
            utc(updated) if updated else None, row["status"],
        ).to_record()
    return [{
        "row_id": f"row:{index}", "provider": metadata["source"],
        **{name: row[name] for name in ("provider_event_id", "provider_player_id",
                                      "provider_market_id", "provider_selection_id")},
        "event_id": contract.event_id, "player_id": contract.player_id,
        "league": "NBA", "stat": contract.stat, "units": contract.units,
        "line": str(contract.line), "side": contract.side, "variant": contract.variant,
        "venue": contract.venue, "product": contract.product, "period": contract.period,
        "extra_time_policy": contract.extra_time_policy,
        "settlement_version": contract.settlement_version,
        "event_starts_at": starts_at, "source_updated_at": updated,
        "game_status": row["status"], "price": price,
        "line_price_evidence_id": metadata["source_payload_sha256"],
        "semantic_evidence_reference": row["semantic_evidence_reference"],
        "contract": contract.to_record(), "quote": quote, "qualified": False,
        "unavailable_reasons": (["price_missing"] if price is None else []) +
                               ["product_and_forecast_qualification_not_established_by_import"],
    }]


def import_capture(capture: dict, *, imported_at: datetime) -> dict:
    """Validate a caller-authorized JSON capture without upgrading its evidence.

    Bad capture metadata raises ValueError. Upstream and per-row failures are
    retained in the report and never masquerade as a successful empty board.
    The 8 MiB path loader and MAX_ROWS bound file imports and parsing workload.
    """
    metadata = _metadata(capture, utc(imported_at))
    report = {"schema_version": REPORT_SCHEMA, "parser_version": PARSER_VERSION,
              **metadata, "status": None, "observations": [], "diagnostics": [],
              "coverage": {stat: 0 for stat in REQUIRED_MARKETS}, "qualified": False,
              "input_row_count": None, "other_sport_rows_ignored": 0,
              "nonplayer_rows_ignored": 0, "subject_type_invalid_rows": 0,
              "ignored_rows": []}
    status = metadata["http_status"]
    if status in {401, 403, 429}:
        report["status"] = "blocked_access"
        return report
    if not 200 <= status < 300:
        report["status"] = "upstream_error"
        return report
    data = capture["data"]
    parser = {"sleeper_lines_v1": _sleeper, "normalized_v1": _normalized}.get(capture["format"])
    if parser is _sleeper and capture["source"] != "sleeper":
        raise ValueError("Sleeper parser requires explicit sleeper source identity")
    if (parser is None or "json" not in capture["content_type"].lower()
            or type(data) is not list):
        report["status"] = "parser_failure"
        report["diagnostics"].append({"reason": "unsupported_format_content_type_or_root"})
        return report
    if len(data) > MAX_ROWS:
        raise ValueError("capture exceeds row limit")
    report["input_row_count"] = len(data)
    for index, row in enumerate(data):
        try:
            if type(row) is not dict:
                raise ValueError("row must be an object")
            if parser is _sleeper and isinstance(row.get("sport"), str) and row["sport"] != "nba":
                report["other_sport_rows_ignored"] += 1
            report["observations"].extend(parser(row, metadata, index))
            if parser is _sleeper and row.get("sport") == "nba" and row.get("subject_type") == "team":
                report["nonplayer_rows_ignored"] += 1
                report["ignored_rows"].append({"row_index": index,
                                               "reason": "recognized_nonplayer_subject_type",
                                               "subject_type": "team", "row_sha256": digest(row)})
        except _SubjectTypeError as error:
            report["subject_type_invalid_rows"] += 1
            diagnostic = {"row_index": index, "reason": str(error), "row_sha256": digest(row)}
            if error.option_index is not None:
                diagnostic["option_index"] = error.option_index
            report["diagnostics"].append(diagnostic)
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            report["diagnostics"].append({"row_index": index, "reason": str(error),
                                          "row_sha256": digest(row)})
    observations = report["observations"]
    # A duplicated provider selection is ambiguous even if the values coincide.
    identities = Counter((o["provider"], o["provider_selection_id"]) for o in observations)
    for observation in observations:
        if identities[(observation["provider"], observation["provider_selection_id"])] > 1:
            observation["unavailable_reasons"].append("duplicate_provider_selection_id")
            observation["quote"] = None
            report["diagnostics"].append({"row_id": observation["row_id"],
                                          "reason": "duplicate_provider_selection_id"})
        if observation["stat"] in report["coverage"]:
            report["coverage"][observation["stat"]] += 1
    if report["diagnostics"] or not metadata["pagination"]["complete"]:
        report["status"] = "partial" if observations else "parser_failure"
        if not metadata["pagination"]["complete"] and not report["diagnostics"]:
            report["status"] = "partial"
    elif not observations:
        report["status"] = "empty"
    elif any(o["stat"] is None or "unmapped_outcome_type" in o["unavailable_reasons"]
             for o in observations):
        report["status"] = "unmapped"
    else:
        report["status"] = "ok"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", help="authorized nba-offer-capture-v1 local JSON file")
    parser.add_argument("receipt", help="create-only local report receipt; never a public website asset")
    args = parser.parse_args()
    report = import_capture(load_json(args.capture), imported_at=datetime.now(timezone.utc))
    created = write_receipt(args.receipt, report)
    print(f"{report['status']}: {len(report['observations'])} observations, "
          f"{len(report['diagnostics'])} diagnostics; receipt_created={created}; qualified=False")


if __name__ == "__main__":
    main()
