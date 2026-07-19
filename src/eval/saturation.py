"""
评测饱和度检测

Anthropic 最佳实践：
"100% 通过率的评估只能跟踪回归，无法驱动改进。需持续增加更难的任务。"

本模块检测评测集是否已经"饱和"（Agent 全通过了），
如果饱和则提示需要扩充更有挑战性的样本。

参考：LiveAgentBench 的 SPDG 流程 — 评测集动态刷新
"""
import json
from datetime import datetime
from pathlib import Path

HISTORY_PATH = Path("data/eval/saturation_history.json")


def check_saturation(report: dict, threshold: float = 0.90) -> dict:
    """
    检测评测集是否饱和。

    逻辑：
    - 如果所有样本的综合分 > threshold → 评测集饱和
    - 如果某个维度所有样本满分 → 该维度饱和
    - 连续 3 次评测分数不再提升 → 能力可能到顶

    返回：
    - {"saturated": bool, "saturated_dimensions": [...], "recommendations": [...]}
    """
    results = report.get("results", [])
    if not results:
        return {"saturated": False, "saturated_dimensions": [], "recommendations": []}

    # 检查整体饱和
    valid_results = [r for r in results if "error" not in r or "dimensions" in r]
    if not valid_results:
        return {"saturated": False, "saturated_dimensions": [], "recommendations": []}

    scores = []
    for r in valid_results:
        dims = r.get("dimensions", {})
        det = dims.get("deterministic", {})
        scores.append(det.get("overall_score", 0))

    avg_score = sum(scores) / len(scores) if scores else 0
    all_pass = all(s >= threshold for s in scores)

    # 检查各维度饱和
    saturated_dims = []
    dim_names = ["deterministic", "trajectory"]
    for dim_name in dim_names:
        dim_scores = []
        for r in valid_results:
            dims = r.get("dimensions", {})
            d = dims.get(dim_name, {})
            if d and "error" not in d:
                dim_scores.append(d.get("overall_score", 0))
        if dim_scores and all(s >= threshold for s in dim_scores):
            saturated_dims.append(dim_name)

    # 生成建议
    recommendations = []
    if all_pass:
        recommendations.append({
            "type": "overall_saturation",
            "message": f"所有样本综合分 ≥ {threshold:.0%}，评测集已饱和",
            "action": "扩充更有挑战性的需求文档（如多模块耦合、模糊需求、矛盾需求）",
        })

    for dim in saturated_dims:
        dim_display = {"deterministic": "确定性", "trajectory": "轨迹"}.get(dim, dim)
        recommendations.append({
            "type": "dimension_saturation",
            "message": f"{dim_display}评测所有样本满分",
            "action": f"增加针对 {dim_display} 维度的更难样本或提高通过阈值",
        })

    if not recommendations:
        recommendations.append({
            "type": "healthy",
            "message": "评测集尚未饱和，仍能有效驱动改进",
            "action": "继续使用当前评测集",
        })

    # 记录历史（用于趋势分析）
    _record_history(avg_score, len(valid_results))

    return {
        "saturated": all_pass,
        "avg_score": round(avg_score, 3),
        "sample_count": len(valid_results),
        "saturated_dimensions": saturated_dims,
        "recommendations": recommendations,
    }


def _record_history(avg_score: float, sample_count: int):
    """记录每次评测的分数到历史，用于趋势分析。"""
    history = []
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)

    history.append({
        "timestamp": datetime.now().isoformat(),
        "avg_score": round(avg_score, 3),
        "sample_count": sample_count,
    })

    # 只保留最近 50 次
    history = history[-50:]

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def check_plateau(n_recent: int = 3) -> dict:
    """
    检查是否进入"平台期"（连续 N 次分数不再提升）。

    返回：{"plateau": bool, "recent_scores": [...], "trend": "rising"|"flat"|"declining"}
    """
    if not HISTORY_PATH.exists():
        return {"plateau": False, "recent_scores": [], "trend": "unknown"}

    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        history = json.load(f)

    if len(history) < n_recent:
        return {"plateau": False, "recent_scores": [], "trend": "insufficient_data"}

    recent = history[-n_recent:]
    recent_scores = [r["avg_score"] for r in recent]

    # 判断趋势
    diffs = [recent_scores[i+1] - recent_scores[i] for i in range(len(recent_scores)-1)]
    avg_diff = sum(diffs) / len(diffs) if diffs else 0

    if avg_diff > 0.02:
        trend = "rising"
    elif avg_diff < -0.02:
        trend = "declining"
    else:
        trend = "flat"

    plateau = trend == "flat" and all(s > 0.85 for s in recent_scores)

    return {
        "plateau": plateau,
        "recent_scores": recent_scores,
        "trend": trend,
        "avg_diff": round(avg_diff, 4),
    }


def format_saturation_report(saturation: dict, plateau: dict) -> str:
    """格式化饱和度报告。"""
    lines = []
    lines.append("  评测饱和度检测")
    lines.append(f"  ├─ 样本数: {saturation.get('sample_count', 0)}")
    lines.append(f"  ├─ 平均分: {saturation.get('avg_score', 0):.3f}")
    lines.append(f"  ├─ 整体饱和: {'⚠️ 是' if saturation.get('saturated') else '✓ 否'}")

    if saturation.get("saturated_dimensions"):
        dims_str = ", ".join(saturation["saturated_dimensions"])
        lines.append(f"  ├─ 饱和维度: {dims_str}")

    if plateau.get("trend") != "unknown":
        trend_icon = {"rising": "📈", "flat": "➡️", "declining": "📉"}.get(plateau["trend"], "?")
        lines.append(f"  ├─ 趋势: {trend_icon} {plateau['trend']}")
        if plateau.get("plateau"):
            lines.append(f"  │   ⚠️ 已进入平台期，建议扩充评测集")

    for rec in saturation.get("recommendations", []):
        icon = "⚠️" if rec["type"] != "healthy" else "✓"
        lines.append(f"  └─ {icon} {rec['message']}")
        lines.append(f"       → {rec['action']}")

    return "\n".join(lines)
