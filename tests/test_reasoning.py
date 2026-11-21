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
