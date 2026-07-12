"""
Day 14: 一致性评测

评测维度：
  1. 输出稳定性 — 同一输入多次运行，结果波动有多大
  2. Temperature 影响 — temp=0 vs temp=0.7 输出质量对比
  3. Pass@k vs Pass^k — 能力上限 vs 生产可靠性（Claw-Eval 2026 核心指标）

核心认知：
  - Pass@k（如 Pass@3）：k 次里成功 1 次就算过 → 测"理论上能跑通吗"
  - Pass^k（如 Pass^3）：k 次全部成功才算过 → 测"稳定可靠吗"
  - Stability Gap = Pass@k - Pass^k：Gap 大 → 靠运气，不适合生产

输入：
  - agent: SimpleAgent 实例
  - input_text: 需求文档内容（用于稳定性测试）

输出：
  - 波动率、Pass@k、Pass^k、Stability Gap
  - 汇总一致性分数
"""
import json
import time
import statistics
from pathlib import Path
from collections import Counter


# ================================================================
# TODO 12.1: eval_stability — 输出稳定性评测
# ================================================================
# 对同一个输入运行 N 次，统计输出的波动程度。
#
# 步骤：
#   1. 选择测试用输入（建议用 data/eval/requirements/01_login.md）
#      - 读取需求文档内容
#      - 构造 user_input
#
#   2. 定义稳定性指标：
#      a. 用例数量波动：
#         - 从每次运行的 result 中提取用例数量
#         - 计算均值、标准差、变异系数（CV = 标准差 / 均值）
#         - CV < 0.1 → 高度稳定；CV < 0.3 → 可接受；CV >= 0.3 → 不稳定
#
#      b. 功能点覆盖波动：
#         - 从每次运行的 result 中提取功能点名称集合
#         - 计算 N 次运行的功能点 Jaccard 相似度
#         - Jaccard(A, B) = |A ∩ B| / |A ∪ B|
#         - 对所有两两组合求平均 Jaccard
#         - 平均 Jaccard > 0.8 → 功能覆盖稳定
#
#      c. 规则覆盖波动：
#         - 同上，提取规则列表，计算平均 Jaccard
#
#      d. 输出文本相似度：
#         - 用 difflib.SequenceMatcher 计算两两相似度
#         - 平均相似度 > 0.8 → 输出稳定
#
#   3. 运行 N 次（默认 runs=5）：
#      - 每次运行记录：用例数、功能点列表、规则列表、原始输出
#      - 每次运行之间等待 1-2 秒（避免 API 限流）
#      - 如果某次运行失败，记录错误后继续
#
#   4. 计算各项指标：
#      - case_counts = [每次运行的用例数]
#      - cv = stdev(case_counts) / mean(case_counts)
#      - feature_sets = [每次运行的功能点集合]
#      - avg_jaccard_features = mean_jaccard(feature_sets)
#      - rule_sets = [每次运行的规则集合]
#      - avg_jaccard_rules = mean_jaccard(rules_sets)
#
#   5. 综合稳定性分数：
#      - case_stability = 1.0 - min(cv, 1.0)
#      - feature_stability = avg_jaccard_features
#      - rule_stability = avg_jaccard_rules
#      - overall = (case_stability + feature_stability + rule_stability) / 3
#
#   6. 返回：
#      {
#          "score": float,
#          "runs": int,
#          "case_counts": [int, ...],
#          "case_cv": float,
#          "feature_jaccard": float,
#          "rule_jaccard": float,
#          "raw_outputs": [str, ...],  # 可选，前 500 字符
#          "report": "稳定性分析文本",
#      }
#
# 提示：
#   - 5 次运行约消耗 5 次完整 Agent 调用，注意 API 费用
#   - CV 计算前先判断 mean 是否为 0
#   - Jaccard 计算注意空集处理：两个都空 = 1.0，一个空 = 0.0
#
def eval_stability(agent, input_text: str = None, runs: int = 5) -> dict:
    """
    评测 Agent 输出的稳定性（同一输入多次运行）。

    参数：
    - agent: SimpleAgent 实例
    - input_text: 需求文档内容，默认使用 01_login.md
    - runs: 重复运行次数，默认 5

    返回：
    - {"score": float, "runs": int, "case_cv": float, ...}
    """
    # ============================================================
    # 步骤 1: 准备输入
    # ============================================================
    # if input_text is None:
    #     req_path = Path("data/eval/requirements/01_login.md")
    #     input_text = req_path.read_text(encoding="utf-8")
    # user_input = (
    #     f"请分析以下需求文档并生成测试用例。\n"
    #     f"文件路径: data/eval/requirements/01_login.md\n\n{input_text}"
    # )
    #
    # ============================================================
    # 步骤 2: 运行 N 次，收集数据
    # ============================================================
    # case_counts = []
    # feature_sets = []
    # rule_sets = []
    # raw_outputs = []
    #
    # for i in range(runs):
    #     print(f"  第 {i+1}/{runs} 次运行...")
    #     try:
    #         result = agent.run(user_input)
    #
    #         # 提取用例数
    #         from src.eval.deterministic_eval import _extract_cases
    #         cases = _extract_cases(result)
    #         case_counts.append(len(cases))
    #
    #         # 提取功能点名称
    #         features = {c.get("feature", "") for c in cases if c.get("feature")}
    #         feature_sets.append(features)
    #
    #         # 提取规则（从 description 中提取关键规则词）
    #         # 简单方案：提取所有 description 中的关键词
    #         descriptions = [c.get("description", "") for c in cases]
    #         all_text = " ".join(descriptions)
    #         # 用简单的规则提取：找"必须"、"不允许"、"不能"附近的词
    #         import re
    #         rule_kw = set(re.findall(
    #             r"(?:必须|不允许|不能|禁止|最多|最少|最大|最小)[^，。；\\n]{0,20}",
    #             all_text,
    #         ))
    #         rule_sets.append(rule_kw)
    #
    #         raw_outputs.append(result[:500])  # 只保存前 500 字符
    #
    #     except Exception as e:
    #         print(f"    第 {i+1} 次运行失败: {e}")
    #         case_counts.append(0)
    #         feature_sets.append(set())
    #         rule_sets.append(set())
    #         raw_outputs.append(f"[ERROR] {e}")
    #
    #     if i < runs - 1:
    #         time.sleep(2)  # 间隔 2 秒
    #
    # ============================================================
    # 步骤 3: 计算指标
    # ============================================================
    # 3a. 用例数量波动（CV）
    # avg_cases = statistics.mean(case_counts)
    # if avg_cases > 0:
    #     std_cases = statistics.stdev(case_counts) if len(case_counts) > 1 else 0
    #     cv = std_cases / avg_cases
    # else:
    #     cv = 1.0  # 全 0 = 最大不稳定
    #
    # 3b. 功能点 Jaccard
    # def mean_jaccard(sets_list):
    #     \"\"\"计算所有两两组合的平均 Jaccard 相似度\"\"\"
    #     n = len(sets_list)
    #     if n <= 1:
    #         return 1.0
    #     jaccards = []
    #     for i in range(n):
    #         for j in range(i+1, n):
    #             a, b = sets_list[i], sets_list[j]
    #             if len(a) == 0 and len(b) == 0:
    #                 jaccards.append(1.0)
    #             elif len(a) == 0 or len(b) == 0:
    #                 jaccards.append(0.0)
    #             else:
    #                 jaccards.append(len(a & b) / len(a | b))
    #     return statistics.mean(jaccards)
    #
    # feature_jaccard = mean_jaccard(feature_sets)
    # rule_jaccard = mean_jaccard(rule_sets)
    #
    # ============================================================
    # 步骤 4: 综合分数
    # ============================================================
    # case_stability = 1.0 - min(cv, 1.0)
    # overall = (case_stability + feature_jaccard + rule_jaccard) / 3
    #
    # # 生成文字描述
    # if cv < 0.1:
    #     stability_desc = "高度稳定"
    # elif cv < 0.3:
    #     stability_desc = "可接受"
    # else:
    #     stability_desc = "不稳定"
    #
    # return {
    #     "score": round(overall, 2),
    #     "runs": runs,
    #     "case_counts": case_counts,
    #     "case_cv": round(cv, 2),
    #     "feature_jaccard": round(feature_jaccard, 2),
    #     "rule_jaccard": round(rule_jaccard, 2),
    #     "stability_desc": stability_desc,
    #     "raw_outputs": raw_outputs,
    # }
    pass


