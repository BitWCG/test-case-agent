"""
Day 13: LLM-as-Judge

用另一个 LLM 模型（不能和 Agent 用同一个）对 Agent 的输出做"主观质量"评分。
确定性评测只能检查"对不对"（格式、覆盖率、数量），
Judge 检查"好不好"（用例质量、是否可执行、是否有意义）。
"""
import json

from src.agent.llm_client import LLMClient


# ================================================================
# 评分 Rubric（评分标准）
# ================================================================
RUBRIC = {
    "correctness": {
        5: "所有用例描述与需求文档完全一致，无事实错误",
        4: "绝大多数用例正确，仅 1-2 处不精确但无伤大雅",
        3: "部分用例描述与需求有偏差，但不影响核心功能",
        2: "多条用例存在事实错误或与需求明显矛盾",
        1: "大部分用例描述错误，无法使用",
    },
    "completeness": {
        5: "覆盖了所有核心功能点、边界场景和异常场景",
        4: "覆盖了大部分核心功能，少量边界场景缺失",
        3: "覆盖了核心功能，但边界和异常场景缺失较多",
        2: "仅覆盖了部分核心功能，遗漏明显",
        1: "严重不完整，大量功能缺失",
    },
    "clarity": {
        5: "每条用例描述清晰、步骤明确、无歧义",
        4: "大部分用例清晰，个别描述稍模糊",
        3: "部分用例描述不够清晰，需要推断",
        2: "多条用例描述模糊、缺少关键信息",
        1: "用例描述混乱，难以理解",
    },
    "actionability": {
        5: "每条用例都包含具体步骤和预期结果，可直接执行",
        4: "大部分用例可执行，个别缺少预期结果",
        3: "部分用例缺少执行步骤或预期结果",
        2: "多数用例缺少可执行信息",
        1: "用例无法直接执行，信息严重不足",
    },
    "edge_case_awareness": {
        5: "充分考虑了边界值、异常输入、并发、安全等场景",
        4: "覆盖了大部分重要的边界场景",
        3: "覆盖了基本边界场景，但深度不够",
        2: "仅 1-2 条边界用例",
        1: "完全没有边界或异常场景的考虑",
    },
}

# 五个评分维度名
DIMENSIONS = ["correctness", "completeness", "clarity",
              "actionability", "edge_case_awareness"]


def _format_rubric() -> str:
    """将 RUBRIC dict 格式化为可读文本，供 Judge Prompt 使用。"""
    lines = []
    for dim, levels in RUBRIC.items():
        lines.append(f"\n【{dim}】")
        for score, desc in sorted(levels.items(), reverse=True):
            lines.append(f"  {score}分: {desc}")
    return "\n".join(lines)


# 预格式化，避免每次调用都重复计算
_RUBRIC_TEXT = _format_rubric()


