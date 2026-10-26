"""鲁班尺核查模块（文化参考层，零依赖）。

设计原则：
  - 确定性纯函数：同一尺寸输入永远同一结论。
  - 判定逻辑用「门光尺八等分 + 吉四字」框架，依据 E8《风水探源》p.109：
    门光尺分八个间隔，落在「财、义、官、本」四字为吉；
    1 门光尺 = 42.76 cm（即每格 42.76/8 = 5.345 cm）。
  - 各家门尺刻度与逐格星名释义不一（各家版本差异，🔶 待核 E7 p.137 表 1 图版），
    因此本模块**不内置**逐毫米吉凶口诀表，只输出格位与吉/凶判定。

引用规范：说「按通行门光尺约定」，不要报「鲁班经明载」。
"""

import json
import sys

# 门光尺一周 42.76 cm，八等分（E8 p.109 ✅）
MENGUANG_CM = 42.76
CELL_CM = MENGUANG_CM / 8.0

# 八格字序（通行版本：财病离义官劫害本；E8 p.109 印证吉四字）
CELLS = ["财", "病", "离", "义", "官", "劫", "害", "本"]
LUCKY_CELLS = {"财", "义", "官", "本"}

CAVEAT = (
    "门光尺各家版本刻度与星名释义不一，本工具采用通行八格字序与吉四字约定"
    "（据《风水探源》p.109，核对状态 ✅）；逐格星名释义为二手整理（🔶），仅供参考。"
)

LIMITS = [
    "各家门尺（鲁班尺/门光尺）刻度划分存在版本差异，本模块只做格位判定，不核对商用量尺刻印。",
    "逐格星名释义（如「财至」「宝库」等）为通行口诀，属二手转引，未核到原书图版。",
    "本模块为文化参考，不参与 18 条空间判定，不构成施工尺寸的强制要求。",
    "施工尺寸仍应以建筑规范（如门窗洞口模数）与人体工程学为准。",
]


def cell_index(width_cm):
    """宽度落在门光尺第几格（0-7）。周长循环，超一周取模。"""
    return int(width_cm // CELL_CM) % 8


def check(width_mm):
    """输入毫米，返回格位判定 dict。

    返回字段：
      width_mm       原始输入
      cell           格位字（财/病/离/义/官/劫/害/本）
      lucky          是否吉格
      cell_cm        该格起点厘米数
      nearest_lucky  最近吉格边界（mm，含负值=需缩短）；已在吉格时为 None
      delta_mm       距最近吉格的调整量
    """
    cm = width_mm / 10.0
    idx = cell_index(cm)
    cell = CELLS[idx]
    lucky = cell in LUCKY_CELLS
    out = {
        "width_mm": width_mm,
        "cell": cell,
        "lucky": lucky,
        "cell_cm": round(cm // CELL_CM * CELL_CM, 2),
        "nearest_lucky": None,
        "delta_mm": 0,
    }
    if lucky:
        return out
    # 找最近吉格边界：在 ±(一周) 范围内枚举边界，取调整量最小者
    best = None
    for k in range(-1, 9):
        boundary_cm = (int(cm // CELL_CM) + k) * CELL_CM
        target_cm = boundary_cm + CELL_CM / 2.0  # 落到格中央最稳
        if cell_index(target_cm) not in [CELLS.index(c) for c in LUCKY_CELLS]:
            continue
        delta = round((target_cm - cm) * 10)
        if best is None or abs(delta) < abs(best[1]):
            best = (round(target_cm * 10), delta)
    if best:
        out["nearest_lucky"] = best[0]
        out["delta_mm"] = best[1]
    return out


def main():
    ap = __import__("argparse").ArgumentParser(description="鲁班尺（门光尺）核查 · 文化参考")
    ap.add_argument("sizes", nargs="+", type=int, help="尺寸（毫米），可多个")
    args = ap.parse_args()
    results = [check(s) for s in args.sizes]
    print(json.dumps({"tool": "lumanchi", "results": results,
                      "caveat": CAVEAT, "limits": LIMITS},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
