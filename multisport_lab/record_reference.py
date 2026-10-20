"""Create/recover the fixed six historical publication exemplars, never picks."""
from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat

from .baseline import MODEL_VERSION, ForecastTarget, forecast_reference
from .forecast_contract import from_reference
from .integrity import IntegrityError, digest, read_receipt, stamp, utc, write_receipt
from .ledger import Ledger, LedgerRef
from .nba_data import NBAPlayerGame
from .research_pilot import MAX_BYTES, read_normalized_panel

PANEL_SHA256 = "489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c"
SOURCE_SHA256 = "29a29dc9efd055a93e069a0382ac830d98a13274bee655beba69d95cff099713"
SUMMARY_V1 = "reference-publication-002-v1"
SUMMARY_V2 = "reference-publication-002-v2"
SUMMARY_PATH = Path("evidence/research/reference-publication-002.json")
MAX_SUMMARY_BYTES = 128 * 1024
PURPOSE = "ENGINEERING_PUBLICATION_NOT_HELD_OUT_EVALUATION"
LANE = "RECONSTRUCTED_RESEARCH"
SELECTION_RULE = "docs/REFERENCE_PUBLICATION_002.md"
BASE_EXAMPLE_FIELDS = {"event_id", "player_id", "issued_at", "forecast_ref", "outcome_ref", "grade_ref"}
SUMMARY_FIELDS = {"schema_version", "recorded_at", "evidence_lane", "purpose", "selection_rule",
                  "model_commit", "normalized_input_sha256", "source_evidence_sha256", "examples",
                  "genuine_future_issuances", "financial_settlement"}


def _now():
    return datetime.now(timezone.utc)


def _clock(value):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value):
        raise IntegrityError("Publication summary clocks require microsecond UTC timestamps")
    return utc(value)


def _example_metadata(store, references):
    """Read clocks and metadata from original records, including retained outcomes."""
    refs = {}
    payloads = {}
    for name, expected_kind in (("forecast", "forecasts"), ("outcome", "outcomes"), ("grade", "grades")):
        ref = LedgerRef.from_record(references[name + "_ref"])
        if ref.kind != expected_kind:
            raise IntegrityError("Publication exemplar reference has the wrong evidence kind")
        refs[name], payloads[name] = ref, store.read(ref)
    try:
        forecast = payloads["forecast"]["data"]["bundle"]
        outcome = payloads["outcome"]["data"]["outcome"]
        grade = payloads["grade"]["data"]["grade"]
    except KeyError:
        raise IntegrityError("Publication exemplar requires typed ledger records") from None
    target_fields = ("id_namespace", "league", "event_id", "player_id", "event_starts_at")
    if (any(forecast[key] != outcome[key] for key in target_fields)
            or forecast["team_id"] != outcome["team_id"] or forecast["opponent_id"] != outcome["opponent_id"]
            or forecast["period"] != outcome["period"] or forecast["extra_time_policy"] != outcome["extra_time_policy"]
            or any(forecast[key] != grade[key] for key in ("id_namespace", "league", "event_id", "player_id"))):
        raise IntegrityError("Publication exemplar target identity mismatch")
    if (forecast["evidence_lane"] != LANE or grade["evidence_lane"] != LANE
            or forecast["model_version"] != MODEL_VERSION or forecast["qualification"] != "UNAVAILABLE"
            or outcome["status"] != "FINAL_APPEARANCE" or grade["status"] != "SCORED"
            or grade["financial_settlement"] != "NOT_EVALUATED"):
        raise IntegrityError("Publication exemplar evidence or purpose is unsupported")
    if (grade["forecast_id"] != forecast["forecast_id"] or grade["outcome_id"] != outcome["outcome_id"]
            or payloads["grade"]["references"] != [refs["forecast"].to_record(), refs["outcome"].to_record()]):
        raise IntegrityError("Publication grade does not depend on the exact summary evidence")
    if (not _clock(outcome["observed_at"]) <= _clock(payloads["outcome"]["received_at"]) <= _clock(grade["graded_at"])
            or not _clock(forecast["issued_at"]) <= _clock(payloads["forecast"]["received_at"]) <= _clock(grade["graded_at"])
            or _clock(grade["graded_at"]) > _clock(payloads["grade"]["received_at"])):
        raise IntegrityError("Publication exemplar receipt chronology is inconsistent")
    return {**{key: forecast[key] for key in target_fields},
            **{key: forecast[key] for key in ("team_id", "opponent_id", "period", "extra_time_policy",
               "conditioning", "cutoff_at", "history_freeze", "trained_through", "issued_at", "model_version",
               "model_commit", "model_code_sha256", "input_sha256", "joint_sha256")},
            "forecast_received_at": payloads["forecast"]["received_at"],
            "source_evidence_sha256": outcome["source_evidence_sha256"],
            "source_observed_at": outcome["observed_at"],
            "source_version": outcome.get("source_version"),
            "outcome_schema_version": outcome["schema_version"],
            "outcome_received_at": payloads["outcome"]["received_at"],
            "graded_at": grade["graded_at"], "grade_received_at": payloads["grade"]["received_at"],
            **{name + "_ref": ref.to_record() for name, ref in refs.items()}}


