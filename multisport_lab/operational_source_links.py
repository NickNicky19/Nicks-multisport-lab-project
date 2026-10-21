"""Authenticated OP002 source links over the existing immutable ledger.

This adapter makes no source request, creates no key, and grants no admission.
Genuine writes still call the unchanged hard-closed activation guard. Readback
authenticates ciphertext and replays the four exact source meanings; neither a
link nor a successful readback establishes source permission or timely issuance.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit

from . import operational_pilot as op
from . import pregame_sources as sources
from . import pros004_inputs as inputs
from .integrity import HASH_FORMAT, RECEIPT_SCHEMA, canonical, digest, stamp
from .ledger import LedgerRef, SCHEMA as LEDGER_SCHEMA
from .operational_raw import EncryptedRawArchive
from .pros004_records import Pros004Store

LINK_SCHEMA = "nba-op002-encrypted-source-link-v1"
BINDING_SCHEMA = "nba-op002-event-source-links-v1"
MAX_LINK_BYTES = 8 * 1024
MAX_BINDING_BYTES = 8 * 1024


def canonical_source_inventory(plan, *, scoreboard_date):
    """Exact intended routes; the reviewed provider calendar date is explicit.

    ESPN's observed calendar partition need not equal the UTC event date. The
    caller must use its reviewed preparation evidence, not infer that mapping.
    """
    op.validate_plan(plan)
    op.require(type(scoreboard_date) is str and len(scoreboard_date) == 8
               and scoreboard_date.isascii() and scoreboard_date.isdecimal(),
               "scoreboard date requires YYYYMMDD")
    try:
        datetime.strptime(scoreboard_date, "%Y%m%d")
    except ValueError as error:
        raise op.IntegrityError("scoreboard date is invalid") from error
    event = plan["event"]
    return {"scoreboard": inputs.BASE + "/scoreboard?dates=" + scoreboard_date + "&limit=1000",
            "summary": inputs.BASE + "/summary?event=" + event["event_id"],
            **{"roster-" + team: inputs.BASE + "/teams/" + team + "/roster?season="
               + str(event["season_ending_year"]) for team in (event["home_team_id"], event["away_team_id"])}}


def _source_route(plan, name, url, *, mode):
    """Validate actual route semantics; legacy unqualified routes are diagnostic."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise op.IntegrityError("source route query is malformed") from error
    op.require(not parsed.fragment and not parsed.username and not parsed.password
               and port is None, "source route contains ambiguous URL components")
    query = dict(pairs)
    op.require(len(pairs) == len(query) and all(value for value in query.values()),
               "source route has repeated or empty query parameters")
    event = plan["event"]
    if name == "scoreboard":
        op.require(set(query) in ({"dates"}, {"dates", "limit"}), "foreign scoreboard query parameter")
        date = inputs.route_date(url).strftime("%Y%m%d")
        canonical_url = canonical_source_inventory(plan, scoreboard_date=date)[name]
        if mode != "REAL_TIME_CAPTURED" and "limit" not in query:
            canonical_url = inputs.BASE + "/scoreboard?dates=" + date
    elif name == "summary":
        canonical_url = inputs.BASE + "/summary?event=" + event["event_id"]
    else:
        canonical_url = (inputs.BASE + "/teams/" + name[7:] + "/roster?season="
                         + str(event["season_ending_year"]))
        if mode != "REAL_TIME_CAPTURED" and not query:
            canonical_url = inputs.BASE + "/teams/" + name[7:] + "/roster"
    op.require(url == canonical_url, "source route differs from the planned event/team/season or canonical query")


