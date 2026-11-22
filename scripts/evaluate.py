"""候选布局方案的全量复检与排序。

章程（reasoning.conflict_policy.layout_tradeoff）：
- 候选方案必须全量复检——每个方案都在完整 20 条规则上重跑，不做局部估算；
- 用户需求只参与可行方案排序——需求不豁免复检，也不影响"可行"的判定。

每个方案的输出：
- recheck: 复检后违规总数、按严重度分布
- diff: 与基线（原始场景）对比的 resolved / remaining / new
- feasible: 复检成功跑完即可行；场景非法或复检失败则不可行，如实报错

排序规则：先按"复检后违规总数"升序，再按"新增问题数"升序；needs 原样透传，
由调用方在可行方案中自行参考，不参与 feasible 判定。
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402
import reasoning  # noqa: E402


def _apply_mutations(scene, mutations):
    """把候选方案的家具变更套用到场景副本，返回 (副本, 成功套用数, 未匹配ID列表)。"""
    data = copy.deepcopy(scene)
    index = {f.get("id"): f for f in data.get("furniture", [])}
    applied, missing = 0, []
    for m in mutations:
        f = index.get(m.get("furniture_id"))
        if f is None:
            missing.append(m.get("furniture_id"))
            continue
        f["rect"] = dict(f["rect"], **m.get("rect", {}))
        applied += 1
    return data, applied, missing


def _sig(v):
    return (v.get("rule_id", ""), tuple(sorted(v.get("objects", []))))


def evaluate_options(scene, options):
    """对 N 个候选布局方案各自做全量复检，输出对比与排序。

    scene: 基线户型 JSON（调整前）。
    options: [{id, label, mutations: [{furniture_id, rect}], needs: {...}}, ...]
    """
    base_result = check.run_data(scene)
    out = {"options": [], "policy": {
        "recheck": "每个方案在完整规则集上全量复检，不做局部估算",
        "ranking": "按复检后违规总数升序，再按新增问题数升序；needs 原样透传，不参与可行性判定",
        "user_needs": "需求仅用于在可行方案之间选择，不能豁免复检",
    }}
    for opt in options:
        mutations = opt.get("mutations", []) if isinstance(opt, dict) else []
        data, applied, missing = _apply_mutations(scene, mutations)
        entry = {
            "id": opt.get("id", "") if isinstance(opt, dict) else "",
            "label": opt.get("label", "") if isinstance(opt, dict) else "",
            "applied_mutations": applied,
            "missing_furniture_ids": missing,
            "needs": opt.get("needs") if isinstance(opt, dict) else None,
        }
        if missing:
            entry["feasible"] = False
            entry["error"] = "部分家具 ID 不存在，无法套用该方案：%s" % ", ".join(missing)
            out["options"].append(entry)
            continue
        try:
            result = check.run_data(data)
        except (ValueError, KeyError, TypeError) as e:
            entry["feasible"] = False
            entry["error"] = "复检失败：%s" % e
            out["options"].append(entry)
            continue
        s = result["summary"]
        diff = reasoning.compare_results(base_result, result)
        entry["feasible"] = True
        entry["recheck"] = {
            "violations": s["violations"],
            "by_severity": s.get("by_severity", {}),
            "skipped": s.get("skipped", 0),
        }
        entry["diff"] = diff["summary"]
        out["options"].append(entry)
    feasible = [o for o in out["options"] if o.get("feasible")]
    infeasible = [o for o in out["options"] if not o.get("feasible")]
    feasible.sort(key=lambda o: (o["recheck"]["violations"], o["diff"]["new"]))
    out["options"] = feasible + infeasible
    out["ranking"] = [o["id"] for o in feasible]
    out["infeasible_ids"] = [o["id"] for o in infeasible]
    out["note"] = "排序基于复检结果；调整方案未经复检前，不声称其已改善。"
    return out
