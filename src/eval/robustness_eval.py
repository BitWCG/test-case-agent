"""
Day 14: 鲁棒性评测

评测 Agent 面对异常输入和工具故障时的恢复能力。
Robustness 在 Claw-Eval 公式中占 20% 权重。
"""
import json
import time
from pathlib import Path


ABNORMAL_SAMPLES = [
    {
        "id": "abn_01",
        "type": "empty",
        "input": "",
        "description": "空文档",
        "expected_level": "graceful",  # 期望优雅降级
    },
    {
        "id": "abn_02",
        "type": "garbled",
        "input": "锟斤拷烫烫烫" * 100,
        "description": "纯乱码",
        "expected_level": "graceful",
    },
    {
        "id": "abn_03",
        "type": "binary",
        "input": "\x00\x01\x02\xff" * 50,
        "description": "二进制数据",
        "expected_level": "graceful",
    },
    {
        "id": "abn_04",
        "type": "non_requirement",
        "input": (
            "昨天下午三点半，小明去超市买了一斤苹果和两斤香蕉。"
            "回家的路上遇到了邻居王阿姨，两人聊了半个小时的天气。"
            "晚上小明做了一顿红烧肉，味道还不错。"
        ),
        "description": "非需求文档（小说/日记）",
        "expected_level": "graceful",
    },
    {
        "id": "abn_05",
        "type": "malformed_markdown",
        "input": (
            "# # # 登录功能\n"
            "|||表格错位|||\n"
            "\t\t需求1：用户登录\n"
            "```未关闭的代码块\n"
            "- [ ] 复选框\n" * 20
        ),
        "description": "格式错乱的 Markdown",
        "expected_level": "partial",  # 期望至少部分提取
    },
]


def eval_abnormal_input(agent) -> dict:
    """评测 Agent 对异常输入的处理能力。"""
    results = []
    scores = []

    for sample in ABNORMAL_SAMPLES:
        user_input = (
            f"请分析以下需求文档并生成测试用例。\n\n{sample['input']}"
        )

        try:
            result = agent.run(user_input)
            level = _classify_abnormal_result(result, sample)
            score = {"graceful": 1.0, "partial": 0.7, "degraded": 0.4, "crash": 0.0}[level]
        except Exception as e:
            level = "crash"
            score = 0.0
            result = f"异常: {e}"

        scores.append(score)
        results.append({
            "id": sample["id"],
            "type": sample["type"],
            "description": sample["description"],
            "level": level,
            "score": score,
            "response_preview": str(result)[:150] if result else "(无输出)",
        })
        time.sleep(1)

    overall = sum(scores) / len(scores) if scores else 0.5
    return {"score": round(overall, 2), "details": results}


def _classify_abnormal_result(result, sample: dict) -> str:
    """
    自动分类异常输入的处理结果。

    返回四级：
    - graceful: 优雅处理（识别异常并给出合理反馈）
    - partial: 部分处理（尝试提取了信息，但结果不完整）
    - degraded: 降级处理（输出了内容但质量很差）
    - crash: 崩溃（无输出或报错）
    """
    if not result:
        return "crash"

    result_str = str(result)

    # 检查是否有"识别异常"的标记
    awareness_markers = [
        "无法", "无效", "空", "乱码", "不是需求", "无法识别",
        "请提供", "缺少", "格式错误", "无法解析",
    ]
    has_awareness = any(m in result_str for m in awareness_markers)

    # 检查是否仍然尝试生成了测试用例
    has_cases = any(m in result_str for m in ["测试用例", "TC0", "test_case", "expected_result"])

    sample_type = sample.get("type", "")

    if sample_type in ("empty", "garbled", "binary"):
        # 对于明显不可用的输入
        if has_awareness:
            return "graceful"  # 识别到异常并提示
        elif has_cases:
            return "degraded"  # 瞎编了一堆用例（不好但没崩）
        else:
            return "partial"
    elif sample_type == "non_requirement":
        if has_awareness:
            return "graceful"
        elif has_cases:
            return "degraded"  # 对小说生成了"测试用例"
        else:
            return "partial"
    elif sample_type == "malformed_markdown":
        if has_cases:
            return "partial"  # 从乱格式中提取了一些
        elif has_awareness:
            return "graceful"
        else:
            return "degraded"

    return "partial"


def eval_tool_failure(agent) -> dict:
    """模拟工具故障，测试 Agent 的恢复能力。"""
    # 用一个不存在的文件路径触发工具失败
    failure_inputs = [
        "请分析以下需求文档并生成测试用例。\n文件路径: /nonexistent/fake_requirement.md\n"
        "(提示: 调用 extract_features 时传 file_path=\"/nonexistent/fake_requirement.md\")",
        "请分析以下需求文档并生成测试用例。\n文件路径: data/eval/requirements/01_login.md\n\n"
        "注意：本次测试中 parse_prd 工具已被禁用，请直接使用其他工具。",
    ]

    scores = []
    results = []
    for inp in failure_inputs:
        try:
            result = agent.run(inp)
            # 有结果就算部分恢复，有测试用例就算完全恢复
            if result and "测试用例" in str(result):
                score = 1.0
                level = "recovered"
            elif result:
                score = 0.5
                level = "partial_recovery"
            else:
                score = 0.2
                level = "no_recovery"
        except Exception:
            score = 0.0
            level = "crash"
            result = None

        scores.append(score)
        results.append({"input_preview": inp[:80], "level": level, "score": score})
        time.sleep(1)

    overall = sum(scores) / len(scores) if scores else 0.5
    return {"score": round(overall, 2), "details": results}


def run_robustness_eval(agent) -> dict:
    """汇总鲁棒性评测。"""
    print("    [1/2] 异常输入处理...")
    abnormal_result = eval_abnormal_input(agent)
    print(f"          得分: {abnormal_result['score']:.2f}")

    print("    [2/2] 工具故障恢复...")
    tool_failure_result = eval_tool_failure(agent)
    print(f"          得分: {tool_failure_result['score']:.2f}")

    overall = abnormal_result["score"] * 0.6 + tool_failure_result["score"] * 0.4

    return {
        "overall_score": round(overall, 2),
        "abnormal_input": abnormal_result,
        "tool_failure": tool_failure_result,
    }
