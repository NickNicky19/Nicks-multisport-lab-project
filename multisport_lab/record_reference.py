"""Create/recover the fixed six historical publication exemplars, never picks."""
from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from .baseline import ForecastTarget, forecast_reference
from .forecast_contract import from_reference
from .integrity import IntegrityError, read_receipt, stamp, write_receipt
from .ledger import Ledger, LedgerRef
from .nba_data import NBAPlayerGame
from .research_pilot import read_normalized_panel

PANEL_SHA256 = "489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c"
SOURCE_SHA256 = "29a29dc9efd055a93e069a0382ac830d98a13274bee655beba69d95cff099713"


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
    summary = read_receipt(path)
    if summary["schema_version"] != "reference-publication-002-v1":
        raise IntegrityError("Unexpected publication receipt version")
    store = Ledger(root)
    store.scan()
    for example in summary["examples"]:
        for kind in ("forecast", "outcome", "grade"):
            store.read(LedgerRef(**example[kind + "_ref"]))
    return summary


def record_examples(root: Path, path: Path, model_commit: str):
    summary_path = root / "evidence/research/reference-publication-002.json"
    # Recovery does not need original local inputs or regenerate a new issue time.
    if summary_path.exists():
        return recover_summary(root, summary_path)
    if not re.fullmatch(r"[a-f0-9]{40}", model_commit):
        raise IntegrityError("Full source commit is required")
    panel, inventory = read_normalized_panel(path)
    if inventory["input_file_sha256"] != PANEL_SHA256:
        raise IntegrityError("Publication sample requires the frozen normalized panel")
    selected = select_examples(panel)
    row_fields = {field.name for field in fields(NBAPlayerGame)}
    rows = {}
    with path.open() as handle:
        for line in handle:
            item = json.loads(line)
            row = NBAPlayerGame(**{key: item[key] for key in row_fields})
            rows[row.event_id, row.player_id] = row
    source_observed_at = datetime.now(timezone.utc)
    store = Ledger(root)
    index = store.scan()
    examples = []
    for target in selected:
        # Resume a partially completed batch from its immutable original records.
        matches = [payload for payload in index["forecasts"].values()
                   if payload["data"].get("bundle", {}).get("event_id") == target.event_id
                   and payload["data"]["bundle"]["player_id"] == target.player_id
                   and payload["data"]["bundle"]["model_commit"] == model_commit]
        if len(matches) > 1:
            raise IntegrityError("Ambiguous original publication exemplar")
        if matches:
            payload = matches[0]
            from .integrity import digest
            forecast_ref = LedgerRef("forecasts", payload["record_id"], digest(payload))
            bundle = payload["data"]["bundle"]
        else:
            reference = forecast_reference(panel, ForecastTarget(target.event_id, target.player_id, target.event_start))
            bundle = from_reference(reference, target, model_commit=model_commit)
            forecast_ref = store.issue_forecast(bundle, reference=reference)
        prior = [payload for payload in index["outcomes"].values()
                 if payload["data"].get("outcome", {}).get("event_id") == target.event_id
                 and payload["data"]["outcome"]["player_id"] == target.player_id
                 and payload["data"]["outcome"]["source_evidence_sha256"] == SOURCE_SHA256]
        if len(prior) > 1:
            raise IntegrityError("Ambiguous original publication outcome")
        if prior:
            from .integrity import digest
            payload = prior[0]
            outcome_ref = LedgerRef("outcomes", payload["record_id"], digest(payload))
        else:
            outcome_ref = store.record_outcome(rows[target.event_id, target.player_id],
                source_evidence_sha256=SOURCE_SHA256, source_observed_at=source_observed_at)
        grade_ref = store.grade_forecast(forecast_ref, outcome_ref)
        examples.append({"event_id": target.event_id, "player_id": target.player_id,
                         "issued_at": bundle["issued_at"],
                         **{kind + "_ref": {"kind": ref.kind, "record_id": ref.record_id,
                            "payload_sha256": ref.payload_sha256}
                            for kind, ref in (("forecast", forecast_ref), ("outcome", outcome_ref), ("grade", grade_ref))}})
    summary = {"schema_version": "reference-publication-002-v1", "recorded_at": stamp(datetime.now(timezone.utc)),
               "evidence_lane": "RECONSTRUCTED_RESEARCH", "purpose": "ENGINEERING_PUBLICATION_NOT_HELD_OUT_EVALUATION",
               "selection_rule": "docs/REFERENCE_PUBLICATION_002.md", "model_commit": model_commit,
               "normalized_input_sha256": PANEL_SHA256, "source_evidence_sha256": SOURCE_SHA256,
               "source_observed_at": stamp(source_observed_at), "examples": examples,
               "genuine_future_issuances": 0, "financial_settlement": "NOT_EVALUATED"}
    write_receipt(summary_path, summary)
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
