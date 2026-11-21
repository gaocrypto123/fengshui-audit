"""Deterministic evidence boundary; no generated quotations or implied verification."""
import json
from pathlib import Path

def evidence_for(rule_id, registry):
    accepted, pending = [], []
    for claim in registry.get("claims", []):
        if rule_id not in claim.get("rule_ids", []):
            continue
        valid = (claim.get("status") == "verified" and
                 all(claim.get(k) for k in ("id", "book_sha256", "edition", "pdf_page", "printed_page", "excerpt", "supported_claim", "reviewer")) and
                 claim.get("relation") == "direct")
        (accepted if valid else pending).append(claim.get("id", "unregistered"))
    return {"verified_claim_ids": accepted, "pending_claim_ids": pending,
            "citation_status": "verified" if accepted else "unverified",
            "allow_generated_quote": False}

def explain(result):
    registry = json.loads((Path(__file__).resolve().parents[1]/"references/evidence-registry.json").read_text(encoding="utf-8"))
    outcomes = {v["rule_id"]: "triggered" for v in result["violations"]}
    outcomes.update({v["rule_id"]: "passed" for v in result["passed_rules"]})
    outcomes.update({v["rule_id"]: "insufficient_evidence" for v in result["skipped"]})
    stages = [("whole_home", "整体门与通行关系", ("FS-ENT-", "FS-GEN-")),
              ("rooms", "卧室、厨房与起居空间", ("FS-BED-", "FS-KIT-", "FS-LIV-"))]
    return {"default_school": "形法空间关系（项目几何转译）",
            "culture_is_separate": True,
            "workflow": ["核对数据", "检查适用条件", "整体关系", "局部关系", "比较调整方案并全量复检", "解释与引用核验"],
            "review_order": [{"stage": key, "label": label, "rules": sorted(r for r in outcomes if r.startswith(prefixes))} for key,label,prefixes in stages],
            "rule_evidence": {r: evidence_for(r, registry) for r in sorted(outcomes)},
            "conflict_policy": {"different_context": "先核对流派与适用条件，不合并", "same_context_disagreement": "保留并列观点，不自动裁决", "layout_tradeoff": "候选方案必须全量复检；需求仅参与可行方案排序"},
            "conflict_detection": "not_implemented",
            "limits": ["检查顺序为解释组织，不代表已实现跨规则推理。", "几何触发不等于文献已核实或规范不合格。", "旧证据表的核对记录尚未全部与本地扫描页对应。"]}
