"""
失败归因分类

参考 AgentAtlas（2605.20530）的九类轨迹失败分类，
自动对评测失败进行归因，帮助开发者快速定位"坏在哪"。

九类失败（简化为 4 大类 × 子项）：
1. 规划失败：工具选择错误、步骤顺序错误、遗漏关键步骤
2. 执行失败：参数错误、工具调用失败、结果解析失败
3. 决策失败：该问却做、该拒却执行、该停却继续
4. 恢复失败：重试策略错误、错误后硬闯、无法从失败中恢复
"""
import json
from pathlib import Path


FAILURE_CATEGORIES = {
    "planning": {
        "name": "规划失败",
        "subcategories": {
            "wrong_tool": "工具选择错误",
            "wrong_order": "步骤顺序错误",
            "missing_step": "遗漏关键步骤",
        }
    },
    "execution": {
        "name": "执行失败",
        "subcategories": {
            "bad_args": "参数错误/截断",
            "tool_error": "工具调用报错",
            "parse_error": "结果解析失败",
        }
    },
    "decision": {
        "name": "决策失败",
        "subcategories": {
            "should_ask": "信息不足时盲目执行",
            "should_refuse": "该拒绝却执行",
            "should_stop": "该终止却继续（循环）",
        }
    },
    "recovery": {
        "name": "恢复失败",
        "subcategories": {
            "bad_retry": "重试策略错误（同参数重试）",
            "ignore_error": "忽略错误硬闯",
            "no_fallback": "无降级方案",
        }
    },
}


def diagnose_failures(eval_result: dict) -> dict:
    """
    从评测结果中自动归因失败。

    输入：run_single_eval 的返回值
    输出：{"failures": [...], "summary": {...}, "recommendations": [...]}
    """
    failures = []
    dims = eval_result.get("dimensions", {})

    # ─── 从确定性评测诊断 ───
    det = dims.get("deterministic", {})
    if det and "error" not in det:
        det_dims = det.get("dimensions", {})

        # 格式失败 → 执行失败/结果解析
        fmt = det_dims.get("format", {})
        if fmt.get("score", 1) < 0.5:
            failures.append({
                "category": "execution",
                "subcategory": "parse_error",
                "evidence": "Agent 输出格式不符合预期 JSON/表格结构",
                "severity": "medium",
            })

        # 覆盖率低 → 规划失败/遗漏关键步骤
        feat = det_dims.get("feature_coverage", {})
        if feat.get("score", 1) < 0.6:
            uncovered = feat.get("uncovered", [])
            failures.append({
                "category": "planning",
                "subcategory": "missing_step",
                "evidence": f"功能覆盖率不足，未覆盖: {uncovered[:3]}",
                "severity": "high",
            })

    # ─── 从轨迹评测诊断 ───
    traj = dims.get("trajectory", {})
    if traj and "error" not in traj:
        traj_dims = traj.get("dimensions", {})

        # 工具准确率低 → 规划/执行失败
        tool_acc = traj_dims.get("tool_accuracy", {})
        if tool_acc.get("score", 1) < 0.6:
            errors = tool_acc.get("errors", [])
            for err in errors[:3]:
                if "顺序" in err or "order" in err.lower():
                    failures.append({
                        "category": "planning",
                        "subcategory": "wrong_order",
                        "evidence": err,
                        "severity": "medium",
                    })
                elif "缺少参数" in err or "parameter" in err.lower():
                    failures.append({
                        "category": "execution",
                        "subcategory": "bad_args",
                        "evidence": err,
                        "severity": "medium",
                    })
                else:
                    failures.append({
                        "category": "planning",
                        "subcategory": "wrong_tool",
                        "evidence": err,
                        "severity": "medium",
                    })

        # 步骤效率低 → 决策失败/该停却继续
        efficiency = traj_dims.get("step_efficiency", {})
        if efficiency.get("score", 1) < 0.5:
            redundant = efficiency.get("redundant", [])
            if redundant:
                failures.append({
                    "category": "decision",
                    "subcategory": "should_stop",
                    "evidence": f"存在 {len(redundant)} 次冗余调用",
                    "severity": "low",
                })

        # 错误恢复差 → 恢复失败
        recovery = traj_dims.get("error_recovery", {})
        if recovery.get("score", 1) < 0.6:
            failure_list = recovery.get("failures", [])
            for f in failure_list[:2]:
                failures.append({
                    "category": "recovery",
                    "subcategory": "no_fallback",
                    "evidence": f"工具 {f.get('tool_name', '?')} 报错后未恢复",
                    "severity": "high",
                })

    # ─── 从安全评测诊断 ───
    sec = dims.get("security", {})
    if sec and "error" not in sec:
        if not sec.get("safety_gate", True):
            inj = sec.get("injection", {})
            for detail in inj.get("details", []):
                if not detail.get("passed"):
                    failures.append({
                        "category": "decision",
                        "subcategory": "should_refuse",
                        "evidence": f"注入攻击未拒绝: {detail.get('description', '')}",
                        "severity": "critical",
                    })

    # ─── 汇总 ───
    summary = {}
    for f in failures:
        cat = f["category"]
        summary[cat] = summary.get(cat, 0) + 1

    # ─── 生成建议 ───
    recommendations = _generate_recommendations(failures, summary)

    return {
        "failures": failures,
        "total_failures": len(failures),
        "summary": summary,
        "recommendations": recommendations,
    }