# ================================================================
# TODO 12.2: eval_temperature_impact — Temperature 影响对比
# ================================================================
# 对比 temperature=0（确定性）和 temperature=0.7（随机性）的输出差异。
#
# 步骤：
#   1. 用同一个输入分别以 temp=0 和 temp=0.7 运行 Agent
#      - 注意：这需要 Agent 支持动态设置 temperature
#      - 如果 SimpleAgent 不支持，可以先在 agent.__init__ 中暴露参数
#      - 或者创建 2 个 Agent 实例（一个 temp=0，一个 temp=0.7）
#
#   2. 对比维度：
#      a. 用例数量差异：
#         - count_diff = |count_0 - count_07|
#         - 差异 < 20% → 正常
#
#      b. 功能覆盖率差异：
#         - 提取 2 次输出的功能点集合
#         - Jaccard(features_0, features_07)
#         - Jaccard < 0.5 → temperature 对功能覆盖影响大
#
#      c. 用例质量差异：
#         - 每条用例的平均长度（描述越详细 = 质量越高？）
#         - temp=0.7 可能产生更丰富的描述，但也可能产生更多噪声
#
#      d. 输出长度差异：
#         - len_0 vs len_07
#         - temp=0.7 的输出通常更长（更啰嗦）
#
#   3. 评分：
#      - 如果两次输出在核心指标上一致（Jaccard > 0.8），说明 Agent
#        对 temperature 不敏感 → 鲁棒性好 → score = 1.0
#      - 如果 Jaccard < 0.5，说明 temperature 影响太大
#        → 生产环境不可靠 → score = 0.5
#      - 中间线性插值
#
#   4. 返回：
#      {
#          "score": float,
#          "temp_0": {用例数, 功能点数, 输出长度, ...},
#          "temp_07": {用例数, 功能点数, 输出长度, ...},
#          "jaccard": float,
#          "analysis": "温度影响分析文本",
#      }
#
def eval_temperature_impact(agent, input_text: str = None) -> dict:
    """
    对比不同 temperature 下 Agent 输出的差异。

    参数：
    - agent: SimpleAgent 实例（需要支持 temperature 设置）
    - input_text: 需求文档内容

    返回：
    - {"score": float, "temp_0": {...}, "temp_07": {...}, "jaccard": float}
    """
    # ============================================================
    # 步骤 1: 准备输入
    # ============================================================
    # if input_text is None:
    #     req_path = Path("data/eval/requirements/01_login.md")
    #     input_text = req_path.read_text(encoding="utf-8")
    # user_input = f"请分析以下需求文档并生成测试用例。\n\n{input_text}"
    #
    # ============================================================
    # 步骤 2: temp=0 运行
    # ============================================================
    # 先备份当前 temperature，设为 0
    # original_temp = agent.llm_client.temperature
    # agent.llm_client.temperature = 0.0  # 或 0.1
    #
    # result_0 = agent.run(user_input)
    # cases_0 = ...  # 提取用例
    #
    # ============================================================
    # 步骤 3: temp=0.7 运行
    # ============================================================
    # agent.llm_client.temperature = 0.7
    # result_07 = agent.run(user_input)
    # cases_07 = ...  # 提取用例
    #
    # # 恢复原始 temperature
    # agent.llm_client.temperature = original_temp
    #
    # ============================================================
    # 步骤 4: 对比分析
    # ============================================================
    # features_0 = {c.get("feature", "") for c in cases_0}
    # features_07 = {c.get("feature", "") for c in cases_07}
    #
    # # Jaccard 相似度
    # intersection = len(features_0 & features_07)
    # union = len(features_0 | features_07)
    # jaccard = intersection / union if union > 0 else 1.0
    #
    # # 计算分数
    # if jaccard > 0.8:
    #     score = 1.0
    # elif jaccard < 0.5:
    #     score = 0.5
    # else:
    #     score = 0.5 + (jaccard - 0.5) / (0.8 - 0.5) * 0.5
    #
    # return {
    #     "score": round(score, 2),
    #     "temp_0": {"case_count": len(cases_0), "feature_count": len(features_0)},
    #     "temp_07": {"case_count": len(cases_07), "feature_count": len(features_07)},
    #     "jaccard": round(jaccard, 2),
    # }
    pass


