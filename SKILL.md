---
name: fengshui-audit
description: 审查住宅户型与家具布局，基于二维结构化数据检查床、门、窗、灶台、沙发等空间关系，输出确定性的调整建议。适用于户型审查、家具摆放与风水文化参考；个人命卦仅在用户明确要求时启用。
---

# 风水审查

把"风水禁忌"翻译成可几何判定的空间规则，跑一遍，给出能落地的调整建议。

这套东西的价值不在"算命"，在于**很多传统禁忌恰好与人因约束、国家规范重合**。
所以判完之后既说文化维度，也给国标依据——这是让产品站得住脚的关键。

## 三层分工

| 层 | 做什么 | 在哪 |
|---|---|---|
| **L1 判定** | 纯几何计算，21 条规则出违规清单，并按施工工序组织成交底卡。不做解释，不说人话 | `scripts/check.py` |
| **L2 知识** | 每条规则的依据、阈值来源、文献出处 | `references/rules.md`、`evidence.md`、`parameters.md` |
| **文化参考层** | 鲁班尺核查（`scripts/lumanchi.py`）、地域五行（`scripts/region.py`）、命卦+四吉方（`scripts/minggua.py`）——均默认/按需关闭，只做文化陈述，不进违规 | 随 `--culture` 或独立 CLI 调用 |
| **L3 表达** | 语气分级、长短版、语言红线 | `references/output-style.md` |

判定必须是确定性的：同一套数据跑两次结果必须一样。解释可以发挥，结论不能。

## 工作流

### 1. 拿到户型数据

需要的是一份俯视平面 JSON：墙、门、梁、家具矩形、房间。格式见 `references/scene-schema.md`。

手上有的是图片、还是设计软件导出的数据、还是只有口头描述？

- **已有结构化数据** → 直接映射到 schema
- **只有户型图** → 结合图读出墙/门坐标，按 schema 手写（一个 80 m² 户型约 40 行 JSON）
- **只有文字描述** → 先把描述落成 JSON 再判定。不要跳过这步直接"凭感觉说风水"，
  那样结论无法复现，也说不清依据

不确定某个字段怎么填时，看 `assets/demo_scene.json` —— 它是完整可跑的样板。

图片或文字不能证明的尺寸、朝向、梁位不得猜成确定事实。先列出不确定字段，向用户确认影响结论的尺寸；未知集合省略，只有确认不存在才填空数组。估算结果必须说明依据，不能称为实测或合规认证。

### 2. 跑判定

```bash
python scripts/check.py --scene <你的场景.json>                # JSON 结果
python scripts/check.py --scene <场景.json> --format md        # 人读的报告
python scripts/check.py --scene <场景.json> --only FS-BED-001,FS-KIT-001   # 只跑指定规则
python scripts/check.py --list                                 # 列出 21 条规则
```

先跑 `assets/demo_scene.json` 验证环境正常——它埋了 9 处问题，应命中 9 条。
跑出来不是 9 条，说明脚本被改过或数据格式对不上。

`assets/demo_scene_fixed.json` 是同一套户型的"调整后"版本，应只剩 1 条
（入户门对卫生间门，这是建筑门位问题，家具层面改不掉）。两个文件对比着跑，
就是「提示 → 调整 → 复检」的完整闭环，演示和自测都用这一对。

### 3. 读结果

输出里三个数组，**三个都要向用户交代**：

- `violations` —— 需要调整的，已按严重度排序
- `passed_rules` —— 通过的
- `skipped` —— **因数据缺失没判成的**

`skipped` 最容易出事。用户会默认"没报问题 = 没问题"，而实际是"压根没检查"。
必须明说：「另有 N 项因缺少梁数据未能检查」。

`object_labels` 已经是对用户友好的名字（「次卧床」「北墙」），
`suggestion` 里的占位符也已替换好，直接用。

### 4. 组织输出

严格按 `references/output-style.md`：severity 决定语气，四段式卡片，长短两版。

用户问"凭什么"时再去 `references/evidence.md` 查出处的**核对状态**——
标 ⚠️ 的只能说"该书有载"，不能报页码；标 🔶 的必须说明是二手转引。

## 三条不能破的线

**不做吉凶断言。** 不说「大凶」「破财」「影响运势」。规则库的 `violation_text`
已经是「传统观念认为……；从环境心理/国标角度看……」的双解释写法，照抄，别加强。

**不承诺功效。** 风水在这里是文化参考 + 空间约束，不是"调完就顺"的功能承诺。

