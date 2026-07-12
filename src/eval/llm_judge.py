"""
Day 13: LLM-as-Judge

用另一个 LLM 模型（不能和 Agent 用同一个）对 Agent 的输出做"主观质量"评分。
确定性评测只能检查"对不对"（格式、覆盖率、数量），
Judge 检查"好不好"（用例质量、是否可执行、是否有意义）。
"""
import json
from pathlib import Path


# ================================================================
# LLM-as-Judge
# ================================================================

# ================================================================
# TODO 8.1: 定义评分 Rubric
# ================================================================
# Rubric（评分标准）是 Judge 打分的依据。每个分数等级有明确的描述，
# 减少 Judge LLM 的主观偏差。
#
# 步骤：
#   1. 定义 5 个质量维度的 Rubric：
#      - correctness（正确性）：用例是否符合需求文档中的描述
#      - completeness（完整性）：是否覆盖了所有需要的场景
#      - clarity（清晰度）：用例描述是否清晰、可执行
#      - actionability（可执行性）：是否包含具体的步骤和预期结果
#      - edge_case_awareness（边界意识）：是否覆盖了边界和异常场景
#   2. 每个维度 1-5 分：
#      - 5 分：优秀，无明显问题
#      - 4 分：良好，有少量可改进之处
#      - 3 分：及格，有较明显遗漏或错误
#      - 2 分：较差，有严重遗漏或错误
#      - 1 分：很差，几乎不可用
#   3. 返回一个 dict，包含每个维度的评分标准文本
#
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


# ================================================================
# TODO 8.2: judge — 单次 LLM 评分
# ================================================================
# 调用 Judge LLM 对 Agent 的输出打分。
#
# 步骤：
#   1. 构建 Judge Prompt：
#      - 包含评分 Rubric（上面的 RUBRIC dict 转成文本）
#      - 包含原始需求文档内容
#      - 包含 Agent 生成的测试用例
#      - 明确要求 Judge 输出 JSON 格式：{"correctness": int, "completeness": int, ...}
#   2. 调用 LLM：
#      - 使用 self.judge_llm.client.chat.completions.create()
#      - model 用另一个模型（如 qwen-max，不能和 Agent 共用 qwen-plus）
#      - temperature=0.1（低温度保证一致性）
#      - response_format={"type": "json_object"} 强制 JSON 输出
#   3. 解析 Judge 返回的 JSON
#   4. 返回 {"scores": {...}, "overall": float, "reason": "..."}
#      - overall = 5 个维度的平均分
#
# 提示：
#   - Judge LLM 的初始化：在 __init__ 中新建一个 LLMClient，指定不同模型
#   - 如果 Judge 返回的 JSON 解析失败，重试 1 次
#   - 如果重试还是失败，返回默认分（全 3 分）
#
def __init__(self, judge_model: str = "qwen-max"):
    """
    初始化 Judge。

    参数：
    - judge_model: 用于评分的 LLM 模型名，必须与 Agent 模型不同
    """
    # ============================================================
    # 步骤 1: 创建独立的 LLM Client
    # ============================================================
    # 用和 Agent 相同的 LLMClient 类，但指定不同的 model 名
    # from src.llm.llm_client import LLMClient
    # self.judge_llm = LLMClient(model=judge_model)
    #
    # ============================================================
    # 步骤 2: 保存模型名（用于日志）
    # ============================================================
    # self.model = judge_model
    #
    # ============================================================
    # 步骤 3: 准备评分 Prompt 模板（2 种模式）
    # ============================================================
    # 严格模式 prompt：
    #   self.strict_prompt_template = (
    #       "你是一位严格的测试评审专家。请对以下测试用例做质量评分。\n\n"
    #       "评分标准（1-5 分）：\n"
    #       + 将 RUBRIC 格式化为文本
    #       + "\n请严格评分，对任何错误都不要放过。\n\n"
    #       "原始需求：{requirement}\n\n"
    #       "测试用例输出：{result}\n\n"
    #       "请返回 JSON: {{\"correctness\": int, \"completeness\": int, "
    #       "\"clarity\": int, \"actionability\": int, "
    #       "\"edge_case_awareness\": int, \"reason\": \"...\"}}"
    #   )
    #
    # 宽松模式 prompt：
    #   self.lenient_prompt_template = (...)
    #   区别：强调"从实用角度评分"，对格式瑕疵宽容
    pass


