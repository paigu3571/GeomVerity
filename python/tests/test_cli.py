# SPDX-License-Identifier: MPL-2.0
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from cst.__main__ import main

ROOT=Path(__file__).resolve().parents[2]


class CLITests(unittest.TestCase):
    def call(self,argv):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):code=main(argv)
        return code,json.loads(output.getvalue())

    def test_project_cli_round_trip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            code,new=self.call(['project','new',folder,'--name','SYNTHETIC项目'])
            self.assertEqual(code,0)
            self.call(['project','add',folder,str(ROOT/'samples/A'),'--name','旧版','--note','SYNTHETIC'])
            _,added=self.call(['project','add',folder,str(ROOT/'samples/A-change'),'--name','新版'])
            old_id=added['project']['versions'][0]['id']
            self.call(['project','select',folder,old_id])
            _,shown=self.call(['project','show',folder]);self.assertEqual(shown['project']['current_version_id'],old_id)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['project','new',folder,'--name','不应覆盖']),2)
            self.assertEqual(self.call(['project','show',folder])[1]['project'],shown['project'])

    def test_inventory_cli_reads_partial_scan_without_calling_it_a_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'building-semantics.v1.json').write_text('{}')
            code,result=self.call(['inventory',folder])
            self.assertEqual(code,0)
            self.assertEqual(result['scan_count'],1)
            self.assertEqual(result['loaded_count'],0)
            self.assertIsNone(result['scans'][0]['room_count'])
