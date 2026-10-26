"""地域文化参考模块（文化参考层，零依赖，默认关闭）。

设计原则：
  - 独立于 18 条几何判定：结果只进 culture_reference.region，
    不进 violations、不参与 severity、不生成改动建议。
  - 输出只到**色彩/意象层**；任何实体化建议（水景、石材、木质吊顶等）
    一律降级为意象提示并附安全提示（安全闸门）。
  - 不做地域风水排名，不做迁居/选址建议。

依据分层：
  - 方位—五行配属：E7《风水理论研究》p.134 五行四方四灵图（✅ 已人工核）
  - 五行—五色联系：E7 p.115 转《管氏地理指蒙》引文（⚠️ 转引）+ E7 p.373 社稷坛五色土实例（✅）
  - 气候代理列：现代体感补充，**不标注传统依据**
  - 「气候 → 室内调和方向」为文化推演（🔶），非原文直译
"""

import sys

# 省份/直辖市/自治区 → 大区（简化映射，港澳台按华南处理）
PROVINCE_TO_REGION = {
    "广东": "华南", "广西": "华南", "海南": "华南", "香港": "华南", "澳门": "华南",
    "北京": "华北", "天津": "华北", "河北": "华北", "山西": "华北", "内蒙古": "华北",
    "上海": "华东", "江苏": "华东", "浙江": "华东", "安徽": "华东", "福建": "华东",
    "江西": "华东", "山东": "华东", "台湾": "华东",
    "陕西": "西北", "甘肃": "西北", "宁夏": "西北", "青海": "西北", "新疆": "西北",
    "重庆": "西南", "四川": "西南", "云南": "西南", "贵州": "西南", "西藏": "西南",
    "湖北": "华中", "湖南": "华中", "河南": "华中",
}

# 大区查表：方位/五行/气候代理/色彩与意象提示
# 五行侧重仅按「大区主方位」归五行，五土寄中；兼参从简，避免过度声称。
REGION_TABLE = {
    "华南": {
        "direction": "南", "wuxing": "火",
        "climate": "湿热、阳盛（气候代理，现代体感补充）",
        "palette": ["蓝灰", "墨绿", "白"],
        "imagery": ["水意象", "玻璃/陶瓷的冷感意象"],
        "note": "传统五行中南属火；按五行色彩体系，可参考水意象色系作为视觉调和。",
    },
    "华北": {
        "direction": "北", "wuxing": "水",
        "climate": "干冷、风寒（气候代理，现代体感补充）",
        "palette": ["木色", "米色", "暖灰"],
        "imagery": ["木材/织物的暖感质感"],
        "note": "传统五行中北属水；按五行色彩体系，可参考木火暖感色系作为视觉调和。",
    },
    "华东": {
        "direction": "东", "wuxing": "木",
        "climate": "温润、近海（气候代理，现代体感补充）",
        "palette": ["绿色系", "浅木色"],
        "imagery": ["木质色调"],
        "note": "传统五行中东属木；可参考木色与绿色系作为视觉调和。",
    },
    "西北": {
        "direction": "西", "wuxing": "金",
        "climate": "干燥、多风（气候代理，现代体感补充）",
        "palette": ["白", "暖灰"],
        "imagery": ["金属质感/光泽点缀"],
        "note": "传统五行中西属金；可参考白色与金属质感作为视觉调和。",
    },
    "西南": {
        "direction": "西南", "wuxing": "土",
        "climate": "湿润、地形封闭（气候代理，现代体感补充）",
        "palette": ["中性暖灰", "陶土色"],
        "imagery": ["陶瓷/石材的色泽意象"],
        "note": "传统五行中西南属土；可参考陶土色调作为视觉调和。",
    },
    "华中": {
        "direction": "中", "wuxing": "土",
        "climate": "四季分明、湿温（气候代理，现代体感补充）",
        "palette": ["米色", "黄褐"],
        "imagery": ["陶土色泽意象"],
        "note": "传统五行中土寄中央；可参考米色/黄褐色系作为视觉调和。",
    },
}

LIMITS = [
    "证据边界：方位—五行配属据 E7《风水理论研究》p.134 图版（✅）；五行—五色联系据 E7 p.115 转引（⚠️）；「地域气候 → 室内调和方向」为文化推演（🔶），原文（如《素问·异法方宜论》）论述的是地域体质差异，并不直接支撑装修建议。",
    "粒度边界：仅到大区。原典只有五方配属，没有省级五行依据，省级输入一律映射到大区。",
    "本模块只输出色彩与意象层提示；实体构造（水景、天然石材、木质吊顶、大面积金属构件等）不在输出范围内——如需实体化，须另行满足对应国标（石材 GB 6566 A 类、玻璃 JGJ 113、木质装修 GB 50222 等），本模块不给出施工建议。",
    "不做地域风水排名，不做迁居/选址建议。",
    "本段为文化参考，不影响任何一条空间检查结论。",
]


def normalize_region(name):
    """省份/大区名 → 大区名；无法识别返回 None。"""
    if not name:
        return None
    name = str(name).strip()
    if name in REGION_TABLE:
        return name
    return PROVINCE_TO_REGION.get(name)


def check_region(region_input):
    """region_input: 大区名或省份名。返回 culture_reference.region dict。"""
    out = {
        "school": "五行方位配属（通行表述）",
        "enabled": True,
        "available": False,
        "reason": "",
        "region": None,
        "direction": None,
        "wuxing": None,
        "palette": [],
        "imagery": [],
        "text": "",
        "caveat": "本段为文化参考，只涉色彩与视觉意象，不构成施工建议，不影响上方任何检查结论。",
        "limits": LIMITS,
    }
    region = normalize_region(region_input)
    if not region:
        out["reason"] = ("未提供可识别的地域信息（meta.region，支持省份或大区名："
                         + "、".join(REGION_TABLE) + "），跳过地域文化参考。")
        return out
    row = REGION_TABLE[region]
    out.update({
        "available": True,
        "region": region,
        "direction": row["direction"],
        "wuxing": row["wuxing"],
        "palette": row["palette"],
        "imagery": row["imagery"],
        "text": (
            "按传统五行方位配属（图证：《风水理论研究》p.134），%s方位属%s。"
            "结合%s的气候特点（现代体感补充），传统色彩体系上可参考%s等色调与%s的视觉意象。"
            "此为文化参考层的文化推演（🔶），仅限色彩与意象层面。"
            % (row["direction"], row["wuxing"], row["climate"],
               "、".join(row["palette"]), "、".join(row["imagery"]))
        ),
    })
    return out


if __name__ == "__main__":
    import json
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    print(json.dumps(check_region(name), ensure_ascii=False, indent=2))
