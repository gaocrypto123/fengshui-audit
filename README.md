# 风水审查 Skill（fengshui-audit）

家居布局的风水审查 Skill：把 18 条形法条目**转译成可几何判定的规则**，输入一份 2D 户型 JSON，输出结构化的违规清单与调整建议。

属于 **ImmerseHome** 项目（毛坯房 AR 沉浸式家居系统）的审查模块。

## 它解决的问题

传统风水条目的表述是"床头不宜靠窗""开门见灶，钱财多耗"这类**定性描述**，机器判不了、设计师也没法照着改。本项目做的是把每条条目拆成三样可执行的东西：

| 层 | 职责 | 产物 |
|---|---|---|
| L1 规则引擎 | 几何判定，输出"哪条规则、命中哪些对象、实测值多少" | `scripts/check.py` |
| L2 知识层 | 规则库覆盖不到时的解释与兜底（RAG） | 提示词，接入侧实现 |
| L3 表达层 | 把违规 JSON 转成分级语气的用户话术 | `references/output-style.md` |

## 快速开始

无需安装依赖，Python 3.9+ 标准库即可运行。

```bash
# 自检：demo 埋了 9 处问题，应命中 9 条
python scripts/check.py --scene assets/demo_scene.json --format md

# 复检：这些问题改完后应只剩 1 条
python scripts/check.py --scene assets/demo_scene_fixed.json --format md

# 列出全部规则
python scripts/check.py --list

# JSON 输出（供上层程序消费）
python scripts/check.py --scene assets/demo_scene.json
```

**改动任何阈值或判定逻辑后，必须跑上面这一对场景。** 数字从 9/1 变了，说明改过头了。

剩下那条无法消除的是「入户门正对卫生间门」——建筑门位问题，挪家具解决不了。这是有意保留的：引擎会如实说"这条得改门"，不会假装一键搞定。

## 目录结构

```
SKILL.md                     主文件：工作流、三条红线、已知局限
scripts/check.py             L1 判定引擎，18 条规则全实现，零依赖
references/
  ├── rules.md               18 条规则手册（判定/阈值/建议/依据）
  ├── evidence.md            出处证据链，按核对状态三级标注
  ├── parameters.md          参数表 + 国标对照
  ├── output-style.md        L3 表达层（语气分级 / 长短版 / 语言红线）
  ├── scene-schema.md        输入格式说明
  └── interview.md           访谈执行手册（用于校准 severity）
assets/
  ├── demo_scene.json        埋了 9 处典型问题
  └── demo_scene_fixed.json  调整后仅剩 1 条
```

## 输入格式

一份 JSON 描述户型：墙体（区分实墙/窗墙）、门（含入户门朝向）、房间、家具（旋转矩形：中心、长、宽、朝向）、梁。完整字段见 `references/scene-schema.md`。

```json
{
  "rect": { "cx": 1.6, "cy": 2.4, "len": 0.9, "wid": 2.2, "heading": 0 }
}
```

注意语义：`len` 沿 `heading` 方向（**进深**），`wid` 为垂直方向（**面宽**）。沙发这类家具填反不会报错，但形状会横过来。

## 出处与可信度

`references/evidence.md` 按核对状态分三级标注，**不做美化**：

- ✅ 已核到原书具体页码
- ⚠️ 有书但页码待补
- 🔶 二手转引，原始出处待核

当前 18 条中，5 条页码待补，《阳宅三要》《鲁班经》两条属二手转引。这是已知缺口，不是遗漏——被问到时应当如实回答"这条还没核到原书"，而不是含糊带过。

## 关于"转译"的说明

部分条目原文讲的是**方位**，实现时转成了**几何关系**。典型例子是「厨灶必须居左位，不宜安在白虎方」：原典的"左/白虎方"是相对坐向的方位概念，本项目转译为"灶与水槽的操作间距"，并保留双属性标注 `ergonomic+culture`。

**这是几何可判定转译，不是直译。** 引用时须说明这层关系，否则容易被指为曲解原典。

## 已知局限

详见 `SKILL.md`。其中最需要留意的一条：`DIST_CORRIDOR_MIN = 0.80 m` 低于 GB 55038-2025 的强制值 0.90 m，两者尚未对齐。

## 许可

课程作业产出，未定许可。引用原典内容请自行核对纸质书页码。