class LLMJudge:
    """
    LLM-as-Judge 评测器。

    使用独立的 LLM 模型对 Agent 输出的测试用例做主观质量评分。
    支持严格模式和宽松模式，multi_judge 取两种模式的中位数减少偏差。
    """

    def __init__(self, judge_model: str = "qwen-max"):
        """
        初始化 Judge。

        参数：
        - judge_model: 用于评分的 LLM 模型名，必须与 Agent 模型不同
        """
        self.judge_llm = LLMClient(model=judge_model)
        self.model = judge_model

        # 严格模式 prompt 模板
        self.strict_prompt_template = (
            "你是一位严格的测试评审专家。请对以下测试用例做质量评分。\n\n"
            "评分标准（每个维度 1-5 分）：\n"
            f"{_RUBRIC_TEXT}\n\n"
            "请严格评分，对任何错误都不要放过。\n\n"
            "---\n"
            "原始需求文档：\n{requirement}\n\n"
            "---\n"
            "Agent 生成的测试用例：\n{result}\n\n"
            "---\n"
            "请先逐维度分析（每个维度 2-3 句话说明打分依据），然后给出最终 JSON。\n"
            "输出格式：先写分析，最后一行输出纯 JSON：\n"
            '{{"correctness": <int 1-5>, "completeness": <int 1-5>, '
            '"clarity": <int 1-5>, "actionability": <int 1-5>, '
            '"edge_case_awareness": <int 1-5>, "reason": "<一句话总结>"}}'
        )

        # 宽松模式 prompt 模板
        self.lenient_prompt_template = (
            "你是一位注重实用性的测试评审专家。请对以下测试用例做质量评分。\n\n"
            "评分标准（每个维度 1-5 分）：\n"
            f"{_RUBRIC_TEXT}\n\n"
            "请从实用角度评分，只要用例能指导测试即可，格式瑕疵可以忽略。\n\n"
            "---\n"
            "原始需求文档：\n{requirement}\n\n"
            "---\n"
            "Agent 生成的测试用例：\n{result}\n\n"
            "---\n"
            "请先逐维度分析（每个维度 2-3 句话说明打分依据），然后给出最终 JSON。\n"
            "输出格式：先写分析，最后一行输出纯 JSON：\n"
            '{{"correctness": <int 1-5>, "completeness": <int 1-5>, '
            '"clarity": <int 1-5>, "actionability": <int 1-5>, '
            '"edge_case_awareness": <int 1-5>, "reason": "<一句话总结>"}}'
        )

    def judge(self, result: str, requirement: str, mode: str = "strict") -> dict:
        """
        用 LLM 对 Agent 输出做质量评分。

        参数：
        - result: Agent 生成的测试用例（Markdown 或 JSON 文本）
        - requirement: 原始需求文档内容
        - mode: "strict"（严格）或 "lenient"（宽松）

        返回：
        - {"scores": {维度名: 分数}, "overall": float, "reason": "评分说明", "mode": str}
        """
        # 选择 prompt 模板
        if mode == "lenient":
            template = self.lenient_prompt_template
        else:
            template = self.strict_prompt_template

        prompt = template.format(requirement=requirement, result=result)

        # 调用 Judge LLM（最多重试 2 次）
        max_retries = 2
        messages = [{"role": "user", "content": prompt}]
        raw_output = None
        scores = {dim: 3 for dim in DIMENSIONS}  # 默认值，防止异常时未绑定

        for attempt in range(max_retries):
            try:
                # 使用普通 chat（允许 CoT 自由文本 + 末尾 JSON）
                raw_output = self.judge_llm.chat(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=2048,
                )
                # 从输出中提取最后一个 JSON 对象
                scores = self._extract_json(raw_output)

                # 验证必填字段并钳位到 1-5
                for dim in DIMENSIONS:
                    if dim not in scores:
                        raise ValueError(f"缺少维度: {dim}")
                    scores[dim] = max(1, min(5, int(scores[dim])))
                break

            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                if attempt == max_retries - 1:
                    # 重试耗尽，返回默认分
                    scores = {dim: 3 for dim in DIMENSIONS}
                    scores["reason"] = f"Judge 解析失败({e})，使用默认分 3"
                else:
                    # 重试：追加纠正提示
                    retry_hint = (
                        f"你上一次的返回无法解析为合法 JSON（错误: {e}）。"
                        "请在分析结束后，最后一行输出纯 JSON，不要包含 markdown 代码块。"
                    )
                    messages = [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": raw_output or ""},
                        {"role": "user", "content": retry_hint},
                    ]

        # 计算总分
        overall = sum(scores.get(dim, 3) for dim in DIMENSIONS) / len(DIMENSIONS)

        return {
            "scores": {dim: scores.get(dim, 3) for dim in DIMENSIONS},
            "overall": round(overall, 2),
            "reason": scores.get("reason", ""),
            "mode": mode,
        }

    @staticmethod
    def _extract_json(text: str) -> dict:
        """
        从 CoT 输出中提取 JSON 对象。

        策略：从后往前找第一个 '{' 到最后一个 '}' 的匹配，解析为 JSON。
        如果输出被 ```json ... ``` 包裹也能处理。
        """
        import re

        # 尝试 1：去掉 markdown 代码块标记
        cleaned = re.sub(r"```json\s*", "", text)
        cleaned = re.sub(r"```\s*$", "", cleaned.strip())

        # 尝试 2：从后往前找最后一个完整的 JSON 对象
        last_brace = cleaned.rfind("}")
        if last_brace == -1:
            raise json.JSONDecodeError("未找到 JSON 结束符 '}'", text, 0)

        # 从 last_brace 往前找对应的 '{'
        depth = 0
        start = -1
        for i in range(last_brace, -1, -1):
            if cleaned[i] == "}":
                depth += 1
            elif cleaned[i] == "{":
                depth -= 1
            if depth == 0:
                start = i
                break

        if start == -1:
            raise json.JSONDecodeError("未找到匹配的 JSON 起始符 '{'", text, 0)

        json_str = cleaned[start:last_brace + 1]
        return json.loads(json_str)

    def multi_judge(self, result: str, requirement: str) -> dict:
        """
        使用严格 + 宽松两种模式分别评分，取中位数减少偏差。

        参数：
        - result: Agent 生成的测试用例
        - requirement: 原始需求文档内容

        返回：
        - {"scores": {...}, "overall": float, "disagreement": [...], "details": [...]}
        """
        # 两种模式分别调用
        strict_result = self.judge(result, requirement, mode="strict")
        lenient_result = self.judge(result, requirement, mode="lenient")

        # 对每个维度取中位数（两个值的向上取整平均）
        final_scores = {}
        disagreement = []

        for dim in DIMENSIONS:
            s1 = strict_result["scores"][dim]
            s2 = lenient_result["scores"][dim]
            final_scores[dim] = (s1 + s2 + 1) // 2

            # 差异 > 2 分记录为不一致
            if abs(s1 - s2) > 2:
                disagreement.append({
                    "dimension": dim,
                    "strict": s1,
                    "lenient": s2,
                    "diff": abs(s1 - s2),
                })

        overall = sum(final_scores.values()) / len(final_scores)

        return {
            "scores": final_scores,
            "overall": round(overall, 2),
            "disagreement": disagreement,
            "details": [strict_result, lenient_result],
        }