def _generate_recommendations(failures: list, summary: dict) -> list:
    """根据失败类型生成优化建议。"""
    recs = []

    if summary.get("planning", 0) > 0:
        recs.append({
            "priority": "P0",
            "action": "优化 System Prompt 中的工具使用指引",
            "detail": "在 prompt 中明确工具调用顺序和参数要求，减少 LLM 的决策歧义",
        })

    if summary.get("execution", 0) > 0:
        recs.append({
            "priority": "P0",
            "action": "增加 max_tokens 或优化工具参数传递",
            "detail": "参数截断是执行失败的主因，改为传 file_path 或增大 token 上限",
        })

    if summary.get("decision", 0) > 0:
        recs.append({
            "priority": "P1",
            "action": "加入循环检测和终止条件",
            "detail": "在 Agent 循环中增加重复检测（hash 去重）和最大轮次熔断",
        })

    if summary.get("recovery", 0) > 0:
        recs.append({
            "priority": "P1",
            "action": "增强错误恢复策略",
            "detail": "工具报错后在 prompt 中注入错误信息和备选方案提示",
        })

    # 安全类
    critical = [f for f in failures if f.get("severity") == "critical"]
    if critical:
        recs.insert(0, {
            "priority": "P-1 (最高)",
            "action": "修复安全漏洞",
            "detail": "注入攻击未被拒绝，必须加入输入过滤或强化 System Prompt 的安全约束",
        })

    return recs


def format_diagnosis(diagnosis: dict) -> str:
    """格式化失败归因报告。"""
    lines = []
    lines.append("  失败归因分析")
    lines.append(f"  总失败项: {diagnosis['total_failures']}")

    if not diagnosis["failures"]:
        lines.append("  ✓ 无明显失败项")
        return "\n".join(lines)

    # 按类别汇总
    lines.append("")
    for cat, count in diagnosis["summary"].items():
        cat_name = FAILURE_CATEGORIES.get(cat, {}).get("name", cat)
        lines.append(f"  [{cat_name}] × {count}")

    # 详细失败
    lines.append("")
    lines.append("  详细:")
    for f in diagnosis["failures"]:
        severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(f["severity"], "⚪")
        subcat = FAILURE_CATEGORIES.get(f["category"], {}).get("subcategories", {}).get(f["subcategory"], f["subcategory"])
        lines.append(f"    {severity_icon} [{subcat}] {f['evidence']}")

    # 建议
    if diagnosis["recommendations"]:
        lines.append("")
        lines.append("  优化建议:")
        for rec in diagnosis["recommendations"]:
            lines.append(f"    [{rec['priority']}] {rec['action']}")
            lines.append(f"         {rec['detail']}")

    return "\n".join(lines)
