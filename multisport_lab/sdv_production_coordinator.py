"""Bounded native NBA phase engine for the one hosted operations coordinator.

Only preparation reserves provider requests. Workers recover immutable task and
source objects; they never collect, change cohorts or shift an expired window.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import re
import hashlib
import os
import sys
import tempfile

from .integrity import IntegrityError, digest, stamp, canonical
from . import sdv_production_common as common
from . import sdv_production_inputs as inputs
from . import sdv_production_forecasts as forecasts
from . import sdv_production_runner as runner
from .sdv_production_store import ProductionStore, validate_snapshot_manifest

TASK_SCHEMA="nba-sdv-production-task-v1"
TASK_FIELDS={"schema_version","protocol_id","mode","plan_ref","plan_source_pack_ref","input_ref","input_source_pack_ref",
    "branch","cycle_id","event_id","shard_index","player_ids","created_at","task_id"}
ACTIONS={"PREPARE","ISSUE","GRADE"}
COMPLETED_STATUSES={"PREPARED","ISSUED_PENDING_OUTCOMES","RECOVERED_ORIGINALS_OPEN_ATTEMPT","STATISTICAL_GRADING_RETAINED"}


def _error(error):
    value=re.sub(r"[\x00-\x1f\x7f]"," ",str(error))
    return re.sub(r"(https?://[^\s?#]+)[?#][^\s]*",r"\1",value)[:1000]


def validate_task(body):
    common.exact(body,TASK_FIELDS,"immutable worker task")
    common.require(body["schema_version"] == TASK_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID
        and body["mode"] in inputs.MODES,"Wrong production task scope")
    for key in ("plan_ref","plan_source_pack_ref","input_ref","input_source_pack_ref"):common.archive_ref(body[key])
    common.require(type(body["shard_index"]) is int and body["branch"] == common.shard_branch(body["cycle_id"],body["shard_index"]),"Task branch/shard identity differs")
    common.require(type(body["player_ids"]) is list and 0 < len(body["player_ids"]) <= common.make_policy()["players_per_shard"]
        and all(type(pid) is str and re.fullmatch(r"[1-9][0-9]*",pid) for pid in body["player_ids"])
        and len(body["player_ids"]) == len(set(body["player_ids"])),"Task player identities differ")
    common.require(type(body["event_id"]) is str and re.fullmatch(r"[1-9][0-9]*",body["event_id"]),"Invalid task event identity")
    common.require(common.clock(body["created_at"]) <= common.now(),"Future worker task")
    common.check_seal(body,"task_id");return body


_OWNED_ISSUANCE_ATTEMPTS={}


class _IssuanceAttempt:
    __slots__=("reference","body","store_root","authorization","closed_reference")
    def __init__(self,reference,body,store,authorization):
        self.reference=reference;self.body=body;self.store_root=Path(store.root).absolute()
        self.authorization=authorization;self.closed_reference=None


def open_issuance_attempt(store,*,input_body,task_id,shard_index,authorization,checkpoint):
    """Durably expose an in-progress writer before any original generation.

    A recovered OPEN is uncertainty, not a license to regenerate invisible local
    originals. Only this process receives the private handle that can close its
    own attempt after independently retaining the entire resulting footprint.
    """
    inputs.validate_input(input_body);common.sha(task_id)
    common.require(type(shard_index) is int and 0 <= shard_index < len(input_body["shards"])
        and callable(checkpoint),"Issuance guard needs an exact shard and checkpoint")
    genuine=input_body["mode"] == "PROSPECTIVE_RESEARCH"
    if genuine:runner.require_execution_context(authorization,input_body,input_body["producer_binding"])
    else:common.require(authorization is None,"Development cannot borrow genuine attempt authority")
    records=store.records();scoped=[body for _,body in records if body["schema_version"] == common.STATUS_SCHEMA
        and body["phase"] == "ISSUE" and body["details"].get("task_id") == task_id]
    closed={body["details"]["issuance_attempt"]["open_status_id"] for body in scoped if body["status"] == runner.ISSUE_CLOSED}
    unresolved=[body["status_id"] for body in scoped if body["status"] == runner.ISSUE_OPEN and body["status_id"] not in closed]
    if unresolved:
        # Existing bytes may still receive their factual timely acknowledgment.
        # This path never fits a model, fabricates a peer or closes the prior
        # process's unknown footprint.
        player_ids=input_body["shards"][shard_index]
        originals=[(ref,record) for ref,record in records if record["schema_version"] == common.FORECAST_SCHEMA
            and record["cycle_id"] == input_body["cycle_id"] and record["player_id"] in player_ids]
        pending=[ref for ref,_ in originals if store.admission(ref)["remote_recovered_at"] is None]
        if pending:
            if genuine:
                inputs.freshness(input_body,at=common.now(),require_retrieval_window=True)
                for ref,original in originals:
                    if ref in pending:forecasts._window(input_body["event"],common.now(),started=common.clock(original["generation_started_at"]))
            checkpoint(tuple(pending))
        expected={(pid,key) for pid in player_ids for key in common.MODEL_VERSIONS}
        if {(record["player_id"],record["model_key"]) for _,record in originals} == expected:
            if genuine:common.require(all(store.admission(ref)["eligible"] for ref,_ in originals),"Recovered originals remain late or ineligible; no missing generation is permitted")
            return None
        raise IntegrityError("Earlier issuance attempt remains OPEN; recover original emergency bytes before generating missing forecasts")
    common.require(not store.recover()["unpublished_entries"],"Unpublished original receipt bytes require recovery before missing generation")
    actual=stamp(common.now());run_id=(authorization or {}).get("run_id",0);run_attempt=(authorization or {}).get("run_attempt",1)
    details={"task_id":task_id,"shard_index":shard_index,"player_ids":input_body["shards"][shard_index],"error":None,
        "final_source_pack_ref":None,"processing_complete":False}
    attempt_number=1+sum(record["status"] == runner.ISSUE_OPEN for record in scoped)
    attempt={"attempt_id":digest({key:details[key] for key in ("task_id","shard_index","player_ids")}|{
        "run_id":run_id,"run_attempt":run_attempt,"opened_at":actual,"attempt_number":attempt_number}),"attempt_number":attempt_number,"run_attempt":run_attempt,"opened_at":actual,
        "open_status_id":None,"footprint_snapshot_ref":None,"footprint_snapshot_id":None,"footprint_recovered_at":None}
    details["issuance_attempt"]=attempt
    body=common.seal({"schema_version":common.STATUS_SCHEMA,"protocol_id":common.PROTOCOL_ID,"plan_id":input_body["plan_id"],
        "cycle_id":input_body["cycle_id"],"phase":"ISSUE","status":runner.ISSUE_OPEN,"details":details,"observed_at":actual,"run_id":run_id},"status_id")
    reference=store.append_body(body);proof=checkpoint(())
    common.require(type(proof) is dict and proof.get("snapshot_ref") is not None,"Issuance OPEN has no independent durable readback")
    snapshot=store.snapshot_resolver(proof["snapshot_ref"]);validate_snapshot_manifest(snapshot)
    path="records/"+reference.kind+"/"+reference.record_id+".json";raw=(Path(store.root)/path).read_bytes()
    common.require({"path":path,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()} in snapshot["entries"],
        "Independently recovered issuance snapshot lacks its exact OPEN original")
    if genuine:runner.require_execution_context(authorization,input_body,input_body["producer_binding"])
    handle=_IssuanceAttempt(reference,body,store,authorization);_OWNED_ISSUANCE_ATTEMPTS[id(handle)]=handle
    return handle


def close_issuance_attempt(store,handle,*,checkpoint,error=None):
    """Close only an actually owned attempt, after its entire footprint recovers."""
    common.require(_OWNED_ISSUANCE_ATTEMPTS.get(id(handle)) is handle and isinstance(handle,_IssuanceAttempt)
        and Path(store.root).absolute() == handle.store_root and callable(checkpoint),"Only this process's original issuance handle can close its attempt")
    if handle.authorization is not None:runner.require_current_authority(handle.authorization)
    if handle.closed_reference is None:
        proof=checkpoint(())
        common.require(type(proof) is dict and proof.get("snapshot_ref") is not None,"Issuance closure has no independently recovered footprint")
        snapshot=store.snapshot_resolver(proof["snapshot_ref"]);validate_snapshot_manifest(snapshot)
        common.require(snapshot == store.snapshot_manifest(),"Issuance closure does not cover the complete current original/forensic footprint")
        body=deepcopy(handle.body);body.pop("status_id")
        body["status"]=runner.ISSUE_CLOSED;body["observed_at"]=stamp(common.now());body["details"]["error"]=error
        body["details"]["issuance_attempt"].update(open_status_id=handle.body["status_id"],footprint_snapshot_ref=proof["snapshot_ref"],
            footprint_snapshot_id=snapshot["snapshot_id"],footprint_recovered_at=proof["remote_recovered_at"])
        closed=common.seal(body,"status_id")
        with store._verified_issue_closure(closed,proof["snapshot_ref"],proof["remote_recovered_at"]):
            handle.closed_reference=store.append_body(closed)
    checkpoint(())
    _OWNED_ISSUANCE_ATTEMPTS.pop(id(handle),None)
    return handle.closed_reference


class Coordinator:
    def __init__(self,registry,writer,archive,authorization,work_root,*,mode="PROSPECTIVE_RESEARCH",source_root=None,
                 binding=None,collector=None,remote_factory=None,store_factory=None):
        common.require(mode in inputs.MODES,"Unknown coordinator mode")
        common.require(mode == "DEVELOPMENT_ONLY" or collector is None and remote_factory is None and store_factory is None,
            "Genuine operation cannot replace its collector, records transport or store")
        self.registry=runner.validate_registry(deepcopy(registry));self.writer=writer;self.archive=archive
        self.authorization=authorization;self.mode=mode;self.root=Path(work_root).absolute()
        common.require(not any(path.is_symlink() for path in (self.root,*self.root.parents)),"Coordinator work root traverses symlink")
        self.root.mkdir(parents=True,exist_ok=True)
        self.source_root=Path(source_root or Path(__file__).resolve().parents[1])
        self.binding=binding;self.collector=collector or runner.collect_sources;self.remote_factory=remote_factory;self.store_factory=store_factory or ProductionStore
        self.reports=[];self._capacity_cache={}
        self._authority()
        prior=self.registry.get("archive_budget")
        if prior is not None:
            runner.validate_archive_budget(prior,registry=self.registry)
            for row in prior["shards"]:
                if row["snapshot_ref"] is not None:
                    snapshot=self.archive.get_json(row["snapshot_ref"])["ledger_snapshot"]
                    validate_snapshot_manifest(snapshot)
                    common.require(snapshot["capacity"] == row["capacity"],"Cold archive reservation differs from its exact authenticated snapshot")
                    self._capacity_cache[digest(row["snapshot_ref"])]=snapshot["capacity"]
            self.archive.reserved_bytes=prior["reserved_bytes"];self.archive.reserved_objects=prior["reserved_objects"]

    def _authority(self):
        if self.mode == "DEVELOPMENT_ONLY":
            common.require(self.authorization is None,"Development cannot borrow operating authorization")
            return
        runner.require_current_authority(self.authorization)


    @staticmethod
    def _directory_bytes(root):
        """Logical regular-file bytes, without following directory symlinks."""
        total=0
        if not Path(root).exists():return total
        for base,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[name for name in dirs if not (Path(base)/name).is_symlink()]
            for name in files:
                path=Path(base)/name
                if not path.is_symlink():total+=path.stat().st_size
        return total

    def _runtime_guard(self,*,reserve=0):
        common.require(type(reserve) is int and reserve >= 0,"Invalid runtime disk reservation")
        roots=((self.root,) if self.source_root == self.root or self.root in self.source_root.parents else
            (self.source_root,) if self.source_root in self.root.parents else (self.root,self.source_root))
        actual=sum(self._directory_bytes(path) for path in roots)
        maximum=common.make_policy()["runtime_disk_bytes"]
        report_reserve=runner.HOSTED_RUN_OBSERVATION_DISK_RESERVE
        common.require(actual+reserve+report_reserve <= maximum,"Aggregate runtime work state and source checkout exceed the explicit two-GiB disk budget")
        return {"actual_bytes":actual,"reserved_bytes":reserve,"maximum_bytes":maximum,
            "hosted_run_observation_reserved_bytes":report_reserve}

    @contextmanager
    def _read_store(self,task):
        # Only fresh recovered caches are temporary. Worker originals, partial
        # writes and unacknowledged state are never removed by this path.
        self._runtime_guard()
        with tempfile.TemporaryDirectory(prefix="read-only-",dir=self.root) as folder:
            store,remote=self._store(task,work_root=Path(folder))
            yield store,remote
            self._runtime_guard()

    @property
    def tag(self):return common.archive_month(common.now())

    def _save(self,status,details=None):
        self._authority()
        run=self.authorization or {}
        shards=[row for day in self.registry["days"] for row in day["shards"]]
        persistent=("INCOMPLETE_OR_UNOBSERVED_WINDOW" if (details or {}).get("reason") else
            "RESEARCH_RECORDS_RETAINED" if any(row["issued_input_task_ref"] is not None for row in shards) else
            "INPUTS_RETAINED" if any(row["input_task_ref"] is not None for row in shards) else
            "PLANS_RETAINED" if shards else "NOT_STARTED")
        self.registry["status"]=persistent
        self.registry["last_run"]=(None if self.mode == "DEVELOPMENT_ONLY" else
            {"run_id":run["run_id"],"run_attempt":run["run_attempt"],"observed_at":stamp(common.now()),"status":status,"details":details or {}})
        if self.mode == "DEVELOPMENT_ONLY":self.registry["status"]="DEVELOPMENT_ONLY_"+persistent
        budget=self._budget()
        self.registry["archive_budget"]=budget
        self.archive.reserved_bytes=max(self.archive.reserved_bytes,budget["reserved_bytes"])
        self.archive.reserved_objects=max(self.archive.reserved_objects,budget["reserved_objects"])
        self.registry=self.writer.write(self.registry)
        return self.registry

    def _binding(self):
        if self.binding is None:self.binding=forecasts.make_source_binding(self.authorization["head_sha"] if self.authorization else None)
        inputs.validate_binding(self.binding,prospective=self.mode == "PROSPECTIVE_RESEARCH")
        if self.mode == "PROSPECTIVE_RESEARCH":forecasts.validate_binding(self.binding,current=True)
        return self.binding

    def _pack(self,reference):return runner.recover_source_pack(reference,self.archive)

    @staticmethod
    def _source_refs(pack,roles=("schedule","roster")):
        by_role={row["role"]:row["source_ref"] for row in pack["sources"]}
        common.require(set(by_role) == set(roles),"Source pack roles differ from the requested phase")
        return tuple(by_role[role] for role in roles)

    def _budget(self):
        from .sdv_production_store import empty_capacity,validate_snapshot_manifest
        rows=[]
        for day in self.registry["days"]:
            for shard in day["shards"]:
                ref=shard["snapshot_ref"]
                if ref is None:capacity=empty_capacity()
                else:
                    key=digest(ref)
                    if key not in self._capacity_cache:
                        snapshot=self.archive.get_json(ref)["ledger_snapshot"]
                        validate_snapshot_manifest(snapshot);self._capacity_cache[key]=snapshot["capacity"]
                    capacity=self._capacity_cache[key]
                rows.append({"branch":shard["branch"],"snapshot_ref":ref,"capacity":capacity})
        budget=runner.make_archive_budget(rows)
        old=self.registry.get("archive_budget")
        if old is not None and all(old[key] == value for key,value in budget.items() if key not in {"observed_at","budget_id"}):return old
        return budget

    def _reserve_archive(self,*,additional_shards=0,source_headroom=0,new_admission=False):
        from .sdv_production_store import archive_liability,empty_capacity
        common.require(type(additional_shards) is int and additional_shards >= 0 and type(source_headroom) is int and source_headroom >= 0,
            "Invalid closed archive admission reservation")
        budget=self._budget();extra=additional_shards*archive_liability(empty_capacity())
        if new_admission or additional_shards:
            common.require(all(row["capacity"]["forensic_fits"] for row in budget["shards"]),
                "An outstanding shard exceeds its forensic evidence limit; no new cohort may be admitted")
        extra_objects=additional_shards*runner.archive_object_liability(empty_capacity())
        if additional_shards and not budget["shards"]:
            policy=common.make_policy()
            extra+=policy["correction_capture_days"]*policy["maximum_final_captures_per_day"]*(2*policy["maximum_csv_bytes"]+2*policy["maximum_metadata_bytes"])
            extra+=policy["maximum_parallel_shards"]*policy["archive_object_bytes"]
            extra_objects+=runner.shared_source_object_liability()+256
        source_objects=(2*((common.make_policy()["maximum_csv_bytes"]+common.make_policy()["archive_chunk_bytes"]-1)//common.make_policy()["archive_chunk_bytes"])+6) if source_headroom else 0
        self.archive.reserved_objects=budget["reserved_objects"]+extra_objects+source_objects
        self.archive.reserved_bytes=budget["reserved_bytes"]+extra+source_headroom
        quota=self.archive.quota(self.tag)
        common.require(quota["fits"],"Archive quota cannot cover all unused roles, pending grading, sources, metadata and parallel writes; stop new capture/issuance")
        # Source's exact new bytes have a separate per-phase hard ceiling. They
        # need not remain double-counted while their actual uploads accrue.
        self.archive.reserved_bytes=budget["reserved_bytes"]+extra
        self.archive.reserved_objects=budget["reserved_objects"]+extra_objects
        return {"additional_shards":additional_shards,"source_headroom_bytes":source_headroom,**quota}

    def _capture(self,phase,scope,*,season,opens,closes,final=False):
        self._authority()
        common.require(opens <= common.now() <= closes,"Source phase window is not open or was missed")
        if self.mode == "DEVELOPMENT_ONLY":common.require(self.collector is not runner.collect_sources,"Development requires an explicit retained/synthetic source collector")
        policy=common.make_policy()
        self._runtime_guard(reserve=policy["source_gets_per_capture"]*policy["maximum_csv_bytes"])
        source_headroom=policy["source_gets_per_capture"]*policy["maximum_csv_bytes"]
        self._reserve_archive(source_headroom=source_headroom,new_admission=phase == "PLAN")
        row=runner.reserve_capture(self.registry,self.writer,phase=phase,scope=list(scope))
        self.registry["attempts"].append(row)
        # An interrupted run cannot reset the reserved GET count. No GET is
        # possible before this small Git index has independently recovered.
        self._save("CAPTURE_RESERVED",{"attempt_id":row["attempt_id"],"phase":phase})
        old_remaining=(None if self.archive.write_budget_bytes is None else self.archive.write_budget_bytes-self.archive.new_bytes_reserved)
        old_objects=(None if self.archive.write_budget_objects is None else self.archive.write_budget_objects-self.archive.new_objects_reserved)
        self.archive.write_budget_bytes=self.archive.new_bytes_reserved+source_headroom
        source_objects=2*((policy["maximum_csv_bytes"]+policy["archive_chunk_bytes"]-1)//policy["archive_chunk_bytes"])+6
        self.archive.write_budget_objects=self.archive.new_objects_reserved+source_objects+4
        try:
            ref,pack=self.collector(self.root/"originals"/row["attempt_id"],self.archive,season=season,tag=self.tag,opens_at=opens,closes_at=closes,final=final,authorization=self.authorization)
            common.archive_ref(ref)
            self._runtime_guard()
            common.require(opens <= common.clock(pack["captured_at"]) <= common.now() <= closes,
                "Source capture or durable archive completion missed its actual phase window")
            common.require(len(pack["requests"]) <= row["reserved_gets"],"Actual collection exceeded its original reservation")
            row.update(status="CAPTURED",used_gets=len(pack["requests"]),source_pack_ref=ref)
            # _save replaced the projection object; update the matching original
            # attempt instead of relying on an alias from the previous revision.
            current=next(item for item in self.registry["attempts"] if item["attempt_id"] == row["attempt_id"]);current.update(row)
            self._save("SOURCE_CAPTURED",{"attempt_id":row["attempt_id"]})
            return ref,pack
        except Exception as error:
            current=next(item for item in self.registry["attempts"] if item["attempt_id"] == row["attempt_id"])
            current["status"]="FAILED"
            try:
                current["source_pack_ref"]=runner.preserve_failed_capture(self.root/"originals"/row["attempt_id"],self.archive,
                    tag=self.tag,authorization=self.authorization,error=error)
            except Exception as retention_error:
                self.reports.append({"phase":"FAILURE_RETENTION","attempt_id":row["attempt_id"],"error":_error(retention_error)})
            self._save("CAPTURE_FAILED",{"attempt_id":row["attempt_id"],"error":_error(error),"unknown_total_still_reserved":True})
            raise
        finally:
            self.archive.write_budget_bytes=(None if old_remaining is None else self.archive.new_bytes_reserved+max(0,old_remaining))
            self.archive.write_budget_objects=(None if old_objects is None else self.archive.new_objects_reserved+max(0,old_objects))

    def _new_plan(self):
        now=common.now();policy=common.make_policy();game_date=(now.date()+timedelta(days=1)).isoformat()
        if any(day["game_date"] == game_date for day in self.registry["days"]):return
        opens,closes=inputs._planning_window(game_date)
        if not opens <= now <= closes or inputs._date(game_date) < common.clock(policy["enabled_after"]).date():return
        season=now.year+1 if now.month >= 7 else now.year
        ref,_=self._capture("PLAN",[game_date],season=season,opens=opens,closes=closes)
        _,sources=self._pack(ref);s,r=sources["schedule"],sources["roster"]
        plan=inputs.make_plan(s[0],r[0],s[1],r[1],source_originals={"schedule":s[2],"roster":r[2]},game_date=game_date,
            producer_binding=self._binding(),mode=self.mode)
        self._reserve_archive(additional_shards=sum(len(event["shards"]) for event in plan["events"]))
        plan_ref=self.archive.put_json(plan,tag=self.tag)
        common.require(self.archive.fresh_reader().get_json(plan_ref) == plan,"Independent archived daily plan readback differs")
        shards=[]
        for event in plan["events"]:
            for index,_ in enumerate(event["shards"]):
                shards.append({"branch":common.shard_branch(event["cycle_id"],index),"cycle_id":event["cycle_id"],"event_id":event["event"]["event_id"],
                    "shard_index":index,"plan_id":plan["plan_id"],"latest_commit":None,"snapshot_ref":None,"input_task_ref":None,"final_source_pack_ref":None,
                    "prepared_input_task_ref":None,"issued_input_task_ref":None,"graded_source_pack_ref":None})
        self.registry["days"].append({"schema_version":runner.DAY_SCHEMA,"game_date":game_date,"plan_ref":plan_ref,"source_pack_ref":ref,
            "plan_id":plan["plan_id"],"shards":shards,"attempts":[],"pending_inputs":[],"status":"PLANNED" if shards else "NO_ELIGIBLE_EVENTS"})
        self._save("DAILY_PLAN_RETAINED",{"game_date":game_date,"events":len(plan["events"]),"subjects":sum(len(event["candidates"]) for event in plan["events"])})

    def _new_inputs(self):
        due=[];retained={};now=common.now()
        for day in self.registry["days"]:
            plan=self.archive.get_json(day["plan_ref"]);inputs.validate_plan(plan)
            for event in plan["events"]:
                shards=[row for row in day["shards"] if row["cycle_id"] == event["cycle_id"]]
                existing=[row["input_task_ref"] for row in shards if row["input_task_ref"] is not None]
                common.require(not existing or len(existing) == len(shards),"Partial shared-input registry cannot silently replace missing shards")
                if existing:continue
                opens,cutoff=(common.clock(event[key]) for key in ("capture_opens_at","cutoff_at"))
                if not opens <= now <= cutoff:continue
                pending=next((row for row in day["pending_inputs"] if row["cycle_id"] == event["cycle_id"]),None)
                if pending is not None:
                    key=digest(pending["input_source_pack_ref"])
                    retained.setdefault(key,(pending["input_source_pack_ref"],[]))[1].append((day,plan,event))
                    continue
                originals=[attempt for attempt in self.registry["attempts"] if attempt["phase"] == "INPUT"
                    and attempt["status"] == "CAPTURED" and event["cycle_id"] in attempt["scope"] and attempt["source_pack_ref"] is not None]
                if originals and day["status"] != "INPUT_UNAVAILABLE":
                    original=min(originals,key=lambda row:common.clock(row["started_at"]))
                    key=digest(original["source_pack_ref"])
                    retained.setdefault(key,(original["source_pack_ref"],[]))[1].append((day,plan,event))
                elif now <= cutoff-timedelta(minutes=15):due.append((day,plan,event))
        # Recover exact original bytes after a capture/registration interruption.
        # No additional request is needed and no already-bound input is changed.
        for ref,events in retained.values():self._bind_inputs(events,ref)
        if not due:return
        seasons={event["event"]["season_ending_year"] for _,_,event in due}
        common.require(len(seasons) == 1,"A shared capture cannot mix source seasons")
        opens=max(common.clock(event["capture_opens_at"]) for _,_,event in due)
        closes=min(common.clock(event["cutoff_at"]) for _,_,event in due)
        ref,_=self._capture("INPUT",[event["cycle_id"] for _,_,event in due],season=seasons.pop(),opens=opens,closes=closes)
        self._bind_inputs(due,ref)

    def _bind_inputs(self,due,ref):
        _,sources=self._pack(ref);s,r=sources["schedule"],sources["roster"]
        for day,plan,event in due:
            # The registry may have been resealed/copied by _capture.
            current=next(row for row in self.registry["days"] if row["game_date"] == day["game_date"])
            try:
                pending=next((row for row in current["pending_inputs"] if row["cycle_id"] == event["cycle_id"]),None)
                if pending is None:
                    body=inputs.make_input(plan,event["event"]["event_id"],s[0],r[0],s[1],r[1],source_originals={"schedule":s[2],"roster":r[2]},mode=self.mode)
                    input_ref=self.archive.put_json(body,tag=self.tag)
                    common.require(self.archive.fresh_reader().get_json(input_ref) == body,"Independent archived shared input readback differs")
                    current["pending_inputs"].append({"cycle_id":event["cycle_id"],"input_ref":input_ref,"input_source_pack_ref":ref})
                    # A failed later task upload can recover this exact input,
                    # including its original normalization clock and input ID.
                    self._save("SHARED_INPUT_PENDING_TASKS",{"cycle_id":event["cycle_id"]})
                    current=next(row for row in self.registry["days"] if row["game_date"] == day["game_date"])
                else:
                    common.require(pending["input_source_pack_ref"] == ref,"Pending input source changed during recovery")
                    input_ref=pending["input_ref"];body=self.archive.get_json(input_ref)
                    inputs.verify_input_sources(body,s[0],r[0],s[1],r[1],source_originals={"schedule":s[2],"roster":r[2]},plan=plan)
                common.require(common.now() <= common.clock(event["cutoff_at"]),"Input task preparation missed T90")
                prepared_tasks=[]
                for index,ids in enumerate(event["shards"]):
                    shard=next(row for row in current["shards"] if row["cycle_id"] == event["cycle_id"] and row["shard_index"] == index)
                    task=common.seal({"schema_version":TASK_SCHEMA,"protocol_id":common.PROTOCOL_ID,"mode":self.mode,"plan_ref":current["plan_ref"],
                        "plan_source_pack_ref":current["source_pack_ref"],"input_ref":input_ref,"input_source_pack_ref":ref,
                        "branch":shard["branch"],"cycle_id":shard["cycle_id"],"event_id":shard["event_id"],"shard_index":index,
                        "player_ids":ids,"created_at":stamp(common.now())},"task_id")
                    validate_task(task);reference=self.archive.put_json(task,tag=self.tag)
                    common.require(self.archive.fresh_reader().get_json(reference) == task,"Independent archived worker task differs")
                    prepared_tasks.append((shard,reference))
                common.require(common.now() <= common.clock(event["cutoff_at"]),"Input task archive completion missed T90")
                for shard,reference in prepared_tasks:shard["input_task_ref"]=reference
                current["pending_inputs"]=[row for row in current["pending_inputs"] if row["cycle_id"] != event["cycle_id"]]
                current["status"]="INPUT_RETAINED"
            except (IntegrityError,OSError,ValueError) as error:
                self.reports.append({"phase":"INPUT","cycle_id":event["cycle_id"],"error":_error(error)})
                current["status"]="INPUT_UNAVAILABLE"
        self._save("SHARED_INPUTS_RETAINED",{"events":len(due),"failures":len(self.reports)})

    def _store(self,task,*,work_root=None):
        policy=common.make_policy();base_root=Path(work_root or self.root)
        # Allow room for the store, its independent readback and bounded Git/
        # archive work before any materialization begins.
        source_bytes=self._directory_bytes(self.source_root)
        self._runtime_guard(reserve=3*(policy["runtime_ledger_bytes"]+source_bytes)+3*policy["archive_object_bytes"])
        name=task["branch"].replace("/","-")
        store=self.store_factory(base_root/"shards"/name,source_root=self.source_root,source_resolver=self.archive.recover_source,
            snapshot_resolver=lambda ref:self.archive.get_json(ref)["ledger_snapshot"])
        factory=self.remote_factory
        if self.mode == "DEVELOPMENT_ONLY":common.require(factory is not None,"Development requires an explicit isolated records transport")
        if factory is None:
            from .sdv_production_remote import ProductionGitCheckpointWriter
            factory=ProductionGitCheckpointWriter
        plan=self.archive.get_json(task["plan_ref"])
        base=plan["producer_binding"]["commit"]
        common.require(base is not None or self.mode == "DEVELOPMENT_ONLY","Genuine shard has no frozen source commit")
        remote=factory(self.source_root,base_root/"writers"/name,base_commit=base,branch=task["branch"],archive=self.archive,tag=self.tag)
        remote.prepare();remote.restore(store)
        self._runtime_guard()
        return store,remote

    def _eligible_final_shards(self):
        result=[];now=common.now();limit=timedelta(days=common.make_policy()["correction_capture_days"])
        for day in self.registry["days"]:
            plan=self.archive.get_json(day["plan_ref"])
            events={event["cycle_id"]:event for event in plan["events"]}
            for shard in day["shards"]:
                if shard["input_task_ref"] is None:continue
                start=common.clock(events[shard["cycle_id"]]["event"]["event_starts_at"])
                if start <= now <= start+limit:result.append((day,shard,events[shard["cycle_id"]]))
        return result

    def _final_sources(self):
        now=common.now();policy=common.make_policy()
        if now.hour != policy["planning_hour_utc"]:return
        if sum(row["phase"] == "FINAL" and common.clock(row["started_at"]).date() == now.date() for row in self.registry["attempts"]) >= policy["maximum_final_captures_per_day"]:return
        due=self._eligible_final_shards()
        if not due:return
        # Confirm at least one actually retained original before a final-data
        # GET. PREPARE-only branches do not establish prospective forecasts.
        has_original=False
        for _,shard,_ in due:
            task=validate_task(self.archive.get_json(shard["input_task_ref"]))
            with self._read_store(task) as (store,_):
                originals=store.recover()["forecasts"]
                if originals and (self.mode == "DEVELOPMENT_ONLY" or any(store.admission(ref)["eligible"] for ref,_ in originals)):
                    has_original=True
            if has_original:break
        if not has_original:return
        scopes=sorted({row[1]["cycle_id"] for row in due});season={row[2]["event"]["season_ending_year"] for row in due}
        common.require(len(season) == 1,"Final capture cannot mix source seasons")
        opens=now.replace(hour=policy["planning_hour_utc"],minute=0,second=0,microsecond=0)
        closes=min(opens+timedelta(hours=1),min(common.clock(event["event"]["event_starts_at"])+timedelta(days=policy["correction_capture_days"]) for _,_,event in due))
        ref,_=self._capture("FINAL",scopes,season=season.pop(),opens=opens,closes=closes,final=True)
        for day,shard,_ in due:
            current=next(row for row in self.registry["days"] if row["game_date"] == day["game_date"])
            next(row for row in current["shards"] if row["branch"] == shard["branch"])["final_source_pack_ref"]=ref
        self._save("SHARED_FINAL_SOURCE_RETAINED",{"cycles":len(scopes)})

    def _retention(self):
        now=common.now();keep=[]
        for day in self.registry["days"]:
            plan=self.archive.get_json(day["plan_ref"])
            starts=[common.clock(event["event"]["event_starts_at"]) for event in plan["events"]]
            latest=max(starts,default=common.clock(plan["planned_at"]))
            if inputs._date(day["game_date"]) < now.date()-timedelta(days=6):
                reference=self.archive.put_json(day,tag=self.tag)
                previous=next((row for row in self.registry["archived_days"] if row["game_date"] == day["game_date"]),None)
                if previous is None:self.registry["archived_days"].append({"game_date":day["game_date"],"archive_ref":reference})
                else:previous["archive_ref"]=reference
            pending=any(shard["final_source_pack_ref"] is not None and shard["graded_source_pack_ref"] != shard["final_source_pack_ref"] for shard in day["shards"])
            if pending or now <= latest+timedelta(days=common.make_policy()["correction_capture_days"]):keep.append(day)
        self.registry["days"]=keep
        old=[row for row in self.registry["attempts"] if common.clock(row["started_at"]).date() < now.date()-timedelta(days=8)]
        if old:
            reference=self.archive.put_json({"schema_version":"nba-sdv-production-attempt-archive-v1","attempts":old},tag=self.tag)
            self.registry["archived_attempts"].append(reference)
            ids={row["attempt_id"] for row in old};self.registry["attempts"]=[row for row in self.registry["attempts"] if row["attempt_id"] not in ids]

    def _window_status(self):
        """Describe closed windows from retained inventory, without backfill."""
        now=common.now();first=common.clock(common.make_policy()["enabled_after"]).date()
        known={day["game_date"] for day in self.registry["days"]+self.registry["archived_days"]}
        target=now.date()+timedelta(days=1);start=max(first,now.date()-timedelta(days=9));missing=[]
        cursor=start
        while cursor <= target:
            date=cursor.isoformat()
            if date not in known and inputs._planning_window(date)[1] < now:missing.append(date)
            cursor+=timedelta(days=1)
        branches=[]
        for day in self.registry["days"]:
            events={row["cycle_id"]:row for row in self.archive.get_json(day["plan_ref"])["events"]}
            for shard in day["shards"]:
                if common.clock(events[shard["cycle_id"]]["issuance_closes_at"]) < now and (
                    shard["input_task_ref"] is None or shard["issued_input_task_ref"] != shard["input_task_ref"]):
                    branches.append(shard["branch"])
        result={"missed_planning_dates":len(missing),"unacknowledged_issuance_shards":len(branches),
            "affected_game_dates":missing[:8],"affected_branches":branches[:8]}
        if missing or branches:result["reason"]="INCOMPLETE_OR_UNOBSERVED_WINDOW"
        return result

    def prepare_tasks(self):
        self._authority();self._retention()
        for phase in (self._new_plan,self._new_inputs,self._final_sources):
            try:phase()
            except (IntegrityError,OSError,ValueError) as error:self.reports.append({"phase":phase.__name__,"error":_error(error)})
        tasks=[];now=common.now()
        for day in self.registry["days"]:
            plan=self.archive.get_json(day["plan_ref"]);events={event["cycle_id"]:event for event in plan["events"]}
            for shard in day["shards"]:
                if shard["input_task_ref"] is None:continue
                event=events[shard["cycle_id"]];cutoff=common.clock(event["cutoff_at"])
                action="PREPARE" if common.clock(event["capture_opens_at"]) <= now < cutoff else "ISSUE" if cutoff <= now <= common.clock(event["issuance_closes_at"]) else None
                if action is None and shard["final_source_pack_ref"] is not None and common.clock(event["event"]["event_starts_at"]) <= now:action="GRADE"
                if action == "PREPARE" and shard["prepared_input_task_ref"] == shard["input_task_ref"]:action=None
                if action == "ISSUE" and shard["issued_input_task_ref"] == shard["input_task_ref"]:action=None
                if action == "GRADE" and shard["graded_source_pack_ref"] == shard["final_source_pack_ref"]:action=None
                if action is not None:tasks.append({"action":action,"task_ref":shard["input_task_ref"],"final_source_pack_ref":shard["final_source_pack_ref"],
                    "branch":shard["branch"],"cycle_id":shard["cycle_id"],"shard_index":shard["shard_index"]})
        events={event["cycle_id"]:event for day in self.registry["days"] for event in self.archive.get_json(day["plan_ref"])["events"]}
        def priority(task):
            event=events[task["cycle_id"]]
            deadline=event["cutoff_at"] if task["action"] == "PREPARE" else event["issuance_closes_at"]
            return (task["action"] == "GRADE",common.clock(event["event"]["event_starts_at"] if task["action"] == "GRADE" else deadline),task["branch"])
        tasks.sort(key=priority)
        details={"tasks":len(tasks),"failures":len(self.reports),**self._window_status()}
        if self.reports:details["recent_errors"]=[{"phase":row["phase"],"error":row["error"][:240]} for row in self.reports[-8:]]
        self._save("TASKS_READY",details)
        return tasks

    def _grade(self,store,task,input_ref,final_ref):
        pack,_=self._pack(final_ref);sref,bref=self._source_refs(pack,("schedule","boxscore"))
        records=store.records();originals=[(ref,body) for ref,body in records if body["schema_version"] == common.FORECAST_SCHEMA]
        result={"outcomes":0,"grades":0,"pending":[],"correction_quota_exhausted":[],"unscored_originals":[],
            "unscored_reason":"ORIGINAL_NOT_TIMELY_ADMITTED"}
        semantic=lambda body:{key:value for key,value in body.items() if key not in {"outcome_id","source_archive_refs","source_observed_at","normalized_at","correction_revision","previous_outcome_id"}}
        for pid in task["player_ids"]:
            player=[(ref,body) for ref,body in originals if body["player_id"] == pid]
            if not player:result["pending"].append(pid);continue
            eligible=[(ref,body) for ref,body in player if self.mode == "DEVELOPMENT_ONLY" or store.admission(ref)["eligible"]]
            result["unscored_originals"].extend(pid+":"+body["model_key"] for ref,body in player if (ref,body) not in eligible)
            if not eligible:continue
            current=sorted([(ref,body) for ref,body in store.records() if body["schema_version"] == common.OUTCOME_SCHEMA and body["player_id"] == pid],key=lambda row:row[1]["correction_revision"])
            previous=current[-1] if current else None
            if previous is not None and previous[1]["source_archive_refs"] == [sref,bref]:outcome_ref,outcome=previous
            else:
                candidate=forecasts.normalize_outcome(player[0][1],store.read_body(input_ref),archive=self.archive,schedule_ref=sref,boxscore_ref=bref)
                if candidate["status"] not in {"APPEARED","DNP"}:
                    result["pending"].append(pid)
                    if previous is None:continue
                    # Repair any interrupted grades for the retained prior
                    # outcome while keeping the newer observation unresolved.
                    outcome_ref,outcome=previous
                elif previous is not None and semantic(previous[1]) == semantic(candidate):outcome_ref,outcome=previous
                elif previous is not None and previous[1]["correction_revision"] >= common.make_policy()["maximum_automatic_outcome_versions"]:
                    result["correction_quota_exhausted"].append(pid)
                    outcome_ref,outcome=previous
                else:
                    outcome=forecasts.normalize_outcome(player[0][1],store.read_body(input_ref),archive=self.archive,schedule_ref=sref,boxscore_ref=bref,
                        previous=previous[1] if previous else None)
                    refs=tuple(ref for ref,_ in player)+((previous[0],) if previous else ())
                    outcome_ref=store.append_body(outcome,references=refs,archive_refs=(sref,bref))
            if outcome["previous_outcome_id"] is not None:
                before=next((ref for ref,body in store.records() if body["schema_version"] == common.OUTCOME_SCHEMA and body["outcome_id"] == outcome["previous_outcome_id"]),None)
                common.require(before is not None,"Outcome revision lost its original predecessor")
                store.correct(before,outcome_ref,reason="Verified appended production final-source correction")
            result["outcomes"]+=1
            for forecast_ref,forecast in eligible:
                all_grades=[(ref,body) for ref,body in store.records() if body["schema_version"] == common.GRADE_SCHEMA and body["forecast_id"] == forecast["forecast_id"]]
                exact=[(ref,body) for ref,body in all_grades if body["outcome_id"] == outcome["outcome_id"]]
                common.require(len(exact) <= 1,"Duplicate original statistical grade")
                if exact:grade_ref,grade=exact[0]
                else:
                    old=max(all_grades,key=lambda row:row[1]["correction_revision"]) if all_grades else None
                    grade=forecasts.make_grade(forecast,outcome,previous=old[1] if old else None)
                    grade_ref=store.append_body(grade,references=(forecast_ref,outcome_ref)+((old[0],) if old else ()))
                if grade["previous_grade_id"] is not None:
                    before=next(ref for ref,body in all_grades if body["grade_id"] == grade["previous_grade_id"])
                    store.correct(before,grade_ref,reason="Statistical grade follows appended production outcome correction")
                result["grades"]+=1
        return result

    def work(self,descriptor):
        self._authority();common.require(type(descriptor) is dict and descriptor.get("action") in ACTIONS,"Unknown production worker action")
        task=validate_task(self.archive.get_json(descriptor["task_ref"]))
        common.require(task["mode"] == self.mode and all(descriptor.get(key) == task[key] for key in ("branch","cycle_id","shard_index")),"Worker descriptor changed the immutable task")
        registered=[row for day in self.registry["days"] for row in day["shards"] if row["branch"] == task["branch"]]
        common.require(len(registered) == 1 and registered[0]["input_task_ref"] == descriptor["task_ref"],"Worker task is not the retained registry original")
        if descriptor["action"] == "GRADE":common.require(descriptor.get("final_source_pack_ref") == registered[0]["final_source_pack_ref"],"Worker final source changed outside the coordinator")
        plan=self.archive.get_json(task["plan_ref"]);body=self.archive.get_json(task["input_ref"]);inputs.validate_input(body,plan)
        common.require(body["cycle_id"] == task["cycle_id"] and body["shards"][task["shard_index"]] == task["player_ids"],"Worker input differs from exact registered shard")
        action=descriptor["action"];now=common.now();cutoff=common.clock(body["event"]["event_starts_at"])-timedelta(minutes=90)
        store=remote=None;attempt_handle=None;report={"branch":task["branch"],"cycle_id":task["cycle_id"],"action":action,"status":"STARTED","task_ref":descriptor["task_ref"],"error":None}
        try:
            store,remote=self._store(task)
            from .sdv_production_store import archive_liability
            budget=self._budget();old=next(row for row in budget["shards"] if row["branch"] == task["branch"])
            others_bytes=budget["reserved_bytes"]-archive_liability(old["capacity"])
            others_objects=budget["reserved_objects"]-runner.archive_object_liability(old["capacity"])
            def fund_worker():
                capacity=store.capacity()
                self.archive.reserved_bytes=others_bytes+archive_liability(capacity)
                self.archive.reserved_objects=others_objects+runner.archive_object_liability(capacity)
                common.require(self.archive.quota(self.tag)["fits"],"Cold worker cannot fund all outstanding archive byte/object obligations")
            fund_worker()
            self.archive.write_budget_bytes=self.archive.new_bytes_reserved+archive_liability(store.capacity())
            self.archive.write_budget_objects=self.archive.new_objects_reserved+runner.archive_object_liability(store.capacity())
            if action == "PREPARE":common.require(cutoff-timedelta(hours=1) <= now <= cutoff,"Shard preparation missed cutoff")
            elif action == "ISSUE":common.require(cutoff <= now <= cutoff+timedelta(seconds=body["policy"]["generation_window_seconds"]),"Shard issuance missed its actual window")
            else:
                start=common.clock(body["event"]["event_starts_at"])
                final_pack,_=self._pack(descriptor["final_source_pack_ref"])
                common.require(start <= now and common.clock(final_pack["captured_at"]) <= start+timedelta(days=body["policy"]["correction_capture_days"]),
                    "Final source observation missed the seven-day grading-source reservation")
            plan_pack,_=self._pack(task["plan_source_pack_ref"]);input_pack,_=self._pack(task["input_source_pack_ref"])
            plan_ref=store.append_body(plan,archive_refs=self._source_refs(plan_pack))
            input_ref=store.append_body(body,references=(plan_ref,),archive_refs=self._source_refs(input_pack))
            authorization_ref=store.append_body(self.authorization) if self.authorization is not None and action in {"PREPARE","ISSUE"} else None
            def checkpoint(refs):
                fund_worker();return remote.checkpoint(store,refs)
            if action == "PREPARE":
                if self.mode == "PROSPECTIVE_RESEARCH" and not store.admission(input_ref)["eligible"]:checkpoint((input_ref,))
                forecasts.prepare_intent(store,input_ref,body["producer_binding"],task["player_ids"],plan_ref=plan_ref,authorization_ref=authorization_ref,checkpoint=checkpoint)
                report["status"]="PREPARED"
            elif action == "ISSUE":
                attempt_handle=open_issuance_attempt(store,input_body=body,task_id=task["task_id"],shard_index=task["shard_index"],
                    authorization=self.authorization,checkpoint=checkpoint)
                if attempt_handle is not None:
                    forecasts.issue_shard(store,input_ref,body["producer_binding"],task["player_ids"],plan_ref=plan_ref,authorization_ref=authorization_ref,checkpoint=checkpoint,mode=self.mode)
                    report["status"]="ISSUED_PENDING_OUTCOMES"
                else:
                    report["status"]="RECOVERED_ORIGINALS_OPEN_ATTEMPT"
                    report["unresolved_prior_attempt"]=True
            else:
                report["grading"]=self._grade(store,task,input_ref,descriptor["final_source_pack_ref"])
                report["status"]="STATISTICAL_GRADING_RETAINED"
            self._runtime_guard()
        except (KeyboardInterrupt,SystemExit) as error:
            report.update(status="FAILED_OR_PARTIAL",error=_error(type(error).__name__+": "+str(error)))
        except Exception as error:
            report.update(status="FAILED_OR_PARTIAL",error=_error(error))
        finally:
            if report["status"] == "STARTED":
                interrupted=sys.exc_info()[1]
                message=(_error(type(interrupted).__name__+": "+str(interrupted)) if interrupted is not None else
                    "Operating phase did not produce a completed result")
                report.update(status="FAILED_OR_PARTIAL",error=message)
            if store is not None and remote is not None:
                if attempt_handle is not None:
                    try:close_issuance_attempt(store,attempt_handle,checkpoint=checkpoint,error=report["error"])
                    except Exception as error:
                        report["attempt_closure_error"]=_error(error)
                        report.update(status="FAILED_OR_PARTIAL",error=report["error"] or _error(error))
                try:
                    details={"task_id":task["task_id"],"shard_index":task["shard_index"],"player_ids":task["player_ids"],"error":report["error"],"final_source_pack_ref":descriptor.get("final_source_pack_ref"),
                        "processing_complete":report["error"] is None and report["status"] in COMPLETED_STATUSES}
                    if action == "GRADE":details["grading"]=report.get("grading",{})
                    status=common.seal({"schema_version":common.STATUS_SCHEMA,"protocol_id":common.PROTOCOL_ID,"plan_id":plan["plan_id"],"cycle_id":task["cycle_id"],
                        "phase":action,"status":report["status"],"details":details,"observed_at":stamp(common.now()),"run_id":(self.authorization or {}).get("run_id",0)},"status_id")
                    old=[record for _,record in store.records() if record["schema_version"] == common.STATUS_SCHEMA
                        and record["phase"] == action and record["details"] == details]
                    if not old:store.append_body(status)
                except Exception as error:report["status_retention_error"]=_error(error)
                try:
                    if "fund_worker" in locals():fund_worker()
                    report["checkpoint"]=remote.flush(store)
                    report["counts"]={key:len(store.recover()[key]) for key in ("forecasts","outcomes","grades")}
                    report["genuine_issued"]=store.recover()["genuine_issued"]
                except Exception as error:report["durability_error"]=_error(error)
            report["completed_at"]=stamp(common.now())
        return report


    def refresh(self):
        """Rebuild mutable catalog acknowledgments from fresh durable originals.

        Worker artifacts are never inputs to this method. Each branch and archive
        snapshot is independently fetched again before its status can advance.
        """
        self._authority();self._reserve_archive();results=[]
        # An immutable unchanged head already has typed readback proof. Probe
        # all heads once; changed or missing heads still take full recovery.
        heads=None
        if self.mode == "PROSPECTIVE_RESEARCH":
            branches=[row["branch"] for day in self.registry["days"] for row in day["shards"] if row["input_task_ref"] is not None]
            if branches:
                output=runner._git(self.source_root,"ls-remote","--heads",common.REMOTE_URL,*["refs/heads/"+branch for branch in branches]).stdout.decode().splitlines()
                heads={}
                for line in output:
                    fields=line.split()
                    common.require(len(fields) == 2 and fields[1].startswith("refs/heads/"),"Malformed shard head inventory")
                    common.sha(fields[0],40);branch=fields[1][len("refs/heads/"):]
                    common.require(branch in branches and branch not in heads,"Unexpected or duplicate shard head")
                    heads[branch]=fields[0]
        for day in self.registry["days"]:
            for shard in day["shards"]:
                if shard["input_task_ref"] is None:continue
                if (heads is not None and heads.get(shard["branch"]) == shard["latest_commit"] and shard["latest_commit"] is not None
                        and shard["snapshot_ref"] is not None and digest(shard["snapshot_ref"]) in self._capacity_cache):
                    results.append({"branch":shard["branch"],"commit":shard["latest_commit"],"status":"UNCHANGED_INDEPENDENTLY_RECOVERED_HEAD"})
                    continue
                try:
                    task=validate_task(self.archive.get_json(shard["input_task_ref"]))
                    with self._read_store(task) as (store,remote):
                        proof=remote.inspect()
                        if proof is None or proof.get("snapshot_ref") is None:continue
                        recovered=store.recover();records=recovered["records"]
                        statuses=[body for _,body in records if body["schema_version"] == common.STATUS_SCHEMA
                            and body["details"].get("task_id") == task["task_id"] and body["details"].get("processing_complete") is True]
                        intents=[(ref,body) for ref,body in records if body["schema_version"] == common.INTENT_SCHEMA
                            and body["player_ids"] == task["player_ids"] and body["plan_id"] == day["plan_id"]]
                        prepared=bool(intents) and any(body["phase"] == "PREPARE" for body in statuses)
                        originals=[(ref,body) for ref,body in recovered["forecasts"] if body["player_id"] in task["player_ids"]]
                        expected={(pid,model) for pid in task["player_ids"] for model in common.MODEL_VERSIONS}
                        issued={(body["player_id"],body["model_key"]) for _,body in originals} == expected
                        if self.mode == "PROSPECTIVE_RESEARCH":
                            prepared=prepared and all(store.admission(ref)["eligible"] for ref,_ in intents)
                            issued=issued and all(store.admission(ref)["eligible"] for ref,_ in originals)
                        shard["latest_commit"]=proof["commit"];shard["snapshot_ref"]=proof["snapshot_ref"]
                        self._capacity_cache[digest(proof["snapshot_ref"])]=recovered["capacity"]
                        if prepared:shard["prepared_input_task_ref"]=shard["input_task_ref"]
                        if issued:shard["issued_input_task_ref"]=shard["input_task_ref"]
                        if shard["final_source_pack_ref"] is not None and any(body["phase"] == "GRADE"
                            and body["details"].get("final_source_pack_ref") == shard["final_source_pack_ref"] for body in statuses):
                            shard["graded_source_pack_ref"]=shard["final_source_pack_ref"]
                        results.append({"branch":shard["branch"],"commit":proof["commit"],"records":len(records),
                            "forecasts":len(originals),"genuine_issued":recovered["genuine_issued"],"status":"INDEPENDENTLY_RECOVERED"})
                except (IntegrityError,OSError,ValueError) as error:
                    results.append({"branch":shard["branch"],"status":"RECOVERY_FAILED","error":_error(error)})
        self._save("CATALOG_RECOVERED",{"shards":len(results),"failed":sum(row["status"] == "RECOVERY_FAILED" for row in results),**self._window_status()})
        return results
