"""Private, price-independent Sleeper threshold review; no collection or publication.

This projection preserves partial line facts without requiring a betting contract.
Original-byte replay and historical derived-receipt recovery remain distinct.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .integrity import (IntegrityError, RECEIPT_SCHEMA, HASH_FORMAT, _bounded_bytes,
    _decode, canonical, digest, read_receipt, stamp, utc)
from .offer_import import import_capture, REQUIRED_MARKETS, SLEEPER_LABELS, MAX_ROWS

SCHEMA = "nba-private-player-lines-v1"
ALL_CATEGORIES = (*REQUIRED_MARKETS, "PA")
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_REVIEW_BYTES = 256 * 1024
MAX_DISPLAY_ROWS = 32
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_FILES = 512
URL = "https://api.sleeper.com/lines/available"
TOP_FIELDS = {"schema_version", "scope", "source", "venue", "product", "parse_status", "generated_at",
    "observed_at", "imported_at", "evidence_lane", "source_evidence", "counts", "selection",
    "category_coverage", "observations", "public_admission", "ticket_eligibility", "qualification", "review_id"}
EVIDENCE_FIELDS = {"kind", "input_sha256", "input_bytes", "metadata_sha256", "source_payload_sha256", "capture_sha256",
    "source_payload_hash_basis", "raw_source_sha256", "raw_source_bytes", "source_url", "provider_permission_verified"}
COUNT_FIELDS = {"source_rows", "nba_rows", "parsed_observations", "displayed_observations", "unmapped_observations", "complete_contracts", "diagnostics"}
ROW_FIELDS = {"row_id", "provider_player_id", "provider_event_id", "provider_selection_id",
    "player_namespace", "player_label", "event_label", "team_label", "stat", "raw_stat_label",
    "line", "side", "variant", "period", "overtime", "event_starts_at", "source_updated_at",
    "source_declared_status", "source_economics", "price_status", "quote", "contract",
    "precision_basis", "source_pointer", "unavailable_reasons", "forecast_match_status", "ticket_eligible"}


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _fields(value, names, label):
    require(type(value) is dict and set(value) == names, "Invalid player-line " + label)


def _text(value, maximum=600):
    return type(value) is str and 0 < len(value) <= maximum and value.strip() == value


def _sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _clock(value):
    require(type(value) is str and stamp(utc(value)) == value, "Precise UTC player-line clock required")
    return utc(value)


def _decimal(value):
    require(type(value) is str and len(value) <= 128, "Line must preserve decimal text")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise IntegrityError("Invalid line decimal") from error
    require(number.is_finite() and number >= 0, "Line must be finite and nonnegative")
    require(-128 <= number.as_tuple().exponent <= 128 and number.adjusted() < 128,
        "Expanded line decimal exceeds its bound")
    result = format(number, "f")
    require(len(result) <= 128, "Expanded line decimal exceeds its bound")
    return result


def validate_review(body, *, now):
    """Reject changed identities/meaning even when an outer checksum is valid."""
    try:
        _fields(body, TOP_FIELDS, "review")
        require(body["schema_version"] == SCHEMA and body["scope"] == "LOCAL_REVIEW_ONLY"
            and body["source"] == "sleeper" and body["venue"] == "Sleeper"
            and body["product"] == "Picks variant unverified"
            and body["public_admission"] is False and body["ticket_eligibility"] is False
            and body["qualification"] == "UNAVAILABLE", "Unadmitted player-line scope")
        require(body["parse_status"] in {"ok", "partial", "unmapped", "empty", "blocked_access", "upstream_error", "parser_failure"}, "Unknown import status")
        require(_clock(body["observed_at"]) <= _clock(body["imported_at"])
            <= _clock(body["generated_at"]) <= utc(now), "Player-line clocks disagree")
        require(body["evidence_lane"] in {"SYNTHETIC_TEST", "RECONSTRUCTED_RESEARCH", "VERIFIED_ASOF_REPLAY", "REAL_TIME_CAPTURED"}, "Unknown line evidence lane")
        evidence = body["source_evidence"]; _fields(evidence, EVIDENCE_FIELDS, "source evidence")
        for key in ("input_sha256", "source_payload_sha256", "capture_sha256"):
            require(_sha(evidence[key]), "Invalid line evidence hash")
        require(type(evidence["input_bytes"]) is int and 0 < evidence["input_bytes"] <= MAX_INPUT_BYTES
            and evidence["source_url"] == URL and evidence["provider_permission_verified"] is False,
            "Invalid input evidence or unsupported permission assertion")
        raw = evidence["kind"] == "RAW_HTTP_BODY_REPLAYED"
        require(raw or evidence["kind"] == "DERIVED_RECEIPT_ONLY", "Unknown line evidence origin")
        if raw:
            require(evidence["raw_source_sha256"] == evidence["input_sha256"]
                and evidence["raw_source_bytes"] == evidence["input_bytes"] and _sha(evidence["metadata_sha256"])
                and evidence["source_payload_hash_basis"] == "CANONICAL_OPTION_DECIMAL_LEXEME_JSON", "Raw line evidence differs")
        else:
            require(evidence["raw_source_sha256"] is None and evidence["raw_source_bytes"] is None
                and evidence["metadata_sha256"] is None
                and evidence["source_payload_hash_basis"] == "CANONICAL_IMPORT_INPUT_JSON", "A derived receipt cannot prove original HTTP bytes")
        counts = body["counts"]; _fields(counts, COUNT_FIELDS, "counts")
        require(all(type(value) is int and 0 <= value <= 2**53-1 for value in counts.values())
            and counts["source_rows"] <= MAX_ROWS and counts["nba_rows"] <= counts["source_rows"]
            and counts["parsed_observations"] <= 20000 and counts["unmapped_observations"] <= counts["parsed_observations"]
            and counts["complete_contracts"] == 0, "Invalid bounded line counts")
        require(counts["parsed_observations"] == 0 or body["parse_status"] in {"ok","partial","unmapped"},
            "A failed or empty import cannot contain parsed observations")
        selection = body["selection"]; _fields(selection, {"offset", "limit", "ordering"}, "display selection")
        require(type(selection["offset"]) is int and 0 <= selection["offset"] <= counts["parsed_observations"]
            and type(selection["limit"]) is int and 1 <= selection["limit"] <= MAX_DISPLAY_ROWS
            and selection["ordering"] == "SOURCE_ROW_OPTION_ORDER", "Invalid explicit display window")
        require(type(body["observations"]) is list and len(body["observations"]) == counts["displayed_observations"]
            == min(selection["limit"], counts["parsed_observations"]-selection["offset"]), "Display window silently loses observations")
        displayed = Counter(); row_ids = set()
        for index, row in enumerate(body["observations"]):
            _fields(row, ROW_FIELDS, "observation")
            for key in ("row_id", "provider_player_id", "provider_event_id", "provider_selection_id", "raw_stat_label", "variant"):
                require(_text(row[key]), "Invalid native line identity")
            require(row["row_id"] not in row_ids, "Duplicate imported row identity"); row_ids.add(row["row_id"])
            identity = re.fullmatch(r"row:(0|[1-9][0-9]*)/option:(0|[1-9][0-9]*)", row["row_id"])
            require(identity is not None and int(identity[1]) < counts["source_rows"]
                and int(identity[2]) < 64, "Invalid original row/option position")
            require(row["player_namespace"] == "sleeper" and row["player_label"] is None and row["event_label"] is None,
                "Native source IDs do not establish a verified human crosswalk")
            require(row["team_label"] is None or _text(row["team_label"], 200), "Invalid literal source team")
            require(row["stat"] == SLEEPER_LABELS.get(row["raw_stat_label"])
                and (row["stat"] is None or row["stat"] in ALL_CATEGORIES), "Category conflicts with exact raw label")
            if row["stat"] is not None: displayed[row["stat"]] += 1
            require(type(row["line"]) is str and re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", row["line"])
                and len(row["line"]) <= 128 and _decimal(row["line"]) == row["line"], "Invalid exact normalized threshold")
            require(row["side"] in {"over", "under"} and all(row[key] is None for key in ("period", "overtime", "event_starts_at")),
                "A threshold does not establish period, overtime or start")
            if row["source_updated_at"] is not None:
                require(_clock(row["source_updated_at"]) <= _clock(body["observed_at"]), "Future source update")
            require(row["source_declared_status"] is None or _text(row["source_declared_status"], 100), "Invalid literal source status")
            economics = row["source_economics"]
            if economics is not None:
                _fields(economics, {"kind", "value"}, "source economics")
                require(economics["kind"] == "pickem_multiplier" and type(economics["value"]) is str
                    and re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", economics["value"])
                    and len(economics["value"]) <= 128 and Decimal(economics["value"]) > 0,
                    "Source multiplier is not a sportsbook price")
            require(row["price_status"] == "PRICE_UNAVAILABLE" and row["quote"] is None and row["contract"] is None
                and row["ticket_eligible"] is False and row["forecast_match_status"] == "NOT_MATCHED_UNVERIFIED_IDENTITY_EVENT_PERIOD",
                "Partial lines cannot become quotes, forecast matches or tickets")
            require(row["precision_basis"] == ("RAW_NUMERIC_LEXEME_REPLAYED" if raw else "DERIVED_TEXT_ONLY"), "Line precision is overstated")
            if raw:
                match = re.fullmatch(r"/(0|[1-9][0-9]*)/options/(0|[1-9][0-9]*)/outcome_value", row["source_pointer"] or "")
                require(match is not None and int(match[1]) < counts["source_rows"]
                    and int(match[2]) < 64 and row["row_id"] == "row:"+match[1]+"/option:"+match[2], "Original line pointer differs")
            else:
                require(row["source_pointer"] == "/payload/observations/"+str(selection["offset"]+index)+"/line", "Derived line pointer differs")
            reasons = row["unavailable_reasons"]
            require(type(reasons) is list and len(reasons) <= 32 and len(set(reasons)) == len(reasons)
                and all(_text(reason) for reason in reasons)
                and {"player_name_unverified", "event_identity_unverified", "period_unverified", "overtime_unverified"}.issubset(reasons),
                "Required identity/semantic gaps are hidden")
        coverage = body["category_coverage"]; _fields(coverage, set(ALL_CATEGORIES), "full NBA inventory")
        for code in ALL_CATEGORIES:
            row = coverage[code]; _fields(row, {"observed_side_options", "displayed_side_options", "status"}, "category coverage")
            require(type(row["observed_side_options"]) is int and 0 <= row["observed_side_options"] <= counts["parsed_observations"]
                and type(row["displayed_side_options"]) is int and row["displayed_side_options"] == displayed[code]
                and row["displayed_side_options"] <= row["observed_side_options"]
                and row["status"] == ("OBSERVED_IN_SAMPLE" if row["observed_side_options"] else "UNOBSERVED_IN_SAMPLE"), "Incorrect source category counts")
        require(sum(row["observed_side_options"] for row in coverage.values())+counts["unmapped_observations"] == counts["parsed_observations"], "Full source inventory loses rows")
        require(body["review_id"] == digest({key:value for key,value in body.items() if key != "review_id"}), "Player-line seal differs")
        require(len(canonical(body)) <= MAX_REVIEW_BYTES, "Player-line display exceeds its byte ceiling")
        return body
    except IntegrityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError) as error:
        raise IntegrityError("Malformed player-line review") from error


def normalize_original(raw, metadata_raw, *, imported_at):
    """Replay a complete retained body; never performs an HTTP request."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT_BYTES, "Original response exceeds its existing byte ceiling")
    require(type(metadata_raw) is bytes and 0 < len(metadata_raw) <= 256*1024, "Original response metadata exceeds its byte ceiling")
    metadata = _decode(metadata_raw)
    require(type(metadata) is dict and metadata.get("complete_body") is True and metadata.get("http_status") == 200
        and "json" in str(metadata.get("content_type", "")).lower()
        and metadata.get("url") == metadata.get("final_url") == URL, "Incomplete or unsupported original response")
    require(type(metadata.get("raw_bytes")) is int and metadata["raw_bytes"] == len(raw)
        and metadata.get("raw_sha256") == hashlib.sha256(raw).hexdigest(), "Original response hash/bytes differ")
    require(_clock(metadata["request_started_at"]) <= _clock(metadata["observed_at"]) <= utc(imported_at), "Original observation clocks disagree")
    lane=metadata.get("evidence_lane","REAL_TIME_CAPTURED")
    require(lane in {"REAL_TIME_CAPTURED","SYNTHETIC_TEST"}, "Unsupported raw-capture evidence lane")
    decoded = _decode(raw)
    require(type(decoded) is list and len(decoded) <= MAX_ROWS, "Expected complete bounded source list")
    # Strict decoding above checks duplicate/nonfinite values. This second parse
    # preserves original decimal lexemes instead of rounding lines through float.
    lexical = json.loads(raw, parse_float=str)
    option_count=0
    for row in lexical:
        if type(row) is dict and row.get("sport") == "nba":
            require(type(row.get("options")) is list and len(row["options"]) <= 64, "NBA option inventory exceeds its explicit bound")
            option_count+=len(row["options"])
            require(option_count <= 20000, "NBA option inventory exceeds the observation ceiling")
            for option in row["options"]:
                if type(option) is dict:
                    for key in ("outcome_value", "payout_multiplier"):
                        if type(option.get(key)) is int: option[key] = str(option[key])
    capture = {"schema_version":"nba-offer-capture-v1", "source":"sleeper", "source_url":URL,
        "observed_at":metadata["observed_at"], "evidence_lane":lane, "http_status":200,
        "content_type":metadata["content_type"], "format":"sleeper_lines_v1",
        "authorization":{"scope":"local_research", "public_redistribution":False,
            "basis":"Owner-authorized bounded private source inspection; no independent provider-permission certification or public admission."},
        "pagination":{"complete":False, "pages_observed":1}, "data":lexical}
    # The response is a complete JSON list; absence of pagination documentation
    # is distinct from complete source coverage, so pagination remains unknown.
    report = import_capture(capture, imported_at=utc(imported_at))
    return report, lexical


