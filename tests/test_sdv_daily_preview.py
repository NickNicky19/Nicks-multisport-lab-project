"""Archive-preservation and bounded-copy risks in the non-issuing preview CLI."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("daily_preview_command",ROOT/"scripts/preview_sdv_daily.py")
preview=importlib.util.module_from_spec(spec);spec.loader.exec_module(preview)


class DailyPreviewSafetyTests(unittest.TestCase):
    def invoke(self,records,output):
        with patch.object(sys,"argv",["preview","--records-root",str(records),"--output",str(output)]):
            preview.main()

    def test_normalized_source_alias_cannot_replace_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"other").mkdir();records=root/"recovered";records.mkdir()
            original=records/"original";original.write_bytes(b"preserved")
            with patch.object(preview,"build_site") as build,self.assertRaises(IntegrityError):
                self.invoke(root/"other/../recovered",records)
            build.assert_not_called();self.assertEqual(original.read_bytes(),b"preserved")

    def test_symlink_aliases_are_rejected_before_read_or_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);records=root/"recovered";records.mkdir();alias=root/"alias";alias.symlink_to(records,target_is_directory=True)
            for source,output in ((alias,root/"output"),(records,alias)):
                with self.subTest(source=source,output=output),patch.object(preview,"snapshot_manifest") as read,self.assertRaises(IntegrityError):
                    self.invoke(source,output)
                read.assert_not_called()

    def test_copy_uses_only_authenticated_manifest_not_extra_archive_blobs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);records=root/"recovered";records.mkdir()
            relative="records/research_inputs/"+"a"*64+".json";raw=b'{"explicit_software_fixture":true}\n'
            path=records/relative;path.parent.mkdir(parents=True);path.write_bytes(raw)
            (records/"records/unaccounted.bin").write_bytes(b"not in the bounded manifest")
            manifest={"entries":[{"path":relative,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}]}
            def build(staged,*_args,**_kwargs):
                self.assertEqual((staged/relative).read_bytes(),raw)
                self.assertFalse((staged/"records/unaccounted.bin").exists())
                return {"daily_research_error":None}
            with patch.object(preview,"snapshot_manifest",return_value=manifest),patch.object(preview,"DailyStore") as store,patch.object(preview,"build_site",side_effect=build):
                store.return_value.recover.return_value={"forecasts":[("synthetic",{"mode":"DEVELOPMENT_ONLY"})]}
                self.invoke(records,root/"output")
            self.assertEqual(path.read_bytes(),raw)


if __name__ == "__main__":unittest.main()