**跳过不等于通过。** 见上。

## v1.2 新增

- **规则 18 → 20**：FS-KIT-004（灶台邻近卫生间门）、FS-BED-007（卫生间门冲床），均属水电阶段硬约束。
- **交底卡**：输出新增 `handover_cards`，按动工前/水电/泥木/竣工四阶段组织，每条带验收标准。
- **鲁班尺模块**：门光尺八格 + 吉四字（财义官本），依据 E8 p.109（✅）；逐格星名释义 🔶 待核。
- **地域模块**：省份/大区 → 方位五行 → 色彩/意象提示（只到色彩层，实体化建议一律降级）；依据 E7 p.134（✅）+ p.115（⚠️），推演段标 🔶。**不做地域排名、不做迁居建议、不实施财位类内容（两书核对 0 命中）。**
- **命卦四吉方**：查 E7 p.96 大游年表（✅），只做方位陈述，不生成布局建议。

## v1.3 新增：证据链、复检与阈值国标化（首批核心规则）

针对床头、门床关系、厨房关系 8 条核心规则 + 通道/门宽类 3 条，把「原页 → 主张 → 阈值 → 判定 → 建议 → 复检」链路落到机器可读数据：

- `references/rule-chain.json`：每条登记主张文本、候选出处（candidate_unverified）、阈值来源（四层标注：national_standard / book_ergonomics_referenced / project_convention / geometry_consistency，见 threshold_source_legend）、适用条件与复检验收标准。
- `reasoning.attach_chains(result)`：给 violations / passed_rules / skipped 中的核心规则项附加 `chain` 字段（含 citation_status）。判定结果本身不变。
- `reasoning.compare_results(baseline, current)`：复检对比，输出 resolved / remaining / new 与 skipped 变化；同规则对象组合变化保守计为「一解决一新增」，不假装知道是修好了。网站端为 `POST /api/recheck`。
- `references/classic-disagreements.json` + `reasoning.conflicts_for(rule_id)`：经典流派分歧按登记表**并列呈现**（如床位吉方的八宅与玄空两派说法），每方标注出处状态（secondary_unverified = 二手通行说法未核原书），不裁决、不调和出新规则。conflict_detection 状态为 `registry_based_listing`——按登记表呈现已实现，**自动发现登记表之外的新冲突仍未实现**。
- `scripts/evaluate.py` + `POST /api/evaluate-options`：候选布局方案**全量复检**——每个方案在完整规则集上重跑，输出复检违规数、与基线对比的 resolved/remaining/new，按复检结果排序；用户需求（needs）原样透传、只用于在可行方案之间选择，不豁免复检。

**阈值来源升级（v1.3 后期）**：能对上国标的阈值从 project_convention 升为 national_standard 并携带条文级证据引用（reference_id → evidence-registry 已核验条目，含条文号/页码/书籍 SHA-256 指纹）：

- 新增 **FS-GEN-005 门通行净宽分级**（规则 20 → 21，claim_type=regulatory）：户门 ≥0.90 / 卧室门 ≥0.80 / 厨卫门 ≥0.70，直接采用 GB 55038-2025 4.1.14（已核验 DB-GB38-004）。门必须显式声明 width，任一门缺失整条记 skipped。
- FS-GEN-003 主通道净宽 0.90：来源升级为 GB 55038-2025 4.1.13（DB-GB38-003），档位取舍如实标注（项目取最低档，复检按实际用途档）。
- FS-BED-006 床侧通道 0.60：项目自定值，标注已核参考值（解剖书 MIN.450 / 人机 914，双档报告）。
- FS-KIT-002 灶-门距离 0.90：与 GB 50096 5.3.5 设备净距**数值巧合但语义不同**，已显式标注不得冒充引用。
- 隔离红线不变：国标依据只声明阈值出处，**不提升风水主张的 citation_status**；
  regulatory 规则不挂风水主张（claims 无对应条目），测试固化见 tests/test_reasoning.py ThresholdSourceTests。

边界不变：citation_status 为 unverified 时仍不得生成原书引文或精确页码；chain 里的主张候选出处只是逐页核对的方向，不是已核实证据。

## 可选的第四层：文化参考（默认关闭）

`scripts/minggua.py` 按**八宅派**约定，用出生年份算居住者命卦，再与宅向比对。

**它不在 21 条判定里，也不该往里挤。** 结果只出现在输出的 `culture_reference` 字段：
不进入 `violations`、不计入 severity 统计、不生成任何改动建议。