def project_report(report, *, evidence, generated_at, offset=0, limit=32, original=None):
    require(type(report) is dict and report.get("schema_version") == "nba-offer-import-v1"
        and report.get("source") == "sleeper" and report.get("source_url") == URL
        and report.get("qualified") is False, "Expected retained Sleeper import report")
    require(type(report.get("observations")) is list and len(report["observations"]) <= 20000, "Parsed source exceeds observation bound")
    require(type(report.get("input_row_count")) is int and 0 <= report["input_row_count"] <= MAX_ROWS
        and type(report.get("other_sport_rows_ignored")) is int
        and 0 <= report["other_sport_rows_ignored"] <= report["input_row_count"], "Invalid whole-source row counts")
    require(_clock(report["observed_at"]) <= _clock(report["imported_at"]) <= utc(generated_at), "Invalid whole-source import clocks")
    require(type(offset) is int and 0 <= offset <= len(report["observations"])
        and type(limit) is int and 1 <= limit <= MAX_DISPLAY_ROWS, "Invalid explicit review window")
    row_ids=set()
    for row in report["observations"]:
        require(type(row) is dict and row.get("provider") == "sleeper" and row.get("subject_type") == "player"
            and row.get("league") == "NBA" and row.get("stat") == SLEEPER_LABELS.get(row.get("raw_stat_label")), "Foreign or contradictory imported subject")
        require(row.get("price") is None or type(row["price"]) is dict and row["price"].get("kind") == "pickem_multiplier",
            "A native source multiplier cannot become sportsbook odds")
        require(row.get("contract") is None and row.get("quote") is None and row.get("qualified") is False,
            "Use the existing full-contract path for complete contracts")
        identity=re.fullmatch(r"row:(0|[1-9][0-9]*)/option:(0|[1-9][0-9]*)",row.get("row_id", ""))
        require(identity is not None and int(identity[1]) < report["input_row_count"] and int(identity[2]) < 64
            and row["row_id"] not in row_ids, "Invalid or repeated whole-source row/option identity")
        row_ids.add(row["row_id"])
        require(all(_text(row.get(key)) for key in ("provider_player_id","provider_event_id","provider_selection_id","raw_stat_label","variant"))
            and row.get("player_id") == "sleeper:nba:player:"+row["provider_player_id"]
            and row.get("event_id") == "sleeper:nba:event:"+row["provider_event_id"], "Invalid whole-source native identity")
        _decimal(row.get("line"))
        require(row.get("side") in {"over","under"}, "Unsupported whole-source side")
        require(row.get("source_updated_at") is None or _clock(row["source_updated_at"]) <= _clock(report["observed_at"]),
            "Whole-source update follows capture")
        require(row.get("game_status") is None or _text(row["game_status"],100), "Invalid whole-source status")
        reasons=row.get("unavailable_reasons")
        require(type(reasons) is list and len(reasons) <= 28 and all(_text(reason) for reason in reasons)
            and len(set(reasons)) == len(reasons), "Invalid whole-source gap inventory")
        if row["price"] is not None:
            _fields(row["price"],{"value","kind"},"whole-source economics")
            require(Decimal(_decimal(row["price"]["value"])) > 0,"Invalid whole-source multiplier")
    observed = Counter(row["stat"] for row in report["observations"])
    chosen = report["observations"][offset:offset+limit]; projected=[]
    for position, row in enumerate(chosen):
        team=None; pointer="/payload/observations/"+str(offset+position)+"/line"
        if original is not None:
            match = re.fullmatch(r"row:([0-9]+)/option:([0-9]+)", row["row_id"])
            require(match is not None, "Imported row lacks exact source position")
            source = original[int(match[1])]["options"][int(match[2])]
            require(_decimal(str(source["outcome_value"])) == _decimal(row["line"]), "Original line replay differs")
            team = source.get("subject_team")
            require(team is None or _text(team, 200), "Invalid original team label")
            pointer="/"+match[1]+"/options/"+match[2]+"/outcome_value"
        economics=None if row["price"] is None else {"kind":"pickem_multiplier", "value":_decimal(row["price"]["value"])}
        reasons=list(dict.fromkeys([*row["unavailable_reasons"], "player_name_unverified", "event_identity_unverified", "period_unverified", "overtime_unverified"]))
        projected.append({"row_id":row["row_id"], "provider_player_id":row["provider_player_id"],
            "provider_event_id":row["provider_event_id"], "provider_selection_id":row["provider_selection_id"],
            "player_namespace":"sleeper", "player_label":None, "event_label":None, "team_label":team,
            "stat":row["stat"], "raw_stat_label":row["raw_stat_label"], "line":_decimal(row["line"]),
            "side":row["side"], "variant":row["variant"], "period":None, "overtime":None, "event_starts_at":None,
            "source_updated_at":row["source_updated_at"], "source_declared_status":row.get("game_status"),
            "source_economics":economics, "price_status":"PRICE_UNAVAILABLE", "quote":None, "contract":None,
            "precision_basis":"RAW_NUMERIC_LEXEME_REPLAYED" if original is not None else "DERIVED_TEXT_ONLY",
            "source_pointer":pointer, "unavailable_reasons":reasons,
            "forecast_match_status":"NOT_MATCHED_UNVERIFIED_IDENTITY_EVENT_PERIOD", "ticket_eligible":False})
    shown=Counter(row["stat"] for row in projected)
    body={"schema_version":SCHEMA, "scope":"LOCAL_REVIEW_ONLY", "source":"sleeper", "venue":"Sleeper",
        "product":"Picks variant unverified", "parse_status":report["status"], "generated_at":stamp(utc(generated_at)),
        "observed_at":report["observed_at"], "imported_at":report["imported_at"], "evidence_lane":report["evidence_lane"],
        "source_evidence":evidence, "counts":{"source_rows":report["input_row_count"],
            "nba_rows":report["input_row_count"]-report["other_sport_rows_ignored"],
            "parsed_observations":len(report["observations"]), "displayed_observations":len(projected),
            "unmapped_observations":observed[None], "complete_contracts":0, "diagnostics":len(report["diagnostics"])},
        "selection":{"offset":offset, "limit":limit, "ordering":"SOURCE_ROW_OPTION_ORDER"},
        "category_coverage":{code:{"observed_side_options":observed[code], "displayed_side_options":shown[code],
            "status":"OBSERVED_IN_SAMPLE" if observed[code] else "UNOBSERVED_IN_SAMPLE"} for code in ALL_CATEGORIES},
        "observations":projected, "public_admission":False, "ticket_eligibility":False, "qualification":"UNAVAILABLE"}
    body["review_id"]=digest(body)
    validate_review(body, now=utc(generated_at))
    return body