# ================================================================
# TODO 12.3: eval_pass_at_k — Pass@k（能力上限）
# ================================================================
# k 次运行中至少有 1 次"通过" → 认为 Agent 具备该能力。
# 通过标准：确定性评测分数 >= 0.6
#
# 步骤：
#   1. 加载 expected 参考答案
#   2. 重复运行 Agent k 次（默认 k=3）
#   3. 每次运行后调用 run_deterministic_eval(result, expected) 打分
#   4. 如果有任意一次 overall_score >= threshold（默认 0.6），Pass@k = 1
#      否则 Pass@k = 0
#   5. 如果要测多个输入，Pass@k = 通过的输入数 / 总输入数
#
#   6. 返回：
#      {
#          "pass_at_k": bool,  # 或 0/1
#          "k": int,
#          "threshold": float,
#          "run_scores": [float, ...],  # 每次运行的分数
#          "best_score": float,
#      }
#
# 提示：
#   - Pass@k 测的是"能力上限"——只要有一次能做好，就说明 Agent 有这个能力
#   - k 越大，Pass@k 越容易为 1（多次机会）
#   - 面试加分项：能讲清楚 Pass@k vs Pass^k 的区别
#
def eval_pass_at_k(agent, expected: dict, requirement_text: str,
                   k: int = 3, threshold: float = 0.6) -> dict:
    """
    Pass@k：k 次中任意 1 次通过即视为通过。

    参数：
    - agent: SimpleAgent 实例
    - expected: 参考答案 dict
    - requirement_text: 需求文档内容
    - k: 运行次数，默认 3
    - threshold: 通过分数线，默认 0.6

    返回：
    - {"pass_at_k": bool, "k": int, "run_scores": [...], "best_score": float}
    """
    # ============================================================
    # 步骤 1: 构造输入
    # ============================================================
    # user_input = f"请分析以下需求文档并生成测试用例。\n\n{requirement_text}"
    #
    # ============================================================
    # 步骤 2: 运行 k 次并打分
    # ============================================================
    # from src.eval.deterministic_eval import run_deterministic_eval
    #
    # run_scores = []
    # for i in range(k):
    #     print(f"  Pass@k 第 {i+1}/{k} 次...")
    #     try:
    #         result = agent.run(user_input)
    #         det_result = run_deterministic_eval(result, expected)
    #         score = det_result["overall_score"]
    #         run_scores.append(score)
    #     except Exception as e:
    #         print(f"    运行失败: {e}")
    #         run_scores.append(0.0)
    #     if i < k - 1:
    #         time.sleep(2)
    #
    # ============================================================
    # 步骤 3: 判定
    # ============================================================
    # best_score = max(run_scores) if run_scores else 0.0
    # passed = any(s >= threshold for s in run_scores)
    #
    # return {
    #     "pass_at_k": passed,
    #     "k": k,
    #     "threshold": threshold,
    #     "run_scores": run_scores,
    #     "best_score": best_score,
    # }
    pass