def _validate_summary(summary, store):
    if (type(summary) is not dict or type(summary.get("schema_version")) is not str
            or summary["schema_version"] not in {SUMMARY_V1, SUMMARY_V2}):
        raise IntegrityError("Unexpected publication receipt version")
    version = summary["schema_version"]
    required = SUMMARY_FIELDS | ({"source_observed_at"} if version == SUMMARY_V1 else set())
    optional = {"common_source_observed_at"} if version == SUMMARY_V2 else set()
    if not required <= set(summary) or not set(summary) <= required | optional:
        raise IntegrityError("Invalid publication summary schema")
    if (summary["evidence_lane"] != LANE or summary["purpose"] != PURPOSE
            or summary["selection_rule"] != SELECTION_RULE
            or summary["normalized_input_sha256"] != PANEL_SHA256
            or summary["source_evidence_sha256"] != SOURCE_SHA256
            or type(summary["genuine_future_issuances"]) is not int or summary["genuine_future_issuances"] != 0
            or summary["financial_settlement"] != "NOT_EVALUATED"):
        raise IntegrityError("Unsupported publication evidence, source inventory or purpose")
    if type(summary["model_commit"]) is not str or not re.fullmatch(r"[a-f0-9]{40}", summary["model_commit"]):
        raise IntegrityError("Invalid publication source commit")
    recorded_at = _clock(summary["recorded_at"])
    if recorded_at > _now():
        raise IntegrityError("Publication summary clock is in the future")
    if type(summary["examples"]) is not list or len(summary["examples"]) != 6:
        raise IntegrityError("Publication requires exactly six exemplars")
    store.scan()
    targets, source_clocks = [], set()
    for example in summary["examples"]:
        if type(example) is not dict or not BASE_EXAMPLE_FIELDS <= set(example):
            raise IntegrityError("Invalid publication exemplar schema")
        actual = _example_metadata(store, example)
        expected_fields = BASE_EXAMPLE_FIELDS if version == SUMMARY_V1 else set(actual)
        if set(example) != expected_fields or any(example[key] != actual[key] for key in expected_fields):
            raise IntegrityError("Publication summary metadata differs from the exact ledger evidence")
        if (actual["model_commit"] != summary["model_commit"]
                or actual["source_evidence_sha256"] != summary["source_evidence_sha256"]):
            raise IntegrityError("Publication source/model metadata differs from its referenced records")
        if any(_clock(actual[key]) > recorded_at for key in (
                "forecast_received_at", "source_observed_at", "outcome_received_at", "graded_at", "grade_received_at")):
            raise IntegrityError("Publication summary predates its exemplar evidence")
        targets.append((_clock(actual["event_starts_at"]), actual["event_id"], actual["player_id"]))
        source_clocks.add(actual["source_observed_at"])
    games = {(start, event) for start, event, _ in targets}
    if (len(set(targets)) != 6 or len(games) != 3 or targets != sorted(targets)
            or any(sum((start, event) == game for start, event, _ in targets) != 2 for game in games)
            or any(start < datetime(2025, 11, 24, tzinfo=timezone.utc) for start, _, _ in targets)
            or len({event for _, event in games}) != 3):
        raise IntegrityError("Publication exemplars violate the declared three-game/two-player rule shape")
    common = "source_observed_at" if version == SUMMARY_V1 else "common_source_observed_at"
    if common in summary:
        _clock(summary[common])
        if len(source_clocks) != 1 or source_clocks != {summary[common]}:
            raise IntegrityError("Aggregate source clock does not describe every retained outcome")
    return summary


def select_examples(panel):
    boundary = datetime(2025, 11, 24, tzinfo=timezone.utc)
    games = sorted({(row.event_start, row.event_id) for row in panel if row.event_start >= boundary})[:3]
    selected = []
    for start, event_id in games:
        players = sorted((row for row in panel if row.event_id == event_id and row.event_start == start),
                         key=lambda row: row.player_id)[:2]
        if len(players) != 2:
            raise IntegrityError("Publication rule requires two eligible players per game")
        selected.extend(players)
    if len(selected) != 6:
        raise IntegrityError("Publication rule requires exactly three eligible games")
    return selected


def recover_summary(root, path):
    return _validate_summary(read_receipt(path, max_bytes=MAX_SUMMARY_BYTES), Ledger(root))


