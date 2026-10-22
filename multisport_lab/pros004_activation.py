"""Read-only review of a source-bound activation proposal, never activation.

The operating producer remains disabled. A passed proposal is an internally
consistent review artifact, not permission, upstream authenticity or evidence
that an actual capture/issuance occurred. No CLI writes an activation record.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re

from .integrity import IntegrityError, canonical, digest, read_receipt, stamp, utc
from .ledger import LedgerRef

SCHEMA = "nba-pros004-activation-proposal-v1"
STUDY_ID = "NBA-ALL13-JOINT-PROS-004"
PROTOCOL_PATH = "evidence/research/prospective004-protocol.json"
PROTOCOL_RAW_SHA256 = "8302bf5455d48c9c0f6ccd40296b971955822ee09edaa9d9af94ad205d06e752"
MAX_PROPOSAL_BYTES = 5 * 1024  # reserve room for review/readback in ONE metadata slot
MAX_PACKAGE_BYTES = 7 * 1024  # leave the registered 8-KiB envelope its overhead
GATES = frozenset(("source_permission", "history_lineage", "software_checks",
                  "completion_recovery", "typed_recovery", "retention_capacity",
                  "public_contract", "raw_retention", "end_to_end_timing"))
CLOCK_POLICY = {"capture_before_t90_seconds": [600, 1200],
                "selection_closes_before_t90_seconds": 600,
                "generation_window_seconds": 300,
                "generation_through_ack_max_seconds": 120,
                "remote_readback_required": True}


def _now():
    return datetime.now(timezone.utc)


def _require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _exact(value, keys, label):
    _require(type(value) is dict and set(value) == set(keys), "invalid " + label + " fields")


def _hash(value, label):
    _require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None,
             "invalid " + label + " hash")


def _commit(value):
    _require(type(value) is str and re.fullmatch(r"[a-f0-9]{40}", value) is not None,
             "review/readback requires exact source commit")


def _clock(value):
    _require(type(value) is str, "proposal clocks must be explicit strings")
    try:
        clock = utc(value)
    except (ValueError, TypeError) as error:
        raise IntegrityError("invalid proposal clock") from error
    _require(stamp(clock) == value, "proposal requires canonical microsecond UTC clocks")
    return clock


def proposal_template(*, source_binding, event_ref, gate_evidence, recorded_at):
    """Build an INACTIVE proposal from supplied evidence; do not admit or write.

    Deliberately no default PASS gates. The caller must retain actual evidence
    behind every digest and then independently recover this proposal from Git.
    """
    from .pros004_records import full_study_capacity
    body = {"schema_version": SCHEMA, "study_id": STUDY_ID,
            "status": "INACTIVE_REVIEW_CANDIDATE", "reservation_raw_sha256": PROTOCOL_RAW_SHA256,
            "source_binding_sha256": digest(source_binding), "event_ref": event_ref.to_record(),
            "source_max_age_seconds": 1200, "clock_policy": dict(CLOCK_POLICY),
            "capacity_sha256": digest(full_study_capacity()), "gates": gate_evidence,
            "recorded_at": recorded_at}
    return {**body, "proposal_id": digest(body)}


def _gate_evidence(gates, *, source_commit, actual, diagnostic):
    _exact(gates, GATES, "activation evidence gates")
    for name, evidence in gates.items():
        _exact(evidence, {"status", "evidence_lane", "source_commit", "evidence_sha256",
                          "observed_at", "details"}, name)
        _require(evidence["status"] == "PASS", "unresolved activation gate: " + name)
        _hash(evidence["evidence_sha256"], name)
        _require(evidence["source_commit"] == source_commit, "gate references another source revision")
        _require(_clock(evidence["observed_at"]) <= actual, "future activation evidence clock")
        lane = evidence["evidence_lane"]
        _require(lane in ({"SYNTHETIC_DIAGNOSTIC"} if diagnostic else
                         {"OBSERVED_REVIEW_EVIDENCE", "OBSERVED_OPERATION_EVIDENCE"}),
                 "synthetic/unknown evidence cannot admit an operational activation gate")
        details = evidence["details"]
        _require(type(details) is dict and len(canonical(details)) <= 512,
                 "activation evidence details exceed their compact bound")
    permission = gates["source_permission"]["details"]
    _require(permission.get("prospective_operations_authorized") is True
             and permission.get("source_reviewed") is True
             and type(permission.get("review_reference")) is str and bool(permission["review_reference"]),
             "bounded inspection permission does not admit prospective source operation")
    raw = gates["raw_retention"]["details"]
    _require(raw.get("private_backend_verified") is True and raw.get("independent_readback") is True
             and raw.get("outcome_linkage_verified") is True,
             "raw evidence requires a verified private durable backend and independent readback")
    timing = gates["end_to_end_timing"]["details"]
    _require(type(timing.get("cohort_seconds")) in (int, float)
             and 0 <= timing["cohort_seconds"] <= 300
             and type(timing.get("max_generation_through_ack_seconds")) in (int, float)
             and 0 <= timing["max_generation_through_ack_seconds"] <= 120
             and timing.get("all_required_acknowledgments_included") is True
             and timing.get("realistic_ledger_verified") is True,
             "end-to-end timing must include required completion/readback and realistic ledger")


def validate_review_candidate(proposal, *, store, source_binding, review, remote_readback,
                              diagnostic=False, root=None):
    """Validate an inactive proposal and two separately observed review receipts.

    ``remote_readback`` is separate to avoid a self-referential commit/hash claim.
    It must bind this proposal's original payload and the exact reviewed source.
    Real operation still requires a later explicit activation decision; this
    function has no permission to change that state, even after PASS.
    """
    from .pros004_inputs import first_event, validate_schedule, validate_event_body
    from .pros004_producer import validate_source_binding
    from .pros004_records import full_study_capacity
    _require(type(diagnostic) is bool, "diagnostic review mode must be explicit")
    _exact(proposal, {"schema_version", "study_id", "status", "reservation_raw_sha256",
                      "source_binding_sha256", "event_ref", "source_max_age_seconds",
                      "clock_policy", "capacity_sha256", "gates", "recorded_at", "proposal_id"},
           "inactive activation proposal")
    _require(proposal["schema_version"] == SCHEMA and proposal["study_id"] == STUDY_ID
             and proposal["status"] == "INACTIVE_REVIEW_CANDIDATE", "proposal cannot activate the study")
    _require(proposal["proposal_id"] == digest({k: v for k, v in proposal.items() if k != "proposal_id"}),
             "proposal content identity changed")
    _require(len(canonical(proposal)) <= MAX_PROPOSAL_BYTES, "activation proposal exceeds envelope reserve")
    base = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    raw = (base / PROTOCOL_PATH).read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == PROTOCOL_RAW_SHA256
             and proposal["reservation_raw_sha256"] == PROTOCOL_RAW_SHA256,
             "original reservation changed")
    read_receipt(base / PROTOCOL_PATH)
    validate_source_binding(source_binding, check_current=not diagnostic)
    _require(proposal["source_binding_sha256"] == digest(source_binding), "review source binding differs")
    source_commit = source_binding["model_commit"]
    if not diagnostic:
        _commit(source_commit)
        _require(source_binding["verification"] == "VERIFIED_COMMIT", "operational review requires committed source")
    _require(proposal["source_max_age_seconds"] == 1200 and type(proposal["source_max_age_seconds"]) is int
             and canonical(proposal["clock_policy"]) == canonical(CLOCK_POLICY),
             "registered completion/source clock policy changed")
    _require(proposal["capacity_sha256"] == digest(full_study_capacity()), "retention plan changed after review")
    event_ref = LedgerRef.from_record(proposal["event_ref"])
    event = store.body(event_ref)
    validate_event_body(event)
    _require((event["mode"] == "SYNTHETIC_DIAGNOSTIC") if diagnostic else
             event["mode"] == "REAL_TIME_CAPTURED", "activation input evidence lane conflicts")
    schedule = validate_schedule(event["schedule"])
    _require(schedule["study_date"] == "2026-10-21", "later date cannot replace the original first date")
    first = first_event(schedule)
    _require(first is not None and first["event_id"] == event["event"]["event_id"]
             and first["scheduled_event_version"] == event["event"]["event_version"],
             "first-event selection changed")
    cutoff = utc(first["event_starts_at"]) - timedelta(minutes=90)
    actual = _now()
    recorded = _clock(proposal["recorded_at"])
    _require(recorded <= actual < cutoff, "original activation cutoff passed or proposal clock is future")
    _gate_evidence(proposal["gates"], source_commit=source_commit, actual=actual, diagnostic=diagnostic)
    _exact(review, {"source_commit", "proposal_id", "reviewed_at", "independent_review", "review_reference"},
           "independent review")
    _require(review["source_commit"] == source_commit and review["proposal_id"] == proposal["proposal_id"]
             and review["independent_review"] is True and type(review["review_reference"]) is str
             and 0 < len(review["review_reference"]) <= 512, "review does not bind this exact proposal/source")
    reviewed = _clock(review["reviewed_at"])
    _exact(remote_readback, {"repository", "source_commit", "records_commit", "proposal_id",
                            "proposal_payload_sha256", "readback_completed_at", "independent_fetch"},
           "activation remote readback")
    _commit(remote_readback["records_commit"])
    _require(remote_readback["repository"] == "NickNicky19/Nicks-multisport-lab-project"
             and remote_readback["source_commit"] == source_commit
             and remote_readback["proposal_id"] == proposal["proposal_id"]
             and remote_readback["proposal_payload_sha256"] == digest(proposal)
             and remote_readback["independent_fetch"] is True, "remote recovery does not bind original proposal")
    completed = _clock(remote_readback["readback_completed_at"])
    _require(recorded <= reviewed <= completed <= actual < cutoff,
             "review and independent remote recovery must finish before first actual T90")
    return {"status": "VALIDATED_NOT_ACTIVE", "activation": "INACTIVE",
            "diagnostic": diagnostic, "proposal_id": proposal["proposal_id"],
            "source_commit": source_commit, "first_cutoff_at": stamp(cutoff),
            "checked_at": stamp(actual), "genuine_issuance_authorized": False,
            "qualification": "UNAVAILABLE"}


def review_package(proposal, *, store, source_binding, review, remote_readback,
                   diagnostic=False, root=None):
    """Bound proposal/review/readback together in one future metadata slot.

    The readback references the earlier original proposal commit, never this
    package's own future commit. Journal + this package + eventual evaluation
    occupy the three registered slots beside the existing study manifest.
    No package is written or admitted to the operating ledger here.
    """
    result = validate_review_candidate(proposal, store=store, source_binding=source_binding,
        review=review, remote_readback=remote_readback, diagnostic=diagnostic, root=root)
    body = {"schema_version": "nba-pros004-inactive-review-package-v1",
            "study_id": STUDY_ID, "status": "VALIDATED_NOT_ACTIVE",
            "proposal": proposal, "review": review, "remote_readback": remote_readback,
            "validation": result}
    _require(len(canonical(body)) <= MAX_PACKAGE_BYTES,
             "combined activation review/readback exceeds one metadata slot")
    return body


def require_operating_activation(*args, **kwargs):
    """No proposal, caller flag or synthetic proof activates this package."""
    raise IntegrityError("PROS004 READINESS_ONLY: operating activation is not authorized")
