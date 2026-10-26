"""fengshui-audit 回归测试套（v1.1 新增）。

运行：cd 仓库根目录 && python3 -m unittest discover -s tests -v
或：pytest tests/

覆盖：
- 几何原语（Rect / seg_intersect / point_seg_dist）
- demo 场景回归（锁 9/1）
- v1.1 修复项：beams 缺失显式 skip、窗内侧方向推断、
  多实例违规、entry 退化 warning、room_type 显式字段
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check  # noqa: E402

ASSETS = ROOT / "assets"


def run_scene(data):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        path = f.name
    return check.run(path)


class TestGeometry(unittest.TestCase):
    def test_rect_corners_axis_aligned(self):
        r = check.Rect({"cx": 0, "cy": 0, "len": 2, "wid": 1, "heading": 0})
        cs = r.corners()
        self.assertAlmostEqual(min(p[0] for p in cs), -1.0)
        self.assertAlmostEqual(max(p[0] for p in cs), 1.0)
        self.assertAlmostEqual(min(p[1] for p in cs), -0.5)
        self.assertAlmostEqual(max(p[1] for p in cs), 0.5)

    def test_back_edge_opposite_heading(self):
        # heading=0（朝东）→ 床头边在西侧（x=-1）
        r = check.Rect({"cx": 0, "cy": 0, "len": 2, "wid": 1, "heading": 0})
        a, b = r.back_edge()
        self.assertAlmostEqual(a[0], -1.0)
        self.assertAlmostEqual(b[0], -1.0)

    def test_seg_intersect_cross(self):
        self.assertTrue(check.seg_intersect((0, 0), (2, 2), (0, 2), (2, 0)))
        self.assertFalse(check.seg_intersect((0, 0), (1, 0), (0, 1), (1, 1)))

    def test_point_seg_dist_clamped(self):
        self.assertAlmostEqual(check.point_seg_dist((3, 0), (0, 0), (1, 0)), 2.0)
        self.assertAlmostEqual(check.point_seg_dist((0.5, 1), (0, 0), (1, 0)), 1.0)


class TestDemoRegression(unittest.TestCase):
    """demo 9/1 回归锁：阈值或逻辑改动后命中数变化即报警。"""

    def setUp(self):
        self.demo = check.run(str(ASSETS / "demo_scene.json"))
        self.fixed = check.run(str(ASSETS / "demo_scene_fixed.json"))

    def test_demo_hits_9(self):
        self.assertEqual(self.demo["summary"]["violations"], 9)
        self.assertEqual(self.demo["summary"]["skipped"], 0)

    def test_fixed_hits_1_and_is_ent001(self):
        self.assertEqual(self.fixed["summary"]["violations"], 1)
        self.assertEqual(self.fixed["violations"][0]["rule_id"], "FS-ENT-001")

    def test_all_18_rules_accounted(self):
        s = self.demo["summary"]
        self.assertEqual(s["violations"] + s["passed"] + s["skipped"], 18)


class TestV11Fixes(unittest.TestCase):
    def test_missing_beams_goes_to_skipped(self):
        d = json.loads((ASSETS / "demo_scene.json").read_text(encoding="utf-8"))
        del d["beams"]
        r = run_scene(d)
        self.assertIn("FS-BED-004", [k["rule_id"] for k in r["skipped"]])
        self.assertFalse(any(p["rule_id"] == "FS-BED-004" for p in r["passed_rules"]))

    def test_empty_beams_list_passes(self):
        d = json.loads((ASSETS / "demo_scene.json").read_text(encoding="utf-8"))
        d["beams"] = []
        r = run_scene(d)
        self.assertTrue(any(p["rule_id"] == "FS-BED-004" for p in r["passed_rules"]))

    def test_window_band_translation_invariant(self):
        """窗内侧方向不得依赖硬编码坐标：整体平移场景，GEN-004 仍应命中。"""
        d = json.loads((ASSETS / "demo_scene.json").read_text(encoding="utf-8"))

        def shift(p):
            return [p[0] + 100, p[1] + 100]

        for w in d["walls"]:
            w["a"], w["b"] = shift(w["a"]), shift(w["b"])
        for door in d["doors"]:
            door["center"] = shift(door["center"])
        for fm in d["furniture"]:
            fm["rect"]["cx"] += 100
            fm["rect"]["cy"] += 100
        for rm in d.get("rooms", []):
            rm["rect"]["cx"] += 100
            rm["rect"]["cy"] += 100
        for bm in d["beams"]:
            bm["a"], bm["b"] = shift(bm["a"]), shift(bm["b"])
        r = run_scene(d)
        self.assertTrue(any(v["rule_id"] == "FS-GEN-004" for v in r["violations"]))

    def test_multiple_beds_reported_individually(self):
        d = json.loads((ASSETS / "demo_scene.json").read_text(encoding="utf-8"))
        beds = [f for f in d["furniture"] if f["type"] == "bed"]
        self.assertGreaterEqual(len(beds), 1)
        src = next(f for f in beds if f["id"] == "BED-S")  # 悬空的次卧床
        # 复制并西移 0.5m：床头边 x=5.3，四周皆无墙可贴，仍应命中
        clone = json.loads(json.dumps(src))
        clone["id"] = "BED-CLONE"
        clone["name"] = "克隆床"
        clone["rect"]["cx"] -= 0.5
        d["furniture"].append(clone)
        r = run_scene(d)
        bed001 = [v for v in r["violations"] if v["rule_id"] == "FS-BED-001"]
        self.assertEqual(len(bed001), 2)  # v1.1：多实例各出一条

    def test_entry_fallback_warns(self):
        d = json.loads((ASSETS / "demo_scene.json").read_text(encoding="utf-8"))
        for door in d["doors"]:
            door["is_entry"] = False
        r = run_scene(d)
        self.assertTrue(any("is_entry" in w for w in r.get("warnings", [])))

    def test_room_type_field_overrides_name_guess(self):
        """门名不含"卫"但 room_type=toilet 时，ENT-001 仍应命中。"""
        d = json.loads((ASSETS / "demo_scene.json").read_text(encoding="utf-8"))
        hit = False
        for door in d["doors"]:
            if "卫" in door.get("name", "") or "toilet" in door.get("id", "").lower():
                door["name"] = "M-door"
                door["id"] = "D-x"
                door["room_type"] = "toilet"
                hit = True
        self.assertTrue(hit, "demo 场景应包含卫生间门以支撑本测试")
        r = run_scene(d)
        self.assertTrue(any(v["rule_id"] == "FS-ENT-001" for v in r["violations"]))


if __name__ == "__main__":
    unittest.main()
