"""Queue integrity, duplicate prevention and explicit-open behavior; no real print."""
from pathlib import Path
import json,time,unittest,zipfile,shutil,sys
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import studio_handoff as h

ROOT=Path(__file__).resolve().parents[1]/'runtime'/('handoff_tests_'+str(time.time_ns()))
ROOT.mkdir()

class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.folder=ROOT/self._testMethodName;self.folder.mkdir()
        self.root_patch=patch.object(h,'ROOT',self.folder/'queue');self.root_patch.start()
        self.available_patch=patch.object(h,'available',return_value=True);self.available_patch.start()
        self.source=self.folder/'source.gcode.3mf'
        with zipfile.ZipFile(self.source,'x') as out:
            out.writestr('Metadata/project_settings.config',json.dumps({'printer_model':'Bambu Lab A1 mini','nozzle_diameter':['0.6']}))
            out.writestr('Metadata/plate_1.gcode','M220 S100\n; test only\n')
        self.sliced=dict(id='a'*20,path=str(self.source),gcode_entry='Metadata/plate_1.gcode',nozzle='0.6',quality='standard',speed_percent=100,model_seconds=240,total_seconds=600,grams=1.4)
    def tearDown(self):self.root_patch.stop();self.available_patch.stop()
    def test_duplicate_request_reuses_identical_print_file(self):
        a=h.enqueue(self.sliced,'カメもどき');b=h.enqueue(self.sliced,'もう一度')
        self.assertEqual(a['id'],b['id']);self.assertEqual(len(h.items()),1)
        self.assertEqual(h.file(a['id']).read_bytes(),self.source.read_bytes())
        self.assertNotIn('started',a)
    def test_open_uses_official_app_without_print_command(self):
        a=h.enqueue(self.sliced,'カメ/もどき')
        with patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
            b=h.open_studio(a['id'])
        self.assertEqual(b['status'],'opened');self.assertNotIn('started',b)
        self.assertEqual(run.call_args.args[0],['/usr/bin/open','-a',str(h.APP),str(h.file(a['id']))])
    def test_tampering_blocks_open(self):
        a=h.enqueue(self.sliced,'テスト');file=h.file(a['id']);shutil.copy2(file,file.with_suffix('.before_tamper'))
        with file.open('ab') as out:out.write(b'changed')
        with patch.object(h.subprocess,'run') as run:
            with self.assertRaises(ValueError):h.open_studio(a['id'])
            run.assert_not_called()
    def test_sent_mark_requires_explicit_open_first(self):
        a=h.enqueue(self.sliced,'テスト')
        with self.assertRaises(ValueError):h.mark_sent(a['id'])
    def test_other_nozzle_rejected(self):
        with self.assertRaises(ValueError):h.enqueue(self.sliced|{'nozzle':'0.4'},'テスト')
    def test_missing_studio_rejected(self):
        with patch.object(h,'available',return_value=False):
            with self.assertRaises(ValueError):h.enqueue(self.sliced,'テスト')
    def test_request_path_traversal_rejected(self):
        with self.assertRaises(ValueError):h.file('../source')

if __name__=='__main__':unittest.main(verbosity=2)
