"""Small diagnostic-control tests; do not load/fit the full historical panel."""
import argparse
import csv
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import diagnose_sdv_production as diagnostic
from multisport_lab import sdv_production_inputs as inputs
from multisport_lab.integrity import IntegrityError, _decode, utc


class ProductionDiagnosticTests(unittest.TestCase):
    def test_synthetic_sources_have_sixteen_unique_aliases_and_explicit_invented_metadata(self):
        history=[SimpleNamespace(player_id=str(pid)) for pid in range(1,17) for _ in range(2)]
        assets,start=diagnostic.synthetic_assets(history,at=utc("2030-01-01T00:00:00.000000Z"))
        self.assertEqual(set(assets),{"schedule","roster"})
        for role,(raw,metadata,original) in assets.items():
            self.assertTrue(_decode(original)["nml_synthetic_diagnostic"])
            self.assertIn("INVENTED METADATA",_decode(original)["description"])
            inputs.validate_source(raw,metadata,original,role,2030)
        roster=list(csv.DictReader(io.StringIO(assets["roster"][0].decode())))
        self.assertEqual(len(roster),16);self.assertEqual(len({row["athlete_id"] for row in roster}),16)
        self.assertTrue(all(row["display_name"].startswith("SYNTHETIC diagnostic alias") for row in roster))
        schedule=list(csv.DictReader(io.StringIO(assets["schedule"][0].decode())))
        self.assertEqual(schedule[0]["game_id"],diagnostic.EVENT_ID)
        self.assertEqual(utc(schedule[0]["game_date_time"]),start)

    def test_diagnostic_never_pads_a_short_history_population(self):
        with self.assertRaisesRegex(IntegrityError,"sixteen distinct"):
            diagnostic.synthetic_assets([SimpleNamespace(player_id="1")]*20,at=utc("2030-01-01T00:00:00.000000Z"))

    def test_cli_has_no_genuine_source_collection_or_publication_modes(self):
        args=diagnostic.parser().parse_args(["--work-dir","/tmp/synthetic-example"])
        self.assertFalse(args.hosted);self.assertFalse(args.authorize_diagnostic_archive)
        for forbidden in ("--mode","--activate","--genuine","--publish","--sports-url"):
            with self.subTest(flag=forbidden),self.assertRaises(SystemExit),patch("sys.stderr",new=io.StringIO()):
                diagnostic.parser().parse_args(["--work-dir","/tmp/synthetic-example",forbidden,"true"])

    def test_host_archive_requires_explicit_repository_actions_context_before_any_history_read(self):
        with patch.object(diagnostic.forecasts,"retained_history",side_effect=AssertionError("Must not load history")):
            with self.assertRaisesRegex(IntegrityError,"explicit authorization"):
                diagnostic.run_diagnostic("/tmp/do-not-create-diagnostic",hosted=True)
            with patch.dict("os.environ",{"GITHUB_ACTIONS":"false","GITHUB_REPOSITORY":"someone/else"}):
                with self.assertRaisesRegex(IntegrityError,"actual Actions environment"):
                    diagnostic.run_diagnostic("/tmp/do-not-create-diagnostic",hosted=True,authorize_diagnostic_archive=True,model_commit="a"*40)
            with self.assertRaisesRegex(IntegrityError,"only meaningful"):
                diagnostic.run_diagnostic("/tmp/do-not-create-diagnostic",authorize_diagnostic_archive=True)

    def test_local_git_remote_is_temporary_bare_and_has_only_synthetic_base(self):
        with tempfile.TemporaryDirectory() as folder:
            remote,commit=diagnostic.local_remote(Path(folder)/"local")
            self.assertEqual(diagnostic._git("-C",remote,"rev-parse","--is-bare-repository"),"true")
            self.assertEqual(diagnostic._git("-C",remote,"show",commit+":README.txt"),"SYNTHETIC diagnostic remote; no public research.")
            self.assertTrue(Path(remote).is_relative_to(folder))


if __name__ == "__main__":unittest.main()