def _private_directory(destination, source_root):
    root=Path(source_root).resolve(); destination=Path(os.path.abspath(destination))
    require(destination.is_relative_to(root/".local-data") and destination != root/".local-data", "Line preview must remain under .local-data")
    current=root
    for part in destination.relative_to(root).parts:
        current=current/part
        require(not current.is_symlink() and (not current.exists() or current.is_dir()), "Private preview parent is not a real directory")
        current.mkdir(exist_ok=True,mode=0o700)
    return destination


def _create(directory, name, raw, *, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, "Private artifact exceeds byte limit")
    path=directory/name;require(path.parent == directory and not path.is_symlink(), "Unsafe local artifact path")
    files=list(directory.iterdir())
    require(all(entry.is_file() and not entry.is_symlink() for entry in files), "Unsafe private evidence package entry")
    additional=0 if path.exists() else 1
    require(len(files)+additional <= MAX_PACKAGE_FILES
        and sum(entry.stat().st_size for entry in files)+(len(raw) if additional else 0) <= MAX_PACKAGE_BYTES,
        "Private evidence package exceeds unchanged file/byte ceilings")
    if path.exists():
        require(_bounded_bytes(path,maximum) == raw, "Conflicting retained private artifact")
        return False
    fd,temporary=tempfile.mkstemp(prefix=".line-staging-",dir=directory)
    try:
        with os.fdopen(fd,"wb") as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
        try:os.link(temporary,path)
        except FileExistsError:require(_bounded_bytes(path,maximum) == raw,"Concurrent private artifact differs")
    finally:Path(temporary).unlink(missing_ok=True)
    return True


