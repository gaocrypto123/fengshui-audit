"""Deterministic evidence boundary; no generated quotations or implied verification.

v1.3 新增：
- attach_chains(result): 把「主张 → 证据状态 → 阈值来源 → 适用条件 → 复检标准」
  链路附加到诊断结果的每条违规/通过项上（仅覆盖 references/rule-chain.json
  中登记的核心规则）。
- compare_results(baseline, current): 复检对比，输出已解决 / 仍存在 / 新增三类。
- conflicts_for(rule_id): 按 references/classic-disagreements.json 查表返回该规则的
  经典流派分歧（并列呈现，不裁决）；自动发现新冲突尚未实现。

边界说明：
- attach_chains 不改变判定结果，只附加解释与来源信息。
- citation_status 为 unverified 时，调用方不得生成原书引文或精确页码。
- compare_results 基于规则 ID + 对象集合的几何签名，不理解空间语义。
- conflicts_for 只按登记表并列呈现流派分歧，不在登记表之外推断新冲突。
"""
import json
from pathlib import Path

_REF_DIR = Path(__file__).resolve().parents[1] / "references"


def _registry():
    return json.loads((_REF_DIR / "evidence-registry.json").read_text(encoding="utf-8"))


def _rule_chains():
    path = _REF_DIR / "rule-chain.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("rules", {})


_DISAGREEMENTS_CACHE = None


def _disagreements():
    global _DISAGREEMENTS_CACHE
    if _DISAGREEMENTS_CACHE is None:
        path = _REF_DIR / "classic-disagreements.json"
        _DISAGREEMENTS_CACHE = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _DISAGREEMENTS_CACHE


def conflicts_for(rule_id):
    """该规则关联的经典流派分歧（并列呈现，不裁决）。

    只按登记表查表返回；登记表之外不推断新冲突。
    未登记分歧的规则返回空列表。
    """
    out = []
    for d in _disagreements().get("disagreements", []):
        if rule_id in d.get("rule_ids", []):
            out.append({
                "id": d.get("id", ""),
                "topic": d.get("topic", ""),
                "positions": d.get("positions", []),
                "resolution": d.get("resolution", ""),
                "note": d.get("note", ""),
            })
    return out


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


def chain_for(rule_id):
    """单条规则的完整证据链；未登记的规则返回 None。"""
    chains = _rule_chains()
    if rule_id not in chains:
        return None
    c = chains[rule_id]
    ev = evidence_for(rule_id, _registry())
    ch = {
        "claim": c.get("claim", ""),
        "claim_ids": c.get("claim_ids", []),
        "citation_status": ev["citation_status"],
        "verified_claim_ids": ev["verified_claim_ids"],
        "pending_claim_ids": ev["pending_claim_ids"],
        "allow_generated_quote": ev["allow_generated_quote"],
        "candidate_sources": c.get("candidate_sources", []),
        "source_status": c.get("source_status", "candidate_unverified"),
        "applicability": c.get("applicability", {}),
        "thresholds": c.get("thresholds", []),
        "recheck": c.get("recheck", ""),
        "suggestion_basis": "项目几何转译建议，非书籍处方。",
        "limits": c.get("limits", []),
    }
    dis = conflicts_for(rule_id)
    if dis:
        ch["known_disagreements"] = dis
    return ch


def attach_chains(result):
    """给 result 中的违规/通过/跳过项附加证据链（仅核心规则）。

    不修改 violations 数量与判定内容；只新增 "chain" 字段。
    """
    for v in result.get("violations", []):
        ch = chain_for(v.get("rule_id", ""))
        if ch:
            v["chain"] = ch
    for p in result.get("passed_rules", []):
        ch = chain_for(p.get("rule_id", ""))
        if ch:
            p["chain"] = ch
    for k in result.get("skipped", []):
        ch = chain_for(k.get("rule_id", ""))
        if ch:
            k["chain"] = ch
    return result


def _sig(v):
    return (v.get("rule_id", ""), tuple(sorted(v.get("objects", []))))


