"""Offline v2 semantic offer review, isolated from public offer-v1 admission.

An external canonical player and a declared market/outcome selection are enough
identity representations for a price-free semantic contract. Missing native IDs,
prices and execution eligibility do not determine semantic completeness. Actual
source meaning, affiliation, version and settlement evidence still must exist.
Hashes verify local bytes, not provider authenticity, rights or availability.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import re
from urllib.parse import urlsplit

from .integrity import IntegrityError, _decode, canonical, digest, stamp, utc
from .offer_import import UNITS
from .offer_publication import SETTLEMENT_FIELDS

SCHEMA = "nba-local-semantic-offer-v2"
MAX_CONTRACT_BYTES = 256 * 1024
MAX_ORIGINAL_BYTES = 2 * 1024 * 1024
MAX_CONTRACTS = 32
TOP = {"schema_version", "scope", "evidence_lane", "contract_id", "source", "normalized_at",
       "contract_observed_at", "knowledge_observed_at", "primary_evidence_id", "category_inventory",
       "player", "event", "selection", "predicate", "settlement", "price", "unassigned_source_economics",
       "execution_review", "evidence", "bindings", "required_gaps", "price_binding_gaps",
       "semantic_status", "completed_at", "public_admission", "ticket_eligibility", "qualification"}
EVIDENCE = {"id", "url", "content_type", "raw_sha256", "raw_bytes", "request_started_at", "observed_at", "source_updated_at"}
FLAGS = {"restricted", "ready", "funded", "accepting_orders", "context_requires_regen"}
TRANSFORMS = {"direct", "string", "utc", "json_array", "outcome_label", "decimal_lexeme", "question_player", "question_threshold",
              "category", "units", "yes_operator", "full_game", "overtime", "gamma_teams",
              "wikidata_identity", "source_version_literal", "observed_snapshot_version",
              "affiliation_team", "affiliation_opponent", "native_player_id", "clob_token", "text_contains"}
HOSTS = {"gamma-api.polymarket.com", "clob.polymarket.com", "docs.polymarket.com", "help.polymarket.com", "www.wikidata.org"}
SHA = re.compile(r"[a-f0-9]{64}\Z")
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
CLOCK = re.compile(r"[0-9]{4}-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9]{6}Z\Z")
BINDING_ROLES = {
    "player.source_label": ("market", "/question", "question_player"),
    "player.native_provider_id": ("market", "/player", "native_player_id"),
    "event.id": ("event", "/id", "string"),
    "event.label": ("event", "/title", "direct"),
    "event.starts_at": ("event", "/startTime", "utc"),
    "event.participants": ("event", "/teams", "gamma_teams"),
    "event.source_version_literal": ("event", "/version", "source_version_literal"),
    "event.event_version": ("event", "", "observed_snapshot_version"),
    "event.player_team_id": ("affiliation", "", "affiliation_team"),
    "event.opponent_id": ("affiliation", "", "affiliation_opponent"),
    "selection.market_id": ("market", "/id", "string"),
    "selection.condition_id": ("market", "/conditionId", "direct"),
    "selection.outcome_label": ("market", "/outcomes", "outcome_label"),
    "selection.native_token_id": ("clob", "", "clob_token"),
    "predicate.category": ("market", "/sportsMarketType", "category"),
    "predicate.units": ("market", "/sportsMarketType", "units"),
    "predicate.operator": ("market", "/description", "yes_operator"),
    "predicate.threshold": ("market", "/question", "question_threshold"),
    "predicate.period": ("market", "/description", "full_game"),
    "predicate.extra_time_policy": ("market", "/description", "overtime"),
    "unassigned_source_economics.outcomes": ("market", "/outcomes", "json_array"),
    "unassigned_source_economics.outcome_prices": ("market", "/outcomePrices", "json_array"),
    "unassigned_source_economics.best_bid": ("market", "/bestBid", "decimal_lexeme"),
    "unassigned_source_economics.best_ask": ("market", "/bestAsk", "decimal_lexeme"),
    "execution_review.flags.restricted": ("market", "/restricted", "direct"),
    "execution_review.flags.ready": ("market", "/ready", "direct"),
    "execution_review.flags.funded": ("market", "/funded", "direct"),
    "execution_review.flags.accepting_orders": ("market", "/acceptingOrders", "direct"),
    "execution_review.flags.context_requires_regen": ("event", "/eventMetadata/context_requires_regen", "direct"),
}
CORRECTION_POLICY_TEXT = re.compile(
    r"\b(?:stat(?:istic(?:al|s)?)?[ \t\r\n\f\v-]+corrections?|regrad(?:e|es|ed|ing)|re[- ]?settl(?:e|es|ed|ing|ements?))\b", re.I | re.ASCII)


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def fields(value, expected, label):
    require(type(value) is dict and set(value) == set(expected), "Invalid " + label + " fields")


def text(value, maximum=2000):
    return type(value) is str and 0 < len(value) <= maximum and value.strip() == value


def clock(value):
    require(type(value) is str and CLOCK.fullmatch(value) is not None, "Microsecond UTC clock required")
    try:
        result = utc(value)
    except (ValueError, TypeError) as error:
        raise IntegrityError("Invalid clock") from error
    require(stamp(result) == value, "Invalid calendar clock")
    return result


def _target(contract, field):
    target = contract
    for part in field.split("."):
        require(type(target) is dict and part in target, "Unknown semantic binding field")
        target = target[part]
    return target


def required_gaps(contract):
    """Only semantic requirements: native IDs, token IDs and prices are absent."""
    gaps = []
    for value, name in ((contract["player"]["canonical_identity"], "PLAYER_CANONICAL_IDENTITY"),
                        (contract["event"]["player_team_id"], "PLAYER_TEAM"),
                        (contract["event"]["opponent_id"], "PLAYER_OPPONENT"),
                        (contract["event"]["event_version"], "EVENT_VERSION"),
                        (contract["predicate"]["period"], "PERIOD"),
                        (contract["predicate"]["extra_time_policy"], "OVERTIME")):
        if value is None:
            gaps.append(name)
    for name in sorted(SETTLEMENT_FIELDS):
        if contract["settlement"][name] is None:
            gaps.append("SETTLEMENT_" + name.upper())
    return gaps


def binding_fields(contract):
    required = {"player.source_label", "event.id", "event.label", "event.starts_at", "event.participants",
                "selection.market_id", "selection.condition_id", "selection.outcome_label",
                "predicate.category", "predicate.units", "predicate.operator", "predicate.threshold",
                "unassigned_source_economics.outcomes"}
    optional = ["player.canonical_identity", "player.native_provider_id", "event.player_team_id", "event.opponent_id",
                "event.event_version", "event.source_version_literal", "selection.native_token_id",
                "predicate.period", "predicate.extra_time_policy"]
    optional += ["settlement." + name for name in sorted(SETTLEMENT_FIELDS)]
    optional += ["unassigned_source_economics." + name for name in ("outcome_prices", "best_bid", "best_ask")]
    optional += ["execution_review.flags." + name for name in sorted(FLAGS)]
    return required | {name for name in optional if _target(contract, name) is not None}


def allowed_binding_roles(contract, field):
    """Known v2 source roles; a matching alias is not the documented source field."""
    if field == "player.canonical_identity":
        identity = contract["player"]["canonical_identity"]
        return {("identity", "/entities/" + identity["id"], "wikidata_identity")}
    if field.startswith("settlement.") and field.split(".")[1] in SETTLEMENT_FIELDS:
        roles = {("market", "/description", "text_contains")}
        if contract["evidence_lane"] == "SYNTHETIC":
            roles.add(("market", "/settlement/" + field.split(".")[1], "direct"))
        return roles
    require(field in BINDING_ROLES, "No reviewed source role for semantic field")
    return {BINDING_ROLES[field]}


def seal_semantic_offer(contract):
    """Compute status and hash; verification/replay must still run afterwards."""
    record = deepcopy(contract)
    record.pop("contract_id", None)
    record["required_gaps"] = required_gaps(record)
    record["semantic_status"] = "INCOMPLETE" if record["required_gaps"] else "COMPLETE_LOCAL"
    record["completed_at"] = None if record["required_gaps"] else record["normalized_at"]
    record["contract_id"] = digest(record)
    return record


def validate_semantic_offer(contract, *, now):
    """Typed validation does not independently attest the provider or its meaning."""
    try:
        return _validate(contract, now=now)
    except IntegrityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise IntegrityError("Malformed semantic offer: " + str(error)) from error


def validate_semantic_batch(contracts, *, now):
    """Bound any caller's multi-contract review without changing the wire type."""
    require(type(contracts) is list and 1 <= len(contracts) <= MAX_CONTRACTS,
            "Semantic batch exceeds the unchanged 32-contract bound")
    require(len(canonical(contracts)) <= MAX_CONTRACT_BYTES, "Semantic batch exceeds 256 KiB")
    for contract in contracts:
        validate_semantic_offer(contract, now=now)
    require(len({contract["contract_id"] for contract in contracts}) == len(contracts), "Duplicate semantic contract")
    return contracts