def _envelope(payload):
    return canonical({"schema_version":RECEIPT_SCHEMA,"hash_format":HASH_FORMAT,
        "payload_sha256":digest(payload),"payload":payload})


def build_preview(*, destination, source_root, now, receipt=None, body=None, metadata=None, offset=0, limit=32):
    """Create-only retained input/preview. Retry reuses original clocks and input."""
    require((receipt is not None and body is None and metadata is None)
        or (receipt is None and body is not None and metadata is not None), "Choose one retained receipt or original body plus metadata")
    destination=_private_directory(destination,source_root)
    raw=_bounded_bytes(Path(receipt or body),MAX_INPUT_BYTES)
    metadata_raw=None if receipt is not None else _bounded_bytes(Path(metadata),256*1024)
    kind="DERIVED_RECEIPT_ONLY" if receipt is not None else "RAW_HTTP_BODY_REPLAYED"
    signature={"kind":kind,"input_sha256":hashlib.sha256(raw).hexdigest(),"input_bytes":len(raw),
        "metadata_sha256":None if metadata_raw is None else hashlib.sha256(metadata_raw).hexdigest(),
        "offset":offset,"limit":limit}
    intent_path=destination/"review-intent.receipt.json"
    prior=read_receipt(intent_path) if intent_path.exists() else None
    if prior is not None:
        _fields(prior,{"schema_version","input","imported_at","generated_at"},"recovery intent")
        require(prior["schema_version"] == "nba-private-player-line-intent-v1" and prior["input"] == signature,
            "A retry cannot rebind source bytes or the display window")
        require(_clock(prior["imported_at"]) <= _clock(prior["generated_at"]) <= utc(now), "Invalid recovery intent clocks")
    imported=utc(prior["imported_at"]) if prior else utc(now)
    if receipt is not None:
        envelope=_decode(raw);report=read_receipt(receipt)
        require(envelope["payload_sha256"] == digest(report),"Derived import receipt differs")
        original=None;imported=utc(report["imported_at"])
    else:report,original=normalize_original(raw,metadata_raw,imported_at=imported)
    generated=utc(prior["generated_at"]) if prior else utc(now)
    evidence={key:signature[key] for key in ("kind","input_sha256","input_bytes","metadata_sha256")}
    evidence.update(source_payload_sha256=report["source_payload_sha256"],capture_sha256=report["capture_sha256"],
        source_payload_hash_basis="CANONICAL_IMPORT_INPUT_JSON" if receipt is not None else "CANONICAL_OPTION_DECIMAL_LEXEME_JSON",
        raw_source_sha256=None if receipt is not None else signature["input_sha256"],
        raw_source_bytes=None if receipt is not None else len(raw),source_url=report["source_url"],provider_permission_verified=False)
    review=project_report(report,evidence=evidence,generated_at=generated,offset=offset,limit=limit,original=original)
    # Intent precedes all other private originals, so interrupted retries retain
    # the same source and import/review clocks without inventing a new capture.
    intent={"schema_version":"nba-private-player-line-intent-v1","input":signature,
        "imported_at":stamp(imported),"generated_at":stamp(generated)}
    _create(destination,intent_path.name,_envelope(intent),maximum=MAX_REVIEW_BYTES)
    _create(destination,"source.receipt.json" if receipt is not None else "source.body",raw,maximum=MAX_INPUT_BYTES)
    if metadata_raw is not None:_create(destination,"source.metadata.json",metadata_raw,maximum=256*1024)
    _create(destination,"normalized.receipt.json",_envelope(report),maximum=MAX_INPUT_BYTES)
    _create(destination,"review.json",canonical(review),maximum=MAX_REVIEW_BYTES)
    _create(destination,"review.receipt.json",_envelope(review),maximum=MAX_REVIEW_BYTES+1024)
    return {"preview":str(destination),"review_id":review["review_id"],"counts":review["counts"],
        "source_evidence":review["source_evidence"],"public_admission":False,"ticket_eligibility":False,
        "source_http_requests":0,"recovered_existing_preview":prior is not None}