```bash
python scripts/check.py --scene scene.json --culture
```

启用条件：场景 `meta.owner` 里有 `birth_year` 和 `gender`；缺了就如实说缺什么。

为什么单独拎出来——这 21 条每条都能用国标或人体工程学撑起第二条腿，命卦撑不起来。
掺进判定层，被问"这不就是算命吗"的时候，前面 21 条的论证会被一起拖下水。
分开摆，反而能主动说："我们区分了可验证的空间约束与不可验证的文化解释。"

算法表、流派局限、5 黄寄宫处理见 `references/minggua.md`。
出处状态：🔶 **二手转引，原书未核**，引用时只说"据八宅派通行说法"，不要报书名页码。

## 文件导航

| 文件 | 什么时候读 |
|---|---|
| `references/rules.md` | 要解释某条规则、或用户问"为什么这条算问题" |
| `references/parameters.md` | 要调阈值、或用户质疑判定松紧 |
| `references/evidence.md` | 用户问出处、或需要应对"这是不是迷信"的质疑 |
| `references/output-style.md` | 每次组织输出前 |
| `references/scene-schema.md` | 要把数据转成输入格式 |
| `references/interview.md` | 要给 severity 找真实用户依据（访谈用） |
| `references/minggua.md` | 用户要求结合生辰八字、或问命卦怎么算 |
| `scripts/lumanchi.py` | 用户报门窗/家具尺寸要查鲁班尺吉凶（`python scripts/lumanchi.py 810 880`）|
| `scripts/region.py` | 用户提供省份/大区要地域文化参考（输出仅色彩/意象层）|
| `references/rule-chain.json` | 需要向用户解释核心规则的依据链、阈值来源或复检标准时 |
| `assets/demo_scene.json` | 自检 / 演示：埋了 9 处问题，应命中 9 条 |
| `assets/demo_scene_fixed.json` | 闭环演示：把 demo 的问题逐项改掉后的结果，应只剩 1 条 |

## 已知局限

这些要主动说，别等被问：

1. **阈值多数是初始假设**，不是从文献量出来的。`DIST_CORRIDOR_MIN = 0.90 m`
   已对齐 GB 55038-2025 的通厨卫强制下限，但通卧室/起居室的通道国标要求 1.00–1.10 m，
   本规则不区分去向——见 `parameters.md`。
2. **只支持矩形家具**。L 形沙发、转角柜需要拆成多个矩形。
3. **二维俯视**，不看层高（除"高家具遮光"用一维高度）。复式、错层判不了。
4. **部分出处仅核到书、未核到具体页码**，《阳宅三要》《鲁班经》是二手转引。`evidence.md` 里标了状态。
5. **严重度未经访谈验证**，目前是团队讨论稿的判断。
6. **命卦模块没有原书依据**。八宅派命卦配宅说通常归于《八宅明镜》，本仓库未收录该书，
   算法依据是通行命卦表（🔶 二手整理）。而且八宅只是流派之一，三合、玄空的判法不同。
   所以它被放在判定层之外，且默认关闭。

局限说清楚，比假装完备更可信——尤其这是要拿去答辩的东西。

## 网站集成

使用 `scripts/check.py` 的 `run_data(scene_dict)` 直接计算，不需要写临时文件；原来的 `run(path)` 与 CLI 保持可用。输入错误抛出 ValueError，接入侧应返回可读的输入错误。`summary.violations` 是问题实例数，`summary.violated_rules` 是命中规则数；后者加 passed 与 skipped 等于本次 rule_count。关闭 low 后 rule_count 只计实际选择的规则。

法规与人因依据须分别核对；几何阈值命中不自动等于违反国家标准，不应将全部文化条目统称为强制规范。


## 引用与推理边界（本地增强）
默认仅形法空间关系，其他体系必须主动启用且分开呈现。读取返回值 reasoning：rule_evidence 未 verified 的，不得生成书籍原话、精确页码或“原书证明”的说法。references/evidence.md 为历史核对记录，不等于本次原页复核。
每条机器引用须在 evidence-registry.json 中登记书籍指纹、版本、PDF物理页、印刷页、摘录、支持的具体主张、直接/间接关系和核对人。项目阈值必须标项目参数，不得冒充古籍原文。
review_order 仅为解释顺序；当前不支持自动判断经典冲突。遇分歧先区分前提与流派；相同前提下仍冲突时并列呈现，不能自行折中生成新规则。候选改法必须在同一输入版本上全量复检；未复检不得声称改善。