def judge(self, result: str, requirement: str) -> dict:
    """
    用 LLM 对 Agent 输出做质量评分。

    参数：
    - result: Agent 生成的测试用例（Markdown 或 JSON）
    - requirement: 原始需求文档内容

    返回：
    - {"scores": {维度名: 分数}, "overall": float, "reason": "评分说明"}
    """
    # ============================================================
    # 步骤 1: 构建 Judge Prompt
    # ============================================================
    # 将 RUBRIC 转为可读文本：
    #   rubric_text = ""
    #   for dim, levels in RUBRIC.items():
    #       rubric_text += f"\n{dim}:\n"
    #       for score, desc in levels.items():
    #           rubric_text += f"  {score}分: {desc}\n"
    #
    # 构建完整 prompt（用 self.strict_prompt_template 或传入的 prompt）：
    #   prompt = self.strict_prompt_template.format(
    #       requirement=requirement,
    #       result=result,
    #       rubric=rubric_text,
    #   )
    #
    # ============================================================
    # 步骤 2: 调用 Judge LLM
    # ============================================================
    # 用低 temperature 保证一致性：
    #   response = self.judge_llm.client.chat.completions.create(
    #       model=self.model,
    #       messages=[{"role": "user", "content": prompt}],
    #       temperature=0.1,
    #       response_format={"type": "json_object"},  # 强制 JSON 输出
    #   )
    #   raw_output = response.choices[0].message.content
    #
    # ============================================================
    # 步骤 3: 解析 Judge 返回的 JSON
    # ============================================================
    # max_retries = 2
    # for attempt in range(max_retries):
    #     try:
    #         scores = json.loads(raw_output)
    #         # 验证必填字段
    #         required_dims = ["correctness", "completeness", "clarity",
    #                          "actionability", "edge_case_awareness"]
    #         for dim in required_dims:
    #             if dim not in scores:
    #                 raise ValueError(f"缺少维度: {dim}")
    #             # 强制分数在 1-5 范围内
    #             scores[dim] = max(1, min(5, int(scores[dim])))
    #         break
    #     except (json.JSONDecodeError, ValueError, KeyError) as e:
    #         if attempt == max_retries - 1:
    #             # 重试失败，返回默认分
    #             scores = {dim: 3 for dim in required_dims}
    #             scores["reason"] = f"解析失败({e})，使用默认分"
    #         else:
    #             # 重试：告诉 LLM 上次返回格式不对，请重新输出
    #             raw_output = retry_call()  # 重新调用 LLM
    #
    # ============================================================
    # 步骤 4: 计算总分并返回
    # ============================================================
    # overall = sum(scores[dim] for dim in required_dims) / len(required_dims)
    # return {
    #     "scores": {dim: scores[dim] for dim in required_dims},
    #     "overall": round(overall, 2),
    #     "reason": scores.get("reason", ""),
    # }
    pass


# ================================================================
# TODO 8.3: multi_judge — 多 Judge 投票
# ================================================================
# 使用 2 种不同风格的 prompt 分别评分，取中位数，减少单一 prompt 偏差。
#
# 步骤：
#   1. 定义 2 种 Judge Prompt：
#      - "严格模式"：强调准确性和完整性，对错误敏感（prompt 中加入"请严格评分"）
#      - "宽松模式"：强调实用性，对格式瑕疵宽容（prompt 中加入"请从实用角度评分"）
#   2. 用 2 个 prompt 分别调用 judge()（注意：共用同一个 LLM，只改 prompt）
#   3. 对每个维度的分数取中位数
#   4. 如果 2 个评分差异过大（> 2 分），标记为"不一致"
#   5. 返回 {"scores": {...}, "overall": float, "disagreement": [...]}
#
# 提示：
#   - 中位数计算：sorted([a, b])[len//2]，对 2 个数取中间值
#   - disagreement 记录差异 > 2 分的维度，方便后续分析
#
def multi_judge(self, result: str, requirement: str) -> dict:
    """
    使用多 Judge 投票减少偏差。

    参数：
    - result: Agent 生成的测试用例
    - requirement: 原始需求文档内容

    返回：
    - {"scores": {...}, "overall": float, "disagreement": [...], "details": [...]}
    """
    # ============================================================
    # 步骤 1: 定义 2 种 Judge Prompt 变体
    # ============================================================
    # 严格模式：追加 "请严格评分，对任何错误都不要放过。"
    # 宽松模式：追加 "请从实用角度评分，只要用例能指导测试即可，格式瑕疵可以忽略。"
    #
    # ============================================================
    # 步骤 2: 分别调用 judge()
    # ============================================================
    # 注意：共用同一个 self.judge_llm，只改 prompt 参数
    #
    # 方案 A（推荐）：在 judge() 中增加 prompt_mode 参数
    #   strict_result = self.judge(result, requirement, mode="strict")
    #   lenient_result = self.judge(result, requirement, mode="lenient")
    #
    # 方案 B（简单）：修改 self.strict_prompt_template 后调用 2 次
    #   original_template = self.strict_prompt_template
    #   self.strict_prompt_template = strict_template
    #   strict_result = self.judge(result, requirement)
    #   self.strict_prompt_template = lenient_template
    #   lenient_result = self.judge(result, requirement)
    #   self.strict_prompt_template = original_template  # 恢复
    #
    # ============================================================
    # 步骤 3: 对每个维度取中位数
    # ============================================================
    # dimensions = ["correctness", "completeness", "clarity",
    #               "actionability", "edge_case_awareness"]
    # final_scores = {}
    # disagreement = []
    # for dim in dimensions:
    #     s1 = strict_result["scores"][dim]
    #     s2 = lenient_result["scores"][dim]
    #     # 对 2 个值取中位数（平均值向上取整）
    #     final_scores[dim] = (s1 + s2 + 1) // 2  # 整数除法向上取整
    #     # 如果差异 > 2 分，记录为不一致
    #     if abs(s1 - s2) > 2:
    #         disagreement.append({
    #             "dimension": dim,
    #             "strict": s1,
    #             "lenient": s2,
    #             "diff": abs(s1 - s2),
    #         })
    #
    # ============================================================
    # 步骤 4: 计算总分并返回
    # ============================================================
    # overall = sum(final_scores.values()) / len(final_scores)
    # return {
    #     "scores": final_scores,
    #     "overall": round(overall, 2),
    #     "disagreement": disagreement,
    #     "details": [strict_result, lenient_result],
    # }
    pass
