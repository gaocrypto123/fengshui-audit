#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
风水审查 · L1 几何判定引擎（零依赖，仅标准库）

输入：户型场景 JSON（schema 见 references/scene-schema.md）
输出：违规清单 JSON / Markdown

用法：
    python check.py --scene assets/demo_scene.json
    python check.py --scene scene.json --out result.json
    python check.py --scene scene.json --format md
    python check.py --list            # 列出全部规则

设计原则：
  1. 只做几何判定，不做解释。解释由 L2（知识层）与 L3（表达层）负责。
  2. 每条规则的阈值来自 references/parameters.md，与国标/人体工程学对照标注。
  3. 判定失败（缺字段）不静默通过，而是记入 skipped，便于上层如实告知用户。
  4. 规则函数可返回单个 dict 或 dict 列表（多实例违规），也可返回
     ("SKIP", 原因) 表示因数据缺失未能判定——绝不用 None 冒充"跳过"。
"""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import minggua  # noqa: E402  八宅派命卦（文化参考层，独立于 18 条判定）

# ---------------------------------------------------------------- 常量

# 参数表（单位：米 / 度）。修改此处即修改全库阈值，references/parameters.md 为人类可读版。
PARAMS = {
    "GAP_HEAD_WALL": 0.05,     # 床头贴墙判定间隙
    "GAP_STOVE_SINK": 0.60,    # 灶-槽最小间距
    "GAP_SOFA_WALL": 0.15,     # 沙发靠墙判定
    "ANGLE_DOOR_FAN": 30.0,    # 门/镜视线锥半角
    "ANGLE_ALIGNED": 15.0,     # 近似共线判定角
    "DIST_DOOR_BED": 2.50,     # 门冲床有效距离
    "DIST_CORRIDOR_MIN": 0.90, # 主通道最小净宽（对齐 GB 55038-2025 通厨卫下限）
    # v1.1 收敛进来的阈值（原先散落在各规则函数里）
    "DIST_MIRROR_BED": 4.00,   # 镜-床最大距离（FS-BED-003）
    "DIST_ENTRY_STOVE": 5.00,  # 入户门-灶台最大距离（FS-ENT-002）
    "DIST_DOOR_DOOR": 3.00,    # 门对门 / 灶对厨房门 / 镜对大门最大距离
    "DIST_STOVE_DOOR": 0.90,   # 灶台-侧门最小距离（FS-KIT-002）
    "CLEARANCE_BED_SIDE": 0.60,# 床侧通道最小净空（FS-BED-006）
    "CLEARANCE_SEARCH": 1.50,  # 净空搜索最大距离
    "HEIGHT_BLOCK_WIN": 1.20,  # 窗前遮光的最小家具高度
    "BAND_WINDOW": 0.50,       # 窗前采光带深度
    "ANGLE_BACK_TO_BACK": 160.0,  # 两门"近似相对"的法线夹角下限（FS-ENT-001）
    "ANGLE_SAME_SIDE": 90.0,   # 判定门在灶台同侧的法线夹角上限（FS-KIT-002）
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# ---------------------------------------------------------------- 几何

EPS = 1e-9


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, k):
    return (a[0] * k, a[1] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def length(a):
    return math.hypot(a[0], a[1])


def norm(a):
    l = length(a)
    return (0.0, 0.0) if l < EPS else (a[0] / l, a[1] / l)


def perp(a):
    return (-a[1], a[0])


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def heading_vec(deg):
    r = math.radians(deg)
    return (math.cos(r), math.sin(r))


def heading_of(v):
    return math.degrees(math.atan2(v[1], v[0]))


def angle_between(a, b):
    """两向量夹角，度，0-180"""
    na, nb = norm(a), norm(b)
    d = max(-1.0, min(1.0, dot(na, nb)))
    return math.degrees(math.acos(d))


def cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def seg_intersect(a1, a2, b1, b2):
    d1 = cross(b1, b2, a1)
    d2 = cross(b1, b2, a2)
    d3 = cross(a1, a2, b1)
    d4 = cross(a1, a2, b2)
    return ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0))


def point_seg_dist(p, a, b):
    ab = sub(b, a)
    l2 = dot(ab, ab)
    if l2 < EPS:
        return dist(p, a)
    t = max(0.0, min(1.0, dot(sub(p, a), ab) / l2))
    return dist(p, add(a, mul(ab, t)))


def seg_seg_dist(a1, a2, b1, b2):
    if seg_intersect(a1, a2, b1, b2):
        return 0.0
    return min(point_seg_dist(a1, b1, b2), point_seg_dist(a2, b1, b2),
               point_seg_dist(b1, a1, a2), point_seg_dist(b2, a1, a2))


class Rect:
    """旋转矩形（俯视）。heading 为家具主朝向角。"""

    def __init__(self, d):
        self.c = (float(d["cx"]), float(d["cy"]))
        self.len = float(d["len"])
        self.wid = float(d["wid"])
        self.heading = float(d.get("heading", 0.0))

    def _at(self, u, v):
        h = heading_vec(self.heading)
        return (self.c[0] + h[0] * u + (-h[1]) * v,
                self.c[1] + h[1] * u + h[0] * v)

    def corners(self):
        hl, hw = self.len / 2.0, self.wid / 2.0
        return [self._at(-hl, -hw), self._at(hl, -hw), self._at(hl, hw), self._at(-hl, hw)]

    def edges(self):
        p = self.corners()
        return [(p[0], p[1]), (p[1], p[2]), (p[2], p[3]), (p[3], p[0])]

    def back_edge(self):
        """与 heading 反向的那条边（床头边 / 沙发背边）。"""
        p = self.corners()
        h = heading_vec(self.heading)
        us = [dot(sub(q, self.c), h) for q in p]
        mn = min(us)
        idx = [i for i, u in enumerate(us) if u <= mn + 1e-4]
        if len(idx) >= 2:
            return (p[idx[0]], p[idx[1]])
        order = sorted(range(4), key=lambda i: us[i])
        return (p[order[0]], p[order[1]])

    def back_mid(self):
        a, b = self.back_edge()
        return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)

    def dist_to_seg(self, a, b):
        return min(seg_seg_dist(p, q, a, b) for p, q in self.edges())

    def dist_to_rect(self, other):
        return min(seg_seg_dist(p, q, r, s) for p, q in self.edges() for r, s in other.edges())

    def contains(self, p):
        h = heading_vec(self.heading)
        v = sub(p, self.c)
        u = dot(v, h)
        w = dot(v, (-h[1], h[0]))
        return abs(u) <= self.len / 2.0 and abs(w) <= self.wid / 2.0


# ---------------------------------------------------------------- 场景

class Scene:
    def __init__(self, data):
        self.raw = data
        self.walls = []
        for w in data.get("walls", []):
            self.walls.append({
                "id": w.get("id", ""),
                "a": tuple(w["a"]), "b": tuple(w["b"]),
                "is_window": bool(w.get("is_window", False)),
            })
        self.doors = []
        for d in data.get("doors", []):
            self.doors.append({
                "id": d.get("id", ""),
                "name": d.get("name", d.get("id", "")),
                "center": tuple(d["center"]),
                "normal": norm(tuple(d["normal"])),
                "width": float(d.get("width", 0.9)),
                "is_entry": bool(d.get("is_entry", False)),
                "room_type": str(d.get("room_type", "")),  # 显式房间类型，优先于名称猜测
            })
        self.beams = []
        for b in data.get("beams", []):
            self.beams.append({
                "id": b.get("id", ""), "name": b.get("name", ""),
                "a": tuple(b["a"]), "b": tuple(b["b"]),
                "width": float(b.get("width", 0.3)),
            })
        self.furn = []
        for f in data.get("furniture", []):
            self.furn.append({
                "id": f.get("id", ""),
                "name": f.get("name", f.get("id", "")),
                "type": str(f.get("type", "other")).lower(),
                "rect": Rect(f["rect"]),
                "height": float(f.get("height", 0.75)),
            })
        self.rooms = []
        for r in data.get("rooms", []):
            self.rooms.append({
                "id": r.get("id", ""), "name": r.get("name", ""),
                "rect": Rect(r["rect"]),
            })

    def of_type(self, t):
        return [f for f in self.furn if f["type"] == t]

    def solid_walls(self):
        return [w for w in self.walls if not w["is_window"]]

    def entry(self):
        for d in self.doors:
            if d["is_entry"]:
                return d
        return self.doors[0] if self.doors else None

    def has_entry_marked(self):
        return any(d["is_entry"] for d in self.doors)

    def los(self, a, b, margin=0.06):
        """视线是否通畅（只看实墙）。"""
        d = sub(b, a)
        if length(d) < 2 * margin:
            return True
        u = norm(d)
        a2, b2 = add(a, mul(u, margin)), sub(b, mul(u, margin))
        for w in self.solid_walls():
            if seg_intersect(a2, b2, w["a"], w["b"]):
                return False
        return True

    def room_of(self, p):
        for r in self.rooms:
            if r["rect"].contains(p):
                return r["name"]
        return ""

    def interior_center(self):
        """场景内部参考点：优先用房间矩形中心的平均；没有房间数据时用全部墙段的包围盒中心。"""
        if self.rooms:
            xs = [r["rect"].c[0] for r in self.rooms]
            ys = [r["rect"].c[1] for r in self.rooms]
            return (sum(xs) / len(xs), sum(ys) / len(ys))
        if self.walls:
            pts = [w["a"] for w in self.walls] + [w["b"] for w in self.walls]
            return ((min(p[0] for p in pts) + max(p[0] for p in pts)) / 2.0,
                    (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2.0)
        return None


def clearance_along(scene, start, normal, max_dist=None, step=0.02, skip=()):
    """从 start 沿 normal 方向能走多远而不撞到障碍。

    这是「净空」的正确度量：床侧通道、沙发背后都要看特定方向上的余量，
    而不是到任意障碍的最短距离（后者会把侧向的墙误算成背后不靠）。
    """
    if max_dist is None:
        max_dist = PARAMS["CLEARANCE_SEARCH"]
    obstacles = []
    for w in scene.solid_walls():
        obstacles.append((w["a"], w["b"]))
    for g in scene.furn:
        if g["id"] in skip:
            continue
        obstacles.extend(g["rect"].edges())

    t = 0.0
    while t <= max_dist:
        p = add(start, mul(normal, t))
        for a, b in obstacles:
            if point_seg_dist(p, a, b) < step:
                return t
        t += step
    return max_dist


def cone_hits_rect(origin, dir_deg, half_angle, rect, max_dist):
    """以 origin 为顶点、半角 half_angle 的视线锥是否罩住矩形。"""
    if dist(origin, rect.c) > max_dist + rect.len:
        return False
    d = heading_vec(dir_deg)
    for p in rect.corners() + [rect.c]:
        v = sub(p, origin)
        if length(v) > max_dist + 1e-6:
            continue
        if angle_between(d, v) <= half_angle:
            return True
    return False


# ---------------------------------------------------------------- 规则实现
# 每个函数签名 (scene) -> None（通过）| dict（单条违规）| list[dict]（多条违规）
#                                                  | ("SKIP", 原因)（数据缺失未判定）


def r_bed001(s):
    """床头靠实墙：床头边到实墙间隙 > GAP_HEAD_WALL，或所贴墙段短于床宽，或该墙是窗墙。

    v1.1 修正：先在「贴墙阈值内」的候选实墙里挑墙长检查，避免附近一段短隔墙
    被误当成床头依靠的墙；每张床独立判定，支持多张床各出一条。
    """
    out = []
    for f in s.of_type("bed"):
        r = f["rect"]
        a, b = r.back_edge()
        cands = sorted(
            ((seg_seg_dist(a, b, w["a"], w["b"]), w) for w in s.solid_walls()),
            key=lambda x: x[0])
        if not cands:
            out.append({"objects": [f["id"]],
                        "detail": "场景中没有实墙，无法判定床头依靠"})
            continue
        best_d, best_w = cands[0]
        tol = PARAMS["GAP_HEAD_WALL"] + 1e-3  # 加 1mm 容差：贴墙判定是浮点比较
        if best_d > tol:
            out.append({
                "objects": [f["id"], best_w["id"]],
                "detail": "床头边距最近实墙 %s m，超过贴墙阈值 %s m"
                          % (round(best_d, 2), PARAMS["GAP_HEAD_WALL"]),
                "measured": round(best_d, 2),
                "wall_id": best_w["id"],
            })
            continue
        # 已贴墙：在贴墙阈值内的候选墙里检查墙段长度（取最长的一段）
        near = [w for d, w in cands if d <= tol]
        longest = max(near, key=lambda w: dist(w["a"], w["b"]))
        wall_len = dist(longest["a"], longest["b"])
        if wall_len < r.wid - 1e-3:
            out.append({
                "objects": [f["id"], longest["id"]],
                "detail": "床头所在墙段仅 %s m，短于床宽 %s m"
                          % (round(wall_len, 2), round(r.wid, 2)),
                "measured": round(wall_len, 2),
                "wall_id": longest["id"],
            })
    return out or None


def r_bed002(s):
    """门冲床：门中心到床 < DIST_DOOR_BED，且门视线锥罩住床，且床头不在该门所在墙段。"""
    out = []
    for f in s.of_type("bed"):
        r = f["rect"]
        for d in s.doors:
            if d["is_entry"]:
                continue
            dd = min(point_seg_dist(d["center"], p, q) for p, q in r.edges())
            if dd >= PARAMS["DIST_DOOR_BED"]:
                continue
            if not cone_hits_rect(d["center"], heading_of(d["normal"]),
                                  PARAMS["ANGLE_DOOR_FAN"], r, PARAMS["DIST_DOOR_BED"]):
                continue
            if not s.los(d["center"], r.c):
                continue
            out.append({
                "objects": [f["id"], d["id"]],
                "detail": "门中心距床 %.2f m（阈值 %.2f m），开门视线锥内可见卧床"
                          % (dd, PARAMS["DIST_DOOR_BED"]),
                "measured": round(dd, 2),
            })
    return out or None


def r_bed003(s):
    """床不对镜：镜面法线指向床（夹角 < 半角），距离 < DIST_MIRROR_BED，视线通畅。"""
    beds = s.of_type("bed")
    if not beds:
        return None
    out = []
    for m in s.of_type("mirror"):
        mr = m["rect"]
        for bed in beds:
            br = bed["rect"]
            dd = mr.dist_to_rect(br)
            if dd > PARAMS["DIST_MIRROR_BED"]:
                continue
            v = sub(br.c, mr.c)
            if angle_between(heading_vec(mr.heading), v) > PARAMS["ANGLE_DOOR_FAN"]:
                continue
            if not s.los(mr.c, br.c):
                continue
            out.append({
                "objects": [m["id"], bed["id"]],
                "detail": "镜面法线与镜→床连线夹角 %.1f°（阈值 %.0f°），距离 %.2f m"
                          % (angle_between(heading_vec(mr.heading), v),
                             PARAMS["ANGLE_DOOR_FAN"], dd),
                "measured": round(dd, 2),
            })
    return out or None


def r_bed004(s):
    """横梁压床：梁的俯视投影带与床矩形相交。

    v1.1 修正：场景 JSON 里没有 beams 字段时返回 SKIP（记入 skipped），
    不再与"确实没有梁"混同为通过。
    """
    beds = s.of_type("bed")
    if not beds:
        return None
    if "beams" not in s.raw:
        return ("SKIP", "场景未提供 beams 字段，横梁压床（FS-BED-004）未能判定")
    if not s.beams:
        return None  # 明确给了空列表 = 确实无梁，正常通过
    out = []
    for bm in s.beams:
        half = bm["width"] / 2.0
        u = norm(sub(bm["b"], bm["a"]))
        n = perp(u)
        # 梁带四角
        band = [add(bm["a"], mul(n, half)), add(bm["b"], mul(n, half)),
                sub(bm["b"], mul(n, half)), sub(bm["a"], mul(n, half))]
        band_edges = [(band[0], band[1]), (band[1], band[2]),
                      (band[2], band[3]), (band[3], band[0])]
        for f in beds:
            r = f["rect"]
            hit = any(seg_intersect(p, q, x, y) for p, q in band_edges for x, y in r.edges())
            if not hit:
                # 床完全在梁带内
                hit = all(abs(dot(sub(c, bm["a"]), n)) <= half for c in r.corners())
            if hit:
                out.append({
                    "objects": [f["id"], bm["id"]],
                    "detail": "床的俯视投影与「%s」梁带重叠（梁宽 %.2f m）"
                              % (bm.get("name") or bm["id"], bm["width"]),
                })
    return out or None


def r_bed005(s):
    """床头不靠窗：床头边贴靠的是窗墙。"""
    out = []
    for f in s.of_type("bed"):
        r = f["rect"]
        a, b = r.back_edge()
        for w in s.walls:
            if not w["is_window"]:
                continue
            if seg_seg_dist(a, b, w["a"], w["b"]) <= PARAMS["GAP_HEAD_WALL"]:
                out.append({
                    "objects": [f["id"], w["id"]],
                    "detail": "床头边贴靠%s" % wall_label(s, w),
                })
    return out or None


def r_bed006(s):
    """床侧通道：两侧长边的外法线方向净空均 < CLEARANCE_BED_SIDE。"""
    out = []
    for f in s.of_type("bed"):
        r = f["rect"]
        h = heading_vec(r.heading)
        out_n = (-h[1], h[0])  # 垂直于床长的方向
        ok, best_side = False, 0.0
        for side in (1, -1):
            n = mul(out_n, side)
            # 长边中点：床中心沿 n 偏移半个床宽
            m = add(r.c, mul(n, r.wid / 2.0))
            gap = clearance_along(s, m, n, max_dist=PARAMS["CLEARANCE_SEARCH"],
                                  skip=(f["id"],))
            best_side = max(best_side, gap)
            if gap >= PARAMS["CLEARANCE_BED_SIDE"]:
                ok = True
                break
        if not ok:
            out.append({
                "objects": [f["id"]],
                "detail": "床两侧外沿净空分别为 %.2f m 以内，均不足 %.2f m"
                          "（人因参考：床边走道 ≥ 0.76 m）"
                          % (min(best_side, PARAMS["CLEARANCE_BED_SIDE"]),
                             PARAMS["CLEARANCE_BED_SIDE"]),
            })
    return out or None


def r_ent001(s):
    """大门对卫生间门：两门法线近似相反、距离 < DIST_DOOR_DOOR、视线通畅。"""
    e = s.entry()
    if not e:
        return None
    out = []
    for d in s.doors:
        if d["id"] == e["id"]:
            continue
        if not _is_toilet_door(d):
            continue
        dd = dist(e["center"], d["center"])
        if dd >= PARAMS["DIST_DOOR_DOOR"]:
            continue
        ang = angle_between(e["normal"], d["normal"])
        if ang < PARAMS["ANGLE_BACK_TO_BACK"]:
            continue
        if not s.los(e["center"], d["center"]):
            continue
        out.append({
            "objects": [e["id"], d["id"]],
            "detail": "入户门与卫生间门相对，中心距 %.2f m（阈值 %.2f m），两门法线夹角 %.0f°"
                      % (dd, PARAMS["DIST_DOOR_DOOR"], ang),
            "measured": round(dd, 2),
        })
    return out or None


def _is_toilet_door(d):
    """识别卫生间门：优先显式 room_type 字段，降级到名称/ID 关键词。"""
    rt = str(d.get("room_type", "")).lower()
    if rt:
        return rt in ("toilet", "bath", "bathroom", "wc")
    return ("卫" in d["name"] or "toilet" in d["id"].lower()
            or "bath" in d["id"].lower())


def _is_kitchen_door(d):
    """识别厨房门：优先显式 room_type 字段，降级到名称/ID 关键词。"""
    rt = str(d.get("room_type", "")).lower()
    if rt:
        return rt in ("kitchen", "kit")
    return "厨" in d["name"] or "kit" in d["id"].lower()


def r_ent002(s):
    """开门见灶：入户门视线锥内命中灶台，距离 < DIST_ENTRY_STOVE，视线通畅。"""
    e = s.entry()
    if not e:
        return None
    out = []
    for st in s.of_type("stove"):
        r = st["rect"]
        dd = min(point_seg_dist(e["center"], p, q) for p, q in r.edges())
        if dd >= PARAMS["DIST_ENTRY_STOVE"]:
            continue
        if not cone_hits_rect(e["center"], heading_of(e["normal"]),
                              PARAMS["ANGLE_DOOR_FAN"], r, PARAMS["DIST_ENTRY_STOVE"]):
            continue
        if not s.los(e["center"], r.c):
            continue
        out.append({
            "objects": [e["id"], st["id"]],
            "detail": "入户门视线锥（±%.0f°）内可见灶台，距离 %.2f m"
                      % (PARAMS["ANGLE_DOOR_FAN"], dd),
            "measured": round(dd, 2),
        })
    return out or None


def r_ent003(s):
    """穿堂煞：入户门法线与「门→窗」连线近似共线，且视线通畅。"""
    e = s.entry()
    if not e:
        return None
    out = []
    for w in s.walls:
        if not w["is_window"]:
            continue
        c = ((w["a"][0] + w["b"][0]) / 2.0, (w["a"][1] + w["b"][1]) / 2.0)
        v = sub(c, e["center"])
        if length(v) < 0.5:
            continue
        if angle_between(heading_vec(heading_of(e["normal"])), v) > PARAMS["ANGLE_ALIGNED"]:
            continue
        if not s.los(e["center"], c):
            continue
        out.append({
            "objects": [e["id"], w["id"]],
            "detail": "入户门正对窗洞「%s」，夹角 %.1f°（阈值 %.0f°），视线无遮挡"
                      % (w["id"], angle_between(heading_vec(heading_of(e["normal"])), v),
                         PARAMS["ANGLE_ALIGNED"]),
        })
    return out or None


def r_gen001(s):
    """内门对冲：任意两扇内门，各自法线指向对方，距离 < DIST_DOOR_DOOR，视线通畅。"""
    inner = [d for d in s.doors if not d["is_entry"]]
    out = []
    for i in range(len(inner)):
        for j in range(i + 1, len(inner)):
            a, b = inner[i], inner[j]
            dd = dist(a["center"], b["center"])
            if dd >= PARAMS["DIST_DOOR_DOOR"]:
                continue
            va, vb = sub(b["center"], a["center"]), sub(a["center"], b["center"])
            if angle_between(a["normal"], va) > PARAMS["ANGLE_DOOR_FAN"]:
                continue
            if angle_between(b["normal"], vb) > PARAMS["ANGLE_DOOR_FAN"]:
                continue
            if not s.los(a["center"], b["center"]):
                continue
            out.append({
                "objects": [a["id"], b["id"]],
                "detail": "两扇内门相对且视线贯通，中心距 %.2f m" % dd,
                "measured": round(dd, 2),
            })
    return out or None


def r_gen002(s):
    """镜面对大门：镜面法线锥命中入户门，距离 < DIST_DOOR_DOOR，视线通畅。"""
    e = s.entry()
    if not e:
        return None
    out = []
    for m in s.of_type("mirror"):
        mr = m["rect"]
        dd = dist(mr.c, e["center"])
        if dd >= PARAMS["DIST_DOOR_DOOR"]:
            continue
        v = sub(e["center"], mr.c)
        if angle_between(heading_vec(mr.heading), v) > PARAMS["ANGLE_DOOR_FAN"]:
            continue
        if not s.los(mr.c, e["center"]):
            continue
        out.append({
            "objects": [m["id"], e["id"]],
            "detail": "镜面法线指向入户门（夹角 %.1f°），距离 %.2f m"
                      % (angle_between(heading_vec(mr.heading), v), dd),
            "measured": round(dd, 2),
        })
    return out or None


def r_gen003(s):
    """主通道净宽：门内 0.5m 处，垂直门向的左右净空之和 < DIST_CORRIDOR_MIN。

    只测「门口通道」而不做全屋寻路，是因为门口净宽才是真正卡人的地方；
    全屋寻路受家具布局路径选择影响大，容易给出无法解释的结论。
    """
    worst = None
    for d in s.doors:
        p = add(d["center"], mul(d["normal"], 0.5))
        side = (-d["normal"][1], d["normal"][0])
        left = clearance_along(s, p, side, max_dist=PARAMS["CLEARANCE_SEARCH"])
        right = clearance_along(s, p, mul(side, -1.0), max_dist=PARAMS["CLEARANCE_SEARCH"])
        width = left + right
        if worst is None or width < worst[0]:
            worst = (width, d)
    if worst and worst[0] < PARAMS["DIST_CORRIDOR_MIN"]:
        d = worst[1]
        return [{
            "objects": [d["id"]],
            "detail": "「%s」门内通道净宽约 %.2f m（阈值 %.2f m；GB 55038-2025 要求"
                      "通往卧室/起居室 ≥ 1.00 m、通往厨卫 ≥ 0.90 m）"
                      % (d["name"], worst[0], PARAMS["DIST_CORRIDOR_MIN"]),
            "measured": round(worst[0], 2),
        }]
    return None


def r_gen004(s):
    """窗前遮光：高于 HEIGHT_BLOCK_WIN 的家具进入窗前 BAND_WINDOW 深度带。

    v1.1 修正：窗的内法线方向不再用硬编码坐标判断，改为指向
    场景内部参考点（房间中心均值，缺房间时用墙包围盒中心）。
    """
    if not s.walls:
        return None
    inside = s.interior_center()
    if inside is None:
        return ("SKIP", "场景没有任何墙体数据，窗前遮光（FS-GEN-004）无法确定内侧方向")
    out = []
    for w in s.walls:
        if not w["is_window"]:
            continue
        u = norm(sub(w["b"], w["a"]))
        n = perp(u)
        mid = ((w["a"][0] + w["b"][0]) / 2.0, (w["a"][1] + w["b"][1]) / 2.0)
        if dot(sub(inside, mid), n) < 0:
            n = mul(n, -1.0)
        x1, x2 = add(w["a"], mul(n, PARAMS["BAND_WINDOW"])), \
            add(w["b"], mul(n, PARAMS["BAND_WINDOW"]))
        band = [w["a"], w["b"], x2, x1]
        band_edges = [(band[0], band[1]), (band[1], band[2]),
                      (band[2], band[3]), (band[3], band[0])]
        for f in s.furn:
            if f["height"] < PARAMS["HEIGHT_BLOCK_WIN"]:
                continue
            r = f["rect"]
            if any(seg_intersect(p, q, x, y) for p, q in band_edges for x, y in r.edges()):
                out.append({
                    "objects": [f["id"], w["id"]],
                    "detail": "高 %.2f m 的「%s」位于窗前 %.2f m 采光带内"
                              % (f["height"], f["name"], PARAMS["BAND_WINDOW"]),
                })
    return out or None


def r_kit001(s):
    """水火不相冲：灶台与水槽间距 < GAP_STOVE_SINK。"""
    out = []
    for st in s.of_type("stove"):
        for sk in s.of_type("sink"):
            dd = st["rect"].dist_to_rect(sk["rect"])
            if dd < PARAMS["GAP_STOVE_SINK"]:
                out.append({
                    "objects": [st["id"], sk["id"]],
                    "detail": "灶台与水槽最小间距 %.2f m，低于 %.2f m"
                              % (dd, PARAMS["GAP_STOVE_SINK"]),
                    "measured": round(dd, 2),
                })
    return out or None


def r_kit002(s):
    """灶台背门：灶台与同侧门距离 < DIST_STOVE_DOOR。"""
    out = []
    for st in s.of_type("stove"):
        r = st["rect"]
        for d in s.doors:
            if d["is_entry"]:
                continue
            dd = min(point_seg_dist(d["center"], p, q) for p, q in r.edges())
            if dd >= PARAMS["DIST_STOVE_DOOR"]:
                continue
            # 门是否在灶台同侧（门法线与「门→灶」同向）
            v = sub(r.c, d["center"])
            if angle_between(d["normal"], v) > PARAMS["ANGLE_SAME_SIDE"]:
                continue
            out.append({
                "objects": [st["id"], d["id"]],
                "detail": "灶台距「%s」仅 %.2f m（阈值 %.2f m），灶后临门"
                          % (d["name"], dd, PARAMS["DIST_STOVE_DOOR"]),
                "measured": round(dd, 2),
            })
    return out or None


def r_kit003(s):
    """灶台正对厨房门：厨房门法线锥命中灶台，距离 < DIST_DOOR_DOOR，视线通畅。"""
    out = []
    for d in s.doors:
        if d["is_entry"] or not _is_kitchen_door(d):
            continue
        for st in s.of_type("stove"):
            r = st["rect"]
            dd = min(point_seg_dist(d["center"], p, q) for p, q in r.edges())
            if dd >= PARAMS["DIST_DOOR_DOOR"]:
                continue
            if not cone_hits_rect(d["center"], heading_of(d["normal"]),
                                  PARAMS["ANGLE_DOOR_FAN"], r, PARAMS["DIST_DOOR_DOOR"]):
                continue
            if not s.los(d["center"], r.c):
                continue
            out.append({
                "objects": [d["id"], st["id"]],
                "detail": "厨房门视线锥内正对灶台，距离 %.2f m" % dd,
                "measured": round(dd, 2),
            })
    return out or None


def r_liv001(s):
    """沙发背后有靠：沙发背边沿法线方向的净空需 <= GAP_SOFA_WALL（墙或高柜皆可）。"""
    out = []
    for f in s.of_type("sofa"):
        r = f["rect"]
        back = r.back_mid()
        n = mul(heading_vec(r.heading), -1.0)  # 背向
        gap = clearance_along(s, back, n, max_dist=1.2, skip=(f["id"],))
        if gap > PARAMS["GAP_SOFA_WALL"]:
            out.append({
                "objects": [f["id"]],
                "detail": "沙发背面净空 %.2f m，超过靠山阈值 %.2f m"
                          % (gap, PARAMS["GAP_SOFA_WALL"]),
                "measured": round(gap, 2),
            })
    return out or None


def r_liv002(s):
    """沙发正对大门：沙发主朝向与「沙发→门」连线夹角 < ANGLE_ALIGNED，距离 < 4.0。"""
    e = s.entry()
    if not e:
        return None
    out = []
    for f in s.of_type("sofa"):
        r = f["rect"]
        dd = dist(r.c, e["center"])
        if dd >= 4.0:
            continue
        v = sub(e["center"], r.c)
        ang = angle_between(heading_vec(r.heading), v)
        if ang < PARAMS["ANGLE_ALIGNED"]:
            out.append({
                "objects": [f["id"], e["id"]],
                "detail": "沙发主朝向正对入户门，夹角 %.1f°，距离 %.2f m" % (ang, dd),
                "measured": round(dd, 2),
            })
    return out or None


# ---------------------------------------------------------------- 规则元数据

RULES = [
    ("FS-BED-001", "床头靠实墙", "bedroom", "high", r_bed001,
     "将 {object_id} 床头旋转至紧邻实墙，贴合 0.05 m 以内。",
     "床头悬空或靠窗。传统居住观念认为床头缺乏实墙依靠则缺乏安全感；环境心理角度，贴实墙入睡的确定感更高。"),
    ("FS-BED-002", "床不对门（门冲床）", "bedroom", "high", r_bed002,
     "旋转床位避开开门视线锥，或加门帘遮挡。",
     "床正对房门，开门视线直及卧床。传统安床忌讳门冲；隐私角度，卧床处于开门视线内影响休息安全感。"),
    ("FS-BED-003", "床不对镜", "bedroom", "medium", r_bed003,
     "调整镜面朝向，或改用衣柜翻门镜。",
     "镜面正对床。传统认为镜对床为忌；现代解释为夜间反光与突发视像易造成惊扰。"),
    ("FS-BED-004", "横梁压床", "bedroom", "high", r_bed004,
     "将床移出梁投影带；无法避开时用吊顶弱化。",
     "床位于横梁投影带内。传统称「横梁压顶」为忌；对应心理压迫感与净高局促。"),
    ("FS-BED-005", "床头不靠窗", "bedroom", "high", r_bed005,
     "床头旋转至紧邻实墙，避开窗墙。",
     "床头贴靠窗墙。窗墙缺乏实体依靠，且温湿度与光线波动大。"),
    ("FS-BED-006", "床侧通道", "bedroom", "low", r_bed006,
     "调整相邻家具，为床侧留出下床通道（建议 ≥ 0.76 m）。",
     "床两侧均无下床通道。人因上影响下床与整理床铺；传统布局观念同样要求「床边有路」。"),
    ("FS-ENT-001", "大门对卫生间门", "entrance", "high", r_ent001,
     "卫生间常闭门，或加设玄关隔断/门帘。",
     "大门直对卫生间门。传统认为秽气之门与大门相对为忌；环境心理角度，开门即见卫生间也影响来访观感与私密感。"),
    ("FS-ENT-002", "开门见灶", "entrance", "medium", r_ent002,
     "在入口与灶台之间增加隔断，或调整橱柜使灶台移出视线锥。",
     "入门视线直达灶台。通行阳宅口诀「开门见灶，钱财多耗」；居住体验上，来客视线直及烹饪区影响操作私密性。"),
    ("FS-ENT-003", "穿堂煞（大门直对阳台/大窗）", "entrance", "medium", r_ent003,
     "入门处增加玄关柜/屏风，可在门内 1.2–1.8 m 处生成鞋柜。",
     "大门与阳台/大窗直通。传统称「穿心杀」，认为气流直进直出、不聚；建筑环境角度对应通风短路、私密性差。"),
    ("FS-GEN-001", "内门对冲（门对门）", "general", "medium", r_gen001,
     "错位开门或加隔断；装修期可考虑改门位。",
     "内门两两相对。传统有「三门莫相对」之说；对应视线贯通与私密性干扰。"),
    ("FS-GEN-002", "镜面对大门", "general", "medium", r_gen002,
     "玄关镜侧移，或改为不直对大门的角度。",
     "玄关镜正对大门。传统忌镜冲门；对应入门眩光与惊扰。"),
    ("FS-GEN-003", "主通道净宽", "general", "medium", r_gen003,
     "移出或收窄侵占通道的家具，保证主通道净宽 ≥ 0.90 m。",
     "主通道净宽不足。GB 55038-2025 要求通往卧室/起居室过道净宽 ≥ 1.00 m、通往厨卫 ≥ 0.90 m。"),
    ("FS-GEN-004", "窗前遮光", "general", "low", r_gen004,
     "高家具移离窗前，采光面留空。",
     "高家具遮挡窗前采光面。传统讲「明堂开阔、纳气」；现代对应日照与采光质量下降。"),
    ("FS-KIT-001", "灶台-水槽间距过近（「水火不相冲」几何转译）", "kitchen", "high", r_kit001,
     "拉开灶台与水槽间距至 ≥ 0.60 m，或中间插入操作台。",
     "灶台与水槽间距过近。传统有「水火不相冲」之说；操作安全上，油溅遇水、动线交叉也确实不利。"),
    ("FS-KIT-002", "灶台背门", "kitchen", "medium", r_kit002,
     "灶台沿台面移离门侧 ≥ 0.90 m。",
     "灶台紧邻门侧，背后有人走动。传统忌灶后无靠/临门；对应安全与操作干扰。"),
    ("FS-KIT-003", "灶台正对厨房门", "kitchen", "low", r_kit003,
     "调整灶台或门向错开。",
     "厨房门视线直对灶台，为「开门见灶」的室内变体（内门暴露度较低，故降级）。"),
    ("FS-LIV-001", "沙发背后有靠", "living", "medium", r_liv001,
     "沙发移靠实墙，或背后加矮柜/书架作为人造靠山。",
     "沙发背后无实墙依靠。传统称「背后有靠」；环境心理学上背后无遮挡的座位安全感较低。"),
    ("FS-LIV-002", "沙发正对大门", "living", "low", r_liv002,
     "沙发朝向偏转 ≥ 30° 或错位摆放。",
     "沙发正对大门，入户视线与气流直冲座位区。传统忌大门直冲座位；对应隐私与干扰。"),
]


# ---------------------------------------------------------------- 主流程

def wall_label(s, w):
    """把墙 ID 变成「北墙 / 南窗 / 隔墙」这类用户看得懂的名字。"""
    a, b = w["a"], w["b"]
    horizontal = abs(a[1] - b[1]) < 1e-6
    ys = [p[1] for p in (a, b)]
    xs = [p[0] for p in (a, b)]
    all_ys = [p[1] for ww in s.walls for p in (ww["a"], ww["b"])]
    all_xs = [p[0] for ww in s.walls for p in (ww["a"], ww["b"])]
    kind = "窗" if w["is_window"] else "墙"
    if horizontal:
        if abs(max(ys) - max(all_ys)) < 1e-6:
            return "北" + kind
        if abs(min(ys) - min(all_ys)) < 1e-6:
            return "南" + kind
        return "东西向隔" + kind
    if abs(max(xs) - max(all_xs)) < 1e-6:
        return "东" + kind
    if abs(min(xs) - min(all_xs)) < 1e-6:
        return "西" + kind
    return "南北向隔" + kind


def _fill(template, labels):
    """把 {object_id} / {wall_id} 替换成用户看得懂的中文名。

    这一步放在 L1 而不是 L3，是因为 L3 只应该做「语气与结构」，
    不该再做对象名映射——否则每换一个表达层都要重新对一遍 ID。
    """
    if not template:
        return template
    out = template
    if labels:
        out = out.replace("{object_id}", labels[0])
    if len(labels) > 1:
        out = out.replace("{wall_id}", labels[1])
    return out


def _label_of(s, o):
    for f in s.furn:
        if f["id"] == o:
            return f["name"]
    for d in s.doors:
        if d["id"] == o:
            return d["name"]
    for w in s.walls:
        if w["id"] == o:
            return wall_label(s, w)
    for b in s.beams:
        if b["id"] == o:
            return b.get("name") or o
    return ""


def run(scene_path, only=None, include_low=True, culture=False):
    data = json.loads(Path(scene_path).read_text(encoding="utf-8"))
    s = Scene(data)
    violations, passed, skipped, warnings = [], [], [], []

    # 隐式假设显式化：入口门退化要提醒，不能静默
    if s.doors and not s.has_entry_marked():
        warnings.append(
            "场景未标注 is_entry，已默认以第一扇门「%s」作为入户门参与判定。"
            % s.doors[0]["name"])

    for rid, name, cat, sev, fn, suggestion, vtext in RULES:
        if only and rid not in only:
            continue
        if not include_low and sev == "low":
            continue
        try:
            res = fn(s)
        except Exception as e:  # 缺字段等情况如实记录，不静默通过
            skipped.append({"rule_id": rid, "name": name,
                            "reason": "%s: %s" % (type(e).__name__, e)})
            continue
        if isinstance(res, tuple) and len(res) == 2 and res[0] == "SKIP":
            # 显式跳过：数据缺失，绝不能与"通过"混淆
            skipped.append({"rule_id": rid, "name": name, "reason": res[1]})
            continue
        if res is None:
            passed.append({"rule_id": rid, "name": name})
            continue
        items = res if isinstance(res, list) else [res]  # 多实例违规
        for res_i in items:
            objs = res_i.get("objects", [])
            label = [_label_of(s, o) or o for o in objs]
            violations.append({
                "rule_id": rid,
                "name": name,
                "category": cat,
                "severity": sev,
                "objects": objs,
                "object_labels": label,
                "violation_text": vtext,
                "suggestion": _fill(suggestion, label),
                "detail": res_i.get("detail", ""),
                "measured": res_i.get("measured"),
            })

    violations.sort(key=lambda v: (SEVERITY_ORDER.get(v["severity"], 9), v["rule_id"]))
    counts = {"high": 0, "medium": 0, "low": 0}
    for v in violations:
        counts[v["severity"]] = counts.get(v["severity"], 0) + 1

    # 文化参考层：与 violations 完全隔离，不参与上面的任何计数。
    if culture:
        culture_ref = minggua.check_owner(data.get("meta", {}).get("owner"), s)
    else:
        culture_ref = {
            "enabled": False,
            "reason": "文化参考模块未启用（默认关闭，加 --culture 开启）。",
        }

    return {
        "scene": data.get("meta", {}).get("name", Path(scene_path).name),
        "rule_version": "v1.1",
        "rule_count": len([r for r in RULES if not only or r[0] in only]),
        "summary": {
            "violations": len(violations),
            "by_severity": counts,
            "passed": len(passed),
            "skipped": len(skipped),
        },
        "violations": violations,
        "passed_rules": passed,
        "skipped": skipped,
        "warnings": warnings,
        "culture_reference": culture_ref,
    }


def to_md(r):
    L = []
    L.append("# 风水布局审查结果 · %s" % r["scene"])
    L.append("")
    s = r["summary"]
    L.append("共检查 %d 条规则：**%d 条需要调整**（高 %d / 中 %d / 低 %d），%d 条通过%s。"
             % (r["rule_count"], s["violations"], s["by_severity"].get("high", 0),
                s["by_severity"].get("medium", 0), s["by_severity"].get("low", 0),
                s["passed"],
                "，%d 条因数据缺失未能判定" % s["skipped"] if s["skipped"] else ""))
    L.append("")
    for wmsg in r.get("warnings", []):
        L.append("> ⚠️ %s" % wmsg)
        L.append("")
    if not r["violations"]:
        L.append("未发现需要调整的布局。")
    for v in r["violations"]:
        mark = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(v["severity"], "•")
        L.append("## %s %s %s" % (mark, v["rule_id"], v["name"]))
        L.append("")
        L.append("- **现状**：%s" % (v["detail"] or v["violation_text"]))
        L.append("- **建议**：%s" % v["suggestion"])
        L.append("")
    if r["skipped"]:
        L.append("## 未能判定")
        L.append("")
        for k in r["skipped"]:
            L.append("- %s %s：%s" % (k["rule_id"], k["name"], k["reason"]))

    # 文化参考单独成段，与上面的空间判定用分隔线隔开。
    c = r.get("culture_reference") or {}
    if c.get("enabled") and c.get("available"):
        L.append("")
        L.append("---")
        L.append("")
        L.append("> 以下为文化参考，与上方空间判定无关，不参与检查计数。")
        L.append("")
        L.append("## 文化参考 · 八宅派命卦")
        L.append("")
        L.append(c["text"])
        L.append("")
        L.append("- 命卦：%s（%s）" % (c["ming_gua"]["name"], c["ming_gua"]["group"]))
        L.append("- 宅向：坐%s朝%s（%s宅，%s）"
                 % (c["house"]["sitting"], c["house"]["facing"],
                    c["house"]["gua"], c["house"]["group"]))
        if c["owner"].get("note"):
            L.append("- 说明：%s" % c["owner"]["note"])
        L.append("")
        L.append("<details><summary>本段局限</summary>")
        L.append("")
        for x in c["limits"]:
            L.append("- %s" % x)
        L.append("")
        L.append("</details>")
    elif c.get("enabled"):
        L.append("")
        L.append("## 文化参考 · 未生成")
        L.append("")
        L.append("原因：%s" % c.get("reason", "未知"))
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="风水审查 L1 几何判定引擎")
    ap.add_argument("--scene", help="场景 JSON 路径")
    ap.add_argument("--out", help="输出文件路径（默认打印到 stdout）")
    ap.add_argument("--format", default="json", choices=["json", "md"], help="输出格式")
    ap.add_argument("--only", help="只跑指定规则，逗号分隔，如 FS-BED-001,FS-KIT-001")
    ap.add_argument("--no-low", action="store_true", help="跳过 low 严重度规则")
    ap.add_argument("--culture", action="store_true",
                    help="启用八宅派命卦文化参考（独立模块，不进入违规统计，需 meta.owner）")
    ap.add_argument("--list", action="store_true", help="列出全部规则")
    args = ap.parse_args()

    if args.list:
        for rid, name, cat, sev, *_ in RULES:
            print("%-12s %-28s %-9s %s" % (rid, name, cat, sev))
        return 0

    if not args.scene:
        ap.error("需要 --scene 参数（或用 --list 查看规则）")

    only = set(x.strip() for x in args.only.split(",")) if args.only else None
    r = run(args.scene, only=only, include_low=not args.no_low, culture=args.culture)
    text = to_md(r) if args.format == "md" else json.dumps(r, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print("已写入 %s" % args.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
