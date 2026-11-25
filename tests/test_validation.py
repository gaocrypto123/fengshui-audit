import unittest, sys, json, copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import check
class ValidationTests(unittest.TestCase):
 def scene(self): return json.loads((ROOT/'assets/demo_scene.json').read_text(encoding='utf-8'))
 def test_empty_input_never_passes(self):
  r=check.run_data({});self.assertEqual(r['summary']['passed'],0);self.assertEqual(r['summary']['skipped'],21)
 def test_missing_collections(self):
  for key in ['walls','doors','furniture']:
   d=self.scene();del d[key];self.assertGreater(check.run_data(d)['summary']['skipped'],0)
 def test_low_filter_count(self):
  r=check.run_data(self.scene(),include_low=False);s=r['summary'];self.assertEqual(r['rule_count'],s['violated_rules']+s['passed']+s['skipped']);self.assertLess(r['rule_count'],21)
 def test_unknown_rule(self):
  with self.assertRaises(ValueError):check.run_data(self.scene(),only={'typo'})
 def test_invalid_values(self):
  for val in [float('nan'),float('inf'),True,-1,0]:
   d=self.scene();d['furniture'][0]['rect']['len']=val
   with self.assertRaises(ValueError):check.run_data(d)
 def test_duplicate(self):
  d=self.scene();d['doors'][0]['id']=d['walls'][0]['id']
  with self.assertRaises(ValueError):check.run_data(d)
 def test_unit(self):
  d=self.scene();d['meta']['unit']='mm'
  with self.assertRaises(ValueError):check.run_data(d)
 def test_no_mutation(self):
  d=self.scene();original=copy.deepcopy(d);check.run_data(d);self.assertEqual(d,original)