def _validate(c, *, now):
    fields(c, TOP, "semantic offer")
    require(len(canonical(c)) <= MAX_CONTRACT_BYTES, "Semantic offer byte limit exceeded")
    require(c["schema_version"] == SCHEMA and c["scope"] == "LOCAL_REVIEW_ONLY"
            and c["evidence_lane"] in {"ACTUAL_SOURCE_OBSERVATION", "SYNTHETIC"}, "Unsupported semantic lane/version")
    require(c["public_admission"] is False and c["ticket_eligibility"] is False
            and c["qualification"] == "UNAVAILABLE", "Local semantic review cannot create admission or qualification")
    require(type(c["contract_id"]) is str and SHA.fullmatch(c["contract_id"])
            and c["contract_id"] == digest({k: v for k, v in c.items() if k != "contract_id"}), "Semantic offer seal mismatch")
    require(c["source"] == {"name": "Polymarket", "venue": "Polymarket", "product": "binary_event_contract"}, "Unsupported source/product")
    require(type(c["category_inventory"]) is list and c["category_inventory"] == list(UNITS), "All fourteen categories required")
    fields(c["player"], {"source_label", "canonical_identity", "native_provider_id"}, "player")
    p = c["player"]
    require(text(p["source_label"], 200), "Invalid source player label")
    identity = p["canonical_identity"]
    if identity is not None:
        fields(identity, {"namespace", "id", "label"}, "canonical identity")
        require(identity["namespace"] == "wikidata" and type(identity["id"]) is str
                and re.fullmatch(r"Q[1-9][0-9]*", identity["id"])
                and identity["label"] == p["source_label"], "Canonical/source player conflict")
    require(p["native_provider_id"] is None or text(p["native_provider_id"], 200), "Invalid optional native player ID")
    fields(c["event"], {"namespace", "id", "label", "starts_at", "participants", "player_team_id", "opponent_id", "event_version", "source_version_literal"}, "event")
    e = c["event"]
    require(e["namespace"] == "polymarket_gamma" and text(e["id"], 200) and text(e["label"], 300), "Invalid event identity")
    clock(e["starts_at"])
    require(type(e["participants"]) is list and len(e["participants"]) == 2, "Two source event participants required")
    for team in e["participants"]:
        fields(team, {"id", "label", "role"}, "event participant")
        require(text(team["id"], 200) and text(team["label"], 200) and team["role"] in {"away", "home"}, "Invalid participant identity")
    teams = {x["id"] for x in e["participants"]}
    require(len(teams) == 2 and {x["role"] for x in e["participants"]} == {"away", "home"}, "Conflicting participants")
    for key in ("player_team_id", "opponent_id"):
        require(e[key] is None or e[key] in teams, "Affiliation outside source matchup")
    require(e["player_team_id"] is None or e["opponent_id"] is None
            or e["player_team_id"] != e["opponent_id"], "Player team conflicts with opponent")
    if e["event_version"] is not None:
        fields(e["event_version"], {"kind", "value"}, "event snapshot version")
        require(e["event_version"]["kind"] == "OBSERVED_SNAPSHOT_SHA256"
                and type(e["event_version"]["value"]) is str and SHA.fullmatch(e["event_version"]["value"]), "Invalid observed snapshot version")
    require(e["source_version_literal"] is None or text(e["source_version_literal"], 200), "Invalid source version literal")
    fields(c["selection"], {"kind", "market_id", "condition_id", "outcome_label", "native_token_id"}, "selection")
    s = c["selection"]
    require(s["kind"] == "MARKET_OUTCOME_LABEL" and text(s["market_id"], 200)
            and type(s["condition_id"]) is str and re.fullmatch(r"0x[a-fA-F0-9]{64}", s["condition_id"])
            and s["outcome_label"] == "Yes", "Invalid declared market/outcome selection")
    require(s["native_token_id"] is None or (type(s["native_token_id"]) is str
            and re.fullmatch(r"[1-9][0-9]{0,100}", s["native_token_id"])), "Invalid optional token ID")
    fields(c["predicate"], {"category", "units", "operator", "threshold", "period", "extra_time_policy", "variant"}, "predicate")
    pred = c["predicate"]
    require(pred["category"] in UNITS and pred["units"] == UNITS[pred["category"]]
            and pred["operator"] == ">" and type(pred["threshold"]) is str
            and len(pred["threshold"]) <= 32 and DECIMAL.fullmatch(pred["threshold"])
            and Decimal(pred["threshold"]) <= Decimal("1000000")
            and pred["variant"] == "binary_player_stat_threshold", "Invalid statistic predicate")
    require(pred["period"] in {None, "full_game"} and pred["extra_time_policy"] in {None, "includes_overtime"}, "Unsupported period/overtime")
    fields(c["settlement"], SETTLEMENT_FIELDS, "settlement")
    for value in c["settlement"].values():
        require(value is None or (text(value) and value.upper() not in {"UNKNOWN", "UNRESOLVED", "TBD", "N/A", "UNVERIFIED"}), "Invalid settlement meaning")
    if c["settlement"]["stat_corrections"] is not None:
        require(CORRECTION_POLICY_TEXT.search(c["settlement"]["stat_corrections"]),
                "Generic finality does not establish statistical correction meaning")
    require(c["price"] == {"status": "PRICE_UNAVAILABLE", "value": None}, "This version does not admit assigned prices")
    fields(c["unassigned_source_economics"], {"outcomes", "outcome_prices", "best_bid", "best_ask"}, "unassigned economics")
    economics = c["unassigned_source_economics"]
    require(economics["outcomes"] == ["Yes", "No"], "Invalid source outcome labels")
    def price(value):
        return type(value) is str and len(value) <= 128 and re.fullmatch(r"(?:0(?:\.[0-9]+)?|1(?:\.0+)?)", value)
    require(economics["outcome_prices"] is None or (type(economics["outcome_prices"]) is list
            and len(economics["outcome_prices"]) == 2 and all(price(x) for x in economics["outcome_prices"])), "Invalid literal outcome price array")
    require(all(value is None or price(value) for value in (economics["best_bid"], economics["best_ask"])), "Invalid literal source bid/ask")
    fields(c["execution_review"], {"eligible", "flags"}, "execution review")
    require(c["execution_review"]["eligible"] is False, "Semantic review is not execution eligibility")
    fields(c["execution_review"]["flags"], FLAGS, "execution flags")
    require(all(value is None or type(value) is bool for value in c["execution_review"]["flags"].values()), "Invalid literal source flags")
    require(type(c["evidence"]) is list and 1 <= len(c["evidence"]) <= 16, "Bounded original evidence required")
    ids, observations = set(), []
    for evidence in c["evidence"]:
        fields(evidence, EVIDENCE, "original evidence")
        require(text(evidence["id"], 120) and evidence["id"] not in ids, "Duplicate/invalid evidence ID")
        ids.add(evidence["id"])
        require(text(evidence["url"], 2048), "Invalid bounded original evidence URL")
        url = urlsplit(evidence["url"])
        require(url.scheme == "https" and url.netloc in HOSTS and not url.username and not url.password and not url.fragment, "Original evidence outside declared sources")
        require(evidence["content_type"] in {"application/json", "text/html", "text/plain"}
                and type(evidence["raw_sha256"]) is str and SHA.fullmatch(evidence["raw_sha256"])
                and type(evidence["raw_bytes"]) is int and 0 <= evidence["raw_bytes"] <= MAX_ORIGINAL_BYTES, "Invalid original evidence digest/size")
        observed = clock(evidence["observed_at"])
        require(clock(evidence["request_started_at"]) <= observed, "Reversed capture clocks")
        if evidence["source_updated_at"] is not None:
            require(clock(evidence["source_updated_at"]) <= observed, "Source update follows capture")
        observations.append(observed)
    by_id = {item["id"]: item for item in c["evidence"]}
    require(c["primary_evidence_id"] in by_id and c["contract_observed_at"] == by_id[c["primary_evidence_id"]]["observed_at"], "Original contract clock was relabeled")
    primary_url = urlsplit(by_id[c["primary_evidence_id"]]["url"])
    require(primary_url.netloc == "gamma-api.polymarket.com" and primary_url.path == "/markets/" + s["market_id"]
            and not primary_url.query and by_id[c["primary_evidence_id"]]["content_type"] == "application/json", "Primary original is not the exact Gamma market route")
    require(clock(c["knowledge_observed_at"]) == max(observations)
            and max(observations) <= clock(c["normalized_at"]) <= utc(now), "Backdated enrichment/normalization clock")
    require(type(c["bindings"]) is list and len(c["bindings"]) <= 64, "Invalid bounded field bindings")
    bound = set()
    for binding in c["bindings"]:
        fields(binding, {"field", "evidence_id", "pointer", "transform"}, "field binding")
        require(text(binding["field"], 120) and binding["field"] not in bound
                and binding["evidence_id"] in ids and binding["transform"] in TRANSFORMS
                and type(binding["pointer"]) is str and len(binding["pointer"]) <= 1000
                and (binding["pointer"] == "" or binding["pointer"].startswith("/")), "Invalid/duplicate original binding")
        require(_target(c, binding["field"]) is not None, "Unresolved field cannot have a verified binding")
        bound.add(binding["field"])
    require(bound == binding_fields(c), "Missing or unexpected semantic/source field bindings")
    for binding in c["bindings"]:
        url = urlsplit(by_id[binding["evidence_id"]]["url"])
        field = binding["field"]
        choices = allowed_binding_roles(c, field)
        matching = [role for role, pointer, transform in choices
                    if binding["pointer"] == pointer and binding["transform"] == transform]
        require(len(matching) == 1, "Binding is not the reviewed source field/pointer/transform role")
        role = matching[0]
        if role == "market":
            require(binding["evidence_id"] == c["primary_evidence_id"], "Semantic fact does not bind its original market")
        elif role == "event":
            require(url.netloc == "gamma-api.polymarket.com" and url.path == "/events/" + e["id"] and not url.query,
                    "Event binding is not the exact retained Gamma event")
        elif role == "identity":
            require(url.netloc == "www.wikidata.org" and url.path == "/wiki/Special:EntityData/" + identity["id"] + ".json"
                    and not url.query, "Canonical witness URL/entity/pointer mismatch")
        elif role == "clob":
            require(url.netloc == "clob.polymarket.com" and url.path == "/clob-markets/" + s["condition_id"] and not url.query,
                    "Token binding is not the exact query-free CLOB condition route")
    gaps = required_gaps(c)
    require(c["required_gaps"] == gaps and c["price_binding_gaps"] == ["PRICE_TO_SELECTION_UNVERIFIED"], "Semantic/price gap inventory mismatch")
    require(c["semantic_status"] == ("INCOMPLETE" if gaps else "COMPLETE_LOCAL")
            and c["completed_at"] == (None if gaps else c["normalized_at"]), "Completion cannot be flag-flipped or backdated")
    return c


