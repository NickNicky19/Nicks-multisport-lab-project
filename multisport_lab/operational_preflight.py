"""Read-only, price-independent preparation checks for the inactive named pilot.

This command cannot capture sources, create forecasts, install an activation or
schedule a worker. A valid preparation result remains operationally blocked.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import subprocess

from .integrity import IntegrityError, digest, read_receipt, stamp, write_receipt
from . import operational_pilot as pilot

FROZEN_PRODUCER = "58530309cf384425e15f02fd9fa980899a4dc0bc"
FROZEN_FILES = (
    "multisport_lab/baseline.py", "multisport_lab/basketball.py",
    "multisport_lab/forecast_contract.py", "multisport_lab/integrity.py",
    "multisport_lab/ledger.py", "multisport_lab/nba_data.py",
    "multisport_lab/pregame_sources.py", "multisport_lab/prospective.py",
    "scripts/prepare_nba_panel.py",
)


def check_frozen_producer(root):
    """Compare all nine executed original-pilot files to the reviewed Git bytes."""
    root = Path(root)
    result = {}
    for name in FROZEN_FILES:
        original = subprocess.run(
            ["git", "-C", str(root), "show", FROZEN_PRODUCER+":"+name],
            capture_output=True, check=False, timeout=10,
        )
        pilot.require(original.returncode == 0, "reviewed original-pilot source object is unavailable")
        raw = (root/name).read_bytes()
        pilot.require(raw == original.stdout, "frozen original-pilot source changed: "+name)
        result[name] = hashlib.sha256(raw).hexdigest()
    return result


def combined_capacity(root):
    """Reserve one complete operating cycle and one offer, with bounded metadata.

    This is a separate named-game operation, not another 21-date comparison.
    Existing records are counted once. Raw ciphertext remains in its separately
    bounded archive; its public ledger links count here. No cap is increased.
    """
    capacity = pilot.capacity_report(root)
    # One <=64KiB offer envelope; <=8 source links of <=8KiB; eight <=16KiB
    # registration/admission receipts plus one complete <=1MiB hosted timing
    # report. Publication maximum32 does not
    # silently expand this one-off operational allocation.
    extra_files = 1+8+8
    extra_bytes = 64*1024+8*8*1024+7*16*1024+1024*1024
    count = capacity["maximum_records"]+extra_files
    size = capacity["maximum_bytes"]+extra_bytes
    pilot.require(count <= pilot.MAX_LEDGER_RECORDS and size <= pilot.MAX_LEDGER_BYTES,
                  "complete one-event/one-offer allocation exceeds unchanged shared ledger capacity")
    return {
        "schema_version": "nba-operational002-combined-capacity-v2",
        "base_operation": capacity,
        "reserved_offer_envelopes": 1,
        "reserved_offer_raw_link_envelopes": 8,
        "reserved_additional_metadata_files": 8,
        "reserved_small_metadata_files": 7,
        "small_metadata_encoded_ceiling": 16*1024,
        "reserved_hosted_report_files": 1,
        "hosted_report_encoded_ceiling": 1024*1024,
        "maximum_files": count,
        "maximum_encoded_bytes": size,
        "global_file_limit": pilot.MAX_LEDGER_RECORDS,
        "global_byte_limit": pilot.MAX_LEDGER_BYTES,
        "raw_archive_separate_maximum_bytes": 64*1024*1024,
        "raw_archive_separate_maximum_captures": 128,
        "raw_archive_eight_capture_reserve_bytes": 8*(2*1024*1024+16*1024+16*1024),
        "raw_plaintext_publication": False,
        "inactive_PROS004_full_study_stacked_with_new_pilot": False,
        "future_reservations_must_recalculate_against_actual_records": True,
    }


def preflight(root, plan, *, producer_commit=None, diagnostic_source=False):
    """Verify local preparation. Nothing here establishes timely future inputs."""
    root = Path(root).absolute()
    pilot.validate_plan(plan)
    binding = pilot.make_source_binding(producer_commit, diagnostic=diagnostic_source, root=root)
    frozen = check_frozen_producer(root)
    capacity = combined_capacity(root)
    actual = datetime.now(timezone.utc)
    start = pilot.clock(plan["event"]["event_starts_at"])
    cutoff = start-timedelta(minutes=90)
    closes = cutoff-timedelta(minutes=10)
    opens = cutoff-timedelta(minutes=20)
    phase = ("PREPARATION" if actual < opens else "CAPTURE_WINDOW" if actual <= closes
             else "CAPTURE_CLOSED" if actual < cutoff else "GENERATION_WINDOW"
             if actual <= cutoff+timedelta(seconds=300) else "EXPIRED")
    return {
        "schema_version": "nba-operational002-preflight-v1",
        "observed_at": stamp(actual), "protocol_id": pilot.PROTOCOL_ID,
        "plan_id": plan["plan_id"], "plan_payload_sha256": digest(plan),
        "producer_binding": binding, "original_pilot_source_sha256": frozen,
        "capacity": capacity, "actual_phase": phase,
        "activation_evidence_deadline_exclusive": stamp(opens),
        "capture_window": [stamp(opens), stamp(closes)],
        "generation_window": [stamp(cutoff), stamp(cutoff+timedelta(seconds=300))],
        "status": "BLOCKED_NOT_ACTIVATED",
        "local_preparation_integrity": "PASS",
        "genuine_execution_enabled": False,
        "unmet_requirements": [
            "Install no genuine activation in this readiness revision; exact reviewed approval remains separate.",
            "Resolve permitted source operations and public derived-fact admission; HTTP success is insufficient.",
            "Admit primary private raw retention and demonstrate authenticated hosted key/readback recovery.",
            "Pass exact-source full eight-original hosted timing, durable checkpoint and independent recovery.",
            "Review the genuine destination/entrypoint and independently recover complete activation evidence before capture opens.",
        ],
        "retained_preparation_input_is_timely_future_input": False,
        "genuine_issuance_created": 0, "outcomes_created": 0,
        "statistical_grades_created": 0, "scheduler_installed": False,
        "qualification": "UNAVAILABLE", "financial_settlement": "NOT_EVALUATED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--producer-commit")
    source.add_argument("--diagnostic-source", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = preflight(args.root, read_receipt(args.plan),
                           producer_commit=args.producer_commit, diagnostic_source=args.diagnostic_source)
        write_receipt(args.output, report, max_bytes=65536)
    except (IntegrityError, OSError, ValueError) as error:
        parser.exit(1, "Preparation rejected: "+str(error)+"\n")
    print(report["status"]+": local integrity PASS; genuine execution remains disabled.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
