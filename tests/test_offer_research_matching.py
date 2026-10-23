"""Shared invented wire graphs, not real offers or prospective issuance."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from multisport_lab import offer_publication as offers
from multisport_lab import sdv_production_common as common
from multisport_lab.integrity import IntegrityError, canonical, digest, utc

ROOT = Path(__file__).resolve().parents[1]


class OfferResearchMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The browser and Python consume exactly the same valid invented
        # authority/input/admission graph. This fits no model and writes nothing.
        source = """
import {channelFixture,dailyFixtures,productionFixtures} from './web/tests/offer-research-fixtures.mjs';
console.log(JSON.stringify({daily:channelFixture('daily'),production:channelFixture('production'),
    developmentDaily:dailyFixtures.development(),developmentProduction:productionFixtures.development()}));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", source], cwd=ROOT,
                                capture_output=True, text=True, check=True, timeout=30)
        cls.fixtures = json.loads(result.stdout)

    def sample(self, kind):
        return deepcopy(self.fixtures[kind])

    @staticmethod
    def contract(sample):
        body, event = sample["body"], sample["input"]["event"]
        return {**{key: body[key] for key in ("event_id", "event_starts_at", "player_id", "team_id",
                    "opponent_id", "period", "extra_time_policy")},
                "league": event["league"], "id_namespace": event["id_namespace"],
                "event_version": body["event_snapshot_id"], "stat": "PTS", "units": "points",
                "evidence_lane": "REAL_TIME_CAPTURED", "market_status": "PRE_GAME",
                "observed_at": body["issued_at"], "imported_at": body["issued_at"],
                "price_status": "PRICE_UNAVAILABLE", "price": None}

    @staticmethod
    def views(sample):
        with patch.object(common, "now", return_value=utc(sample["at"])):
            return offers.offer_research_forecasts(**sample["channel"], at=sample["at"])

    def test_exact_price_free_matching_preserves_both_lanes_and_all_fourteen_categories(self):
        for kind in ("daily", "production"):
            with self.subTest(kind=kind):
                sample = self.sample(kind)
                before = canonical(sample)
                view = self.views(sample)[0]
                self.assertEqual(view["original"], sample["body"])
                self.assertEqual(view["input"]["input_id"], sample["body"]["input_id"])
                self.assertEqual(view["original"]["evidence_lane"],
                                 "DAILY_SNAPSHOT_PROSPECTIVE" if kind == "daily" else "SDV_PRODUCTION_PROSPECTIVE")
                self.assertNotIn("event_version", view["original"])
                for category in view["original"]["categories"]:
                    offer = self.contract(sample) | {"stat": category["code"], "units": category["units"]}
                    result = offers.match_research_forecast(offer, view, at=sample["at"])
                    self.assertEqual(result["status"], "MATCHED_RESEARCH_ONLY", category["code"])
                    self.assertEqual(result["qualification"], "UNAVAILABLE")
                    self.assertFalse(result["ticket_eligible"])
                    self.assertIsNone(result["ev"])
                self.assertEqual(len(view["original"]["categories"]), 14)
                self.assertEqual(canonical(sample), before)
                view["original"]["event_id"] = "cannot-change-validated-fields"
                self.assertEqual(view["original"], sample["body"])
                with self.assertRaises(AttributeError):
                    view._raw = b"{}"
                for untrusted in (sample["body"], {"original": sample["body"], "admission": {"eligible": True}}):
                    self.assertEqual(offers.match_research_forecast(self.contract(sample), untrusted,
                                                                  at=sample["at"])["status"], "UNMATCHED")

    def test_namespace_event_period_overtime_and_availability_must_match_exactly(self):
        for kind in ("daily", "production"):
            sample = self.sample(kind)
            view, offer = self.views(sample)[0], self.contract(sample)
            for changed in ({"league": "NFL"}, {"id_namespace": "sleeper"}, {"event_id": "another-event"},
                            {"event_version": "f" * 64}, {"player_id": "another-player"},
                            {"team_id": "another-team"}, {"opponent_id": "another-opponent"},
                            {"period": "first_quarter"}, {"extra_time_policy": "regulation_only"},
                            {"units": "rebounds"}, {"market_status": "IN_PLAY"},
                            {"evidence_lane": "RECONSTRUCTED_RESEARCH"},
                            {"observed_at": sample["body"]["event_starts_at"]}):
                self.assertEqual(offers.match_research_forecast(offer | changed, view,
                                                               at=sample["at"])["status"], "UNMATCHED", changed)
            for when in (sample["body"]["cutoff_at"], sample["body"]["issued_at"],
                         sample["body"]["event_starts_at"]):
                self.assertEqual(offers.match_research_forecast(offer, view, at=when)["status"], "UNMATCHED")

    def test_development_and_retained_unacknowledged_originals_cannot_match(self):
        daily = deepcopy(self.fixtures["developmentDaily"])
        self.assertEqual(offers.offer_research_forecasts(daily=daily, at="2026-10-23T00:10:00.000000Z"), [])
        production = deepcopy(self.fixtures["developmentProduction"])
        with patch.object(common, "now", return_value=utc(production["index"]["generated_at"])):
            self.assertEqual(offers.offer_research_forecasts(production=production,
                                at=production["index"]["generated_at"]), [])
        sample = self.sample("daily")
        asset = sample["channel"]["daily"]
        excluded = asset["forecasts"][0]["body"]["forecast_id"]
        asset["forecasts"][0]["admission"].update(eligible=False, remote_recovery_completed_at=None,
                                                reasons=["Original recovery not acknowledged."])
        asset["counts"]["eligible_forecasts"] = 7
        asset["status"] = "PARTIAL"
        asset["asset_id"] = digest({key: value for key, value in asset.items() if key != "asset_id"})
        self.assertEqual(len(self.views(sample)), 7)
        self.assertNotIn(excluded, [view["original"]["forecast_id"] for view in self.views(sample)])

    def test_completion_flag_cannot_bypass_missing_authority_or_exact_input(self):
        for mutate in (lambda a: a.update(activation=None),
                       lambda a: a["forecasts"][0]["body"].update(event_snapshot_id="f" * 64),
                       lambda a: a["forecasts"][0]["admission"].update(remote_recovery_completed_at=None),
                       lambda a: a["forecasts"][0]["admission"].update(remote_recovery_completed_at="2026-10-23T00:05:02.000000Z")):
            sample = self.sample("daily")
            mutate(sample["channel"]["daily"])
            with self.assertRaises(IntegrityError):
                self.views(sample)
        sample = self.sample("production")
        sample["channel"]["production"].pop("pages")
        with self.assertRaisesRegex(IntegrityError, "original production index and pages"):
            self.views(sample)
        sample = self.sample("production")
        sample["channel"]["production"]["pages"][0]["records"].pop()
        with self.assertRaises(IntegrityError):
            self.views(sample)


if __name__ == "__main__":
    unittest.main()