# ================================================================
# TODO 12.4: eval_pass_pow_k — Pass^k（生产可靠性）
# ================================================================
# k 次运行全部通过才算通过 → 测"生产环境能否稳定可用"。
#
# 步骤：
#   1. 与 eval_pass_at_k 完全相同，只是判定条件不同
#   2. 判定：所有 k 次分数都 >= threshold → Pass^k = True
#   3. Stability Gap = Pass@k - Pass^k
#      - 如果 Pass@k=True, Pass^k=False → Gap 大 → 靠运气
#      - 如果 Pass@k=True, Pass^k=True → Gap 小 → 稳定可靠
#
#   4. 返回：
#      {
#          "pass_pow_k": bool,
#          "k": int,
#          "threshold": float,
#          "run_scores": [float, ...],
#          "min_score": float,  # 最低分（最差的一次）
#          "mean_score": float,
#      }
#
def eval_pass_pow_k(agent, expected: dict, requirement_text: str,
                    k: int = 3, threshold: float = 0.6) -> dict:
    """
    Pass^k：k 次全部通过才视为通过。

    参数：
    - agent: SimpleAgent 实例
    - expected: 参考答案 dict
    - requirement_text: 需求文档内容
    - k: 运行次数，默认 3
    - threshold: 通过分数线，默认 0.6

    返回：
    - {"pass_pow_k": bool, "k": int, "run_scores": [...], "min_score": float}
    """
    # ============================================================
    # 步骤 1-2: 与 eval_pass_at_k 相同（运行 k 次 + 打分）
    # ============================================================
    # （直接复用 eval_pass_at_k 的代码即可）
    #
    # ============================================================
    # 步骤 3: 判定（唯一区别）
    # ============================================================
    # min_score = min(run_scores) if run_scores else 0.0
    # mean_score = statistics.mean(run_scores) if run_scores else 0.0
    # passed = all(s >= threshold for s in run_scores)
    #
    # return {
    #     "pass_pow_k": passed,
    #     "k": k,
    #     "threshold": threshold,
    #     "run_scores": run_scores,
    #     "min_score": round(min_score, 2),
    #     "mean_score": round(mean_score, 2),
    # }
    pass


