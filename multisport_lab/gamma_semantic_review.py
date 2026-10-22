"""Replay one retained Gamma contract plus the separately reviewed CLOB witness.

Offline, local review only. This does not collect, publish, issue forecasts, trade,
or modify the original v1 observation. Missing settlement facts remain missing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re

from .gamma_offer_review import inspect_bundle, original
from .integrity import (IntegrityError, _bounded_bytes, _decode, canonical, load_json,
                        read_receipt, stamp, utc, write_receipt)
from .offer_import import UNITS
from .semantic_offer import (MAX_ORIGINAL_BYTES, SCHEMA, replay_semantic_offer,
                             seal_semantic_offer)

VERSION = "gamma-exact-contract-semantic-review-2"
SUPPLEMENT_LABELS = ("clob-market-info-doc", "polymarket-help-root",
                     "polymarket-help-en", "clob-selected-market")


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def strict(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except IntegrityError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, StopIteration) as error:
            raise IntegrityError("Malformed retained semantic input: " + str(error)) from error
    return checked


def _supplement(directory: Path, prior: Path, *, now):
    """One shared counter, exact retained originals, and no implicit redirects."""
    ledger = load_json(directory / "requests.json")
    entries = ledger.get("requests")
    require(ledger.get("limit") == 4 and type(entries) is list and len(entries) == 4
            and ledger.get("max_response_bytes") == MAX_ORIGINAL_BYTES,
            "Expected the completed, bounded four-request supplement")
    require(ledger.get("parent_request_ledger_sha256") == hashlib.sha256(
        _bounded_bytes(prior / "requests.json", MAX_ORIGINAL_BYTES)).hexdigest(),
        "Supplement does not reference these original observations")
    for ordinal, (entry, label) in enumerate(zip(entries, SUPPLEMENT_LABELS), 1):
        require(entry.get("label") == label and entry.get("ordinal") == ordinal
                and entry.get("automatic_redirects") is False and entry.get("retries") == 0,
                "Unaccounted supplement request, redirect or retry")
        require(load_json(directory / (label + ".metadata.json")) == entry,
                "Supplement ledger/sidecar mismatch")
        raw = _bounded_bytes(directory / (label + ".body"), MAX_ORIGINAL_BYTES)
        require(entry.get("complete_body") is True and type(entry.get("raw_bytes")) is int
                and entry["raw_bytes"] == len(raw)
                and entry.get("raw_sha256") == hashlib.sha256(raw).hexdigest(),
                "Supplement original hash/size mismatch")
        require(entry.get("url") == entry.get("final_url")
                and utc(entry["request_started_at"]) <= utc(entry["observed_at"]) <= utc(now),
                "Supplement redirects/clocks are inconsistent")
    expected = (
        ("https://docs.polymarket.com/api-reference/markets/get-clob-market-info", 200),
        ("https://help.polymarket.com", 302),
        ("https://help.polymarket.com/en/", 200),
    )
    for entry, (url, status) in zip(entries, expected):
        require(entry["url"] == url and entry.get("http_status") == status,
                "Supplement documentation route/status changed")
    require(entries[1].get("location") == entries[2]["url"],
            "Help Center redirect was not explicitly accounted for")
    decision = load_json(directory / "clob-source-decision.json")
    require(decision.get("decision") == "ALLOW_EXACT_PUBLIC_CREDENTIALLESS_INFORMATIONAL_GET"
            and decision.get("exact_url") == entries[3]["url"]
            and utc(entries[0]["observed_at"]) <= utc(decision["recorded_at"])
            <= utc(entries[3]["request_started_at"])
            and decision.get("public_redistribution_admitted") is False,
            "Missing separate pre-request CLOB scope/auth review")
    require(entries[3].get("http_status") == 200, "No successful exact-condition CLOB original")
    return ledger


@strict
def load_inputs(prior: Path | str, supplement: Path | str, *, now):
    """Validate/recover retained bytes. A local scope declaration is not a grant."""
    prior, supplement = Path(prior), Path(supplement)
    old_review, readiness = inspect_bundle(prior, now=now)
    selected, selected_meta = original(prior, "gamma-edwards-market")
    event, event_meta = original(prior, "gamma-game-event")
    crosswalk = readiness["canonical_player_crosswalk"]
    rows = [r for r in old_review["observations"] if r["source_market_id"] == selected["id"]]
    require(len(rows) == 1 and rows[0]["player_identity"] == crosswalk["identity"],
            "Selected subject lacks its independently reviewed canonical identity")
    ledger = _supplement(supplement, prior, now=now)
    raw_clob = _bounded_bytes(supplement / "clob-selected-market.body", MAX_ORIGINAL_BYTES)
    clob = _decode(raw_clob)
    expected_url = "https://clob.polymarket.com/clob-markets/" + selected["conditionId"]
    require(ledger["requests"][-1]["url"] == expected_url
            and type(clob) is dict and clob.get("c") == selected["conditionId"]
            and utc(clob["gst"]) == utc(event["startTime"]),
            "CLOB condition/start does not match the original contract")
    tokens = clob.get("t")
    require(type(tokens) is list and len(tokens) == 2
            and {x.get("o") for x in tokens} == {"Yes", "No"}
            and len({x.get("t") for x in tokens}) == 2
            and all(type(x.get("t")) is str and re.fullmatch(r"[1-9][0-9]*", x["t"]) for x in tokens)
            and {x["t"] for x in tokens} == set(json.loads(selected["clobTokenIds"])),
            "CLOB outcome tokens conflict with the retained Gamma token set")
    evidence, originals = [], {}
    sources = (
        ("market", prior, "gamma-edwards-market", selected.get("updatedAt")),
        ("event", prior, "gamma-game-event", event.get("updatedAt")),
        ("identity", prior, "wikidata-edwards-entity", None),
        ("identifier_properties", prior, "wikidata-identifier-properties", None),
        ("clob", supplement, "clob-selected-market", None),
        ("clob_doc", supplement, "clob-market-info-doc", None),
        ("help_redirect", supplement, "polymarket-help-root", None),
        ("help_index", supplement, "polymarket-help-en", None),
    )
    for key, directory, label, updated in sources:
        meta = load_json(directory / (label + ".metadata.json"))
        raw = _bounded_bytes(directory / (label + ".body"), MAX_ORIGINAL_BYTES)
        require(len(raw) == meta["raw_bytes"] and hashlib.sha256(raw).hexdigest() == meta["raw_sha256"],
                "Recovered semantic evidence changed")
        evidence.append({"id": key, "url": meta["url"],
            "content_type": meta["content_type"].split(";", 1)[0],
            "raw_sha256": meta["raw_sha256"], "raw_bytes": len(raw),
            "request_started_at": stamp(utc(meta["request_started_at"])),
            "observed_at": stamp(utc(meta["observed_at"])),
            "source_updated_at": stamp(utc(updated)) if updated else None})
        originals[key] = raw
    return {"selected": selected, "event": event, "row": rows[0], "crosswalk": crosswalk,
            "clob": clob, "evidence": evidence, "originals": originals, "ledger": ledger,
            "primary_clock": stamp(utc(selected_meta["observed_at"]))}


@strict
def build_contract(prior, supplement, *, now, evidence_lane="ACTUAL_SOURCE_OBSERVATION"):
    data = load_inputs(prior, supplement, now=now)
    selected, event, row = data["selected"], data["event"], data["row"]
    no_sentence = re.search(r'This market will resolve to "No" if .*? during the game\.',
                            selected["description"], flags=re.S)
    require(no_sentence is not None, "The source's complementary NO predicate is missing")
    settlement = {key: row["settlement"].get(key) for key in (
        "participation", "dnp", "postponement", "ties", "official_stat_source", "stat_corrections")}
    settlement["ties"] = no_sentence.group(0)
    c = {"schema_version": SCHEMA, "scope": "LOCAL_REVIEW_ONLY", "evidence_lane": evidence_lane,
        "source": {"name": "Polymarket", "venue": "Polymarket", "product": "binary_event_contract"},
        "normalized_at": stamp(utc(now)), "contract_observed_at": data["primary_clock"],
        "knowledge_observed_at": max(x["observed_at"] for x in data["evidence"]),
        "primary_evidence_id": "market", "category_inventory": list(UNITS),
        "player": {"source_label": row["player_name"], "canonical_identity": {
            **data["crosswalk"]["identity"], "label": row["player_name"]}, "native_provider_id": None},
        "event": {"namespace": "polymarket_gamma", "id": event["id"], "label": event["title"],
            "starts_at": stamp(utc(event["startTime"])), "participants": [
                {"id": str(x["id"]), "label": x["name"], "role": x["ordering"]} for x in event["teams"]],
            "player_team_id": None, "opponent_id": None, "event_version": None,
            "source_version_literal": event.get("version")},
        "selection": {"kind": "MARKET_OUTCOME_LABEL", "market_id": selected["id"],
            "condition_id": selected["conditionId"], "outcome_label": "Yes",
            "native_token_id": next(x["t"] for x in data["clob"]["t"] if x["o"] == "Yes")},
        "predicate": {"category": row["category"], "units": UNITS[row["category"]],
            "operator": row["operator"], "threshold": row["threshold"], "period": row["period"],
            "extra_time_policy": row["overtime"], "variant": row["variant"]},
        "settlement": settlement, "price": {"status": "PRICE_UNAVAILABLE", "value": None},
        "unassigned_source_economics": {"outcomes": row["prices_as_supplied"]["outcomes"],
            "outcome_prices": row["prices_as_supplied"]["outcomePrices"],
            "best_bid": row["prices_as_supplied"]["bestBid"], "best_ask": row["prices_as_supplied"]["bestAsk"]},
        "execution_review": {"eligible": False, "flags": {
            "restricted": selected.get("restricted"), "ready": selected.get("ready"),
            "funded": selected.get("funded"), "accepting_orders": selected.get("acceptingOrders"),
            "context_requires_regen": event.get("eventMetadata", {}).get("context_requires_regen")}},
        "evidence": data["evidence"], "bindings": [],
        "price_binding_gaps": ["PRICE_TO_SELECTION_UNVERIFIED"],
        "public_admission": False, "ticket_eligibility": False, "qualification": "UNAVAILABLE"}
    def bind(field, evidence, pointer, transform="direct"):
        c["bindings"].append({"field": field, "evidence_id": evidence, "pointer": pointer, "transform": transform})
    bind("player.source_label", "market", "/question", "question_player")
    bind("player.canonical_identity", "identity", "/entities/" + data["crosswalk"]["identity"]["id"], "wikidata_identity")
    for key, pointer, transform in (("id", "/id", "string"), ("label", "/title", "direct"),
            ("starts_at", "/startTime", "utc"), ("participants", "/teams", "gamma_teams")):
        bind("event." + key, "event", pointer, transform)
    if c["event"]["source_version_literal"] is not None:
        bind("event.source_version_literal", "event", "/version", "source_version_literal")
    for field, pointer, transform in (("market_id", "/id", "string"),
            ("condition_id", "/conditionId", "direct"), ("outcome_label", "/outcomes", "outcome_label")):
        bind("selection." + field, "market", pointer, transform)
    bind("selection.native_token_id", "clob", "", "clob_token")
    for field, pointer, transform in (("category", "/sportsMarketType", "category"),
            ("units", "/sportsMarketType", "units"), ("operator", "/description", "yes_operator"),
            ("threshold", "/question", "question_threshold"), ("period", "/description", "full_game"),
            ("extra_time_policy", "/description", "overtime")):
        if c["predicate"][field] is not None:
            bind("predicate." + field, "market", pointer, transform)
    for key, value in settlement.items():
        if value is not None:
            bind("settlement." + key, "market", "/description", "text_contains")
    for field, pointer in (("outcomes", "/outcomes"), ("outcome_prices", "/outcomePrices"),
                           ("best_bid", "/bestBid"), ("best_ask", "/bestAsk")):
        if c["unassigned_source_economics"][field] is not None:
            bind("unassigned_source_economics." + field, "market", pointer,
                 "json_array" if field in {"outcomes", "outcome_prices"} else "decimal_lexeme")
    for field, pointer in (("restricted", "/restricted"), ("ready", "/ready"),
                           ("funded", "/funded"), ("accepting_orders", "/acceptingOrders")):
        if c["execution_review"]["flags"][field] is not None:
            bind("execution_review.flags." + field, "market", pointer)
    if c["execution_review"]["flags"]["context_requires_regen"] is not None:
        bind("execution_review.flags.context_requires_regen", "event", "/eventMetadata/context_requires_regen")
    contract = seal_semantic_offer(c)
    replay = replay_semantic_offer(contract, data["originals"], now=now)
    return contract, replay


@strict
def persist_review(prior, supplement, destination, *, now, source_root,
                   evidence_lane="ACTUAL_SOURCE_OBSERVATION"):
    """Create once; retries independently replay existing content without re-dating."""
    source_root = Path(source_root).resolve()
    destination = Path(os.path.abspath(destination))
    require(destination.is_relative_to(source_root / ".local-data")
            and destination != source_root / ".local-data", "Private review must stay in ignored local storage")
    current = source_root
    for part in destination.relative_to(source_root).parts:
        current = current / part
        require(not current.is_symlink() and (not current.exists() or current.is_dir()),
                "Review parent must be a real directory")
    for name in ("contract.receipt.json", "replay.receipt.json", "contract.json"):
        p = destination / name
        require(not p.is_symlink() and (not p.exists() or p.is_file()), "Review file must be regular")
    receipt = destination / "contract.receipt.json"
    if receipt.exists():
        contract = read_receipt(receipt)
        require(contract["evidence_lane"] == evidence_lane, "Recovery evidence lane differs")
        inputs = load_inputs(prior, supplement, now=now)
        require(contract["evidence"] == inputs["evidence"], "Recovery inputs differ from the original review")
        replay = replay_semantic_offer(contract, inputs["originals"], now=now)
        recovered = True
    else:
        contract, replay = build_contract(prior, supplement, now=now, evidence_lane=evidence_lane)
        destination.mkdir(parents=True, exist_ok=True)
        write_receipt(receipt, contract)
        recovered = False
    write_receipt(destination / "replay.receipt.json", replay)
    p = destination / "contract.json"
    raw = canonical(contract)
    if p.exists():
        require(p.read_bytes() == raw, "Conflicting private review asset")
    else:
        with p.open("xb") as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
    return {"schema_version": "gamma-local-semantic-write-v2", "contract_id": contract["contract_id"],
            "semantic_status": contract["semantic_status"], "required_gaps": contract["required_gaps"],
            "recovered_existing": recovered, "normalized_at": contract["normalized_at"],
            "knowledge_observed_at": contract["knowledge_observed_at"], "replay": replay}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prior-bundle", type=Path, required=True)
    p.add_argument("--supplement", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(persist_review(args.prior_bundle, args.supplement, args.output,
        now=datetime.now(timezone.utc), source_root=Path(__file__).resolve().parents[1]), sort_keys=True))


if __name__ == "__main__":
    main()
