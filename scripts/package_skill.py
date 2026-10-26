#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重新打包 fengshui-audit.skill（可复现构建）。

.skill 是一个 zip 包，内部布局为 fengshui-audit/ 前缀。
每次修改 SKILL.md / scripts / references / assets 后必须重新打包：
    python3 scripts/package_skill.py
打包后自检：解包 → 跑 demo 回归（9 条）→ 与源码 diff 确认无漂移。
"""

import hashlib
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fengshui-audit.skill"
PREFIX = "fengshui-audit"

# 打包清单：与仓库文件一一对应，新增文件要在这里登记
INCLUDE = [
    "SKILL.md",
    "README.md",
    "assets/demo_scene.json",
    "assets/demo_scene_fixed.json",
    "references/evidence.md",
    "references/interview.md",
    "references/minggua.md",
    "references/output-style.md",
    "references/parameters.md",
    "references/rules.md",
    "references/scene-schema.md",
    "scripts/check.py",
    "scripts/minggua.py",
    "scripts/lumanchi.py",
    "scripts/region.py",
    "scripts/package_skill.py",
    "tests/test_check.py",
    "修改日志.md",
]


def build():
    missing = [f for f in INCLUDE if not (ROOT / f).exists()]
    if missing:
        sys.exit("清单中有文件不存在：%s" % missing)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in INCLUDE:
            z.write(ROOT / f, "%s/%s" % (PREFIX, f))
    print("已打包 %s（%d 个文件，%d 字节）"
          % (OUT.name, len(INCLUDE), OUT.stat().st_size))


def verify():
    """解包到临时目录 → 跑 demo 回归 → 校验文件与源码一致。"""
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(OUT) as z:
            z.extractall(td)
        pkg = Path(td) / PREFIX
        r = subprocess.run(
            [sys.executable, str(pkg / "scripts" / "check.py"),
             "--scene", str(pkg / "assets" / "demo_scene.json")],
            capture_output=True, text=True)
        if r.returncode != 0 or '"violations": 9' not in r.stdout:
            sys.exit("自检失败：解包后 demo 回归不等于 9 条\n%s" % r.stdout[-500:])
        # 与源码逐文件比对哈希，防内容漂移
        drift = []
        for f in INCLUDE:
            src = hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
            dst = hashlib.sha256((pkg / f).read_bytes()).hexdigest()
            if src != dst:
                drift.append(f)
        if drift:
            sys.exit("自检失败：包内文件与源码不一致 %s" % drift)
    print("自检通过：demo 回归 9 条，包内 %d 个文件与源码逐字节一致" % len(INCLUDE))


if __name__ == "__main__":
    build()
    verify()
