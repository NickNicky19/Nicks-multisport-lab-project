"""Future-policy contracts with invented sources; no capture or model scoring."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_inputs as inputs
from multisport_lab.integrity import IntegrityError, canonical, stamp, utc
import test_sdv_production_inputs as input_fixtures

ROOT=Path(__file__).resolve().parents[1]
V1_ID="2a2543c981c23c6c09b0af8eb598fc5eaeae4a6278233acef1c59e265acedf43"
V2_ID="3ea45e39dddee1222a04d2998003ec90f7241f59f2e0a721b2fba128ad97f4ed"


class ProductionPolicyRegistrationTests(unittest.TestCase):
    def test_exact_v1_identity_bytes_and_default_remain_unchanged(self):
        raw=(ROOT/"config/sdv_production_policy_v1.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),"f1ff3563c172c6989a74d75249c9d26bac3c44c1912acd1a4e62485ad0808711")
        body=json.loads(raw)
        self.assertEqual(common.make_policy(),body)
        self.assertEqual(common.make_policy("v1")["policy_id"],V1_ID)
        self.assertIs(common.validate_policy(body),body)
        self.assertEqual(common.policy_for_id(V1_ID),body)

    def test_v2_changes_only_registered_operation_and_has_bounded_hold_budget(self):
        old,new=common.make_policy(),common.make_policy("v2")
        self.assertEqual(new["policy_id"],V2_ID)
        self.assertEqual(json.loads((ROOT/"config/sdv_production_policy_v2.json").read_bytes()),new)
        allowed={"schema_version","policy_id","enabled_after","planning_hour_utc",
                 "planning_window_seconds","rationale"}
        for key in old:
            if key not in allowed:self.assertEqual(new[key],old[key],key)
        self.assertEqual(new["enabled_after"],"2026-10-25T00:00:00.000000Z")
        self.assertEqual(new["planning_window_seconds"],77400)
        self.assertIs(new["planning_close_exclusive"],True)
        self.assertEqual(new["held_runtime_maximum_seconds"],350*60)
        self.assertEqual(new["held_runtime_poll_seconds"],30)
        self.assertEqual(new["held_registry_maximum_probes"],96)
        self.assertEqual(new["held_registry_maximum_readbacks"],16)
        self.assertEqual(new["held_capture_refresh_seconds"],300)
        self.assertEqual(new["held_capture_maximum_refreshes"],72)
        self.assertEqual(new["held_publication_check_seconds"],900)
        self.assertEqual(new["held_publication_maximum_checks"],24)
        self.assertEqual(new["held_minimum_prepare_seconds"],300)
        self.assertEqual(new["held_maximum_tasks"],16)
        self.assertEqual(new["held_input_recovery_maximum_attempts"],16)
        self.assertEqual(new["final_capture_minimum_game_age_seconds"],4*3600)
        self.assertEqual(new["final_capture_minimum_interval_seconds"],10*3600)
        self.assertEqual(new["final_capture_window_seconds"],24*3600)
        self.assertEqual(new["maximum_final_captures_per_day"],2)
        self.assertEqual(common.policy_for_id(V2_ID),new)

    def test_mutation_type_coercion_unknown_version_or_identity_cannot_register_itself(self):
        for version in ("v1","v2"):
            original=common.make_policy(version)
            for field,value in (("maximum_plan_capture_attempts",2.0),
                                ("checkpoint_subjects",True),("original_latency_seconds",301)):
                body=deepcopy(original);body[field]=value
                body=common.seal({key:value for key,value in body.items() if key!="policy_id"},"policy_id")
                with self.subTest(version=version,field=field),self.assertRaises(IntegrityError):
                    common.validate_policy(body)
            copy=common.make_policy(version);copy["law_sha256"]["R0"]="0"*64
            self.assertEqual(common.make_policy(version),original)
        with self.assertRaises(IntegrityError):common.make_policy("v3")
        with self.assertRaises(IntegrityError):common.policy_for_id("0"*64)
        malformed=common.make_policy("v2");malformed["schema_version"]=[]
        with self.assertRaises(IntegrityError):common.validate_policy(malformed)


class ProductionV2InputTests(unittest.TestCase):
    def setUp(self):
        self.case=input_fixtures.ProductionInputTests()
        self.addCleanup(self.case.doCleanups);self.case.setUp()
        self.case.now=utc("2026-10-24T13:17:00.000000Z")
        for row in self.case.schedule:
            for field in ("date","start_date","game_date_time"):
                row[field]=row[field].replace("2026-10-24","2026-10-25")

    def build(self,*,policy=None,mode="PROSPECTIVE_RESEARCH",assets=None,game_date="2026-10-25",at=None):
        assets=assets or self.case.assets()
        return inputs.make_plan(*assets[:4],source_originals=assets[4],game_date=game_date,
            producer_binding=self.case.binding,policy=policy or common.make_policy("v2"),mode=mode,at=at)

    def test_v2_window_is_prior_midnight_to_strict_2130_and_v1_stays_inclusive(self):
        v2=common.make_policy("v2")
        opens,closes=inputs._planning_window("2026-10-25",v2)
        self.assertEqual((stamp(opens),stamp(closes)),("2026-10-24T00:00:00.000000Z","2026-10-24T21:30:00.000000Z"))
        self.case.now=closes-timedelta(microseconds=1)
        self.assertEqual(self.build()["planned_at"],stamp(self.case.now))
        for at in (closes,closes+timedelta(microseconds=1),opens-timedelta(microseconds=1)):
            self.case.now=at
            with self.subTest(at=at),self.assertRaisesRegex(IntegrityError,"daily window"):
                self.build()
        self.case.now=utc("2026-10-24T14:00:00.000000Z")
        self.assertEqual(self.build(policy=common.make_policy())["policy"]["policy_id"],V1_ID)

    def test_first_v2_date_is_future_only_and_no_supplied_prospective_clock_is_admitted(self):
        for mode in ("DEVELOPMENT_ONLY","PROSPECTIVE_RESEARCH"):
            with self.subTest(mode=mode),self.assertRaisesRegex(IntegrityError,"future-only effective date"):
                self.build(game_date="2026-10-24",mode=mode)
        with self.assertRaisesRegex(IntegrityError,"supplied clock"):
            self.build(at=self.case.now)
        # Standalone input recovery must reject the old date too, even before
        # the parent plan is supplied for a cross-record identity check.
        for row in self.case.schedule:
            for field in ("date","start_date","game_date_time"):
                row[field]=row[field].replace("2026-10-25","2026-10-24")
        self.case.now=utc("2026-10-23T13:17:00.000000Z")
        old_plan=self.case.build(mode="PROSPECTIVE_RESEARCH")
        self.case.now=common.clock(old_plan["events"][0]["cutoff_at"])-timedelta(minutes=20)
        old_input=self.case.fresh(old_plan)
        changed=common.seal({key:value for key,value in old_input.items() if key!="input_id"}|
            {"policy":common.make_policy("v2")},"input_id")
        with self.assertRaisesRegex(IntegrityError,"future-only effective date"):
            inputs.validate_input(changed)

    def test_v2_source_capture_must_really_belong_to_its_planning_window(self):
        self.case.now=utc("2026-10-24T00:03:00.000000Z")
        with self.assertRaisesRegex(IntegrityError,"planning capture window"):
            self.build()
        self.case.now=utc("2026-10-24T00:04:00.000000Z")
        self.assertEqual(len(self.build()["events"]),3)

    def test_v2_complete_plan_and_input_recover_their_own_policy_not_global_default(self):
        assets=self.case.assets();plan=self.build(assets=assets)
        expected_seed=inputs._seed(plan["game_date"],plan["sources"],plan["producer_binding"],plan["events"],plan["policy"])
        self.assertEqual(expected_seed,plan["plan_seed"])
        self.assertNotEqual(expected_seed,inputs._seed(plan["game_date"],plan["sources"],plan["producer_binding"],plan["events"]))
        self.case.now=common.clock(plan["events"][0]["cutoff_at"])-timedelta(minutes=20)
        fresh=self.case.assets();body=self.case.fresh(plan,fresh)
        self.assertEqual(body["policy"],plan["policy"])
        # A later process must replay original source clocks and the exact
        # embedded version without any implicit current/default-policy call.
        self.case.now+=timedelta(days=2)
        real=common.make_policy
        def explicit_only(*args,**kwargs):
            if not args and "version" not in kwargs:raise AssertionError("Unexpected v1 fallback")
            return real(*args,**kwargs)
        with patch.object(common,"make_policy",side_effect=explicit_only):
            self.assertIs(inputs.verify_plan_sources(plan,*assets[:4],source_originals=assets[4]),plan)
            self.assertIs(inputs.verify_input_sources(body,*fresh[:4],source_originals=fresh[4],plan=plan),body)

    def test_v2_completion_and_final_verification_cannot_cross_strict_close(self):
        original=inputs._tables
        self.case.now=utc("2026-10-24T21:29:59.000000Z")
        def delayed(*args):
            result=original(*args);self.case.now+=timedelta(seconds=1);return result
        with patch.object(inputs,"_tables",side_effect=delayed),self.assertRaisesRegex(IntegrityError,"daily window"):
            self.build()
        self.case.now=utc("2026-10-24T21:29:59.000000Z")
        original_validate=inputs.validate_plan;calls=[]
        def slow_verification(body):
            result=original_validate(body);calls.append(body["plan_id"])
            if len(calls)==2:self.case.now+=timedelta(seconds=1)
            return result
        with patch.object(inputs,"validate_plan",side_effect=slow_verification),self.assertRaisesRegex(IntegrityError,"admission missed"):
            self.build()

    def test_v2_stale_future_sources_and_changed_plan_policy_reject(self):
        with self.assertRaisesRegex(IntegrityError,"stale"):
            self.build(assets=self.case.assets(age=timedelta(hours=36,microseconds=1)))
        assets=list(self.case.assets());assets[2]["retrieved_at"]=stamp(self.case.now+timedelta(seconds=1))
        with self.assertRaises(IntegrityError):self.build(assets=assets)
        plan=self.build();self.case.now=common.clock(plan["events"][0]["cutoff_at"])-timedelta(minutes=20)
        body=self.case.fresh(plan)
        changed=deepcopy(body);changed["policy"]=common.make_policy()
        changed=common.seal({key:value for key,value in changed.items() if key!="input_id"},"input_id")
        with self.assertRaisesRegex(IntegrityError,"frozen plan"):
            inputs.validate_input(changed,plan)
        changed=deepcopy(plan);changed["policy"]=common.make_policy()
        changed=common.seal({key:value for key,value in changed.items() if key!="plan_id"},"plan_id")
        with self.assertRaisesRegex(IntegrityError,"immutable plan seed"):
            inputs.validate_plan(changed)

    def test_both_binding_versions_preserve_laws_and_t150_t90_t75_windows(self):
        for schema in (inputs.BINDING_SCHEMA,inputs.BINDING_SCHEMA_V2):
            self.case.binding=common.seal({key:value for key,value in self.case.binding.items() if key!="binding_id"}|{"schema_version":schema},"binding_id")
            plan=self.build()
            self.assertEqual(plan["producer_binding"]["law_sha256"],common.LAW_SHA256)
            self.assertEqual(plan["history_rows"],26645)
            for row in plan["events"]:
                start=common.clock(row["event"]["event_starts_at"])
                self.assertEqual(start-common.clock(row["capture_opens_at"]),timedelta(minutes=150))
                self.assertEqual(start-common.clock(row["cutoff_at"]),timedelta(minutes=90))
                self.assertEqual(start-common.clock(row["issuance_closes_at"]),timedelta(minutes=75))
        malformed=deepcopy(self.case.binding);malformed["schema_version"]=[]
        malformed=common.seal({key:value for key,value in malformed.items() if key!="binding_id"},"binding_id")
        with self.assertRaises(IntegrityError):inputs.validate_binding(malformed)


if __name__=="__main__":unittest.main()
