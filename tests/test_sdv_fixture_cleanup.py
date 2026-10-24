"""Failed synthetic fixture setup must not corrupt later history contracts."""
import errno
import unittest
from unittest.mock import patch
from multisport_lab import sdv_production_common as common
import test_sdv_production_inputs as inputs
import test_sdv_production_store as stores
import test_sdv_production_coordinator as coordinators
import test_sdv_production_held as held

class FixtureCleanupTests(unittest.TestCase):
    def check_failed_setup(self,parent,method,child):
        original=common.HISTORY_ID
        touched=[]
        def fail_setup(instance):
            touched.append(instance)
            pin=patch.object(common,"HISTORY_ID","0"*64)
            pin.start();instance.addCleanup(pin.stop)
            raise OSError(errno.EAGAIN,"Synthetic child setup could not fork")
        try:
            with patch.object(child,"setUp",fail_setup):
                result=unittest.TestResult()
                parent(method).run(result)
            observed=common.HISTORY_ID
            self.assertEqual(len(result.errors),1)
            self.assertIn("Synthetic child setup could not fork",result.errors[0][1])
        finally:
            for instance in touched:instance.doCleanups()
        self.assertEqual(observed,original,"A failed child fixture leaked its synthetic history identity")

    def test_held_fixture_registers_native_cleanup_before_native_setup(self):
        self.check_failed_setup(held.HeldProductionTests,
            "test_waiting_worker_recovers_exact_input_prepares_and_issues_both_laws",coordinators.ProductionCoordinatorTests)

    def test_coordinator_registers_store_cleanup_before_store_setup(self):
        self.check_failed_setup(coordinators.ProductionCoordinatorTests,
            "test_complete_native_local_phases_recover_exact_forecasts_and_separate_grades",stores.ProductionStoreTests)

    def test_store_registers_input_cleanup_before_input_setup(self):
        self.check_failed_setup(stores.ProductionStoreTests,
            "test_independent_archive_restart_keeps_exact_originals_and_all14_categories",inputs.ProductionInputTests)

if __name__=="__main__":unittest.main()