def _read_outcome_rows(path):
    # Recheck the exact bounded second-pass bytes: a file changed after the panel
    # audit cannot supply outcomes under the earlier frozen file hash.
    if not stat.S_ISREG(path.lstat().st_mode):
        raise IntegrityError("Publication panel must be a regular file")
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
        raise IntegrityError("Publication outcome bytes differ from the frozen normalized panel")
    row_fields = {field.name for field in fields(NBAPlayerGame)}
    rows = {}
    for line in raw.splitlines():
        item = json.loads(line)
        row = NBAPlayerGame(**{key: item[key] for key in row_fields})
        if row.identity in rows:
            raise IntegrityError("Duplicate publication outcome identity")
        rows[row.identity] = row
    return rows


def record_examples(root: Path, path: Path, model_commit: str):
    summary_path = root / SUMMARY_PATH
    # Recovery does not need original local inputs or regenerate a new issue time.
    if summary_path.exists():
        return recover_summary(root, summary_path)
    if type(model_commit) is not str or not re.fullmatch(r"[a-f0-9]{40}", model_commit):
        raise IntegrityError("Full source commit is required")
    panel, inventory = read_normalized_panel(path)
    if inventory["input_file_sha256"] != PANEL_SHA256:
        raise IntegrityError("Publication sample requires the frozen normalized panel")
    selected = select_examples(panel)
    rows = _read_outcome_rows(path)
    source_observed_at = _now()
    store = Ledger(root)
    index = store.scan()
    examples = []
    for target in selected:
        # Resume a partially completed batch from its immutable original records.
        matches = [payload for payload in index["forecasts"].values()
                   if payload["data"].get("bundle", {}).get("event_id") == target.event_id
                   and payload["data"]["bundle"]["player_id"] == target.player_id
                   and payload["data"]["bundle"]["id_namespace"] == target.id_namespace
                   and payload["data"]["bundle"]["event_starts_at"] == stamp(target.event_start)
                   and payload["data"]["bundle"]["model_commit"] == model_commit]
        if len(matches) > 1:
            raise IntegrityError("Ambiguous original publication exemplar")
        if matches:
            payload = matches[0]
            forecast_ref = LedgerRef("forecasts", payload["record_id"], digest(payload))
            bundle = payload["data"]["bundle"]
        else:
            reference = forecast_reference(panel, ForecastTarget(target.event_id, target.player_id, target.event_start))
            bundle = from_reference(reference, target, model_commit=model_commit)
            forecast_ref = store.issue_forecast(bundle, reference=reference)
        prior = [payload for payload in index["outcomes"].values()
                 if payload["data"].get("outcome", {}).get("event_id") == target.event_id
                 and payload["data"]["outcome"]["player_id"] == target.player_id
                 and payload["data"]["outcome"]["id_namespace"] == target.id_namespace
                 and payload["data"]["outcome"]["event_starts_at"] == stamp(target.event_start)
                 and payload["data"]["outcome"]["source_evidence_sha256"] == SOURCE_SHA256]
        if len(prior) > 1:
            raise IntegrityError("Ambiguous original publication outcome")
        if prior:
            payload = prior[0]
            outcome_ref = LedgerRef("outcomes", payload["record_id"], digest(payload))
        else:
            outcome_ref = store.record_outcome(rows[target.id_namespace, target.event_id, target.player_id],
                source_evidence_sha256=SOURCE_SHA256, source_observed_at=source_observed_at)
        grade_ref = store.grade_forecast(forecast_ref, outcome_ref)
        examples.append(_example_metadata(store, {kind + "_ref": ref.to_record()
                         for kind, ref in (("forecast", forecast_ref), ("outcome", outcome_ref), ("grade", grade_ref))}))
    summary = {"schema_version": SUMMARY_V2, "recorded_at": stamp(_now()),
               "evidence_lane": LANE, "purpose": PURPOSE,
               "selection_rule": SELECTION_RULE, "model_commit": model_commit,
               "normalized_input_sha256": PANEL_SHA256, "source_evidence_sha256": SOURCE_SHA256,
               "examples": examples,
               "genuine_future_issuances": 0, "financial_settlement": "NOT_EVALUATED"}
    source_clocks = {example["source_observed_at"] for example in examples}
    if len(source_clocks) == 1:
        summary["common_source_observed_at"] = next(iter(source_clocks))
    _validate_summary(summary, store)
    write_receipt(summary_path, summary, max_bytes=MAX_SUMMARY_BYTES)
    return recover_summary(root, summary_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--model-commit", required=True)
    args = parser.parse_args()
    summary = record_examples(Path(__file__).resolve().parent.parent, args.input, args.model_commit)
    print(json.dumps({"examples": len(summary["examples"]), "recorded_at": summary["recorded_at"],
                      "evidence_lane": summary["evidence_lane"], "genuine_future_issuances": 0}))


if __name__ == "__main__":
    main()