def verify_package(directory, *, now):
    """Read-only independent replay from retained package bytes, with no writes."""
    directory=Path(directory)
    require(not directory.is_symlink() and directory.is_dir(), "Invalid private recovery directory")
    entries=list(directory.iterdir())
    require(all(entry.is_file() and not entry.is_symlink() for entry in entries)
        and len(entries) <= MAX_PACKAGE_FILES
        and sum(entry.stat().st_size for entry in entries) <= MAX_PACKAGE_BYTES,
        "Private recovery exceeds file/byte ceilings or contains unsafe paths")
    intent=read_receipt(directory/"review-intent.receipt.json",max_bytes=MAX_REVIEW_BYTES)
    _fields(intent,{"schema_version","input","imported_at","generated_at"},"recovery intent")
    require(intent["schema_version"] == "nba-private-player-line-intent-v1", "Unsupported recovery intent")
    review=_decode(_bounded_bytes(directory/"review.json",MAX_REVIEW_BYTES))
    validate_review(review,now=now)
    require(read_receipt(directory/"review.receipt.json",max_bytes=MAX_REVIEW_BYTES+1024) == review,
        "Recovery review differs from its retained receipt")
    evidence=review["source_evidence"]; raw=evidence["kind"] == "RAW_HTTP_BODY_REPLAYED"
    source_path=directory/("source.body" if raw else "source.receipt.json")
    source=_bounded_bytes(source_path,MAX_INPUT_BYTES)
    metadata_raw=_bounded_bytes(directory/"source.metadata.json",256*1024) if raw else None
    expected={"kind":evidence["kind"],"input_sha256":hashlib.sha256(source).hexdigest(),"input_bytes":len(source),
        "metadata_sha256":hashlib.sha256(metadata_raw).hexdigest() if raw else None,
        "offset":review["selection"]["offset"],"limit":review["selection"]["limit"]}
    require(intent["input"] == expected
        and all(evidence[key] == expected[key] for key in ("kind","input_sha256","input_bytes","metadata_sha256"))
        and intent["imported_at"] == review["imported_at"] and intent["generated_at"] == review["generated_at"],
        "Recovery original hashes, input window or clocks differ")
    if raw:
        report,original=normalize_original(source,metadata_raw,imported_at=intent["imported_at"])
    else:
        report,original=read_receipt(source_path),None
    require(read_receipt(directory/"normalized.receipt.json") == report
        and evidence["source_payload_sha256"] == report["source_payload_sha256"]
        and evidence["capture_sha256"] == report["capture_sha256"], "Recovery normalized source differs")
    replay=project_report(report,evidence=evidence,generated_at=intent["generated_at"],
        offset=expected["offset"],limit=expected["limit"],original=original)
    require(canonical(replay) == canonical(review), "Recovery source facts differ from the preview")
    return {"review_id":review["review_id"],"counts":review["counts"],
        "recovery":"LOCAL_SOURCE_REPLAY_VERIFIED" if raw else "LOCAL_DERIVED_RECEIPT_REPLAY_VERIFIED",
        "original_http_bytes_recovered":raw,"durable_remote_archive_verified":False,
        "source_http_requests":0,"writes":0,"public_admission":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--receipt",type=Path);group.add_argument("--body",type=Path);group.add_argument("--verify",type=Path)
    parser.add_argument("--metadata",type=Path);parser.add_argument("--output",type=Path)
    parser.add_argument("--offset",type=int,default=0);parser.add_argument("--limit",type=int,default=32)
    args=parser.parse_args()
    if args.verify is not None:
        require(args.output is None and args.metadata is None, "Read-only recovery does not accept output or metadata overrides")
        print(json.dumps(verify_package(args.verify,now=datetime.now(timezone.utc)),sort_keys=True))
        return
    require(args.output is not None, "A private output directory is required")
    result=build_preview(destination=args.output,source_root=Path(__file__).resolve().parents[1],
        now=datetime.now(timezone.utc),receipt=args.receipt,body=args.body,metadata=args.metadata,offset=args.offset,limit=args.limit)
    print(json.dumps(result,sort_keys=True))


if __name__ == "__main__":
    main()
