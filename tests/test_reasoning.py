import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from reasoning import evidence_for, explain

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