class EncryptedSourceLinks:
    """Read exact bytes; append small links under both existing writer locks.

    Mutating methods acquire OP002 then PROS004/offer locks nonblockingly. Call
    them outside an already-held store lock. This prevents overlap with either
    existing writer without changing their locks or enabling genuine operation.
    The archive must be independently recovered with its original certificate
    and private key before this reader can be used on a fetched checkpoint.
    """

    def __init__(self, root, archive, *, diagnostic=False):
        op.require(isinstance(archive, EncryptedRawArchive),
                   "source links require the authenticated encrypted archive")
        self.archive = archive
        self.store = op.OperationalStore(root, diagnostic=diagnostic)
        self.ledger, self.root = self.store.ledger, self.store.root
        self.peer = Pros004Store(root)
        self.peer.ledger = self.ledger

    @contextmanager
    def _writer(self):
        with self.store.single_writer(), self.peer.single_writer():
            yield

    def _write_mode(self, mode):
        op.require(type(mode) is str and mode in op.MODES, "unknown source-link mode")
        if mode == "REAL_TIME_CAPTURED":
            op.require_activation()
        else:
            op.require(self.store.diagnostic, "diagnostic links require an isolated diagnostic store")

    def _append(self, logical, data, references=(), *, ceiling=MAX_LINK_BYTES):
        reference = self.ledger._existing("input_captures", logical)
        if reference is None:
            payload = {"schema_version": LEDGER_SCHEMA, "kind": "input_captures",
                       "record_id": digest({"kind": "input_captures", "logical_id": logical}),
                       "logical_id": logical, "received_at": stamp(op._now()),
                       "data": data, "references": [ref.to_record() for ref in references],
                       "supersedes": None, "persistence_status": "LOCAL_RECEIPT_ONLY"}
            encoded = len(canonical({"schema_version": RECEIPT_SCHEMA, "hash_format": HASH_FORMAT,
                                     "payload_sha256": digest(payload), "payload": payload}))
            op.require(encoded <= ceiling, "source link exceeds its encoded envelope limit")
            self.store._check_budget(extra_files=1, extra_bytes=encoded)
        else:
            self.store._check_budget()
        return self.ledger.append("input_captures", logical, data, references=references)

    @staticmethod
    def _identity(body):
        return {"protocol_id": op.PROTOCOL_ID, "event_id": body["event_id"],
                "mode": body["mode"], "source_id": body["source"]["source_id"]}

    def _validate_link(self, body):
        op.exact(body, {"schema_version", "protocol_id", "event_id", "mode", "source",
                        "raw_reference", "link_id"}, "encrypted source link")
        op.require(body["schema_version"] == LINK_SCHEMA and body["protocol_id"] == op.PROTOCOL_ID,
                   "unknown encrypted source link schema")
        op.check_seal(body, "link_id")
        metadata, raw = self.archive.read(body["raw_reference"])
        op.require((body["event_id"], body["mode"]) == (metadata["event_id"], metadata["mode"]),
                   "source link changes the archived event or evidence mode")
        source = inputs._source_check(body["source"], raw=raw,
                                      imported_at=op.clock(metadata["imported_at"]))
        op.require(len(source["source_id"]) <= 128 and source["source_id"].strip() == source["source_id"],
                   "source identity exceeds its bound or contains surrounding whitespace")
        for field, archived in (("source_url", "source_url"), ("request_started_at", "request_started_at"),
                                ("observed_at", "source_observed_at"), ("source_updated_at", "source_updated_at"),
                                ("raw_sha256", "raw_sha256"), ("raw_bytes", "raw_bytes")):
            op.require(source[field] == metadata[archived],
                       "source link contradicts original archive metadata: " + field)
        return metadata, raw

    def link(self, raw_reference, source_metadata):
        """Retain a link to already encrypted bytes; original clocks are reused."""
        metadata, _ = self.archive.read(raw_reference)
        self._write_mode(metadata["mode"])
        body = op.seal({"schema_version": LINK_SCHEMA, "protocol_id": op.PROTOCOL_ID,
                        "event_id": metadata["event_id"], "mode": metadata["mode"],
                        "source": deepcopy(source_metadata), "raw_reference": deepcopy(raw_reference)}, "link_id")
        self._validate_link(body)
        with self._writer():
            reference = self._append("op002-source-link:" + body["link_id"],
                                     {"identity": self._identity(body), "encrypted_source_link": body})
            self.read(reference)
            return reference

    def read(self, reference):
        """Authenticate a linked source, including after independent fetch."""
        op.require(isinstance(reference, LedgerRef) and reference.kind == "input_captures",
                   "source evidence requires an exact input-capture reference")
        payload = self.ledger.read(reference)
        op.exact(payload["data"], {"identity", "encrypted_source_link"}, "encrypted source envelope")
        body = payload["data"]["encrypted_source_link"]
        metadata, raw = self._validate_link(body)
        op.require(payload["logical_id"] == "op002-source-link:" + body["link_id"]
                   and payload["data"]["identity"] == self._identity(body)
                   and payload["references"] == [] and payload["supersedes"] is None,
                   "encrypted source envelope identity or references conflict")
        op.require(op.clock(metadata["manifest_prepared_at"]) <= op.clock(payload["received_at"]),
                   "source link predates its original encrypted manifest")
        op.require(self.ledger._path(reference.kind, reference.record_id).stat().st_size <= MAX_LINK_BYTES,
                   "source link exceeds its encoded envelope limit")
        return {"body": body, "archive_metadata": metadata, "raw": raw}

    def observations(self, plan, source_refs, *, mode, expected_routes=None):
        """Rebuild the exact four-observation interface without HTTP or clocks."""
        op.validate_plan(plan)
        op.require(type(mode) is str and mode in op.MODES, "unknown event evidence mode")
        refs = tuple(source_refs)
        op.require(len(refs) == 4 and all(isinstance(ref, LedgerRef) for ref in refs)
                   and len(set(refs)) == 4, "four distinct exact source links are required")
        event = plan["event"]
        expected = {"scoreboard", "summary", "roster-" + event["home_team_id"],
                    "roster-" + event["away_team_id"]}
        op.require(expected_routes is not None or mode != "REAL_TIME_CAPTURED",
                   "genuine inputs require the reviewed exact source inventory")
        if expected_routes is not None:
            op.require(type(expected_routes) is dict and set(expected_routes) == expected,
                       "reviewed source inventory differs from the four planned sources")
            for name, url in expected_routes.items():
                op.require(type(url) is str, "reviewed source route must be text")
                _source_route(plan, name, url, mode=mode)
        observations = {}
        for reference in refs:
            recovered = self.read(reference)
            body, raw = recovered["body"], recovered["raw"]
            source = body["source"]
            name = source["source_id"]
            op.require(body["mode"] == mode and body["event_id"] == event["event_id"],
                       "source link differs from the planned event or evidence mode")
            op.require(name in expected and name not in observations,
                       "duplicate or foreign source in the four-input inventory")
            _source_route(plan, name, source["source_url"], mode=mode)
            if expected_routes is not None:
                op.require(source["source_url"] == expected_routes[name],
                           "captured route differs from the reviewed exact source inventory")
            observations[name] = {"source_id": name, "raw": raw, "metadata": deepcopy(source)}
        current = sources.normalize_event(observations["scoreboard"]["raw"], observations["summary"]["raw"],
                                          event["event_id"])
        op.require(current == event, "recovered source bytes changed the frozen event")
        rosters = {team: sources.normalize_roster(observations["roster-" + team]["raw"], team,
                                                 season_ending_year=event["season_ending_year"])
                   for team in (event["home_team_id"], event["away_team_id"])}
        op.require(sources.freeze_selection(current, rosters)["players"] == plan["candidates"],
                   "recovered source bytes changed the frozen player cohort")
        return [observations[name] for name in sorted(observations)]

    def verify_event(self, event_body, source_refs, *, expected_routes=None):
        """Replay source meaning and compare exact retained event metadata."""
        op.validate_event(event_body)
        observations = self.observations(event_body["plan"], source_refs, mode=event_body["mode"],
                                         expected_routes=expected_routes)
        expected = sorted(event_body["sources"], key=lambda source: source["source_id"])
        op.require([item["metadata"] for item in observations] == expected,
                   "recovered source metadata differs from the original event inputs")
        return observations

    def bind_event(self, event_ref, source_refs, *, expected_routes=None):
        """Append one immutable event-to-four-sources link; no timing grant."""
        event = self.store.body(event_ref)
        self._write_mode(event["mode"])
        refs = tuple(source_refs)
        observations = self.verify_event(event, refs, expected_routes=expected_routes)
        by_source = {self.read(ref)["body"]["source"]["source_id"]: ref for ref in refs}
        ordered = [item["source_id"] for item in observations]
        body = op.seal({"schema_version": BINDING_SCHEMA, "protocol_id": op.PROTOCOL_ID,
                        "event_input_id": event["event_input_id"], "event_ref": event_ref.to_record(),
                        "source_inventory": {item["source_id"]: item["metadata"]["source_url"] for item in observations},
                        "source_refs": {name: by_source[name].to_record() for name in ordered}}, "binding_id")
        with self._writer():
            reference = self._append("op002-event-source-links:" + body["binding_id"],
                                     {"event_source_links": body},
                                     (event_ref, *(by_source[name] for name in ordered)), ceiling=MAX_BINDING_BYTES)
            self.recover_binding(reference)
            return reference

    def recover_binding(self, reference):
        """Read the original event and authenticate/replay all four raw links."""
        op.require(isinstance(reference, LedgerRef) and reference.kind == "input_captures",
                   "event source binding requires an exact input-capture reference")
        payload = self.ledger.read(reference)
        op.exact(payload["data"], {"event_source_links"}, "event source binding envelope")
        body = payload["data"]["event_source_links"]
        op.exact(body, {"schema_version", "protocol_id", "event_input_id", "event_ref", "source_refs",
                        "source_inventory", "binding_id"},
                 "event source binding")
        op.require(body["schema_version"] == BINDING_SCHEMA and body["protocol_id"] == op.PROTOCOL_ID,
                   "unknown event source binding schema")
        op.check_seal(body, "binding_id")
        op.require(type(body["source_refs"]) is dict and len(body["source_refs"]) == 4,
                   "event binding requires four named source references")
        event_ref = LedgerRef.from_record(body["event_ref"])
        refs = tuple(LedgerRef.from_record(body["source_refs"][name]) for name in sorted(body["source_refs"]))
        op.require(payload["logical_id"] == "op002-event-source-links:" + body["binding_id"]
                   and payload["references"] == [ref.to_record() for ref in (event_ref, *refs)]
                   and payload["supersedes"] is None, "event source binding envelope conflicts")
        # This method is also a standalone recovery surface. Do not rely on a
        # separate whole-ledger scan to reject a checksum-consistent binding
        # that claims to have existed before one of its original references.
        binding_clock = op.clock(payload["received_at"])
        op.require(all(op.clock(self.ledger.read(ref)["received_at"]) <= binding_clock
                       for ref in (event_ref, *refs)),
                   "event binding reference creation clock follows the binding receipt")
        event = self.store.body(event_ref)
        op.require(body["event_input_id"] == event["event_input_id"], "binding names a different original event")
        observations = self.verify_event(event, refs, expected_routes=body["source_inventory"])
        op.require([item["source_id"] for item in observations] == sorted(body["source_refs"])
                   and all(self.read(LedgerRef.from_record(ref))["body"]["source"]["source_id"] == name
                           for name, ref in body["source_refs"].items()),
                   "binding source names do not match their referenced captures")
        op.require(self.ledger._path(reference.kind, reference.record_id).stat().st_size <= MAX_BINDING_BYTES,
                   "event binding exceeds its encoded envelope limit")
        return {"event_ref": event_ref, "event": event, "source_refs": refs, "observations": observations}

    def offer_reader(self, reference, *, mode="REAL_TIME_CAPTURED"):
        """Callable OfferStore reader. Diagnostics require their explicit mode."""
        recovered = self.read(reference)
        body, metadata = recovered["body"], recovered["archive_metadata"]
        op.require(type(mode) is str and mode in op.MODES and body["mode"] == mode,
                   "offer raw evidence has a different evidence mode")
        return {"metadata": {**deepcopy(body["source"]), "imported_at": metadata["imported_at"]},
                "raw": recovered["raw"]}
