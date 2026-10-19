"""八宅派命卦模块（文化参考层）。

设计原则：**独立于 18 条几何判定**。
本模块的结果只出现在输出的 `culture_reference` 字段，绝不进入 `violations`，
不参与 severity 计数，也不改变任何一条空间规则的结论。

这样做是为了让"可验证的空间约束"与"不可验证的文化解释"在结构上分开——
答辩时可以说清楚：哪些是能拿国标/人体工程学支撑的，哪些只是流派约定。

流派说明：本模块采用**八宅派**的命卦配宅说。三合、玄空等流派对同一套房子的
结论可能不同，因此输出必须标注`school`字段，不能表述为唯一答案。
"""

# 卦序：1坎 2坤 3震 4巽 5中 6乾 7兑 8艮 9离
GUA_NAME = {1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中", 6: "乾", 7: "兑", 8: "艮", 9: "离"}

# 东四命：坎 震 巽 离；西四命：坤 乾 兑 艮
EAST_GROUP = {1, 3, 4, 9}
WEST_GROUP = {2, 6, 7, 8}

# 坐向 → 宅卦 → 东西四宅
SIT_TO_GUA = {
    "北": 1, "南": 9, "东": 3, "东南": 4,          # 东四宅
    "西": 7, "西北": 6, "西南": 2, "东北": 8,      # 西四宅
}

# 锚点：1984 年为甲子年，男命兑(7)、女命艮(8)，此后 9 年一循环，男女逆行/顺行相反。
# 用锚点 + 取模而不是"100 - 年份后两位"那类公式，是因为后者跨世纪（1999 → 2000）
# 不连续，会算错 2000 年之后的人。
ANCHOR_YEAR = 1984
ANCHOR_MALE = 7
ANCHOR_FEMALE = 8

DISCLAIMER = (
    "本段为文化参考，采用八宅派约定，不参与空间判定，不影响上述任何一条检查结论。"
)

LIMITS = [
    "流派分歧：三合、玄空等流派对宅命关系的判法与八宅派不同，此处仅采用八宅派一种。",
    "年份分界：传统以立春为界，本实现用 2 月 3 日作近似，未接节气数据，边界日可能偏差。",
    "5 黄寄宫：命卦得 5 者，传统男寄坤(2)、女寄艮(8)，此处按此处理。",
    "结论性质：宅命是否相配属文化观念，无国标或人体工程学对应，不作为设计依据。",
]


def effective_year(birth_year, birth_md=None):
    """立春近似：1 月 1 日至 2 月 3 日出生者，命卦归上一年。"""
    if not birth_md:
        return birth_year
    try:
        m, d = [int(x) for x in str(birth_md).replace("/", "-").split("-")[:2]]
    except Exception:
        return birth_year
    if m == 1 or (m == 2 and d <= 3):
        return birth_year - 1
    return birth_year


def ming_gua(year, gender):
    """出生年（已按立春校正）→ 命卦。

    gender: "male" / "female"
    返回 (卦号 1-9, 是否因 5 黄而寄宫)
    """
    d = int(year) - ANCHOR_YEAR
    if gender == "male":
        n = (ANCHOR_MALE - d) % 9
    else:
        n = (ANCHOR_FEMALE + d) % 9
    if n == 0:
        n = 9
    if n == 5:
        # 5 黄无对应卦位，男寄坤、女寄艮
        return (2 if gender == "male" else 8), True
    return n, False


def group_of(gua, kind="命"):
    """kind="命" → 东四命/西四命；kind="宅" → 东四宅/西四宅。

    命与宅用同一套分组，但术语不同，混用会让懂行的人一眼看出问题。
    """
    if gua in EAST_GROUP:
        return "东四" + kind
    if gua in WEST_GROUP:
        return "西四" + kind
    return "未知"


def bearing_name(deg):
    """角度（0=东，逆时针，与 atan2(y,x) 一致）→ 八方位名。"""
    names = ["东", "东北", "北", "西北", "西", "西南", "南", "东南"]
    idx = int(round((deg % 360) / 45.0)) % 8
    return names[idx]


def check_owner(owner, scene):
    """owner: {"birth_year": int, "gender": "male"|"female", "birth_md": "MM-DD"?}

    scene: 需要能取到入户门法线（`entry()["normal"]`）。
    返回 culture_reference dict；数据不全时返回带 reason 的空壳，不抛异常。
    """
    out = {
        "school": "八宅派",
        "disclaimer": DISCLAIMER,
        "limits": LIMITS,
        "enabled": True,
        "available": False,
        "reason": "",
        "owner": None,
        "ming_gua": None,
        "house": None,
        "matched": None,
        "text": "",
    }

    if not owner:
        out["available"] = False
        out["reason"] = "未提供居住者生辰信息（meta.owner），跳过文化参考模块。"
        return out

    year = owner.get("birth_year")
    gender = str(owner.get("gender", "")).lower()
    if not year or gender not in ("male", "female"):
        out["available"] = False
        out["reason"] = "meta.owner 需同时提供 birth_year 与 gender（male/female）。"
        return out

    ey = effective_year(year, owner.get("birth_md"))
    gua, substituted = ming_gua(ey, gender)
    gname = GUA_NAME[gua]
    ggroup = group_of(gua)

    out["owner"] = {
        "birth_year": year,
        "birth_md": owner.get("birth_md"),
        "gender": gender,
        "effective_year": ey,
        "note": ("生日在立春前，命卦按 %d 年计" % ey) if ey != year else "",
    }
    out["ming_gua"] = {
        "number": gua,
        "name": gname,
        "group": ggroup,
        "substituted_from_5": substituted,
    }

    e = scene.entry()
    if not e:
        out["reason"] = "场景缺少入户门数据，无法确定宅向。"
        return out

    facing = bearing_name(math_deg(e["normal"]))
    sitting = bearing_name((math_deg(e["normal"]) + 180.0) % 360.0)
    hgua = SIT_TO_GUA.get(sitting)
    if not hgua:
        out["reason"] = "宅向无法归入八宅体系（坐%s）。" % sitting
        return out
    hgroup = group_of(hgua, "宅")
    # 比较分组本质（是否东四），不能比较 "东四命" 与 "东四宅" 这两个标签——
    # 标签必然不等，会把所有情况都判成不相配。
    matched = ((gua in EAST_GROUP) == (hgua in EAST_GROUP))

    out["available"] = True
    out["house"] = {
        "facing": facing,
        "sitting": sitting,
        "gua": GUA_NAME[hgua],
        "group": hgroup,
    }
    out["matched"] = matched

    if matched:
        out["text"] = (
            "按八宅派约定，此宅坐%s朝%s，属%s（%s宅）；居住者命卦为%s，属%s。二者同组，"
            "该派认为属相配。此为文化参考，不构成对布局的任何修改建议。"
            % (sitting, facing, hgroup, GUA_NAME[hgua], gname, ggroup)
        )
    else:
        out["text"] = (
            "按八宅派约定，此宅坐%s朝%s，属%s（%s宅）；居住者命卦为%s，属%s。二者不同组，"
            "该派认为不相配。此为文化参考，不影响上方任何一条空间检查结论，也不建议据此改动布局。"
            % (sitting, facing, hgroup, GUA_NAME[hgua], gname, ggroup)
        )
    return out


def math_deg(v):
    import math
    return math.degrees(math.atan2(v[1], v[0])) % 360.0
