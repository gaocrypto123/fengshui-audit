import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from reasoning import evidence_for, explain, chain_for, attach_chains, compare_results

class EvidenceTests(unittest.TestCase):
    def test_missing_citation_is_unverified(self):
        self.assertEqual(evidence_for("R", {"claims":[]})["citation_status"], "unverified")
    def test_verified_label_alone_is_not_enough(self):
        c={"id":"E1","rule_ids":["R"],"status":"verified"}
        self.assertFalse(evidence_for("R", {"claims":[c]})["verified_claim_ids"])
    def test_indirect_evidence_cannot_prove_claim(self):
        c=dict(id="E1",rule_ids=["R"],status="verified",book_sha256="hash",edition="edition",pdf_page=61,printed_page=54,excerpt="excerpt",supported_claim="claim",reviewer="human",relation="indirect")
        self.assertEqual(evidence_for("R", {"claims":[c]})["citation_status"],"unverified")
        c["relation"]="direct"
        self.assertEqual(evidence_for("R", {"claims":[c]})["verified_claim_ids"],["E1"])

    def test_design_bases_do_not_verify_fengshui_rules(self):
        """OCR核对出的人体工程学依据不得提升风水规则的引用状态。"""
        import json
        reg = json.loads((Path(__file__).resolve().parents[1]/"references"/"evidence-registry.json").read_text(encoding="utf-8"))
        bases = reg.get("verified_design_bases", {}).get("claims", [])
        self.assertTrue(bases)
        for b in bases:
            self.assertEqual(b.get("status"), "verified")
            self.assertEqual(b.get("rule_ids"), [])  # 刻意留空，隔离风水规则
            for k in ("book_sha256", "edition", "pdf_page", "excerpt", "supported_claim", "reviewer"):
                self.assertTrue(b.get(k), "missing %s in %s" % (k, b["id"]))
            # printed_page 允许 None（如 GB50096 文字版 PDF 无印刷页码），但必须给出说明
            if b.get("printed_page") is None:
                self.assertTrue(b.get("note"), "printed_page 为 None 的条目 %s 必须在 note 中说明原因" % b["id"])
        # 真实诊断中风水规则仍为未核实
        for rid in ("FS-BED-001", "FS-BED-002", "FS-KIT-001"):
            ch = chain_for(rid)
            self.assertEqual(ch["citation_status"], "unverified")
            self.assertFalse(ch["verified_claim_ids"])
        self.assertFalse(evidence_for("FS-BED-001", reg)["allow_generated_quote"])

class ChainTests(unittest.TestCase):
    def test_core_rule_has_chain_with_pending_citation(self):
        """核心规则能取到证据链；登记表中主张为 pending，故引用状态必须为未核实。"""
        ch = chain_for("FS-BED-001")
        self.assertIsNotNone(ch)
        self.assertEqual(ch["citation_status"], "unverified")
        self.assertFalse(ch["allow_generated_quote"])
        self.assertEqual(ch["pending_claim_ids"], ["CLM-BED-001-01"])
        self.assertTrue(ch["claim"])
        self.assertTrue(all(t.get("source") != "book" for t in ch["thresholds"]))
    def test_unregistered_rule_has_no_chain(self):
        self.assertIsNone(chain_for("FS-LIV-001"))
    def test_attach_chains_annotates_without_changing_verdicts(self):
        result = {"violations": [{"rule_id": "FS-BED-001", "objects": ["b1"]}],
                  "passed_rules": [{"rule_id": "FS-KIT-001"}],
                  "skipped": [{"rule_id": "FS-LIV-002"}]}
        before = (len(result["violations"]), len(result["passed_rules"]), len(result["skipped"]))
        attach_chains(result)
        self.assertEqual((len(result["violations"]), len(result["passed_rules"]), len(result["skipped"])), before)
        self.assertIn("chain", result["violations"][0])
        self.assertIn("chain", result["passed_rules"][0])
        self.assertNotIn("chain", result["skipped"][0])
        self.assertIn("rule_chains", explain(result))

class RecheckTests(unittest.TestCase):
    def test_missing_data_does_not_resolve_previous_violation(self):
        base = {"violations": [self.v("FS-BED-001", ["bed", "door"])]}
        current = {"violations": [], "skipped": [{"rule_id": "FS-BED-001"}]}
        diff = compare_results(base, current)
        self.assertEqual(diff["summary"]["resolved"], 0)
        self.assertEqual(diff["summary"]["unassessed"], 1)
        self.assertEqual(diff["unassessed"][0]["objects"], ["bed", "door"])

    @staticmethod
    def v(rid, objs):
        return {"rule_id": rid, "objects": objs, "name": rid, "object_labels": objs}
    def test_resolved_remaining_new(self):
        base = {"violations": [self.v("A", ["x"]), self.v("B", ["y"]), self.v("C", ["z"])],
                "skipped": []}
        curr = {"violations": [self.v("B", ["y"]), self.v("D", ["w"])], "skipped": []}
        diff = compare_results(base, curr)
        self.assertEqual(diff["summary"]["resolved"], 2)
        self.assertEqual(diff["summary"]["remaining"], 1)
        self.assertEqual(diff["summary"]["new"], 1)
        self.assertEqual([r["rule_id"] for r in diff["resolved"]], ["A", "C"])
        self.assertEqual([r["rule_id"] for r in diff["remaining"]], ["B"])
        self.assertEqual([r["rule_id"] for r in diff["new"]], ["D"])
    def test_object_change_counts_as_resolved_plus_new(self):
        """同规则但对象组合变了：保守计为一解决一新增，不假装知道是修好了。"""
        base = {"violations": [self.v("A", ["x"])], "skipped": []}
        curr = {"violations": [self.v("A", ["y"])], "skipped": []}
        diff = compare_results(base, curr)
        self.assertEqual(diff["summary"]["resolved"], 1)
        self.assertEqual(diff["summary"]["new"], 1)
        self.assertEqual(diff["summary"]["remaining"], 0)
    def test_skipped_change_is_reported(self):
        base = {"violations": [], "skipped": [{"rule_id": "S1"}]}
        curr = {"violations": [], "skipped": []}
        diff = compare_results(base, curr)
        self.assertEqual(diff["summary"]["newly_checkable"], ["S1"])
        self.assertEqual(diff["summary"]["newly_skipped"], [])
