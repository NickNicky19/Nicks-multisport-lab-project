"""Synthetic operating-version interoperability, never a real issuance."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_forecasts as forecasts
from multisport_lab import sdv_production_publication as public
from multisport_lab.integrity import IntegrityError, load_json
from test_sdv_production_publication import synthetic_publication


class DeliveryPublicationTests(unittest.TestCase):
    def test_partial_hosted_recovery_is_visible_without_invented_source_captures(self):
        from multisport_lab import sdv_production_runner as runner
        now = common.clock("2026-10-24T13:17:00.000000Z")
        registry = runner.empty_registry(now)
        before = public.publication_content_identity(registry)
        registry["last_run"] = {"run_id": 123, "run_attempt": 1, "observed_at": common.stamp(now),
            "status": "HOSTED_PHASES_PARTIAL_OR_FAILED", "details": {"PRODUCTION_CAPTURE_RESULT": "failure"}}
        after = public.publication_content_identity(registry)
        self.assertNotEqual(before["content_id"], after["content_id"])
        self.assertTrue(after["has_operational_failure"])
        status = public.make_operations(registry, [], now=now)
        self.assertIn("failed or remains incomplete", status["reason"])
        self.assertIsNone(status["last_source_capture_at"])
        self.assertIsNone(status["last_issued_at"])

    def test_legacy_exact_inventory_recovers_but_cannot_impersonate_current_execution(self):
        fixture = load_json("tests/fixtures/sdv-production-synthetic.json")
        body = next(public.original_record(row) for page in fixture["pages"] for row in page["records"]
                    if public.original_record(row)["schema_version"] == common.PLAN_SCHEMA)
        binding = body["producer_binding"]
        self.assertEqual(binding["schema_version"], forecasts.LEGACY_BINDING_SCHEMA)
        self.assertIs(forecasts.validate_binding(binding), binding)
        with patch.object(forecasts, "make_source_binding", return_value={"different": "current source"}):
            with self.assertRaisesRegex(IntegrityError, "Current executed"):
                forecasts.validate_binding(binding, current=True)
        for schema in (forecasts.LEGACY_BINDING_SCHEMA, forecasts.BINDING_SCHEMA):
            changed = deepcopy(binding)
            changed["schema_version"] = schema
            changed["files"]["multisport_lab/unregistered.py"] = "f" * 64
            changed = common.seal({k:v for k,v in changed.items() if k != "binding_id"}, "binding_id")
            with self.assertRaisesRegex(IntegrityError, "inventory"):
                forecasts.validate_binding(changed)

    def test_v2_inputs_recover_and_publish_with_their_own_policy_and_all_categories(self):
        now, rows = synthetic_publication(at="2026-10-24T13:17:00.000000Z",
            policy=common.make_policy("v2"), game_date="2026-10-25")
        originals = deepcopy(rows)
        with patch.object(common, "now", return_value=now):
            public.validate_records(rows, generated_at=common.stamp(now))
            index, pages = public.make_publication(rows, now=now, allow_development=True)
        self.assertEqual(index["counts"]["genuine_forecasts"], 0)
        self.assertEqual(index["policy"], common.make_policy("v2"))
        self.assertEqual(index["counts"]["development_forecasts"], 2)
        for row in [r for p in pages for r in p["records"]]:
            body = public.original_record(row)
            if "policy" in body:
                self.assertEqual(body["policy"], common.make_policy("v2"))
            if body["schema_version"] == common.FORECAST_SCHEMA:
                self.assertEqual(len(body["categories"]), 14)
                self.assertIsNone(body["issued_at"])
        self.assertEqual(rows, originals)
        # The independently recovered originals never gain public prospective
        # eligibility simply because a newer operating policy is understood.
        with patch.object(common, "now", return_value=now):
            with self.assertRaisesRegex(IntegrityError, "Development records"):
                public.make_publication(rows, now=now)


if __name__ == "__main__":
    unittest.main()