def compare_results(baseline, current):
    """复检对比：基于 (rule_id, sorted(objects)) 几何签名。

    注意：同一规则因对象组合不同会同时出现在「已解决」和「新增」中，
    这是有意的保守行为——不假装知道"是同一个问题被修好了"。
    """
    base = {_sig(v): v for v in baseline.get("violations", [])}
    curr = {_sig(v): v for v in current.get("violations", [])}
    curr_skip = {k.get("rule_id", "") for k in current.get("skipped", [])}
    unassessed = [{"rule_id": v["rule_id"], "name": v.get("name", ""),
                   "objects": v.get("objects", []),
                   "object_labels": v.get("object_labels", [])}
                  for sig, v in sorted(base.items())
                  if sig not in curr and v["rule_id"] in curr_skip]
    resolved = [{"rule_id": v["rule_id"], "name": v.get("name", ""),
                 "objects": v.get("objects", []),
                 "object_labels": v.get("object_labels", [])}
                for sig, v in sorted(base.items())
                if sig not in curr and v["rule_id"] not in curr_skip]
    remaining = [{"rule_id": v["rule_id"], "name": v.get("name", ""),
                  "objects": v.get("objects", []),
                  "object_labels": v.get("object_labels", [])}
                 for sig, v in sorted(curr.items()) if sig in base]
    new = [{"rule_id": v["rule_id"], "name": v.get("name", ""),
            "objects": v.get("objects", []),
            "object_labels": v.get("object_labels", [])}
           for sig, v in sorted(curr.items()) if sig not in base]
    # 跳过项变化：数据补齐/缺失会让某些规则从未判定变为已判定，或反之
    base_skip = {k.get("rule_id", "") for k in baseline.get("skipped", [])}
    curr_skip = {k.get("rule_id", "") for k in current.get("skipped", [])}
    summary = {
        "baseline_violations": len(base),
        "current_violations": len(curr),
        "resolved": len(resolved),
        "unassessed": len(unassessed),
        "remaining": len(remaining),
        "new": len(new),
        "newly_skipped": sorted(curr_skip - base_skip),
        "newly_checkable": sorted(base_skip - curr_skip),
    }
    return {
        "summary": summary,
        "resolved": resolved,
        "unassessed": unassessed,
        "remaining": remaining,
        "new": new,
        "note": "对比基于规则 ID 与对象集合的几何签名；调整方案未经全量复检前，不声称其已改善。",
        "conflict_policy": "候选方案须全量复检；用户需求仅参与可行方案排序。",
    }


def explain(result):
    registry = _registry()
    outcomes = {v["rule_id"]: "triggered" for v in result["violations"]}
    outcomes.update({v["rule_id"]: "passed" for v in result["passed_rules"]})
    outcomes.update({v["rule_id"]: "insufficient_evidence" for v in result["skipped"]})
    stages = [("whole_home", "整体门与通行关系", ("FS-ENT-", "FS-GEN-")),
              ("rooms", "卧室、厨房与起居空间", ("FS-BED-", "FS-KIT-", "FS-LIV-"))]
    out = {"default_school": "形法空间关系（项目几何转译）",
            "culture_is_separate": True,
            "workflow": ["核对数据", "检查适用条件", "整体关系", "局部关系", "比较调整方案并全量复检", "解释与引用核验"],
            "review_order": [{"stage": key, "label": label, "rules": sorted(r for r in outcomes if r.startswith(prefixes))} for key,label,prefixes in stages],
            "rule_evidence": {r: evidence_for(r, registry) for r in sorted(outcomes)},
            "conflict_policy": {"different_context": "先核对流派与适用条件，不合并", "same_context_disagreement": "保留并列观点，不自动裁决", "layout_tradeoff": "候选方案必须全量复检；需求仅参与可行方案排序"},
            "conflict_detection": "registry_based_listing（仅按 classic-disagreements.json 并列呈现；自动发现新冲突 not_implemented）",
            "disagreement_ids": sorted({d["id"] for r in outcomes for d in conflicts_for(r)}),
            "limits": ["检查顺序为解释组织，不代表已实现跨规则推理。", "几何触发不等于文献已核实或规范不合格。", "旧证据表的核对记录尚未全部与本地扫描页对应。"]}
    out["rule_chains"] = {r: chain_for(r) for r in sorted(outcomes) if chain_for(r)}
    attach_chains(result)
    return out