def _pointer(value, pointer):
    if pointer == "":
        return value
    for token in pointer[1:].split("/"):
        require(not re.search(r"~(?![01])", token), "Invalid JSON pointer escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if type(value) is list:
            require(re.fullmatch(r"0|[1-9][0-9]*", token) is not None and int(token) < len(value), "Invalid array pointer")
            value = value[int(token)]
        else:
            require(type(value) is dict and token in value, "Original JSON pointer missing")
            value = value[token]
    return value


def _transform(value, binding, c, evidence):
    op = binding["transform"]
    target = _target(c, binding["field"])
    if op == "direct": return value
    if op in {"string", "source_version_literal"}: return str(value)
    if op == "utc": return stamp(utc(value))
    if op == "decimal_lexeme": return value
    if op in {"json_array", "outcome_label", "clob_token"}:
        if op in {"json_array", "outcome_label"}:
            result = _decode(value.encode()) if type(value) is str else value
            if op == "json_array": return result
            require(result == ["Yes", "No"], "Declared outcome lacks source label")
            return c["selection"]["outcome_label"]
        require(urlsplit(evidence["url"]).netloc == "clob.polymarket.com"
                and urlsplit(evidence["url"]).path == "/clob-markets/" + c["selection"]["condition_id"]
                and not urlsplit(evidence["url"]).query
                and type(value) is dict and value.get("c") == c["selection"]["condition_id"], "Token witness belongs to another condition/source")
        rows = value.get("t")
        require(type(rows) is list and len(rows) == 2 and {row.get("o") for row in rows} == {"Yes", "No"}
                and len({row.get("t") for row in rows}) == 2, "CLOB binary token witness is ambiguous")
        if value.get("gst") is not None:
            require(stamp(utc(value["gst"])) == c["event"]["starts_at"], "CLOB/game start conflict")
        matches = [row["t"] for row in rows if row.get("o") == c["selection"]["outcome_label"]]
        require(len(matches) == 1, "CLOB outcome/token mapping ambiguous")
        return matches[0]
    if op in {"question_player", "question_threshold"}:
        match = re.fullmatch(r"(.+): (?:Points|Rebounds|Assists) O/U ((?:0|[1-9][0-9]*)(?:\.[0-9]+)?)", value)
        require(match is not None, "Unverified player/threshold question")
        return match.group(1 if op == "question_player" else 2)
    if op in {"category", "units"}:
        category = {"points": "PTS", "rebounds": "REB", "assists": "AST"}.get(value)
        require(category is not None, "Unsupported source family binding")
        return category if op == "category" else UNITS[category]
    if op == "yes_operator":
        name, line = c["player"]["source_label"], c["predicate"]["threshold"]
        noun = {"PTS": "points", "REB": "rebounds", "AST": "assists"}.get(c["predicate"]["category"])
        require(noun is not None and re.search(r'"Yes" if ' + re.escape(name) + r' (?:scores|records) more than '
                + re.escape(line) + r' (?:total )?' + noun + r' during the game\.', value), "Source predicate does not bind this player/stat/threshold")
        require(re.search(r'"No" if ' + re.escape(name) + r' (?:scores|records) '
                + re.escape(line) + ' ' + noun + r' or fewer during the game\.', value),
                "Source NO predicate does not complement the offered threshold")
        return ">"
    if op in {"full_game", "overtime"}:
        require("The entire game including all overtime periods will be considered." in value, "Period/overtime meaning unverified")
        return "full_game" if op == "full_game" else "includes_overtime"
    if op == "gamma_teams":
        require(type(value) is list and all(team.get("league") == "nba" for team in value), "Source teams not NBA")
        return [{"id": str(team["id"]), "label": team["name"], "role": team["ordering"]} for team in value]
    if op == "wikidata_identity":
        require(urlsplit(evidence["url"]).netloc == "www.wikidata.org"
                and "basketball player" in value["descriptions"]["en"]["value"], "Canonical identity lacks basketball/source context")
        return {"namespace": "wikidata", "id": value["id"], "label": value["labels"]["en"]["value"]}
    if op == "observed_snapshot_version":
        return {"kind": "OBSERVED_SNAPSHOT_SHA256", "value": digest(value)}
    if op in {"affiliation_team", "affiliation_opponent"}:
        identity = c["player"]["canonical_identity"]
        require(identity is not None and value.get("player_namespace") == identity["namespace"]
                and value.get("player_id") == identity["id"] and value.get("event_id") == c["event"]["id"], "Affiliation witness is not this player/event")
        return value["team_id" if op == "affiliation_team" else "opponent_id"]
    if op == "native_player_id":
        require(value.get("subject_type") == "player" and value.get("label") == c["player"]["source_label"], "Native player witness is not this subject")
        return value["id"]
    if op == "text_contains":
        require(type(value) is str and type(target) is str and target in value, "Reviewed source quotation missing")
        return target
    raise IntegrityError("Unknown reviewed transform")


def replay_semantic_offer(contract, originals, *, now):
    """Hash-check every original and replay every reviewed binding. No network."""
    validate_semantic_offer(contract, now=now)
    try:
        evidence = {item["id"]: item for item in contract["evidence"]}
        decoded, lexical = {}, {}
        for key, item in evidence.items():
            raw = originals[key]
            require(type(raw) is bytes and len(raw) <= MAX_ORIGINAL_BYTES and len(raw) == item["raw_bytes"]
                    and hashlib.sha256(raw).hexdigest() == item["raw_sha256"], "Original source hash/size mismatch")
            decoded[key] = _decode(raw) if item["content_type"] == "application/json" else raw.decode("utf-8")
            lexical[key] = json.loads(raw, parse_float=str, parse_int=str) if item["content_type"] == "application/json" else decoded[key]
        for binding in contract["bindings"]:
            item = evidence[binding["evidence_id"]]
            raw_value = _pointer((lexical if binding["transform"] == "decimal_lexeme" else decoded)[item["id"]], binding["pointer"])
            require(_transform(raw_value, binding, contract, item) == _target(contract, binding["field"]),
                    "Original semantic binding mismatch: " + binding["field"])
        primary = decoded[contract["primary_evidence_id"]]
        primary_lexical = lexical[contract["primary_evidence_id"]]
        require(type(primary) is dict and str(primary.get("id")) == contract["selection"]["market_id"]
                and primary.get("conditionId") == contract["selection"]["condition_id"], "Primary original market/condition identity conflict")
        question = re.fullmatch(r"(.+): (Points|Rebounds|Assists) O/U ((?:0|[1-9][0-9]*)(?:\.[0-9]+)?)", primary.get("question", ""))
        require(question is not None and question.group(1) == contract["player"]["source_label"]
                and {"Points": "PTS", "Rebounds": "REB", "Assists": "AST"}[question.group(2)] == contract["predicate"]["category"]
                and question.group(3) == contract["predicate"]["threshold"], "Question/player/category/threshold conflict")
        if primary_lexical.get("line") is not None:
            require(Decimal(str(primary_lexical["line"])) == Decimal(contract["predicate"]["threshold"]), "Supplied line contradicts source question")
        if primary.get("gameStartTime") is not None:
            require(stamp(utc(primary["gameStartTime"])) == contract["event"]["starts_at"], "Market/event start conflict")
        event_binding = next(binding for binding in contract["bindings"] if binding["field"] == "event.id")
        event = decoded[event_binding["evidence_id"]]
        event_lexical = lexical[event_binding["evidence_id"]]
        require(type(event) is dict and str(event.get("id")) == contract["event"]["id"],
                "Original event top-level identity conflict")
        if "markets" in event:
            rows = event["markets"]
            require(type(rows) is list and len(rows) <= 128 and all(type(row) is dict for row in rows),
                    "Malformed bounded event market membership")
            matches = [index for index, row in enumerate(rows)
                       if str(row.get("id")) == contract["selection"]["market_id"]]
            require(len(matches) == 1, "Selected contract missing or duplicated in original event")
            linked, linked_lexical = rows[matches[0]], event_lexical["markets"][matches[0]]
            for field in ("id", "conditionId", "question", "sportsMarketType", "gameStartTime", "description", "outcomes", "clobTokenIds"):
                require(linked.get(field) == primary.get(field), "Linked event/primary contract conflict: " + field)
            if linked_lexical.get("line") is not None or primary_lexical.get("line") is not None:
                require(linked_lexical.get("line") is not None and primary_lexical.get("line") is not None
                        and Decimal(str(linked_lexical["line"])) == Decimal(str(primary_lexical["line"])),
                        "Linked event/primary contract line conflict")
        return {"schema_version": "nba-local-semantic-replay-v2", "contract_id": contract["contract_id"],
                "originals_verified": len(evidence), "bindings_verified": len(contract["bindings"]),
                "semantic_status": contract["semantic_status"], "remote_durable_archive_verified": False,
                "public_admission": False, "ticket_eligibility": False}
    except IntegrityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, UnicodeDecodeError) as error:
        raise IntegrityError("Malformed original semantic binding: " + str(error)) from error
