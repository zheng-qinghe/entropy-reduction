#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
熵减计划 · 模型卡校验器

用法：
    /Users/yushuo/.workbuddy/binaries/python/envs/default/bin/python \
        entropy-reduction/scripts/validate_model_cards.py

退出码 0 = 全部通过；1 = 有失败项。

校验的是「引擎级不变量」—— 任何一张卡违反，L0 抽象就不成立。
阈值（如 min_evidence）可按物种调，这里只查「结构是否齐备、是否自相矛盾」。
"""

import sys
import pathlib

try:
    import yaml
except ImportError:
    print("需要 PyYAML。装法："
          "/Users/yushuo/.workbuddy/binaries/python/envs/default/bin/pip install pyyaml")
    sys.exit(2)

DIMS = [
    "D1_substrate", "D2_temporality", "D3_symbolic", "D4_boundary", "D5_needs",
    "D6_vulnerabilities", "D7_relations", "D8_mortality", "D9_agency",
]

# 伦理通用内核的权威版本在 docs/熵减计划-蓝图.md 第 8 章。
# 所有物种卡必须逐字继承 —— 下面这份是本地冻结副本，卡里必须与之逐字相等。
UNIVERSAL_ETHICS = [
    '不得替当事者定义"好结局"；价值排序必须来自他自己的材料与确认',
    '不得制造对本书的依赖；须明确"这是照一次镜子，不是日常用品"',
    '不得美化创伤；禁止把痛苦写成有意义的必经之路',
    '材料仅本地处理；落盘为特征与短引用，不存原文',
    '出现危机信号时中止生成，输出人类求助资源',
    '每一章的情节必须有 evidence 指针，无证据者标 unverified',
]

GATES = ["evidence_gate", "falsification_gate", "comprehensibility_gate"]
OUT_KEYS = ["recipient", "channel", "deliverable", "human_translation",
            "assert_not_human_language"]
# 归一化容差：权重按两位小数手写，允许 0.005 的浮点误差
TOL = 5e-3


def entropy_id(token):
    """从 'E4 分离焦虑：...' / 'E4_disconnection' 里取出 E 编号。"""
    t = str(token).strip()
    if not t:
        return None
    head = t.replace("_", " ").split(" ")[0].rstrip("：:")
    return head if head.startswith("E") and head[1:].isdigit() else None


def check_card(path, results, universal_ref):
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    name = path.name

    def ck(ok, label, detail=""):
        results.append((path.name, label, bool(ok), detail))

    # 1 九维齐备
    dims = list(d.get("dimensions", {}).keys())
    ck(sorted(dims) == sorted(DIMS), "九维齐备 D1-D9",
       f"缺 {sorted(set(DIMS) - set(dims))} 多 {sorted(set(dims) - set(DIMS))}")

    # 2 熵源权重归一
    pri = d.get("entropy_priors", {})
    total = sum(pri.values())
    ck(abs(total - 1.0) < TOL, "熵源权重合计 = 1.00", f"实际 {total:.4f}")
    ck(len(pri) >= 7, "熵源条目 >= 7", f"实际 {len(pri)}")

    # 3 声明不可用的熵源，权重必须为 0（否则自相矛盾）
    bad = []
    for token in d.get("entropy_unavailable", []) or []:
        eid = entropy_id(token)
        if eid is None:
            bad.append(f"{token}(无法解析)")
            continue
        for k, v in pri.items():
            if entropy_id(k) == eid and abs(v) > TOL:
                bad.append(f"{eid}={v}")
    ck(not bad, "不可用熵源权重必须为 0", ",".join(bad))

    # 4 独有熵源必须有非零权重
    bad = []
    for token in d.get("extra_entropies", []) or []:
        eid = entropy_id(token)
        if eid is None:
            continue
        hit = [v for k, v in pri.items() if entropy_id(k) == eid]
        if hit and abs(sum(hit)) < TOL:
            bad.append(f"{eid}=0")
    ck(not bad, "独有熵源权重应非零", ",".join(bad))

    # 5 伦理双层结构 + 通用内核逐字继承
    eth = d.get("ethics", {}) or {}
    uni = eth.get("universal")
    ck(isinstance(uni, list) and isinstance(eth.get("species_specific"), list),
       "伦理为 universal / species_specific 双层")
    if isinstance(uni, list):
        ck(len(uni) == 6, "通用伦理 6 条", f"实际 {len(uni)}")
        diff = [x for x in uni if x not in UNIVERSAL_ETHICS]
        ck(not diff, "通用伦理逐字继承权威版本",
           ";".join(x[:16] for x in diff))
        if universal_ref[0] is None:
            universal_ref[0] = list(uni)
        else:
            ck(list(uni) == universal_ref[0], "跨卡通用伦理一致")
    ck(len(eth.get("species_specific", []) or []) >= 2, "物种特有伦理 >= 2 条")

    # 6 诊断三道门（引擎级不变量：门不可删，阈值可调）
    g = d.get("diagnosis_gates", {}) or {}
    ck(all(k in g for k in GATES), "诊断三道门齐备",
       f"缺 {[k for k in GATES if k not in g]}")

    # 7 输出层：这是本轮新增的核心字段
    out = d.get("output", {}) or {}
    missing = [k for k in OUT_KEYS if k not in out]
    ck(not missing, "output 五字段齐备", f"缺 {missing}")
    if "recipient" in out and "human_translation" in out:
        no_recv = "没有接收者" in str(out["recipient"]) or out["recipient"] is None
        flagged = out.get("assert_not_human_language") is True
        # 边界案例必须显式声明无接收者，且不得用人类语言交付
        ck(not (no_recv and not flagged),
           "无接收者时必须 assert_not_human_language = true")
    ck("channel" in out and str(out.get("channel", "")).strip() != "",
       "output.channel 非空")

    # 8 叙事禁令（禁忌比形状重要）
    nar = d.get("narrative", {}) or {}
    ck(bool(nar.get("forbidden_endings")), "narrative.forbidden_endings 非空")
    ck("modality" in nar, "narrative.modality 已声明")

    # 9 采样接口
    ck(bool(d.get("sampling")), "sampling 已声明")
    ck(bool(d.get("entropy_couplings")), "entropy_couplings 已声明（处方要打在上游）")

    # 10 元信息
    ck(bool(d.get("being_id")) and bool(d.get("status")), "being_id / status 齐备")
    ck(bool(d.get("fault")), "fault 断层已声明")


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    cards = sorted((root / "model-cards").glob("*.yaml"))
    if not cards:
        print("未找到模型卡")
        return 1

    print(f"校验 {len(cards)} 张模型卡 —— {root / 'model-cards'}\n")
    results = []
    universal_ref = [None]
    seen_ids = {}
    for p in cards:
        check_card(p, results, universal_ref)
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        seen_ids.setdefault(d.get("being_id"), []).append(p.name)

    dup = {k: v for k, v in seen_ids.items() if len(v) > 1}
    for k, v in dup.items():
        results.append((v[0], f"being_id 唯一（{k}）", False, "重复：" + ",".join(v)))

    fails = [r for r in results if not r[2]]
    for fname, label, ok, detail in results:
        if not ok:
            print(f"  FAIL  {fname:26s} {label}" + (f"  → {detail}" if detail else ""))

    print(f"\n共 {len(results)} 项断言：{len(results) - len(fails)} 通过 / {len(fails)} 失败")
    if not fails:
        print("全部通过。L0 抽象在结构上是自洽的。")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
