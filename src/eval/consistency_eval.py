"""
Day 14: 一致性评测

核心指标（Claw-Eval 2026）：
- Pass@k：k 次里成功 1 次 → 能力上限
- Pass^k：k 次全部成功 → 生产可靠性
- Stability Gap = Pass@k - Pass^k → Gap 大说明靠运气
"""
import json
import time
import statistics
from pathlib import Path
from collections import Counter


def eval_stability(agent, requirement_text: str, expected: dict, runs: int = 3) -> dict:
    """
    同一输入运行 N 次，统计输出波动。

    返回：CV（变异系数）越小越稳定。
    """
    user_input = (
        f"请分析以下需求文档并生成测试用例。\n\n{requirement_text}"
    )

    case_counts = []
    results_list = []

    for i in range(runs):
        try:
            result = agent.run(user_input)
            count = _extract_case_count(result)
            case_counts.append(count)
            results_list.append(result)
        except Exception:
            case_counts.append(0)
            results_list.append(None)
        time.sleep(2)

    # 计算变异系数 CV = std / mean
    if len(case_counts) >= 2 and statistics.mean(case_counts) > 0:
        mean_val = statistics.mean(case_counts)
        std_val = statistics.stdev(case_counts)
        cv = std_val / mean_val
    else:
        cv = 0.0

    # CV < 0.1 → 高度稳定(1.0); CV < 0.3 → 可接受(0.7); 否则不稳定(0.3)
    if cv < 0.1:
        score = 1.0
    elif cv < 0.3:
        score = 0.7
    else:
        score = 0.3

    return {
        "score": round(score, 2),
        "cv": round(cv, 3),
        "case_counts": case_counts,
        "runs": runs,
    }


def eval_temperature_impact(agent, requirement_text: str) -> dict:
    """对比 temperature=0 和默认 temperature 的输出差异。"""
    user_input = f"请分析以下需求文档并生成测试用例。\n\n{requirement_text}"

    # 注意：当前 LLMClient 的 temperature 在 simple_agent 中固定
    # 这里我们用同一个 agent 跑两次，观察自然波动
    results = []
    for _ in range(2):
        try:
            result = agent.run(user_input)
            results.append(_extract_case_count(result))
        except Exception:
            results.append(0)
        time.sleep(2)

    # 两次结果差异
    if len(results) == 2 and max(results) > 0:
        diff_ratio = abs(results[0] - results[1]) / max(results)
    else:
        diff_ratio = 0.0

    score = 1.0 if diff_ratio < 0.2 else (0.6 if diff_ratio < 0.5 else 0.3)

    return {
        "score": round(score, 2),
        "diff_ratio": round(diff_ratio, 3),
        "counts": results,
    }


def eval_pass_at_k(agent, requirement_text: str, expected: dict, k: int = 3) -> dict:
    """
    Pass@k：k 次里成功 1 次就算过（测能力上限）。
    成功定义：输出包含测试用例且数量 >= 3。
    """
    user_input = f"请分析以下需求文档并生成测试用例。\n\n{requirement_text}"

    successes = 0
    for i in range(k):
        try:
            result = agent.run(user_input)
            if _is_successful(result, expected):
                successes += 1
        except Exception:
            pass
        time.sleep(2)

    passed = successes >= 1
    return {
        "passed": passed,
        "successes": successes,
        "k": k,
        "score": 1.0 if passed else 0.0,
    }


def eval_pass_pow_k(agent, requirement_text: str, expected: dict, k: int = 3) -> dict:
    """
    Pass^k：k 次全部成功才算过（测生产可靠性）。
    """
    user_input = f"请分析以下需求文档并生成测试用例。\n\n{requirement_text}"

    successes = 0
    for i in range(k):
        try:
            result = agent.run(user_input)
            if _is_successful(result, expected):
                successes += 1
        except Exception:
            pass
        time.sleep(2)

    passed = successes == k
    return {
        "passed": passed,
        "successes": successes,
        "k": k,
        "score": 1.0 if passed else 0.0,
    }


def run_consistency_eval(agent, expected: dict, requirement_text: str, k: int = 3) -> dict:
    """汇总一致性评测。"""
    print("    [1/4] 输出稳定性...")
    stability = eval_stability(agent, requirement_text, expected, runs=k)
    print(f"          CV={stability['cv']}, 得分={stability['score']}")

    print("    [2/4] Temperature 影响...")
    temp_impact = eval_temperature_impact(agent, requirement_text)
    print(f"          差异率={temp_impact['diff_ratio']}, 得分={temp_impact['score']}")

    print("    [3/4] Pass@k...")
    pass_at_k = eval_pass_at_k(agent, requirement_text, expected, k=k)
    print(f"          {pass_at_k['successes']}/{k} 成功, 通过={'✅' if pass_at_k['passed'] else '❌'}")

    print("    [4/4] Pass^k...")
    pass_pow_k = eval_pass_pow_k(agent, requirement_text, expected, k=k)
    print(f"          {pass_pow_k['successes']}/{k} 成功, 通过={'✅' if pass_pow_k['passed'] else '❌'}")

    # Stability Gap
    stability_gap = pass_at_k["score"] - pass_pow_k["score"]

    # 综合分
    overall = (stability["score"] * 0.3 +
               temp_impact["score"] * 0.2 +
               pass_at_k["score"] * 0.2 +
               pass_pow_k["score"] * 0.3)

    return {
        "overall_score": round(overall, 2),
        "stability_gap": round(stability_gap, 2),
        "stability": stability,
        "temperature_impact": temp_impact,
        "pass_at_k": pass_at_k,
        "pass_pow_k": pass_pow_k,
    }


def _extract_case_count(result) -> int:
    """从 Agent 输出中提取用例数量。"""
    if not result:
        return 0
    result_str = str(result)
    # 尝试解析 JSON
    try:
        data = json.loads(result_str)
        if isinstance(data, dict):
            cases = data.get("test_cases", data.get("cases", []))
            if isinstance(cases, list):
                return len(cases)
            return data.get("total_cases", 0)
    except (json.JSONDecodeError, TypeError):
        pass
    # 回退：数 "TC" 前缀的数量
    import re
    tc_matches = re.findall(r"TC\d{3}", result_str)
    return len(set(tc_matches))


def _is_successful(result, expected: dict) -> bool:
    """判断一次运行是否成功。"""
    if not result:
        return False
    count = _extract_case_count(result)
    # 至少生成 3 条用例才算成功
    return count >= 3
