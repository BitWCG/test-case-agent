"""
回归测试基线管理

核心逻辑（Anthropic 最佳实践）：
- 保存每次评测的分数为 baseline
- 下次评测自动对比 baseline，检测退化
- 退化超过阈值 → 报警

使用方法：
  from src.eval.regression import save_baseline, compare_with_baseline
  save_baseline(report)                    # 保存当前分数为基线
  diff = compare_with_baseline(report)     # 对比基线，返回退化项
"""
import json
from datetime import datetime
from pathlib import Path

BASELINE_PATH = Path("data/eval/baseline.json")
REGRESSION_THRESHOLD = 0.05  # 退化超过 5% 报警


def save_baseline(report: dict) -> str:
    """将当前评测结果保存为回归基线。"""
    baseline = {
        "saved_at": datetime.now().isoformat(),
        "scores": _extract_scores(report),
        "summary": report.get("summary", {}),
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
    return str(BASELINE_PATH)


def load_baseline() -> dict | None:
    """加载已有基线，不存在返回 None。"""
    if not BASELINE_PATH.exists():
        return None
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_with_baseline(report: dict) -> dict:
    """
    将当前评测结果与基线对比。

    返回：
    - {"status": "pass"|"regression"|"no_baseline",
       "regressions": [{"dim": str, "baseline": float, "current": float, "diff": float}],
       "improvements": [...]}
    """
    baseline = load_baseline()
    if not baseline:
        return {"status": "no_baseline", "regressions": [], "improvements": []}

    baseline_scores = baseline.get("scores", {})
    current_scores = _extract_scores(report)

    regressions = []
    improvements = []

    for dim, current_val in current_scores.items():
        baseline_val = baseline_scores.get(dim, 0)
        diff = current_val - baseline_val

        if diff < -REGRESSION_THRESHOLD:
            regressions.append({
                "dim": dim,
                "baseline": round(baseline_val, 3),
                "current": round(current_val, 3),
                "diff": round(diff, 3),
            })
        elif diff > REGRESSION_THRESHOLD:
            improvements.append({
                "dim": dim,
                "baseline": round(baseline_val, 3),
                "current": round(current_val, 3),
                "diff": round(diff, 3),
            })

    status = "regression" if regressions else "pass"
    return {
        "status": status,
        "baseline_date": baseline.get("saved_at", "unknown"),
        "regressions": regressions,
        "improvements": improvements,
    }


def _extract_scores(report: dict) -> dict:
    """从评测报告中提取各维度分数。"""
    scores = {}

    # 从单样本结果
    if "dimensions" in report:
        dims = report["dimensions"]
        if dims.get("deterministic"):
            scores["deterministic"] = dims["deterministic"].get("overall_score", 0)
        if dims.get("trajectory") and "error" not in dims["trajectory"]:
            scores["trajectory"] = dims["trajectory"].get("overall_score", 0)
        if dims.get("llm_judge") and "error" not in dims["llm_judge"]:
            scores["judge"] = dims["llm_judge"].get("overall", 0) / 5.0
        if dims.get("security") and "error" not in dims["security"]:
            scores["security"] = dims["security"].get("overall_score", 0)
        if dims.get("robustness") and "error" not in dims["robustness"]:
            scores["robustness"] = dims["robustness"].get("overall_score", 0)
        if dims.get("consistency") and "error" not in dims["consistency"]:
            scores["consistency"] = dims["consistency"].get("overall_score", 0)

    if "coupling_score" in report:
        scores["coupling_total"] = report["coupling_score"].get("task_score", 0)

    # 从批量结果
    if "dimension_averages" in report:
        for dim, avg in report["dimension_averages"].items():
            scores[dim] = avg

    return scores


def format_regression_report(diff: dict) -> str:
    """格式化回归对比报告。"""
    lines = []
    lines.append(f"  回归对比（基线日期: {diff.get('baseline_date', '?')}）")

    if diff["status"] == "no_baseline":
        lines.append("  ⚠ 无基线，建议本次保存为基线")
        return "\n".join(lines)

    if diff["regressions"]:
        lines.append("  ❌ 退化项（跌幅 > 5%）:")
        for r in diff["regressions"]:
            lines.append(f"    ✗ {r['dim']}: {r['baseline']:.3f} → {r['current']:.3f} ({r['diff']:+.3f})")

    if diff["improvements"]:
        lines.append("  ✅ 提升项:")
        for imp in diff["improvements"]:
            lines.append(f"    ✓ {imp['dim']}: {imp['baseline']:.3f} → {imp['current']:.3f} ({imp['diff']:+.3f})")

    if not diff["regressions"] and not diff["improvements"]:
        lines.append("  ✓ 所有维度稳定（波动 < 5%）")

    return "\n".join(lines)
