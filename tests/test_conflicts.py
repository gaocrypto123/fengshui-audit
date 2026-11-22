"""Conflict registry listing and candidate recheck ranking."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reasoning import conflicts_for, explain
from evaluate import evaluate_options

ROOT = Path(__file__).resolve().parents[1]


class ConflictTests(unittest.TestCase):
    def test_bed_rule_lists_both_schools_without_verdict(self):
        """床位规则的分歧条目：两派并列、均标注未核，且不裁决。"""
        dis = conflicts_for("FS-BED-001")
        self.assertEqual(len(dis), 1)
        schools = [p["school"] for p in dis[0]["positions"]]
        self.assertEqual(len(schools), len(set(schools)))  # 并列，不合并
        for p in dis[0]["positions"]:
            if p["source_status"] == "secondary_unverified":
                self.assertTrue(p["source_note"])
        self.assertIn("不裁决", dis[0]["resolution"])
        self.assertTrue(dis[0]["resolution"])

    def test_unregistered_rule_has_no_conflicts(self):
        self.assertEqual(conflicts_for("FS-LIV-001"), [])

    def test_chain_includes_disagreements_and_explain_reports_state(self):
        ch = reasoning_chain()
        self.assertIn("known_disagreements", ch)
        result = {"violations": [], "passed_rules": [{"rule_id": "FS-BED-001"}], "skipped": []}
        exp = explain(result)
        self.assertIn("registry_based_listing", exp["conflict_detection"])
        self.assertIn("DIS-BED-001-01", exp["disagreement_ids"])


def reasoning_chain():
    sys.path.insert(0, str(ROOT / "scripts"))
    from reasoning import chain_for
    return chain_for("FS-BED-001")


class EvaluateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = json.loads((ROOT / "assets" / "demo_scene.json").read_text(encoding="utf-8"))

    def test_options_full_recheck_and_sorting_key(self):
        """每个方案都全量复检；排序严格按（复检违规数, 新增数）升序。"""
        bed = [f for f in self.scene["furniture"] if f["id"] == "BED-M"][0]
        moved = dict(bed["rect"], cx=bed["rect"]["cx"] + 1.5, cy=bed["rect"]["cy"] + 1.5)
        out = evaluate_options(self.scene, [
            {"id": "A_same", "label": "维持现状", "mutations": []},
            {"id": "B_moved", "label": "挪床", "mutations": [{"furniture_id": "BED-M", "rect": moved}]},
        ])
        self.assertEqual(out["infeasible_ids"], [])
        for o in out["options"]:
            self.assertTrue(o["feasible"])
            self.assertIn("recheck", o)
            self.assertIn("diff", o)
        keys = [(o["recheck"]["violations"], o["diff"]["new"]) for o in out["options"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(out["ranking"], [o["id"] for o in out["options"]])
        self.assertIn("全量复检", out["policy"]["recheck"])

    def test_missing_furniture_id_is_infeasible_not_silent(self):
        out = evaluate_options(self.scene, [
            {"id": "X", "label": "不存在的家具", "mutations": [{"furniture_id": "NOPE", "rect": {}}]},
        ])
        x = out["options"][0]
        self.assertFalse(x["feasible"])
        self.assertEqual(out["infeasible_ids"], ["X"])
        self.assertIn("NOPE", x["error"])


if __name__ == "__main__":
    unittest.main()
