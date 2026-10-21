"""Versioned envelope bridge for independent static publication channels.

The frozen Ledger keeps its original source_pack-only input contract. This bridge
recognizes the two separately versioned input envelopes without treating their
contents as legacy forecasts. PROS004 and OP002 bodies remain the responsibility
of their strict stores/exporters, including recursive input and outcome links.

All scans still verify bounded inventory, receipt seals, complete references,
chronology and corrections. A checksum-consistent foreign body is never admitted
merely by this envelope bridge; its own publication channel must validate it.
"""
from .integrity import IntegrityError, digest
from . import ledger as frozen
from .ledger import LedgerRef
from .pros004_records import _Pros004Ledger

OPERATIONAL_INPUT_SCHEMAS = frozenset({
    "nba-operational002-history-v1", "nba-operational002-event-v1",
})


class CompositeEnvelopeLedger(_Pros004Ledger):
    """Read all known envelopes while retaining unchanged legacy semantics."""
    def _validate_payload(self, payload, *, kind, record_id):
        data = payload.get("data") if type(payload) is dict else None
        if kind != "research_inputs" or type(data) is not dict or "operational" not in data:
            return super()._validate_payload(payload, kind=kind, record_id=record_id)
        fields = {"schema_version", "kind", "record_id", "logical_id", "received_at", "data",
                  "references", "supersedes", "persistence_status"}
        if set(payload) != fields or payload["schema_version"] != frozen.SCHEMA or payload["kind"] != kind:
            raise IntegrityError("Invalid operational publication input envelope")
        frozen._text(payload["logical_id"], "logical_id")
        if (payload["record_id"] != record_id
                or record_id != digest({"kind":kind, "logical_id":payload["logical_id"]})
                or frozen._wire_time(payload["received_at"]) > frozen._now()
                or payload["persistence_status"] != "LOCAL_RECEIPT_ONLY"
                or payload["supersedes"] is not None):
            raise IntegrityError("Operational publication input identity/clock/status conflict")
        body = data["operational"]
        if (set(data) != {"identity", "operational"} or type(data["identity"]) is not dict
                or type(body) is not dict or type(body.get("schema_version")) is not str
                or body["schema_version"] not in OPERATIONAL_INPUT_SCHEMAS):
            raise IntegrityError("Unknown operational publication input contract")
        if type(payload["references"]) is not list:
            raise IntegrityError("Invalid operational publication input references")
        refs = [LedgerRef.from_record(item) for item in payload["references"]]
        if len(refs) != len(set(refs)):
            raise IntegrityError("Duplicate operational publication input references")
