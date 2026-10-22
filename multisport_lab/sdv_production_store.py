"""Typed immutable event-shard records with explicit future grading reserves.

Each shard has the production policy's own 512-record/32-MiB limit.  Source
originals are exact shared archive objects; the fixed history remains external.
This does not change any older pilot's storage budget or record bytes.  Receipt
creation precedes writing, so only separate post-action markers can establish
local completion.  Missing, late and unacknowledged originals remain evidence.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import threading

from .integrity import (HASH_FORMAT, RECEIPT_SCHEMA, IntegrityError, canonical,
                        digest, read_receipt, stamp, utc)
from .ledger import Ledger, LedgerRef, KINDS as LEDGER_KINDS, SCHEMA, MAX_RECORD_BYTES
from . import sdv_production_common as common

SNAPSHOT_SCHEMA = "nba-sdv-production-snapshot-v1"
ROOT = Path(__file__).resolve().parents[1]
MAX_RECORDS = 512
MAX_BYTES = 32 * 1024 * 1024
MAX_FORENSIC_FILES = 8
MAX_FORENSIC_FILE_BYTES = 512 * 1024
MAX_FORENSIC_BYTES = MAX_FORENSIC_FILES * MAX_FORENSIC_FILE_BYTES
CEILINGS = {common.PLAN_SCHEMA:512*1024, common.INPUT_SCHEMA:256*1024,
    common.AUTH_SCHEMA:256*1024, common.INTENT_SCHEMA:8*1024,
    common.FORECAST_SCHEMA:64*1024, common.OUTCOME_SCHEMA:32*1024,
    common.GRADE_SCHEMA:32*1024, common.LOCAL_COMPLETION_SCHEMA:8*1024,
    common.COMPLETION_SCHEMA:8*1024, common.STATUS_SCHEMA:8*1024}
SLOTS = {common.PLAN_SCHEMA:1, common.INPUT_SCHEMA:1, common.AUTH_SCHEMA:8,
    common.INTENT_SCHEMA:1, common.FORECAST_SCHEMA:32, common.OUTCOME_SCHEMA:32,
    common.GRADE_SCHEMA:64, common.LOCAL_COMPLETION_SCHEMA:34,
    common.COMPLETION_SCHEMA:34, common.STATUS_SCHEMA:64, "corrections":48}
TIMED_SCHEMAS = {common.INPUT_SCHEMA, common.INTENT_SCHEMA, common.FORECAST_SCHEMA}
CAPACITY_FIELDS = {"schema_version","existing_records","existing_bytes","remaining_records","remaining_bytes",
    "maximum_projected_records","maximum_projected_bytes","future_grading_receipt_bytes",
    "future_grading_liability_bytes","future_status_receipt_bytes","future_status_liability_bytes",
    "maximum_records","maximum_bytes","role_counts","fits","forensic_files","forensic_bytes",
    "forensic_oversized_files","forensic_fits","remaining_forensic_files","remaining_forensic_bytes",
    "maximum_forensic_files","maximum_forensic_bytes","maximum_forensic_file_bytes"}


def _capacity_summary(existing_records, actual_bytes, counts, forensic_bytes=0, forensic_oversized_files=0):
    common.require(all(counts[key] <= SLOTS[key] for key in SLOTS),"Production shard exhausted a declared role reserve")
    remaining_records = sum(SLOTS[key]-counts[key] for key in SLOTS)
    remaining_bytes = sum((SLOTS[key]-counts[key])*(8*1024 if key == "corrections" else CEILINGS[key]) for key in SLOTS)
    # Interrupted unpublished bytes consume the actual budget but never gain
    # slot credit or forecast validity.
    forensic_files = existing_records-sum(counts.values())
    remaining_forensic_files = max(0,MAX_FORENSIC_FILES-forensic_files)
    remaining_forensic_bytes = min(remaining_forensic_files*MAX_FORENSIC_FILE_BYTES,
                                  max(0,MAX_FORENSIC_BYTES-forensic_bytes))
    total_records = existing_records+remaining_records+remaining_forensic_files
    total_bytes = actual_bytes+remaining_bytes+remaining_forensic_bytes
    liability_keys = {common.OUTCOME_SCHEMA,common.GRADE_SCHEMA,"corrections"}
    receipt_liability = sum((SLOTS[key]-counts[key])*(8*1024 if key == "corrections" else CEILINGS[key]) for key in liability_keys)
    # Archive packs base64 their complete receipt originals before zlib.
    # These component summaries do not fund cumulative full manifests. The
    # global reservation must use archive_liability() over every unused role.
    archive_liability = 2*receipt_liability+1024*1024 if receipt_liability else 0
    status_receipt_liability = (SLOTS[common.STATUS_SCHEMA]-counts[common.STATUS_SCHEMA])*CEILINGS[common.STATUS_SCHEMA]
    status_archive_liability = 2*status_receipt_liability+256*1024 if status_receipt_liability else 0
    return {"schema_version":"nba-sdv-production-capacity-v1","existing_records":existing_records,
        "existing_bytes":actual_bytes,"remaining_records":remaining_records,"remaining_bytes":remaining_bytes,
        "maximum_projected_records":total_records,"maximum_projected_bytes":total_bytes,
        "future_grading_receipt_bytes":receipt_liability,
        "future_grading_liability_bytes":archive_liability,
        "future_status_receipt_bytes":status_receipt_liability,
        "future_status_liability_bytes":status_archive_liability,
        "maximum_records":MAX_RECORDS,"maximum_bytes":MAX_BYTES,
        "role_counts":counts,"fits":total_records <= MAX_RECORDS and total_bytes <= MAX_BYTES,
        "forensic_files":forensic_files,"forensic_bytes":forensic_bytes,
        "forensic_oversized_files":forensic_oversized_files,
        "forensic_fits":forensic_files <= MAX_FORENSIC_FILES and forensic_bytes <= MAX_FORENSIC_BYTES
            and forensic_oversized_files == 0,
        "remaining_forensic_files":remaining_forensic_files,"remaining_forensic_bytes":remaining_forensic_bytes,
        "maximum_forensic_files":MAX_FORENSIC_FILES,"maximum_forensic_bytes":MAX_FORENSIC_BYTES,
        "maximum_forensic_file_bytes":MAX_FORENSIC_FILE_BYTES}



def empty_capacity():
    """Pure full-role reservation for a shard that has not created any files."""
    return validate_capacity(_capacity_summary(0,0,{key:0 for key in SLOTS}))


def validate_capacity(body):
    common.exact(body,CAPACITY_FIELDS,"production capacity summary")
    common.require(body["schema_version"] == "nba-sdv-production-capacity-v1",
                   "Wrong production capacity protocol")
    common.exact(body["role_counts"],set(SLOTS),"production capacity role counts")
    counts = body["role_counts"]
    common.require(all(type(counts[key]) is int and 0 <= counts[key] <= SLOTS[key] for key in SLOTS),
                   "Production capacity role count exceeds its fixed reserve")
    numeric = CAPACITY_FIELDS-{"schema_version","role_counts","fits","forensic_fits"}
    common.require(all(type(body[key]) is int and body[key] >= 0 for key in numeric)
        and type(body["fits"]) is bool and type(body["forensic_fits"]) is bool,
        "Production capacity contains invalid numeric claims")
    remaining_records = sum(SLOTS[key]-counts[key] for key in SLOTS)
    def remaining(keys):
        return sum((SLOTS[key]-counts[key])*(8192 if key == "corrections" else CEILINGS[key]) for key in keys)
    remaining_bytes = remaining(SLOTS)
    grading = remaining({common.OUTCOME_SCHEMA,common.GRADE_SCHEMA,"corrections"})
    status = remaining({common.STATUS_SCHEMA})
    forensic_files = body["existing_records"]-sum(counts.values())
    remaining_forensic_files = max(0,MAX_FORENSIC_FILES-forensic_files)
    remaining_forensic_bytes = min(remaining_forensic_files*MAX_FORENSIC_FILE_BYTES,
                                  max(0,MAX_FORENSIC_BYTES-body["forensic_bytes"]))
    common.require(body["existing_records"] >= sum(counts.values())
        and body["remaining_records"] == remaining_records and body["remaining_bytes"] == remaining_bytes
        and body["maximum_projected_records"] == body["existing_records"]+remaining_records+remaining_forensic_files
        and body["maximum_projected_bytes"] == body["existing_bytes"]+remaining_bytes+remaining_forensic_bytes
        and body["future_grading_receipt_bytes"] == grading
        and body["future_grading_liability_bytes"] == (2*grading+1024*1024 if grading else 0)
        and body["future_status_receipt_bytes"] == status
        and body["future_status_liability_bytes"] == (2*status+256*1024 if status else 0)
        and body["maximum_records"] == MAX_RECORDS and body["maximum_bytes"] == MAX_BYTES
        and body["forensic_files"] == forensic_files and body["forensic_bytes"] <= body["existing_bytes"]
        and body["forensic_oversized_files"] <= forensic_files
        and body["maximum_forensic_files"] == MAX_FORENSIC_FILES
        and body["maximum_forensic_bytes"] == MAX_FORENSIC_BYTES
        and body["maximum_forensic_file_bytes"] == MAX_FORENSIC_FILE_BYTES
        and body["remaining_forensic_files"] == remaining_forensic_files
        and body["remaining_forensic_bytes"] == remaining_forensic_bytes
        and body["forensic_fits"] == (forensic_files <= MAX_FORENSIC_FILES
            and body["forensic_bytes"] <= MAX_FORENSIC_BYTES and body["forensic_oversized_files"] == 0)
        and body["fits"] == (body["maximum_projected_records"] <= MAX_RECORDS
            and body["maximum_projected_bytes"] <= MAX_BYTES),
        "Production capacity summary contradicts exact role reserves or actual inventory")
    return body


def archive_liability(capacity):
    """Remaining receipt wire budget, excluding already archived actual bytes.

    All unused roles and the explicit eight-file forensic failure allowance
    are funded. Each new immutable file can introduce one distinct full
    manifest; unchanged-state retries are content-addressed. One extra manifest
    covers the current pending state. Its compressed ceiling is enforced by
    the archive before upload. Shared source originals are reserved separately.
    """
    validate_capacity(capacity)
    common.require(capacity["fits"],"Production shard has no valid remaining archive reserve")
    from .sdv_production_archive import SNAPSHOT_MAX_WIRE
    raw = capacity["remaining_bytes"]+capacity["remaining_forensic_bytes"]
    manifests = capacity["remaining_records"]+capacity["remaining_forensic_files"]+1
    return 2*raw+manifests*SNAPSHOT_MAX_WIRE+1024*1024


def _checked(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except IntegrityError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError, OSError) as exc:
        raise IntegrityError("Malformed or unavailable production evidence") from exc


def _path(root):
    root = Path(root).absolute()
    for item in (root, *root.parents):
        common.require(not item.is_symlink(), "Production paths cannot traverse symlinks")
    return root


def _identity(body):
    return {key:body[key] for key in ("protocol_id", "plan_id", "cycle_id", "mode",
        "event_id", "event_snapshot_id", "player_id", "team_id", "opponent_id", "model_key") if key in body}


def validate_local_completion(body):
    common.exact(body, {"schema_version", "protocol_id", "target", "local_completed_at", "completion_id"},
                 "local post-write completion")
    common.require(body["schema_version"] == common.LOCAL_COMPLETION_SCHEMA
        and body["protocol_id"] == common.PROTOCOL_ID, "Wrong local completion protocol")
    common.sha(body["target"])
    common.require(common.clock(body["local_completed_at"]) <= common.now(), "Local completion is future-dated")
    common.check_seal(body, "completion_id")
    return body


def _logical(body):
    schema = body["schema_version"]
    if schema == common.PLAN_SCHEMA:
        return "production-plan:"+body["game_date"]
    if schema == common.INPUT_SCHEMA:
        return "production-input:"+body["cycle_id"]
    if schema == common.INTENT_SCHEMA:
        return "production-intent:"+body["cycle_id"]+":"+digest(body["player_ids"])
    if schema == common.FORECAST_SCHEMA:
        return "production-forecast:"+body["cycle_id"]+":"+body["player_id"]+":"+body["model_key"]
    if schema == common.OUTCOME_SCHEMA:
        return "production-outcome:"+body["cycle_id"]+":"+body["player_id"]+":"+str(body["correction_revision"])
    if schema == common.GRADE_SCHEMA:
        return "production-grade:"+body["forecast_id"]+":"+str(body["correction_revision"])
    if schema in {common.LOCAL_COMPLETION_SCHEMA, common.COMPLETION_SCHEMA}:
        return schema+":"+body["target"]
    return schema+":"+body[common.ID_KEYS[schema]]


def _size(kind, logical_id, data, references):
    payload = {"schema_version":SCHEMA,"kind":kind,
        "record_id":digest({"kind":kind,"logical_id":logical_id}),"logical_id":logical_id,
        "received_at":stamp(common.now()),"data":data,
        "references":[ref.to_record() for ref in references],"supersedes":None,
        "persistence_status":"LOCAL_RECEIPT_ONLY"}
    return len(canonical({"schema_version":RECEIPT_SCHEMA,"hash_format":HASH_FORMAT,
        "payload_sha256":digest(payload),"payload":payload}))


class ProductionStore:
    def __init__(self, root, *, source_root=ROOT, source_resolver=None, snapshot_resolver=None,
                 allow_diagnostics=False):
        self.root = _path(root)
        self.source_root = _path(source_root)
        self.project_root = self.source_root
        common.require(self.root != self.source_root, "Production shard cannot overwrite the original project ledger")
        protected = (self.source_root/"records",self.source_root/"daily",self.source_root/"recurring")
        common.require(not any(self.root == path or self.root.is_relative_to(path) for path in protected),
                       "Production shard cannot reuse a protected pilot/planning namespace")
        self.ledger = Ledger(self.root)
        self.source_resolver = source_resolver
        self.snapshot_resolver = snapshot_resolver
        common.require(type(allow_diagnostics) is bool,"Invalid diagnostic archive scope")
        self.allow_diagnostics = allow_diagnostics
        self._mutex = threading.RLock()
        self._depth = 0
        self._permit = None
        self._remote_permit = None
        self._local_permit = None
        self._cache = None
        # Only successful semantic validation is reused. Every top-level
        # operation still reads/authenticates the actual parent receipt bytes.
        self._history_semantics = set()

    @contextmanager
    def lock(self):
        with self._mutex:
            self.root.mkdir(parents=True, exist_ok=True)
            if self._depth:
                self._depth += 1
                try: yield
                finally: self._depth -= 1
                return
            path = self.root/".production-writer.lock"
            common.require(not path.is_symlink(), "Production writer lock is a symlink")
            with path.open("a+b") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                self._depth = 1
                try: yield
                finally:
                    self._depth = 0
                    fcntl.flock(handle, fcntl.LOCK_UN)

    @contextmanager
    def _operation(self):
        previous = self._cache
        if previous is None:
            self._cache = {"sources":{}, "snapshots":{}, "history":{}}
        try: yield
        finally: self._cache = previous

    def _inventory(self):
        entries = []
        records = self.root/"records"
        common.require(not records.is_symlink(), "Production records directory is a symlink")
        if not records.exists(): return entries
        common.require(records.is_dir() and set(item.name for item in records.iterdir()) <= set(LEDGER_KINDS),
                       "Unknown production ledger directory")
        for kind in LEDGER_KINDS:
            directory = records/kind
            common.require(not directory.is_symlink(), "Production kind directory is a symlink")
            if not directory.exists(): continue
            common.require(directory.is_dir(), "Production kind is not a directory")
            with os.scandir(directory) as items:
                for item in items:
                    temporary = item.name.startswith(".receipt-")
                    common.require(temporary or re.fullmatch(r"[a-f0-9]{64}\.json",item.name),
                                   "Unknown production receipt file")
                    info = item.stat(follow_symlinks=False)
                    common.require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= MAX_RECORD_BYTES,
                                   "Unsafe or oversized production receipt")
                    entries.append((kind,Path(item.path),info.st_size,temporary))
        common.require(len(entries) <= MAX_RECORDS and sum(item[2] for item in entries) <= MAX_BYTES,
                       "Production shard exceeds unchanged runtime ledger limits")
        return entries

    def _history(self, value=None):
        if self._cache["history"]:
            ref = next(iter(self._cache["history"]))
            if value is not None:
                common.require(LedgerRef.from_record(value) == ref,"Production forecast changed the fixed history reference")
            return ref
        path = self.source_root/"records/research_inputs"/(common.HISTORY_ID+".json")
        payload = read_receipt(path,max_bytes=MAX_RECORD_BYTES)
        ref = LedgerRef("research_inputs",common.HISTORY_ID,digest(payload))
        common.require(utc(payload["received_at"]) <= common.now(),"Fixed history receipt is future-dated")
        if value is not None:
            common.require(LedgerRef.from_record(value) == ref, "Production forecast changed the fixed history reference")
        key = (ref,digest(payload))
        if key not in self._history_semantics:
            Ledger(self.source_root).read(ref)
            self._history_semantics.add(key)
        self._cache["history"][ref] = True
        return ref

    def _source(self, reference):
        common.archive_ref(reference,diagnostic=self.allow_diagnostics)
        key = digest(reference)
        if key not in self._cache["sources"]:
            common.require(callable(self.source_resolver), "Production source originals are unavailable for independent replay")
            result = self.source_resolver(reference)
            common.require(type(result) in {tuple,list} and len(result) == 3
                and type(result[0]) is bytes and type(result[1]) is dict and type(result[2]) is bytes,
                "Production source resolver returned invalid originals")
            self._cache["sources"][key] = result
        return self._cache["sources"][key]

    def _snapshot(self, reference):
        common.archive_ref(reference,diagnostic=self.allow_diagnostics)
        key = digest(reference)
        if key not in self._cache["snapshots"]:
            common.require(callable(self.snapshot_resolver), "Original remote recovery snapshot is unavailable")
            snapshot = self.snapshot_resolver(reference)
            if type(snapshot) is dict and "ledger_snapshot" in snapshot:
                snapshot = snapshot["ledger_snapshot"]
            validate_snapshot_manifest(snapshot)
            self._cache["snapshots"][key] = snapshot
        return self._cache["snapshots"][key]

    def _rows(self):
        self._inventory()
        scan = self.ledger.scan()
        rows = {}
        for kind, payloads in scan.items():
            for payload in payloads.values():
                ref = LedgerRef(kind,payload["record_id"],digest(payload))
                if kind == "corrections":
                    common.require((self.root/"records"/kind/(ref.record_id+".json")).stat().st_size <= 8*1024,
                                   "Production correction envelope exceeds its explicit ceiling")
                    rows[ref] = (payload,None,[])
                    continue
                data = payload["data"]
                common.exact(data,{"identity","production","archive_refs"},"typed ledger wrapper")
                body = data["production"]
                common.validate_body(body)
                schema = body["schema_version"]
                common.require(schema in CEILINGS and kind == common.KINDS[schema]
                    and data["identity"] == _identity(body) and payload["logical_id"] == _logical(body),
                    "Production record kind, identity or logical original differs")
                observed_field = {common.PLAN_SCHEMA:"planned_at",common.INPUT_SCHEMA:"normalized_at",
                    common.INTENT_SCHEMA:"created_at",common.FORECAST_SCHEMA:"verified_at",
                    common.OUTCOME_SCHEMA:"normalized_at",common.GRADE_SCHEMA:"graded_at",
                    common.AUTH_SCHEMA:"verified_at",common.STATUS_SCHEMA:"observed_at"}.get(schema)
                if observed_field is not None:
                    common.require(common.clock(body[observed_field]) <= utc(payload["received_at"]),
                                   "Production body completion follows its original receipt")
                archives = data["archive_refs"]
                common.require(type(archives) is list and len(archives) <= 2,"Production archive reference count differs")
                for reference in archives:
                    common.archive_ref(reference,diagnostic=self.allow_diagnostics and body.get("mode") == "DEVELOPMENT_ONLY")
                common.require(len({digest(item) for item in archives}) == len(archives),"Duplicate production archive references")
                size = (self.root/"records"/kind/(ref.record_id+".json")).stat().st_size
                common.require(size <= CEILINGS[schema],"Production typed envelope exceeds its ceiling")
                rows[ref] = (payload,body,archives)
        return rows

    def _validate_graph(self, rows):
        def targets(payload):
            refs = tuple(LedgerRef.from_record(item) for item in payload["references"])
            return refs, [rows[ref][1] for ref in refs]
        def find(bodies,schema):
            return [body for body in bodies if body is not None and body["schema_version"] == schema]
        contexts = {"inputs":{}, "intents":{}, "forecasts":{}, "local":{}, "remote":{}}
        plans = []
        for ref,(payload,body,archives) in rows.items():
            if body is None: continue
            refs, bodies = targets(payload)
            schema = body["schema_version"]
            if schema in {common.PLAN_SCHEMA,common.INPUT_SCHEMA}:
                from . import sdv_production_inputs as inputs
                common.require(len(archives) == 2,"Production input/plan lacks both exact source archives")
                sources = [self._source(item) for item in archives]
                common.require([item[1]["role"] for item in sources] == ["schedule","roster"],"Production source roles differ")
                originals = {"schedule":sources[0][2],"roster":sources[1][2]}
                if schema == common.PLAN_SCHEMA:
                    common.require(not refs,"Production plan has unexpected internal references")
                    inputs.verify_plan_sources(body,sources[0][0],sources[1][0],sources[0][1],sources[1][1],source_originals=originals)
                    plans.append(body)
                else:
                    common.require(len(refs) == 1 and len(find(bodies,common.PLAN_SCHEMA)) == 1,"Production input lacks its exact plan")
                    plan = bodies[0]
                    inputs.validate_input(body,plan=plan)
                    inputs.verify_input_sources(body,sources[0][0],sources[1][0],sources[0][1],sources[1][1],source_originals=originals,plan=plan)
                    contexts["inputs"][ref] = body
                self._history()
            elif schema == common.INTENT_SCHEMA:
                inputs = find(bodies,common.INPUT_SCHEMA); linked_plans = find(bodies,common.PLAN_SCHEMA)
                auth = find(bodies,common.AUTH_SCHEMA)
                genuine = body["mode"] == "PROSPECTIVE_RESEARCH"
                common.require(len(inputs) == len(linked_plans) == 1 and len(auth) == int(genuine)
                    and len(refs) == 2+int(genuine),"Production intent lacks exact input, plan or authority")
                input_body = inputs[0]
                input_reference = next(item for item,target in zip(refs,bodies) if target["schema_version"] == common.INPUT_SCHEMA)
                common.require(body["input_ref"] == input_reference.to_record()
                    and body["input_id"] == input_body["input_id"] and body["plan_id"] == input_body["plan_id"] == linked_plans[0]["plan_id"]
                    and body["cycle_id"] == input_body["cycle_id"] and body["mode"] == input_body["mode"]
                    and body["producer_binding_id"] == input_body["producer_binding"]["binding_id"],"Production intent changed its original input or producer")
                common.require(body["player_ids"] in input_body["shards"],"Production intent cohort is not a registered shard")
                if genuine:
                    common.require(auth[0]["executed_files"] == input_body["producer_binding"]["files"],
                                   "Production authority changed the executed producer bytes")
                    common.require(common.clock(auth[0]["verified_at"]) <= common.clock(body["created_at"]),
                                   "Production intent predates authenticated execution authority")
                common.require(common.clock(input_body["normalized_at"]) <= common.clock(body["created_at"]),
                               "Production intent precedes its admitted input")
                self._history(body["history_ref"])
                contexts["intents"][ref] = (body,refs)
            elif schema == common.FORECAST_SCHEMA:
                from . import sdv_production_forecasts as forecasts
                inputs = find(bodies,common.INPUT_SCHEMA); intents = find(bodies,common.INTENT_SCHEMA)
                common.require(len(refs) == 2 and len(inputs) == len(intents) == 1,"Production forecast lacks exact input and intent")
                forecasts.validate_forecast(body,inputs[0])
                intent = intents[0]
                input_reference = next(item for item,target in zip(refs,bodies) if target["schema_version"] == common.INPUT_SCHEMA)
                common.require(body["input_ref"] == input_reference.to_record()
                    and body["input_id"] == intent["input_id"] and body["plan_id"] == intent["plan_id"]
                    and body["cycle_id"] == intent["cycle_id"] and body["player_id"] in intent["player_ids"]
                    and body["producer_binding"]["binding_id"] == intent["producer_binding_id"],"Production forecast changed the bound intent")
                self._history(body["history_ref"])
                contexts["forecasts"][ref] = (body,refs)
            elif schema == common.OUTCOME_SCHEMA:
                from . import sdv_production_forecasts as forecasts
                originals = find(bodies,common.FORECAST_SCHEMA); previous = find(bodies,common.OUTCOME_SCHEMA)
                common.require(1 <= len(originals) <= 2 and len(refs) == len(originals)+len(previous)
                    and len({item["model_key"] for item in originals}) == len(originals),"Production outcome lacks its original player forecasts")
                expected = {target for target,(_,candidate,_) in rows.items() if candidate is not None
                    and candidate["schema_version"] == common.FORECAST_SCHEMA
                    and all(candidate[key] == body[key] for key in ("cycle_id","player_id","mode"))}
                common.require({target for target,candidate in zip(refs,bodies)
                    if candidate["schema_version"] == common.FORECAST_SCHEMA} == expected,
                    "Shared outcome omitted a retained original model")
                for original in originals:
                    common.require(all(original[key] == body[key] for key in ("plan_id","cycle_id","mode","event_id","event_snapshot_id","event_starts_at","player_id","team_id","opponent_id")),"Production outcome changed its original subject")
                self._revision(body,previous,"outcome_id","previous_outcome_id")
                common.require(archives == body["source_archive_refs"] and len(archives) == 2,"Production outcome archives differ from original source binding")
                sources = [self._source(item) for item in archives]
                input_ref = LedgerRef.from_record(originals[0]["input_ref"])
                common.require(input_ref in rows,"Production outcome lost its original input")
                forecasts.verify_outcome_sources(body,sources[0][0],sources[1][0],sources[0][1],sources[1][1],
                    source_originals={"schedule":sources[0][2],"boxscore":sources[1][2]},
                    forecasts=tuple(originals),input_body=rows[input_ref][1])
            elif schema == common.GRADE_SCHEMA:
                from . import sdv_production_forecasts as forecasts
                originals = find(bodies,common.FORECAST_SCHEMA); outcomes = find(bodies,common.OUTCOME_SCHEMA)
                previous = find(bodies,common.GRADE_SCHEMA)
                common.require(len(originals) == len(outcomes) == 1 and len(refs) == 2+len(previous),"Production grade has orphan or unexpected references")
                forecasts.validate_grade(body,originals[0],outcomes[0],previous=previous[0] if previous else None)
                self._revision(body,previous,"grade_id","previous_grade_id")
                if previous:
                    common.require(previous[0]["forecast_id"] == body["forecast_id"]
                        and outcomes[0]["previous_outcome_id"] == previous[0]["outcome_id"],
                        "Production grade correction lost its original forecast/outcome chain")
                common.require(not archives,"Production grade cannot introduce source originals")
            elif schema == common.LOCAL_COMPLETION_SCHEMA:
                common.require(len(refs) == 1 and bodies[0] is not None and bodies[0]["schema_version"] in TIMED_SCHEMAS
                    and body["target"] == refs[0].record_id and not archives,"Local completion lacks its exact timed original")
                common.require(utc(rows[refs[0]][0]["received_at"]) <= common.clock(body["local_completed_at"])
                    <= utc(payload["received_at"]),"Post-write completion precedes the original or its metadata record")
                contexts["local"][refs[0]] = (ref,body)
            elif schema == common.COMPLETION_SCHEMA:
                local = find(bodies,common.LOCAL_COMPLETION_SCHEMA)
                timed = [(item,target) for item,target in zip(refs,bodies) if target is not None and target["schema_version"] in TIMED_SCHEMAS]
                common.require(len(refs) == 2 and len(local) == len(timed) == 1 and not archives,"Remote completion lacks original and post-write marker")
                target_ref, original = timed[0]
                common.archive_ref(body["archive_ref"],diagnostic=self.allow_diagnostics
                    and original.get("mode") == "DEVELOPMENT_ONLY")
                common.require(body["target"] == target_ref.record_id == local[0]["target"]
                    and body["local_completed_at"] == local[0]["local_completed_at"]
                    and common.clock(body["remote_recovered_at"]) <= utc(payload["received_at"]),"Remote completion changed original clocks")
                snapshot = self._snapshot(body["archive_ref"])
                entries = {item["path"]:item for item in snapshot["entries"]}
                for target in refs:
                    path = "records/"+target.kind+"/"+target.record_id+".json"
                    raw = (self.root/path).read_bytes()
                    common.require(entries.get(path) == {"path":path,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()},
                                   "Remote original snapshot lacks the exact target or local marker")
                contexts["remote"][target_ref] = body
            elif schema == common.STATUS_SCHEMA:
                common.require(not refs and not archives,"Production status cannot introduce unrelated references or source originals")
                matching = [candidate for _,candidate,_ in rows.values() if candidate is not None
                    and candidate["schema_version"] == common.INPUT_SCHEMA
                    and all(candidate[key] == body[key] for key in ("plan_id","cycle_id"))]
                common.require(len(matching) == 1,"Production status lacks its exact native event input")
                details = body["details"]
                common.sha(details.get("task_id"))
                index = details.get("shard_index")
                common.require(type(index) is int and 0 <= index < len(matching[0]["shards"])
                    and details.get("player_ids") == matching[0]["shards"][index],
                    "Production status changed its exact registered player shard")
            else:
                common.require(not archives,"Production run/status cannot introduce source originals")
        for ref,(payload,body,_) in rows.items():
            if body is not None: continue
            refs, bodies = targets(payload)
            common.require(len(refs) == 2 and all(item is not None for item in bodies)
                and bodies[0]["schema_version"] in {common.OUTCOME_SCHEMA,common.GRADE_SCHEMA}
                and bodies[0]["schema_version"] == bodies[1]["schema_version"],"Production correction must preserve typed outcome/grade originals")
            old = rows[LedgerRef.from_record(payload["supersedes"])][1]
            new = rows[LedgerRef.from_record(payload["data"]["replacement"])][1]
            previous_key = "previous_outcome_id" if old["schema_version"] == common.OUTCOME_SCHEMA else "previous_grade_id"
            id_key = common.ID_KEYS[old["schema_version"]]
            common.require(new[previous_key] == old[id_key] and _identity(new) == _identity(old),"Production correction changed its original subject or chain")
        return contexts

    @staticmethod
    def _revision(body, previous, id_key, previous_key):
        revision = body["correction_revision"]
        common.require(len(previous) == revision-1 and revision in {1,2},"Production revision lacks its unique previous original")
        if revision == 1:
            common.require(body[previous_key] is None,"First production revision cannot supersede an original")
        else:
            old = previous[0]
            common.require(body[previous_key] == old[id_key] and old["correction_revision"] == 1
                and _identity(body) == _identity(old),"Production revision changed its original identity")
            clock_key = "graded_at" if id_key == "grade_id" else "source_observed_at"
            common.require(common.clock(body[clock_key]) >= common.clock(old[clock_key]),"Production correction clock precedes original")

    def _admission(self, ref, rows, contexts, visiting=None):
        visiting = set() if visiting is None else visiting
        common.require(ref not in visiting,"Production admission graph cycles")
        visiting.add(ref)
        _,body,_ = rows[ref]
        common.require(body is not None and body["schema_version"] in TIMED_SCHEMAS,"Record has no prospective timing admission")
        reasons = []
        local = contexts["local"].get(ref); remote = contexts["remote"].get(ref)
        if body["mode"] != "PROSPECTIVE_RESEARCH": reasons.append("DEVELOPMENT_ONLY_NOT_PROSPECTIVE")
        if local is None: reasons.append("LOCAL_POSTWRITE_COMPLETION_UNACKNOWLEDGED")
        if remote is None: reasons.append("REMOTE_ORIGINAL_READBACK_UNACKNOWLEDGED")
        if local is not None and remote is not None:
            finished = common.clock(remote["remote_recovered_at"])
            if body["schema_version"] == common.FORECAST_SCHEMA:
                cutoff = common.clock(body["cutoff_at"])
                if finished < cutoff: reasons.append("FORECAST_REMOTE_RECOVERY_BEFORE_WINDOW")
                if finished > cutoff+timedelta(seconds=900): reasons.append("FORECAST_REMOTE_RECOVERY_AFTER_WINDOW")
                if (finished-common.clock(body["generation_started_at"])).total_seconds() > 300:
                    reasons.append("ORIGINAL_LATENCY_EXCEEDED")
                _,references = contexts["forecasts"][ref]
                peers = [item for item in references if rows[item][1]["schema_version"] in {common.INPUT_SCHEMA,common.INTENT_SCHEMA}]
                for target in peers:
                    parent = self._admission(target,rows,contexts,visiting.copy())
                    reasons.extend("BOUND_"+item for item in parent["reasons"])
                input_body = rows[next(item for item in peers if rows[item][1]["schema_version"] == common.INPUT_SCHEMA)][1]
            else:
                if body["schema_version"] == common.INPUT_SCHEMA:
                    input_body = body
                else:
                    _,references = contexts["intents"][ref]
                    input_ref = next(item for item in references if rows[item][1]["schema_version"] == common.INPUT_SCHEMA)
                    input_body = rows[input_ref][1]
                    parent = self._admission(input_ref,rows,contexts,visiting.copy())
                    reasons.extend("BOUND_"+item for item in parent["reasons"])
                cutoff = common.clock(input_body["event"]["event_starts_at"])-timedelta(minutes=90)
                if finished > cutoff: reasons.append("INPUT_OR_INTENT_RECOVERY_AFTER_CUTOFF")
            for source in input_body["sources"]:
                if (finished-common.clock(source["publisher_updated_at"])).total_seconds() > 129600:
                    reasons.append("BOUND_SOURCE_PUBLISHER_STALE_AT_RECOVERY")
        reasons = sorted(set(reasons))
        result = {"eligible":not reasons,"local_completed_at":local[1]["local_completed_at"] if local else None,
            "remote_recovered_at":remote["remote_recovered_at"] if remote else None,
            "reasons":reasons,"archive_ref":remote["archive_ref"] if remote else None}
        if remote is not None and remote["eligible"] is not None:
            common.require(remote["eligible"] == result["eligible"] and remote["reasons"] == reasons,
                           "Stored production admission contradicts actual completion or bound inputs")
        return result

    def _capacity(self, rows):
        inventory = self._inventory()
        counts = {key:0 for key in SLOTS}
        for ref,(_,body,_) in rows.items(): counts["corrections" if body is None else body["schema_version"]] += 1
        forensic = [item for item in inventory if item[3]]
        return _capacity_summary(len(inventory),sum(item[2] for item in inventory),counts,
            sum(item[2] for item in forensic),sum(item[2] > MAX_FORENSIC_FILE_BYTES for item in forensic))

    def _load(self):
        rows = self._rows()
        contexts = self._validate_graph(rows)
        capacity = self._capacity(rows)
        common.require(capacity["fits"],"Actual production records plus unused obligations exceed runtime limits")
        admissions = {ref.record_id:self._admission(ref,rows,contexts) for ref,(_,body,_) in rows.items()
                      if body is not None and body["schema_version"] in TIMED_SCHEMAS}
        for ref,(_,body,_) in rows.items():
            if body is None or body["schema_version"] != common.GRADE_SCHEMA or body["mode"] != "PROSPECTIVE_RESEARCH": continue
            forecast_ref = next(item for item in rows[ref][0]["references"] if item["kind"] == "forecasts")
            common.require(admissions[forecast_ref["record_id"]]["eligible"],"Genuine grade cannot score an ineligible forecast")
        return rows,contexts,capacity,admissions

    def recover(self):
        with self.lock(), self._operation():
            rows,_,capacity,admissions = _checked(self._load)
            pairs = [(ref,body) for ref,(_,body,_) in rows.items() if body is not None]
            def selected(schema): return [(ref,body) for ref,body in pairs if body["schema_version"] == schema]
            corrections = [{"reference":ref.to_record(),"original_ref":payload["supersedes"],
                "replacement_ref":payload["data"]["replacement"],"reason":payload["data"]["reason"]}
                for ref,(payload,body,_) in rows.items() if body is None]
            return {"records":pairs,"forecasts":selected(common.FORECAST_SCHEMA),
                "outcomes":selected(common.OUTCOME_SCHEMA),"grades":selected(common.GRADE_SCHEMA),
                "corrections":corrections,"admissions":admissions,"capacity":capacity,
                "unpublished_entries":self._snapshot_entries()[1],
                "genuine_issued":sum(admissions[ref.record_id]["eligible"] for ref,_ in selected(common.FORECAST_SCHEMA))}

    def records(self): return self.recover()["records"]

    def read_body(self, reference):
        common.require(isinstance(reference,LedgerRef),"Production read needs an exact reference")
        with self.lock(),self._operation():
            rows,_,_,_ = _checked(self._load)
            common.require(reference in rows and rows[reference][1] is not None,"Missing or changed production original")
            return rows[reference][1]

    def admission(self, reference):
        with self.lock(),self._operation():
            rows,_,_,admissions = _checked(self._load)
            common.require(reference in rows and reference.record_id in admissions,"Unknown production timing original")
            return admissions[reference.record_id]

    def local_completion(self, reference):
        with self.lock(),self._operation():
            rows,contexts,_,_ = _checked(self._load)
            common.require(reference in rows and reference in contexts["local"],"Original has no acknowledged post-write completion")
            return contexts["local"][reference][1]

    def capacity(self):
        with self.lock(),self._operation(): return _checked(self._load)[2]

    @contextmanager
    def _verified_forecast_write(self, body, references):
        previous = self._permit
        self._permit = (digest(body),tuple(references))
        try: yield
        finally: self._permit = previous

    @contextmanager
    def _verified_remote_completion(self, references, archive_ref, remote_recovered_at):
        previous = self._remote_permit
        self._remote_permit = (frozenset(references),digest(common.archive_ref(archive_ref,diagnostic=self.allow_diagnostics)),remote_recovered_at)
        try: yield
        finally: self._remote_permit = previous

    def append_body(self, body, *, references=(), archive_refs=(), logical_id=None):
        with self.lock(),self._operation():
            _checked(common.validate_body,body)
            schema = body["schema_version"]
            common.require(schema in CEILINGS,"Unsupported production storage contract")
            refs = tuple(references); archives = list(archive_refs)
            common.require(all(isinstance(ref,LedgerRef) for ref in refs) and len(set(refs)) == len(refs),"Production references must be unique exact originals")
            for item in archives:
                common.archive_ref(item,diagnostic=self.allow_diagnostics and body.get("mode") == "DEVELOPMENT_ONLY")
            logical = _logical(body)
            common.require(logical_id is None or logical_id == logical,"Custom logical ID cannot bypass production duplicate protection")
            data = {"identity":_identity(body),"production":body,"archive_refs":archives}
            kind = common.KINDS[schema]
            record_id = digest({"kind":kind,"logical_id":logical})
            path = self.root/"records"/kind/(record_id+".json")
            exists = path.exists()
            if not exists:
                if schema == common.LOCAL_COMPLETION_SCHEMA:
                    common.require(self._local_permit == digest(body),"Local completion requires actual post-write capture")
                if schema == common.COMPLETION_SCHEMA:
                    common.require(self._remote_permit is not None and self._remote_permit[1:] == (digest(body["archive_ref"]),body["remote_recovered_at"])
                        and any(item.record_id == body["target"] for item in self._remote_permit[0]),"Remote completion requires actual independent archive recovery")
                if schema == common.FORECAST_SCHEMA and body["mode"] == "PROSPECTIVE_RESEARCH":
                    common.require(self._permit == (digest(body),refs),"Genuine forecast append requires verified production generation")
            size = _size(kind,logical,data,refs)
            common.require(size <= CEILINGS[schema],"Production envelope exceeds its typed byte ceiling")
            rows = self._rows()
            if not exists:
                # Validate prospective references and semantics before publishing
                # any new original; ordinary ledger validation also rechecks refs.
                synthetic = {"schema_version":SCHEMA,"kind":kind,"record_id":record_id,"logical_id":logical,
                    "received_at":stamp(common.now()),"data":data,"references":[ref.to_record() for ref in refs],
                    "supersedes":None,"persistence_status":"LOCAL_RECEIPT_ONLY"}
                prospective_ref = LedgerRef(kind,record_id,digest(synthetic))
                prospective = {**rows,prospective_ref:(synthetic,body,archives)}
                common.require(all(ref in rows for ref in refs),"Production append references missing originals")
                contexts = self._validate_graph(prospective)
                if schema == common.GRADE_SCHEMA and body["mode"] == "PROSPECTIVE_RESEARCH":
                    forecast_ref = next(ref for ref in refs if rows[ref][1]["schema_version"] == common.FORECAST_SCHEMA)
                    common.require(self._admission(forecast_ref,prospective,contexts)["eligible"],
                                   "Genuine grade cannot score an ineligible forecast")
                capacity = self._capacity(rows)
                common.require(capacity["fits"],"Actual records plus remaining production obligations exceed runtime limits")
                common.require(capacity["forensic_fits"] and capacity["remaining_forensic_files"] > 0
                    and capacity["remaining_forensic_bytes"] >= size,
                    "Production forensic failure allowance exhausted; preserve originals without new writes")
                counts = capacity["role_counts"]
                common.require(counts[schema] < SLOTS[schema],"Production role reserve exhausted")
            ref = self.ledger.append(kind,logical,data,references=refs)
            completed = stamp(common.now())
            if not exists and schema in TIMED_SCHEMAS:
                marker = common.seal({"schema_version":common.LOCAL_COMPLETION_SCHEMA,"protocol_id":common.PROTOCOL_ID,
                    "target":ref.record_id,"local_completed_at":completed},"completion_id")
                previous = self._local_permit
                self._local_permit = digest(marker)
                try: self.append_body(marker,references=(ref,))
                finally: self._local_permit = previous
            _checked(self._load)
            return ref

    def record_completion(self, reference, local_completed_at, remote_recovered_at, archive_ref):
        with self.lock(),self._operation():
            rows,contexts,_,_ = _checked(self._load)
            common.require(reference in contexts["local"],"Unacknowledged original cannot acquire an invented local completion")
            marker_ref,marker = contexts["local"][reference]
            common.require(marker["local_completed_at"] == local_completed_at,"Remote acknowledgment changed the original local completion")
            # Calculate admission from this exact proposed action, including
            # deadline/latency and already retained input/intent acknowledgments.
            body = common.seal({"schema_version":common.COMPLETION_SCHEMA,"protocol_id":common.PROTOCOL_ID,
                "target":reference.record_id,"local_completed_at":local_completed_at,
                "remote_recovered_at":remote_recovered_at,"archive_ref":archive_ref,
                "eligible":False,"reasons":["CALCULATING"]},"completion_id")
            contexts["remote"][reference] = body
            # _admission validates persisted claims; omit this temporary claim
            # while calculating, then cross-check after the immutable write.
            body["eligible"] = None
            result = self._admission_unclaimed(reference,rows,contexts)
            body.update(eligible=result["eligible"],reasons=result["reasons"])
            body = common.seal({key:value for key,value in body.items() if key != "completion_id"},"completion_id")
            return self.append_body(body,references=(reference,marker_ref))

    def _admission_unclaimed(self, reference, rows, contexts):
        remote = contexts["remote"][reference]
        # Admission checks can distinguish this in-process calculation from a
        # stored claim. No unclaimed dictionary is ever appended to the ledger.
        return self._admission(reference,rows,contexts)

    def correct(self, original, replacement, *, reason):
        with self.lock(),self._operation():
            common.text(reason,2048)
            rows,_,capacity,_ = _checked(self._load)
            common.require(original in rows and replacement in rows,"Correction lacks retained originals")
            before,after = rows[original][1],rows[replacement][1]
            common.require(before is not None and after is not None and _identity(before) == _identity(after)
                and before["schema_version"] == after["schema_version"]
                and before["schema_version"] in {common.OUTCOME_SCHEMA,common.GRADE_SCHEMA},"Correction changed typed subject")
            previous_key = "previous_outcome_id" if before["schema_version"] == common.OUTCOME_SCHEMA else "previous_grade_id"
            id_key = common.ID_KEYS[before["schema_version"]]
            common.require(after[previous_key] == before[id_key] and before["correction_revision"] == 1
                and after["correction_revision"] == 2,"Correction changed its exact original revision chain")
            logical = f"supersedes:{original.kind}:{original.record_id}"
            record_id = digest({"kind":"corrections","logical_id":logical})
            exists = (self.root/"records/corrections"/(record_id+".json")).exists()
            if not exists:
                common.require(capacity["forensic_fits"] and capacity["remaining_forensic_files"] > 0
                    and capacity["remaining_forensic_bytes"] >= 8192,
                    "Production forensic failure allowance exhausted; preserve originals without new writes")
                common.require(capacity["role_counts"]["corrections"] < SLOTS["corrections"],"Production correction reserve exhausted")
            ref = self.ledger.correct(original,replacement,reason=reason)
            _checked(self._load)
            return ref

    def snapshot_manifest(self):
        with self.lock(),self._operation():
            _,_,capacity,_ = _checked(self._load)
            entries,unpublished = self._snapshot_entries()
            return common.seal({"schema_version":SNAPSHOT_SCHEMA,"protocol_id":common.PROTOCOL_ID,
                "entries":entries,"unpublished_entries":unpublished,"records":len(entries),
                "bytes":sum(row["bytes"] for row in entries),"capacity":capacity},"snapshot_id")

    def _snapshot_entries(self):
        entries,unpublished = [],[]
        for kind,path,size,temporary in self._inventory():
            raw=path.read_bytes()
            common.require(len(raw) == size,"Production evidence changed during snapshot")
            item={"path":"records/"+kind+"/"+path.name,"bytes":size,"sha256":hashlib.sha256(raw).hexdigest()}
            if temporary:
                common.require(re.fullmatch(r"\.receipt-[A-Za-z0-9_-]{1,128}",path.name),
                               "Unsafe unpublished receipt filename")
                unpublished.append(item)
            else:entries.append(item)
        return sorted(entries,key=lambda row:row["path"]),sorted(unpublished,key=lambda row:row["path"])


def validate_snapshot_manifest(body):
    common.exact(body,{"schema_version","protocol_id","entries","unpublished_entries","records","bytes","capacity","snapshot_id"},"ledger snapshot")
    common.require(body["schema_version"] == SNAPSHOT_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID
        and type(body["entries"]) is list and type(body["unpublished_entries"]) is list
        and len(body["entries"])+len(body["unpublished_entries"]) <= MAX_RECORDS,"Wrong production snapshot protocol or inventory")
    paths = []
    for unpublished,collection in ((False,body["entries"]),(True,body["unpublished_entries"])):
        current=[]
        suffix=r"\.receipt-[A-Za-z0-9_-]{1,128}" if unpublished else r"[a-f0-9]{64}\.json"
        pattern=r"records/(?:"+"|".join(LEDGER_KINDS)+r")/"+suffix
        for row in collection:
            common.exact(row,{"path","bytes","sha256"},"snapshot entry")
            common.require(type(row["path"]) is str and re.fullmatch(pattern,row["path"])
                and type(row["bytes"]) is int and int(not unpublished) <= row["bytes"] <= MAX_RECORD_BYTES,
                "Unsafe production snapshot entry")
            common.sha(row["sha256"]);current.append(row["path"])
        common.require(current == sorted(set(current)),"Production snapshot entries repeat or reorder paths")
        if not unpublished:paths=current
    common.require(paths == sorted(set(paths)) and body["records"] == len(paths) and type(body["records"]) is int
        and body["bytes"] == sum(row["bytes"] for row in body["entries"]) and type(body["bytes"]) is int
        and body["bytes"]+sum(row["bytes"] for row in body["unpublished_entries"]) <= MAX_BYTES,
        "Production snapshot summary differs from exact admitted/unpublished entries")
    capacity = validate_capacity(body["capacity"])
    common.require(capacity["fits"] and sum(capacity["role_counts"].values()) == body["records"]
        and capacity["existing_records"] == body["records"]+len(body["unpublished_entries"])
        and capacity["existing_bytes"] == body["bytes"]+sum(row["bytes"] for row in body["unpublished_entries"])
        and capacity["forensic_bytes"] == sum(row["bytes"] for row in body["unpublished_entries"])
        and capacity["forensic_oversized_files"] == sum(row["bytes"] > MAX_FORENSIC_FILE_BYTES for row in body["unpublished_entries"]),
        "Production snapshot capacity differs from admitted and unpublished receipt inventory")
    common.check_seal(body,"snapshot_id")
    return body
