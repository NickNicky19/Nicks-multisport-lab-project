"""Strict, separately admitted NBA offer-only facts; never ticket eligibility.

Typed validation performs no network access. After the independent public
admission gate, native ledger recovery can authenticate its private originals
through the existing fixed GitHub draft. A reviewed contract may be displayed
without a price. Checksums and review declarations do not establish provider
permission, upstream authenticity, or a usable betting quote.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import zlib
from weakref import WeakKeyDictionary

from .integrity import (HASH_FORMAT, RECEIPT_SCHEMA, IntegrityError, canonical,
                        digest, load_json, read_receipt, stamp, utc)
from .offer_import import UNITS
from .source_evidence import (replay_text_evidence, validate_text_binding,
                              validate_text_replay)

ASSET_SCHEMA = "nba-player-offers-v1"
NATIVE_ASSET_SCHEMA = "nba-player-offers-v2"
OFFER_SCHEMA = "nba-player-offer-v1"
ADMISSION_SCHEMA = "nba-offer-publication-admission-v1"
RAW_SCHEMA = "nba-offer-raw-capture-v1"
CATEGORIES = tuple(UNITS)
MAX_ASSET_BYTES = 256 * 1024
MAX_OFFERS = 32
MAX_OFFER_BYTES = 32 * 1024
MAX_ENVELOPE_BYTES = 64 * 1024
MAX_RAW_BYTES = 2 * 1024 * 1024
# A caller's assertion cannot grant itself public admission. Any future addition
# requires source/contract/rights review and the corresponding frontend pin.
APPROVED_PUBLIC_ADMISSION_IDS = frozenset()
SHA = re.compile(r"[a-f0-9]{64}\Z")
CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")
DECIMAL = re.compile(r"(?:0|[1-9]\d*)(?:\.\d+)?\Z")
PROVIDER_FIELDS = {"name", "id_namespace", "event_id", "player_id", "market_id", "selection_id"}
SETTLEMENT_FIELDS = {"participation", "dnp", "postponement", "ties", "official_stat_source", "stat_corrections"}
OFFER_FIELDS = {"schema_version", "offer_id", "sport", "league", "id_namespace", "event_id",
    "event_version", "event_starts_at", "player_id", "player_label", "team_id", "opponent_id",
    "stat", "units", "period", "extra_time_policy", "line", "side", "variant", "venue", "product",
    "settlement_version", "settlement_terms", "stat_definition", "provider", "observed_at", "source_updated_at", "imported_at",
    "market_status", "evidence_lane", "source_evidence", "admission_id", "price_status", "price",
    "quote", "qualification"}
ADMISSION_FIELDS = {"schema_version", "admission_id", "subject_sha256", "reviewed_at", "reviewer",
    "decision", "scope", "basis", "raw_redistribution", "scheduled_collection"}
EVIDENCE_FIELDS = {"evidence_id", "kind", "source_url", "raw_sha256", "raw_bytes", "raw_record_id",
    "request_started_at", "observed_at", "source_updated_at", "bindings"}
# Normalized meanings must be explicit, reviewed, and linked to actual raw values.
# A binding is not a claim that the raw source used our normalized vocabulary.
BOUND_FIELDS = {"id_namespace", "event_id", "event_version", "event_starts_at", "player_id", "player_label", "team_id",
    "opponent_id", "stat", "period", "extra_time_policy", "line", "side", "variant", "venue", "product",
    "settlement_version", "stat_definition", "market_status", *("provider." + key for key in PROVIDER_FIELDS),
    *("settlement_terms." + key for key in SETTLEMENT_FIELDS)}
KINDS = {"CONTRACT_VIEW", "EVENT_IDENTITY", "PLAYER_IDENTITY", "RULES", "CROSSWALK"}
KIND_BINDINGS = {
    "CONTRACT_VIEW": {"provider.selection_id", "provider.market_id", "provider.event_id", "provider.player_id", "stat", "line", "side", "market_status"},
    "EVENT_IDENTITY": {"event_id", "event_version", "event_starts_at", "team_id", "opponent_id"},
    "PLAYER_IDENTITY": {"player_id", "player_label", "team_id"},
    "RULES": {"period", "extra_time_policy", "variant", "product", "settlement_version", "stat_definition",
              *("settlement_terms." + key for key in SETTLEMENT_FIELDS)},
    "CROSSWALK": {"id_namespace", "provider.id_namespace", "provider.event_id", "provider.player_id"},
}


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
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise IntegrityError("Malformed offer contract: " + str(error)) from error
    return checked


def _fields(value, expected, label):
    _require(type(value) is dict and set(value) == set(expected), "Invalid " + label + " fields")


def _text(value, label, maximum=200):
    _require(type(value) is str and bool(value) and value == value.strip() and len(value) <= maximum,
             "Invalid " + label)


def _hash(value, label):
    _require(type(value) is str and SHA.fullmatch(value) is not None, "Invalid " + label)


def _clock(value):
    _require(type(value) is str and CLOCK.fullmatch(value) is not None, "Microsecond UTC clock required")
    try:
        result = utc(value)
    except (ValueError, TypeError) as error:
        raise IntegrityError("Invalid clock") from error
    _require(stamp(result) == value, "Invalid calendar clock")
    return result


def _url(value):
    _text(value, "source URL", 2048)
    parsed = urlparse(value)
    _require(parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
             and not parsed.password and not parsed.fragment, "A public HTTPS evidence URL is required")


def _decimal(value, label):
    _require(type(value) is str and len(value) <= 32 and DECIMAL.fullmatch(value) is not None,
             "Invalid " + label + " decimal text")
    result = Decimal(value)
    _require(result <= Decimal("1000000"), "Unbounded " + label)
    return result


def seal(record, field):
    """Return a sealed copy. Validation still must run after construction."""
    copied = deepcopy(record)
    copied.pop(field, None)
    return {**copied, field: digest(copied)}


def offer_subject(offer):
    return digest({key: value for key, value in offer.items() if key not in {"offer_id", "admission_id"}})


def _target(offer, path):
    if path.startswith(("provider.", "price.", "settlement_terms.")):
        group, key = path.split(".")
        return offer[group][key]
    return offer[path]


@_strict
def validate_offer(offer, admission, *, now, allow_synthetic=False):
    _fields(offer, OFFER_FIELDS, "offer")
    _fields(admission, ADMISSION_FIELDS, "admission")
    _require(offer["schema_version"] == OFFER_SCHEMA and admission["schema_version"] == ADMISSION_SCHEMA,
             "Unsupported offer/admission version")
    _hash(offer["offer_id"], "offer ID")
    _hash(admission["admission_id"], "admission ID")
    _require(offer["offer_id"] == digest({k: v for k, v in offer.items() if k != "offer_id"}),
             "Offer seal mismatch")
    _require(admission["admission_id"] == digest({k: v for k, v in admission.items() if k != "admission_id"}),
             "Admission seal mismatch")
    _require(offer["admission_id"] == admission["admission_id"]
             and admission["subject_sha256"] == offer_subject(offer), "Admission does not bind this exact contract")
    _require(offer["sport"] == "basketball" and offer["league"] == "NBA", "Unsupported sport/league")
    for name in ("id_namespace", "event_id", "player_id", "player_label", "team_id", "opponent_id",
                 "variant", "venue", "product", "settlement_version"):
        _text(offer[name], name)
    _hash(offer["event_version"], "event version")
    _require(offer["team_id"] != offer["opponent_id"], "Conflicting team identity")
    _require(offer["stat"] in CATEGORIES and offer["units"] == UNITS[offer["stat"]], "Invalid category/units")
    _text(offer["stat_definition"], "source-verified statistic meaning", 600)
    _fields(offer["settlement_terms"], {"status", *SETTLEMENT_FIELDS}, "settlement meaning")
    _require(offer["settlement_terms"]["status"] == "SOURCE_VERIFIED", "Unverified settlement meaning")
    for field in SETTLEMENT_FIELDS:
        value = offer["settlement_terms"][field]
        _text(value, "settlement " + field, 600)
        _require(value.upper() not in {"UNKNOWN", "UNVERIFIED", "UNRESOLVED", "TBD", "N/A"},
                 "Incomplete settlement " + field)
    _require(offer["period"] == "full_game" and offer["extra_time_policy"] in
             {"includes_overtime", "regulation_only"}, "Unverified or unsupported period/OT meaning")
    _decimal(offer["line"], "line")
    _require(offer["side"] in {"over", "under"}, "Explicit over/under side required")
    _fields(offer["provider"], PROVIDER_FIELDS, "provider identity")
    for key, value in offer["provider"].items():
        _text(value, "provider " + key)
    observed, imported, start = map(_clock, (offer["observed_at"], offer["imported_at"], offer["event_starts_at"]))
    reviewed = _clock(admission["reviewed_at"])
    _require(observed <= imported <= reviewed <= utc(now), "Offer/import/review clocks out of order")
    if offer["source_updated_at"] is not None:
        _require(_clock(offer["source_updated_at"]) <= observed, "Source update is later than observation")
    _require(offer["market_status"] in {"PRE_GAME", "LIVE", "CLOSED", "SUSPENDED"}, "Unknown source market status")
    if offer["market_status"] == "PRE_GAME":
        _require(observed < start, "Pregame offer captured after event start")
    synthetic = offer["evidence_lane"] == "SYNTHETIC_TEST"
    _require(offer["evidence_lane"] in {"REAL_TIME_CAPTURED", "SYNTHETIC_TEST"}
             and (not synthetic or allow_synthetic), "Synthetic or reconstructed offer is not publicly admitted")
    _require(admission["decision"] == ("SYNTHETIC_ONLY" if synthetic else "ADMITTED_DERIVED_FACTS")
             and admission["scope"] == "ONE_CAPTURE_DERIVED_FACTS_ONLY"
             and admission["raw_redistribution"] is False and admission["scheduled_collection"] is False,
             "Unreviewed publication scope")
    _require(synthetic or admission["admission_id"] in APPROVED_PUBLIC_ADMISSION_IDS,
             "Actual public offer admission is not in the reviewed registry")
    _text(admission["reviewer"], "reviewer")
    _fields(admission["basis"], {"kind", "reference", "evidence_sha256", "description"}, "review basis")
    _require(admission["basis"]["kind"] in ({"SYNTHETIC_FIXTURE"} if synthetic else
             {"PUBLIC_SOURCE_SCOPED_REVIEW", "SOURCE_LICENSE", "EXPLICIT_PROVIDER_PERMISSION", "USER_PROVIDED_RIGHTS"}),
             "Unestablished review basis")
    _text(admission["basis"]["reference"], "review reference", 2048)
    _hash(admission["basis"]["evidence_sha256"], "review evidence hash")
    _text(admission["basis"]["description"], "review description", 1000)
    _require(type(offer["source_evidence"]) is list and 1 <= len(offer["source_evidence"]) <= 8,
             "Bounded source evidence required")
    required = BOUND_FIELDS | ({"price.kind", "price.value"} if offer["price"] is not None else set())
    if offer["price"] is not None:
        _fields(offer["price"], {"kind", "value", "evidence_id"}, "observed price")
    ids, covered, kinds = set(), set(), set()
    for evidence in offer["source_evidence"]:
        text_rules = type(evidence) is dict and "text_replay" in evidence
        _fields(evidence, EVIDENCE_FIELDS | ({"text_replay"} if text_rules else set()), "source evidence")
        if text_rules:
            _require(evidence["kind"] == "RULES", "Text replay is restricted to RULES evidence")
            validate_text_replay(evidence["text_replay"])
        _text(evidence["evidence_id"], "evidence ID")
        _require(evidence["evidence_id"] not in ids and evidence["kind"] in KINDS, "Duplicate or unknown evidence")
        ids.add(evidence["evidence_id"]); kinds.add(evidence["kind"])
        _url(evidence["source_url"])
        for field in ("raw_sha256", "raw_record_id"):
            _hash(evidence[field], field)
        _require(type(evidence["raw_bytes"]) is int and 0 < evidence["raw_bytes"] <= MAX_RAW_BYTES,
                 "Invalid bounded source byte count")
        at = _clock(evidence["observed_at"])
        _require(_clock(evidence["request_started_at"]) <= at <= imported, "Evidence observation clock mismatch")
        if evidence["source_updated_at"] is not None:
            _require(_clock(evidence["source_updated_at"]) <= at, "Evidence source update after observation")
        _require(type(evidence["bindings"]) is dict and set(evidence["bindings"]) <= required
                 and bool(evidence["bindings"]), "Unknown or empty normalized field bindings")
        _require(KIND_BINDINGS[evidence["kind"]] <= set(evidence["bindings"]),
                 "Source evidence lacks the fields required for its claimed role")
        if evidence["kind"] == "CONTRACT_VIEW":
            _require(evidence["observed_at"] == offer["observed_at"]
                     and evidence["source_updated_at"] == offer["source_updated_at"],
                     "Contract source observation/update clocks differ from the offer")
        for field, binding in evidence["bindings"].items():
            if text_rules:
                validate_text_binding(binding, evidence["text_replay"])
            else:
                _fields(binding, {"pointer", "source_value", "meaning"}, "source binding")
                _text(binding["pointer"], "JSON pointer", 512)
                _require(binding["pointer"].startswith("/"), "Source binding requires a JSON pointer")
            _require(canonical(binding["meaning"]) == canonical(_target(offer, field)),
                     "Source binding contradicts normalized offer")
            covered.add(field)
    _require(covered == required and {"CONTRACT_VIEW", "EVENT_IDENTITY", "PLAYER_IDENTITY", "RULES", "CROSSWALK"} <= kinds,
             "Incomplete identity, contract, crosswalk or rule evidence")
    _require(offer["quote"] is None and offer["qualification"] == "UNAVAILABLE", "Offer display confers no quote/ticket qualification")
    if offer["price"] is None:
        _require(offer["price_status"] == "PRICE_UNAVAILABLE", "Missing price status disagrees with price")
    else:
        _fields(offer["price"], {"kind", "value", "evidence_id"}, "observed price")
        _require(offer["price_status"] == "OBSERVED_PRICE_NOT_QUALIFIED" and offer["price"]["kind"] in
                 {"sportsbook_decimal", "pickem_multiplier"} and offer["price"]["evidence_id"] in ids,
                 "Invalid observed price source/type")
        value = _decimal(offer["price"]["value"], "price")
        _require(value > (1 if offer["price"]["kind"] == "sportsbook_decimal" else 0), "Invalid observed price value")
        price_evidence = next(e for e in offer["source_evidence"] if e["evidence_id"] == offer["price"]["evidence_id"])
        _require({"price.kind", "price.value", "line", "side", "provider.selection_id"} <= set(price_evidence["bindings"])
                 and price_evidence["observed_at"] == offer["observed_at"], "Line, side and price must be one source observation")
    _require(len(canonical(offer)) <= MAX_OFFER_BYTES, "Offer exceeds individual encoded limit")
    return offer


@_strict
def validate_asset(asset, *, now, allow_synthetic=False):
    _fields(asset, {"schema_version", "asset_id", "league", "generated_at", "status", "category_inventory",
                    "admissions", "offers", "unavailable_reasons"}, "offer asset")
    _require(asset["schema_version"] in {ASSET_SCHEMA, NATIVE_ASSET_SCHEMA} and asset["league"] == "NBA"
             and asset["status"] == "OFFER_ONLY_RESEARCH" and asset["category_inventory"] == list(CATEGORIES),
             "Unsupported offer asset or incomplete category inventory")
    _hash(asset["asset_id"], "asset ID")
    _require(asset["asset_id"] == digest({k: v for k, v in asset.items() if k != "asset_id"}), "Offer asset seal mismatch")
    generated = _clock(asset["generated_at"])
    _require(generated <= utc(now), "Offer asset generated in the future")
    _require(type(asset["offers"]) is list and len(asset["offers"]) <= MAX_OFFERS
             and type(asset["admissions"]) is list and len(asset["admissions"]) <= MAX_OFFERS,
             "Offer collection exceeds count limit")
    admissions = {}
    for admission in asset["admissions"]:
        _require(type(admission) is dict and "admission_id" in admission
                 and admission["admission_id"] not in admissions, "Duplicate or invalid admission")
        _hash(admission["admission_id"], "admission ID")
        admissions[admission["admission_id"]] = admission
    used, ids, selections = set(), set(), set()
    for offer in asset["offers"]:
        _require(type(offer) is dict, "Invalid typed offer")
        if offer.get("schema_version") == "nba-native-player-offer-v2":
            from .native_offer import validate_native_offer, native_offer_publicly_admitted
            _require(asset["schema_version"] == NATIVE_ASSET_SCHEMA, "Native offers require the versioned v2 asset")
            validate_native_offer(offer, now=generated)
            _require((allow_synthetic and offer["evidence_lane"] == "SYNTHETIC_TEST")
                     or native_offer_publicly_admitted(offer), "Native offer has no reviewed public admission")
            selection = (offer["venue"], offer["product"], offer["event"]["id_namespace"], offer["event"]["id"],
                         *(offer["selection"][key] for key in ("group_id", "market_id", "selection_id")), offer["observed_at"])
        else:
            _require(offer.get("admission_id") in admissions, "Offer missing publication review")
            validate_offer(offer, admissions[offer["admission_id"]], now=generated, allow_synthetic=allow_synthetic)
            selection = (offer["venue"], offer["product"], offer["provider"]["id_namespace"],
                         offer["provider"]["selection_id"], offer["observed_at"])
            used.add(offer["admission_id"])
        _require(offer["offer_id"] not in ids and selection not in selections, "Duplicate offer/provider selection")
        ids.add(offer["offer_id"]); selections.add(selection)
    _require(used == set(admissions), "Unreferenced admission review")
    _require(type(asset["unavailable_reasons"]) is list and len(asset["unavailable_reasons"]) <= 16,
             "Invalid offer availability reasons")
    for reason in asset["unavailable_reasons"]:
        _text(reason, "offer availability reason", 1000)
    _require(bool(asset["offers"]) or bool(asset["unavailable_reasons"]), "Empty offers require an ordinary-language reason")
    _require(len(canonical(asset)) <= MAX_ASSET_BYTES, "Offer asset exceeds byte limit")
    return asset


@_strict
def validate_descriptor(descriptor, *, now):
    _fields(descriptor, {"path", "sha256", "generated_at", "status", "retained", "error"}, "offer descriptor")
    _hash(descriptor["sha256"], "asset raw hash")
    _require(descriptor["path"] == "nba-offers." + descriptor["sha256"] + ".json"
             and descriptor["status"] == "OFFER_ONLY_RESEARCH" and type(descriptor["retained"]) is bool,
             "Unsafe offer asset descriptor")
    _require(_clock(descriptor["generated_at"]) <= utc(now), "Future descriptor clock")
    if descriptor["error"] is not None:
        _text(descriptor["error"], "offer descriptor error", 1000)
    return descriptor


def read_asset(data_dir, descriptor, *, now):
    validate_descriptor(descriptor, now=now)
    path = Path(data_dir) / descriptor["path"]
    asset = load_json(path, max_bytes=MAX_ASSET_BYTES)
    _require(hashlib.sha256(path.read_bytes()).hexdigest() == descriptor["sha256"], "Offer asset raw hash mismatch")
    validate_asset(asset, now=now)
    _require(asset["generated_at"] == descriptor["generated_at"], "Offer descriptor generation clock mismatch")
    return asset


def _pointer(value, pointer):
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        try:
            if type(value) is list:
                _require(re.fullmatch(r"0|[1-9]\d*", token) is not None, "Invalid array pointer")
                value = value[int(token)]
            else:
                _require(type(value) is dict, "Source pointer traverses a scalar")
                value = value[token]
        except (KeyError, IndexError) as error:
            raise IntegrityError("Source binding pointer does not exist") from error
    return value


def make_raw_capture(raw, *, source_url, request_started_at, observed_at, imported_at,
                     source_updated_at=None, http_status=200, content_type="application/json"):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW_BYTES, "Raw offer evidence exceeds bound")
    body = {"schema_version": RAW_SCHEMA, "evidence_lane": "SYNTHETIC_TEST", "source_url": source_url, "request_started_at": request_started_at,
            "observed_at": observed_at, "source_updated_at": source_updated_at, "imported_at": imported_at,
            "http_status": http_status, "content_type": content_type, "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_bytes": len(raw), "encoding": "zlib-base64", "encoded": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}
    validate_raw_capture(body)
    return body


@_strict
def validate_raw_capture(body):
    _fields(body, {"schema_version", "evidence_lane", "source_url", "request_started_at", "observed_at", "source_updated_at",
                   "imported_at", "http_status", "content_type", "raw_sha256", "raw_bytes", "encoding", "encoded"}, "raw capture")
    _require(body["schema_version"] == RAW_SCHEMA and body["encoding"] == "zlib-base64", "Unsupported raw capture")
    _url(body["source_url"]); _hash(body["raw_sha256"], "raw source hash")
    _require(body["evidence_lane"] == "SYNTHETIC_TEST" and
             urlparse(body["source_url"]).hostname.endswith((".test", ".invalid")),
             "Plaintext/compressed raw helper is restricted to synthetic test hosts; real sources require private retention")
    _require(type(body["http_status"]) is int and body["http_status"] == 200
             and body["content_type"].split(";")[0].strip() == "application/json", "Source is not a successful JSON response")
    _require(_clock(body["request_started_at"]) <= _clock(body["observed_at"]) <= _clock(body["imported_at"]), "Raw capture clocks out of order")
    if body["source_updated_at"] is not None:
        _require(_clock(body["source_updated_at"]) <= _clock(body["observed_at"]), "Raw source clock is after capture")
    _require(type(body["raw_bytes"]) is int and 0 < body["raw_bytes"] <= MAX_RAW_BYTES
             and type(body["encoded"]) is str and len(body["encoded"]) <= MAX_RAW_BYTES * 2, "Unbounded raw capture")
    try:
        compressed = base64.b64decode(body["encoded"], validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, MAX_RAW_BYTES + 1)
        _require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                 "Incomplete, oversized or concatenated raw compression")
    except (ValueError, zlib.error) as error:
        raise IntegrityError("Invalid raw capture encoding") from error
    _require(len(raw) == body["raw_bytes"] and hashlib.sha256(raw).hexdigest() == body["raw_sha256"], "Retained raw bytes/hash mismatch")
    # Decode with the same strict duplicate/nonfinite JSON checks as receipts.
    from .integrity import _decode
    return _decode(raw)


class OfferStore:
    """One-writer ledger retention, exact readback, explicit correction links.

    Uses generic input-capture records and the existing writer lock; it does not
    modify the frozen ledger schema or establish prospective admission clocks.
    """
    def __init__(self, root, *, allow_synthetic=False, raw_reader=None):
        from .pros004_records import Pros004Store
        from .publication_ledger import CompositeEnvelopeLedger
        self.root = Path(root)
        self.store = Pros004Store(root)
        self.ledger = CompositeEnvelopeLedger(root)
        self.store.ledger = self.ledger
        self.allow_synthetic = allow_synthetic
        self.raw_reader = raw_reader

    def _check_budget(self, payload, *, ceiling=MAX_ENVELOPE_BYTES):
        from . import ledger
        from .operational_pilot import metadata_inventory
        # Include every shared journal and current/archived recovery proof.
        # Base ledger counts its own files, including the encrypted-ref links.
        _, count, size = self.ledger._inventory()
        metadata = metadata_inventory(self.root)
        encoded = len(canonical({"schema_version": RECEIPT_SCHEMA, "hash_format": HASH_FORMAT,
                                 "payload_sha256": digest(payload), "payload": payload}))
        _require(encoded <= ceiling, "Offer record exceeds its encoded-envelope ceiling")
        _require(count + metadata["file_count"] + 1 <= ledger.MAX_LEDGER_RECORDS
                 and size + metadata["total_bytes"] + encoded <= ledger.MAX_LEDGER_BYTES, "Offer exceeds shared ledger budget")

    def _append(self, logical, data, references=()):
        from . import ledger
        record_id = digest({"kind": "input_captures", "logical_id": logical})
        if self.ledger._path("input_captures", record_id).exists():
            return self.ledger.append("input_captures", logical, data, references=references)
        payload = {"schema_version": ledger.SCHEMA, "kind": "input_captures", "record_id": record_id,
                   "logical_id": logical, "received_at": stamp(datetime.now(timezone.utc)), "data": data,
                   "references": [ref.to_record() for ref in references], "supersedes": None,
                   "persistence_status": "LOCAL_RECEIPT_ONLY"}
        self._check_budget(payload, ceiling=ledger.MAX_RECORD_BYTES if "offer_raw_capture" in data else MAX_ENVELOPE_BYTES)
        return self.ledger.append("input_captures", logical, data, references=references)

    def retain_raw(self, body):
        validate_raw_capture(body)
        with self.store.single_writer():
            reference = self._append("offer-raw-v1:" + digest(body), {"offer_raw_capture": body})
            _require(self.ledger.read(reference)["data"] == {"offer_raw_capture": body}, "Raw readback mismatch")
            return reference

    @_strict
    def _validate_retained(self, offer, admission, references):
        if offer.get("schema_version") == "nba-native-player-offer-v2":
            from .native_offer import validate_native_offer, replay_native_offer, native_offer_publicly_admitted
            from .moviodds_archive import validate_manifest, validate_reference
            validate_native_offer(offer, now=datetime.now(timezone.utc))
            _require(admission is None and ((self.allow_synthetic and offer["evidence_lane"] == "SYNTHETIC_TEST")
                     or native_offer_publicly_admitted(offer)), "Native record requires a reviewed public admission")
            _require(len(references) == 1 and references[0].kind == "input_captures",
                     "Native contract requires one independently recoverable private source reference")
            source = self.ledger.read(references[0])["data"]
            _fields(source, {"native_offer_archive"}, "private native source pointer")
            pointer = validate_reference(source["native_offer_archive"])
            if self.raw_reader is None:
                _require(offer["evidence_lane"] == "ACTUAL_SOURCE_REPLAY",
                         "Synthetic native records require an explicit offline source reader")
                from .moviodds_archive import GuardedGitHubReleaseArchive, PrivateMoviOddsArchive
                # No provider request or write is possible on this default path.
                # The empty public registry rejects unreviewed records above,
                # before even constructing the authenticated archive client.
                retained = PrivateMoviOddsArchive(GuardedGitHubReleaseArchive(
                    allow_diagnostics=True)).load_recovered_assets(pointer, now=datetime.now(timezone.utc))
            else:
                retained = self.raw_reader(references[0])
            _require(type(retained) is dict and {"assets", "review", "manifest", "manifest_ref"} <= set(retained),
                     "Native private source reader lacks original bytes and manifest")
            _require(offer["evidence_lane"] == "SYNTHETIC_TEST"
                     or retained.get("durable_remote_archive_verified") is True,
                     "Actual native source requires authenticated durable remote recovery")
            validate_manifest(retained["manifest"], reference=pointer)
            _require(retained["manifest_ref"] == pointer["manifest_ref"]
                     and pointer["review_id"] == offer["original_review_id"]
                     and retained["review"]["review_id"] == pointer["review_id"], "Native source archive identity differs")
            replay_native_offer(offer, retained["assets"], now=datetime.now(timezone.utc), allow_synthetic=self.allow_synthetic)
            return
        validate_offer(offer, admission, now=datetime.now(timezone.utc), allow_synthetic=self.allow_synthetic)
        refs = {ref.record_id: ref for ref in references}
        _require(set(refs) == {item["raw_record_id"] for item in offer["source_evidence"]}, "Exact raw source references required")
        for evidence in offer["source_evidence"]:
            reference = refs[evidence["raw_record_id"]]
            source = self.ledger.read(reference)["data"].get("offer_raw_capture")
            text_rules = "text_replay" in evidence
            raw = None
            if source is not None:
                _require(offer["evidence_lane"] == "SYNTHETIC_TEST", "Real provider raw bodies must not enter the public ledger")
                _require(not text_rules, "Text RULES require original bytes through the verified raw reader; the legacy helper is JSON-only")
                decoded = validate_raw_capture(source)
            else:
                _require(self.raw_reader is not None, "A verified private raw reader is required for real source evidence")
                retained = self.raw_reader(reference)
                _fields(retained, {"metadata", "raw"}, "private source readback")
                source = retained["metadata"]
                raw = retained["raw"]
                _require(type(source) is dict and type(raw) is bytes and 0 < len(raw) <= MAX_RAW_BYTES,
                         "Invalid private source readback")
                _require(len(raw) == evidence["raw_bytes"] and hashlib.sha256(raw).hexdigest() == evidence["raw_sha256"],
                         "Private raw bytes/hash mismatch")
                if not text_rules:
                    from .integrity import _decode
                    decoded = _decode(raw)
            for field in ("source_url", "raw_sha256", "raw_bytes", "request_started_at", "observed_at", "source_updated_at"):
                _require(source[field] == evidence[field], "Retained raw metadata differs from evidence")
            _require(_clock(source["imported_at"]) <= _clock(offer["imported_at"]), "Raw source imported after contract import")
            if text_rules:
                replay_text_evidence(raw, evidence)
            else:
                for binding in evidence["bindings"].values():
                    _require(canonical(_pointer(decoded, binding["pointer"])) == canonical(binding["source_value"]),
                             "Retained raw value contradicts source binding")

    @staticmethod
    def _identity(offer):
        if offer.get("schema_version") == "nba-native-player-offer-v2":
            return {"league": offer["league"], "source": offer["source"], "event": offer["event"],
                    "canonical_player": offer["canonical_player"], "selection": offer["selection"],
                    "observed_at": offer["observed_at"]}
        return {**{key: offer[key] for key in ("league", "id_namespace", "event_id", "event_version", "player_id", "venue", "product", "observed_at")},
                "provider": offer["provider"]}

    def retain_native_archive(self, reference):
        """Retain metadata only. Private originals never enter the public ledger."""
        from .moviodds_archive import validate_reference
        validate_reference(reference)
        with self.store.single_writer():
            return self._append("native-offer-archive-v1:" + digest(reference), {"native_offer_archive": reference})

    def persist(self, offer, admission, *, raw_references):
        references = tuple(raw_references)
        with self.store.single_writer():
            self._validate_retained(offer, admission, references)
            data = {"identity": self._identity(offer), "offer_capture": {"offer": offer, "admission": admission}}
            reference = self._append("offer-publication-v1:" + offer["offer_id"], data, references)
            self._validate_retained(**self.ledger.read(reference)["data"]["offer_capture"], references=references)
            return reference

    @_strict
    def active(self):
        from .ledger import KINDS as LEDGER_KINDS, LedgerRef, MAX_RECORD_BYTES, MAX_LEDGER_BYTES, MAX_LEDGER_RECORDS
        from .operational_pilot import metadata_inventory
        # Publication is a separate channel: a malformed unrelated forecast or
        # outcome must not suppress a valid offer. Still check bounded inventory,
        # all input envelope checksums (needed to classify them), every selected
        # offer's typed meaning, exact raw refs, and its correction graph.
        inventory, count, size = self.ledger._inventory()
        metadata = metadata_inventory(self.root)
        _require(count + metadata["file_count"] <= MAX_LEDGER_RECORDS
                 and size + metadata["total_bytes"] <= MAX_LEDGER_BYTES, "Retained offers exceed shared ledger budget")
        index = {kind: {} for kind in LEDGER_KINDS}
        retained = []
        for path, _ in inventory["input_captures"]:
            payload = read_receipt(path, max_bytes=MAX_RECORD_BYTES)
            if type(payload) is not dict or type(payload.get("data")) is not dict:
                raise IntegrityError("Cannot safely classify a malformed input receipt")
            if "offer_capture" not in payload["data"]:
                continue
            reference = LedgerRef("input_captures", path.stem, digest(payload))
            payload = self.ledger.read(reference)
            capture = payload["data"]["offer_capture"]
            _fields(capture, {"offer", "admission"}, "retained offer")
            refs = tuple(LedgerRef.from_record(value) for value in payload["references"])
            self._validate_retained(**capture, references=refs)
            _require(payload["data"]["identity"] == self._identity(capture["offer"])
                     and payload["logical_id"] == "offer-publication-v1:" + capture["offer"]["offer_id"],
                     "Retained offer identity/logical ID mismatch")
            _require(all(utc(self.ledger.read(ref)["received_at"]) <= utc(payload["received_at"]) for ref in refs),
                     "Retained source reference chronology mismatch")
            index["input_captures"][reference.record_id] = payload
            retained.append((reference, capture))
        offer_ids = set(index["input_captures"])
        for path, _ in inventory["corrections"]:
            payload = read_receipt(path, max_bytes=MAX_RECORD_BYTES)
            _require(type(payload) is dict and type(payload.get("data")) is dict, "Cannot classify malformed correction")
            old = payload.get("supersedes")
            new = payload.get("data", {}).get("replacement")
            relevant = any(type(ref) is dict and ref.get("kind") == "input_captures"
                           and ref.get("record_id") in offer_ids for ref in (old, new))
            if relevant:
                reference = LedgerRef("corrections", path.stem, digest(payload))
                payload = self.ledger.read(reference)
                for value in payload["references"]:
                    target = LedgerRef.from_record(value)
                    _require(target.kind == "input_captures" and target.record_id in offer_ids,
                             "Offer correction references a non-offer record")
                    _require(utc(self.ledger.read(target)["received_at"]) <= utc(payload["received_at"]),
                             "Offer correction precedes its referenced original/replacement")
                index["corrections"][reference.record_id] = payload
        superseded = set(self.ledger._correction_map(index))
        active = []
        for reference, capture in retained:
            if reference not in superseded:
                active.append((reference, capture))
        return active

    def correct(self, original, replacement, *, reason):
        from .ledger import SCHEMA
        _text(reason, "correction reason", 1000)
        with self.store.single_writer():
            self.active()
            old, new = self.ledger.read(original), self.ledger.read(replacement)
            _require("offer_capture" in old["data"] and "offer_capture" in new["data"], "Only offer corrections are admitted here")
            logical = f"supersedes:{original.kind}:{original.record_id}"
            existing = self.ledger._existing("corrections", logical)
            if existing is None:
                payload = {"schema_version": SCHEMA, "kind": "corrections", "record_id": digest({"kind": "corrections", "logical_id": logical}),
                    "logical_id": logical, "received_at": stamp(datetime.now(timezone.utc)), "data": {"reason": reason, "replacement": replacement.to_record()},
                    "references": [original.to_record(), replacement.to_record()], "supersedes": original.to_record(), "persistence_status": "LOCAL_RECEIPT_ONLY"}
                self._check_budget(payload)
            reference = self.ledger.correct(original, replacement, reason=reason)
            self.active()
            return reference


def make_asset(root, *, now, raw_reader=None):
    captures = OfferStore(root, raw_reader=raw_reader).active()
    offers = [item["offer"] for _, item in captures]
    admissions = [item["admission"] for _, item in captures if item["admission"] is not None]
    schema = NATIVE_ASSET_SCHEMA if any(item.get("schema_version") == "nba-native-player-offer-v2" for item in offers) else ASSET_SCHEMA
    asset = seal({"schema_version": schema, "league": "NBA", "generated_at": stamp(utc(now)),
                  "status": "OFFER_ONLY_RESEARCH", "category_inventory": list(CATEGORIES),
                  "admissions": admissions, "offers": offers,
                  "unavailable_reasons": [] if offers else [
                      "No complete player offer has a retained source contract and a reviewed permission basis for publication. Prices alone do not establish those requirements."]}, "asset_id")
    return validate_asset(asset, now=now)


_ADMITTED_MATCH_VIEWS = WeakKeyDictionary()


class _AdmittedForecastView:
    """A read-only view of validated originals, never a new evidence lane.

    Copies of the displayed dictionaries cannot mutate the validated matching
    fields. A caller-supplied dictionary/eligible flag cannot create this view.
    """
    __slots__ = ("_raw", "__weakref__")

    def __init__(self, payload):
        object.__setattr__(self, "_raw", canonical(payload))

    def __setattr__(self, key, value):
        raise AttributeError("An admitted forecast matching view is immutable")

    def __getitem__(self, key):
        return json.loads(self._raw)[key]


def _production_match_records(collection, *, at):
    from . import sdv_production_publication as production
    _require(type(collection) is dict and type(collection.get("pages")) is list,
             "Offer matching requires the original production index and pages")
    index, pages = collection["index"], collection["pages"]
    production.validate_index(index, now=at)
    _require(len(pages) == len(index["pages"]), "Offer matching omitted a declared production page")
    records, total = [], len(canonical(index))
    for descriptor, page in zip(index["pages"], pages):
        production.validate_page(page, generated_at=index["generated_at"], game_date=descriptor["game_date"])
        raw = canonical(page)
        _require(hashlib.sha256(raw).hexdigest() == descriptor["sha256"]
                 and len(page["records"]) == descriptor["record_count"],
                 "Offer matching production page hash/count differs")
        total += len(raw)
        _require(total <= production.MAX_TOTAL_BYTES, "Offer matching production byte budget exceeded")
        records.extend(page["records"])
    production.validate_records(records, generated_at=index["generated_at"], allow_development=True)
    production._coverage(index, records)
    _require(production.counts(records) == index["counts"], "Offer matching production counts differ")
    for day in index["dates"]:
        rows = [row for page in pages if page["game_date"] == day["game_date"] for row in page["records"]]
        _require(production.counts(rows) == day["counts"], "Offer matching production date counts differ")
    originals = [(row, production.original_record(row)) for row in records]
    inputs = {body["input_id"]: body for _, body in originals
              if body["schema_version"] == "nba-sdv-production-input-v1"}
    # Shared authority/input rows may appear on multiple date pages; matching
    # never displays a repeated original as another model.
    forecasts = {body["forecast_id"]: {"reference": row["reference"], "body": body,
                                       "admission": row["admission"]}
                 for row, body in originals if body["schema_version"] == "nba-sdv-production-forecast-v1"}
    return list(forecasts.values()), inputs


@_strict
def offer_research_forecasts(*, legacy=(), paired=(), daily=None, production=None, at):
    """Adapt fully validated admitted originals for exact, price-free matching.

    This does not admit offers, issue forecasts or replace their schema/lane.
    Daily authorization and production authority, input and remote-completion
    relationships are checked before a forecast can enter this private view.
    """
    _require(isinstance(legacy, (list, tuple)) and isinstance(paired, (list, tuple)),
             "Invalid offer research forecast collections")
    result = [*legacy, *paired]

    def append(rows, inputs, kind, lane, published_at):
        for row in rows:
            body = row["body"]
            if not (row["admission"]["eligible"] and body["mode"] == "PROSPECTIVE_RESEARCH"
                    and body["evidence_lane"] == lane):
                continue
            input_body = inputs.get(body["input_id"])
            _require(input_body is not None and body["event_snapshot_id"] == input_body["event"]["event_snapshot_id"],
                     "Offer matching lost the exact admitted forecast input")
            view = _AdmittedForecastView({"kind": kind, "reference": row["reference"], "original": body,
                                           "admission": row["admission"], "input": input_body})
            admission = row["admission"]
            completed = ([admission["local_persistence_completed_at"], admission["remote_recovery_completed_at"]]
                         if kind == "SDV_DAILY" else [admission["local_completed_at"], admission["remote_recovered_at"]])
            _ADMITTED_MATCH_VIEWS[view] = canonical({"forecast": {**body,
                "league": input_body["event"]["league"], "id_namespace": input_body["event"]["id_namespace"],
                "event_version": body["event_snapshot_id"]},
                "available_at": max([published_at, *completed], key=_clock)})
            result.append(view)

    if daily is not None:
        from . import sdv_daily_publication
        sdv_daily_publication.validate_asset(daily, now=at)
        append(daily["forecasts"], {body["input_id"]: body for body in daily["inputs"]},
               "SDV_DAILY", "DAILY_SNAPSHOT_PROSPECTIVE", daily["generated_at"])
    if production is not None:
        rows, inputs = _production_match_records(production, at=at)
        append(rows, inputs, "SDV_PRODUCTION", "SDV_PRODUCTION_PROSPECTIVE", production["index"]["generated_at"])
    return result


def match_research_forecast(offer, forecast, *, at):
    """Exact semantic/time match only. Does not compute EV or confer eligibility."""
    if offer.get("schema_version") == "nba-native-player-offer-v2":
        from .native_offer import validate_native_offer
        validate_native_offer(offer, now=at)
        # Source-native identity is enough to describe the offer. It is not a
        # reviewed cross-provider event/version join, even when times coincide.
        return {"status": "UNMATCHED", "reasons": [
            "Native event requires a reviewed canonical event/version crosswalk; "
            + offer["event"]["forecast_match_status"]], "qualification": "UNAVAILABLE",
            "ticket_eligible": False, "ev": None}
    admitted = _ADMITTED_MATCH_VIEWS.get(forecast) if isinstance(forecast, _AdmittedForecastView) else None
    admitted = json.loads(admitted) if admitted is not None else None
    forecast = admitted["forecast"] if admitted is not None else forecast
    if not isinstance(forecast, dict):
        forecast = {}
    reasons = []
    for field in ("league", "id_namespace", "event_id", "player_id", "team_id", "opponent_id",
                  "event_starts_at", "period", "extra_time_policy"):
        if forecast.get(field) != offer[field]:
            reasons.append("Forecast and offer differ: " + field)
    version = forecast.get("event_version", forecast.get("prospective", {}).get("event_version"))
    if version != offer["event_version"]:
        reasons.append("Forecast and offer have different or absent event versions")
    if not any(item.get("code") == offer["stat"] and item.get("units") == offer["units"] for item in forecast.get("categories", [])):
        reasons.append("Forecast does not support the exact offered category and units")
    try:
        when = utc(at)
        if admitted is not None and when < _clock(admitted["available_at"]):
            reasons.append("Required forecast persistence, remote recovery and publication were not yet available")
        if not (_clock(offer["observed_at"]) <= _clock(offer["imported_at"]) <= when < _clock(offer["event_starts_at"])
                and _clock(forecast["cutoff_at"]) <= _clock(forecast["issued_at"]) <= when):
            reasons.append("Forecast/offer were not both available at this pregame decision time")
    except (KeyError, IntegrityError, ValueError, TypeError):
        reasons.append("Missing or invalid forecast decision clocks")
    if (offer["evidence_lane"] != "REAL_TIME_CAPTURED" or (admitted is None and forecast.get("evidence_lane") != "REAL_TIME_CAPTURED")
            or offer["market_status"] != "PRE_GAME" or forecast.get("conditioning") != "CONDITIONAL_ON_APPEARANCE"):
        reasons.append("A genuinely captured pregame research forecast and offer are required")
    return {"status": "UNMATCHED" if reasons else "MATCHED_RESEARCH_ONLY", "reasons": reasons,
            "qualification": "UNAVAILABLE", "ticket_eligible": False, "ev": None}