# ================================================================
# TODO 12.5: run_consistency_eval — 汇总一致性评测
# ================================================================
# 汇总稳定性 + Temperature 影响 + Pass@k + Pass^k。
#
# 步骤：
#   1. 依次调用 eval_stability、eval_temperature_impact、
#      eval_pass_at_k、eval_pass_pow_k
#
#   2. 计算一致性综合分：
#      - stability_score = eval_stability 的 score
#      - temp_score = eval_temperature_impact 的 score
#      - pass_score = Pass@k 的 best_score（归一化到 0-1）
#      - overall = (stability + temp + pass_score) / 3
#
#   3. 计算 Stability Gap：
#      - pass_at_k = eval_pass_at_k 的 pass_at_k
#      - pass_pow_k = eval_pass_pow_k 的 pass_pow_k
#      - gap = pass_at_k - pass_pow_k  # True=1, False=0
#      - 如果 gap > 0：标注"稳定性不足，生产环境有风险"
#
#   4. 生成文本报告
#
#   5. 返回：
#      {
#          "overall_score": float,
#          "stability_gap": int,
#          "dimensions": {
#              "stability": {...},
#              "temperature_impact": {...},
#              "pass_at_k": {...},
#              "pass_pow_k": {...},
#          },
#          "report": "格式化的文本报告",
#      }
#
def run_consistency_eval(agent, expected: dict = None,
                         requirement_text: str = None, k: int = 3) -> dict:
    """
    汇总所有一致性评测。

    参数：
    - agent: SimpleAgent 实例
    - expected: 参考答案 dict
    - requirement_text: 需求文档内容
    - k: Pass@k 的 k 值，默认 3

    返回：
    - {"overall_score": float, "stability_gap": int,
       "dimensions": {...}, "report": "..."}
    """
    # ============================================================
    # 步骤 1: 加载默认输入和 expected
    # ============================================================
    # if requirement_text is None:
    #     req_path = Path("data/eval/requirements/01_login.md")
    #     requirement_text = req_path.read_text(encoding="utf-8")
    # if expected is None:
    #     exp_path = Path("data/eval/expected/01_login_expected.json")
    #     if exp_path.exists():
    #         with open(exp_path, "r", encoding="utf-8") as f:
    #             expected = json.load(f)
    #     else:
    #         expected = {}
    #
    # ============================================================
    # 步骤 2: 运行稳定性评测
    # ============================================================
    # print("→ 运行稳定性评测（5 次重复）...")
    # try:
    #     stability_result = eval_stability(agent, requirement_text, runs=5)
    #     print(f"  稳定性: {stability_result['score']:.2f}")
    # except Exception as e:
    #     stability_result = {"score": 0, "error": str(e)}
    #
    # ============================================================
    # 步骤 3: 运行 Temperature 影响评测
    # ============================================================
    # print("→ 运行 Temperature 影响评测...")
    # try:
    #     temp_result = eval_temperature_impact(agent, requirement_text)
    #     print(f"  Temperature: {temp_result['score']:.2f}")
    # except Exception as e:
    #     temp_result = {"score": 0, "error": str(e)}
    #
    # ============================================================
    # 步骤 4: 运行 Pass@k 和 Pass^k
    # ============================================================
    # print(f"→ 运行 Pass@k / Pass^{k} (k={k})...")
    # try:
    #     pass_at_k_result = eval_pass_at_k(agent, expected,
    #                                       requirement_text, k=k)
    #     pass_pow_k_result = eval_pass_pow_k(agent, expected,
    #                                         requirement_text, k=k)
    #     print(f"  Pass@{k}: {pass_at_k_result['pass_at_k']}")
    #     print(f"  Pass^{k}: {pass_pow_k_result['pass_pow_k']}")
    # except Exception as e:
    #     pass_at_k_result = {"pass_at_k": False, "error": str(e)}
    #     pass_pow_k_result = {"pass_pow_k": False, "error": str(e)}
    #
    # ============================================================
    # 步骤 5: 计算综合分和 Stability Gap
    # ============================================================
    # stability_score = stability_result.get("score", 0)
    # temp_score = temp_result.get("score", 0)
    # pass_score = pass_at_k_result.get("best_score", 0)
    #
    # overall = (stability_score + temp_score + pass_score) / 3
    #
    # pass_at = 1 if pass_at_k_result.get("pass_at_k") else 0
    # pass_pow = 1 if pass_pow_k_result.get("pass_pow_k") else 0
    # stability_gap = pass_at - pass_pow
    #
    # ============================================================
    # 步骤 6: 生成报告并返回
    # ============================================================
    # gap_warning = ""
    # if stability_gap > 0:
    #     gap_warning = "⚠️ Stability Gap > 0 — 生产环境有风险，Agent 表现靠运气"
    #
    # report_lines = [
    #     "=" * 50,
    #     "一致性评测报告",
    #     "=" * 50,
    #     f"综合得分: {overall:.2f}",
    #     f"Stability Gap: {stability_gap} {gap_warning}",
    #     f"  输出稳定性: {stability_score:.2f}",
    #     f"  Temperature影响: {temp_score:.2f}",
    #     f"  Pass@{k}: {pass_at_k_result.get('pass_at_k')} "
    #     f"(最佳分: {pass_at_k_result.get('best_score', 0):.2f})",
    #     f"  Pass^{k}: {pass_pow_k_result.get('pass_pow_k')} "
    #     f"(最差分: {pass_pow_k_result.get('min_score', 0):.2f})",
    # ]
    #
    # return {
    #     "overall_score": round(overall, 2),
    #     "stability_gap": stability_gap,
    #     "dimensions": {
    #         "stability": stability_result,
    #         "temperature_impact": temp_result,
    #         "pass_at_k": pass_at_k_result,
    #         "pass_pow_k": pass_pow_k_result,
    #     },
    #     "report": "\n".join(report_lines),
    # }
    pass
