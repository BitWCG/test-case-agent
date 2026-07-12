"""
Day 14: 鲁棒性评测

评测维度：
  1. 异常输入处理 — 空文档、乱码、超长文档、格式错误
  2. 工具故障恢复 — 模拟工具返回 error，Agent 能否优雅降级
  3. 输入格式变异 — 纯文本 vs JSON vs Markdown 混排

核心认知：
  鲁棒性不是"不出错"，而是"出错后能恢复或给出有价值的反馈"。
  Claw-Eval 公式中 Robustness 占 20% 权重（经 Safety 门控后）。

输入：
  - agent: SimpleAgent 实例
  - abnormal_samples: 异常输入样本

输出：
  - 每个异常样本的处理结果（崩溃/优雅降级/正常处理）
  - 汇总鲁棒性分数
"""
import json
import time
from pathlib import Path


# ================================================================
# TODO 11.1: eval_abnormal_input — 异常输入处理评测
# ================================================================
# 测试 Agent 在面对各种异常输入时的表现。
#
# 步骤：
#   1. 定义异常输入样本（5-6 个）：
#      a. 空文档：content = ""
#         - 期望：Agent 能识别空输入，提示用户提供有效文档
#      b. 纯乱码：content = "锟斤拷烫烫烫" * 100
#         - 期望：Agent 能识别乱码，提示无法解析
#      c. 纯二进制：content = "\x00\x01\x02\xFF" * 50
#         - 期望：Agent 能处理编码异常，不崩溃
#      d. 超长文档：正常需求文档重复拼接 50 次（50万字符）
#         - 期望：Agent 不会因 token 超限崩溃，给出合理反馈
#      e. 格式错误：需求文档中 Markdown 格式错乱
#         （用 Tab 代替 #, 表格错位等）
#         - 期望：Agent 尽可能提取信息，或在无法提取时说明原因
#      f. 非需求文档：传入一段小说、新闻或代码
#         - 期望：Agent 能识别"这不是需求文档"，给出提示
#
#   2. 对每个异常样本调用 agent.run(sample["input"])，获取 result
#      - 设置 timeout=60 秒（防止 Agent 卡死）
#      - 捕获所有异常（包括超时、API 错误等）
#
#   3. 对每个样本分类判定（4 级）：
#      级别 3 — 完美处理：
#        - Agent 识别出异常输入，给出了有意义的提示或反馈
#        - 没有崩溃、没有输出无意义内容
#      级别 2 — 降级处理：
#        - Agent 没有崩溃，但输出了一些低质量或无意义的内容
#        - 或者忽略了异常输入，强行生成了一些空泛的测试用例
#      级别 1 — 异常终止：
#        - Agent 抛出未捕获的异常、返回了 traceback
#        - 或者触发了 API 错误（如 token 超限）后没有恢复
#      级别 0 — 完全崩溃：
#        - Agent 的 run() 方法抛出异常，或超时未返回
#
#   4. 使用关键词+规则自动判定级别（无需 LLM）：
#      自动判定规则：
#        - 如果 result 中包含 "traceback" / "Error:" / "Exception" → 级别 1
#        - 如果 result 中包含 "无法" / "不支持" / "请提供" / "不是" → 级别 3
#        - 如果 result 中有结构化测试用例输出 → 级别 2（降级但仍生成了内容）
#        - 如果 try/except 捕获到异常 → 级别 0
#        - 否则默认级别 2
#
#   5. 计算分数：
#      - 每个样本的分数 = 判定级别 / 3（归一化到 0-1）
#      - 总分 = 所有样本分数的平均值
#
#   6. 返回：
#      {
#          "score": float,
#          "total": int,
#          "level_distribution": {3: count, 2: count, 1: count, 0: count},
#          "results": [{sample_id, level, result_preview, details}, ...],
#      }
#
# 提示：
#   - 超长文档测试注意：可能消耗大量 token，建议放在最后测
#   - 乱码和二进制输入要先确认 Agent 的编码处理方式
#   - 如果某个样本耗时太长，可以跳过并标记为"超时"
#
def eval_abnormal_input(agent, samples: list[dict] = None) -> dict:
    """
    评测 Agent 对异常输入的鲁棒性。

    参数：
    - agent: SimpleAgent 实例
    - samples: 异常输入样本列表，默认使用内置样本

    返回：
    - {"score": float, "total": int, "level_distribution": {...},
       "results": [...]}
    """
    # ============================================================
    # 步骤 1: 定义异常输入样本
    # ============================================================
    # if samples is None:
    #     # 读取一个正常的需求文档作为"格式错误"和的"超长文档"基础
    #     normal_req_path = Path("data/eval/requirements/01_login.md")
    #     normal_text = normal_req_path.read_text(encoding="utf-8")
    #     long_text = normal_text * 50  # 重复 50 次
    #
    #     # 制造格式错乱的文档
    #     messy_text = normal_text.replace("##", "\t\t")  # Tab 代替标题
    #     messy_text = messy_text.replace("-", "~")        # 破坏列表
    #
    #     samples = [
    #         {
    #             "id": "abn_01",
    #             "type": "empty",
    #             "input": "",
    #             "expected_level": 3,
    #             "description": "空文档输入",
    #         },
    #         {
    #             "id": "abn_02",
    #             "type": "garbled",
    #             "input": "锟斤拷烫烫烫" * 100,
    #             "expected_level": 3,
    #             "description": "纯乱码输入",
    #         },
    #         {
    #             "id": "abn_03",
    #             "type": "binary",
    #             "input": "\\x00\\x01\\x02\\xFF" * 50,
    #             "expected_level": 2,
    #             "description": "二进制内容输入",
    #         },
    #         {
    #             "id": "abn_04",
    #             "type": "too_long",
    #             "input": "请分析以下需求文档并生成测试用例：\n\n" + long_text,
    #             "expected_level": 2,
    #             "description": "超长文档（约50万字符）",
    #         },
    #         {
    #             "id": "abn_05",
    #             "type": "malformed",
    #             "input": "请分析以下需求文档并生成测试用例：\n\n" + messy_text,
    #             "expected_level": 2,
    #             "description": "Markdown 格式错乱",
    #         },
    #         {
    #             "id": "abn_06",
    #             "type": "not_requirement",
    #             "input": (
    #                 "请分析以下内容并生成测试用例：\n\n"
    #                 "第一章 陨落的天才\n"
    #                 "夜，深了。萧炎躺在床上，翻来覆去睡不着。\n"
    #                 "三年前，他还是公认的修炼天才...\n"
    #                 "（此处省略 2000 字玄幻小说内容）"
    #             ),
    #             "expected_level": 3,
    #             "description": "传入小说而非需求文档",
    #         },
    #     ]
    #
    # ============================================================
    # 步骤 2: 逐个测试
    # ============================================================
    # results = []
    # level_counts = {3: 0, 2: 0, 1: 0, 0: 0}
    # total_score = 0.0
    #
    # for sample in samples:
    #     sample_id = sample["id"]
    #     print(f"  测试 {sample_id} ({sample['type']})...")
    #
    #     try:
    #         # 调用 Agent，设置超时
    #         result = agent.run(sample["input"])
    #
    #         # 自动判定级别
    #         level = _classify_abnormal_result(result)
    #
    #     except Exception as e:
    #         # Agent 崩溃
    #         level = 0
    #         result = f"[CRASH] {type(e).__name__}: {str(e)[:200]}"
    #
    #     # 统计
    #     level_counts[level] += 1
    #     sample_score = level / 3.0
    #     total_score += sample_score
    #
    #     results.append({
    #         "sample_id": sample_id,
    #         "type": sample["type"],
    #         "level": level,
    #         "score": round(sample_score, 2),
    #         "result_preview": str(result)[:300],
    #     })
    #
    #     time.sleep(1)  # 避免 API 限流
    #
    # ============================================================
    # 步骤 3: 计算分数并返回
    # ============================================================
    # total = len(samples)
    # score = total_score / total if total > 0 else 0.0
    # return {
    #     "score": round(score, 2),
    #     "total": total,
    #     "level_distribution": level_counts,
    #     "results": results,
    # }
    pass


# ================================================================
# TODO 11.2: _classify_abnormal_result — 自动判定异常处理级别
# ================================================================
# 辅助函数：根据 Agent 的输出自动判定处理级别（3/2/1/0）。
#
# 步骤：
#   1. 检查崩溃信号（最高优先级）：
#      - "Traceback (most recent call last)" in result
#      - "Error:" in result
#      - result 中异常信息占比 > 50%
#      → 级别 1
#
#   2. 检查完美处理信号：
#      - 包含明确拒绝/提示："无法"、"不支持"、"请提供"、"不是需求"
#      - 包含错误说明："格式错误"、"无法解析"、"不包含"
#      → 级别 3
#
#   3. 检查降级处理信号：
#      - result 中有 | --- | --- | 表格（说明 Agent 仍尝试生成了用例）
#      - result 中有 feature / type / description 字段
#      - result 长度 > 500 字符且有结构化内容
#      → 级别 2
#
#   4. 兜底：
#      - 以上都不匹配 → 级别 2（保守估计）
#
#   5. 返回 int（0-3）
#
# 提示：
#   - 这个函数是启发式的，不要求 100% 准确
#   - 后续可以升级为 LLM 判断（但默认用规则，省 Token）
#
def _classify_abnormal_result(result: str) -> int:
    """
    自动判定异常输入的处理级别。

    参数：
    - result: Agent 的输出文本

    返回：
    - 0-3 的级别整数
    """
    # ============================================================
    # 步骤 1: 检查崩溃信号 → 级别 1
    # ============================================================
    # crash_signals = [
    #     "Traceback (most recent call last)",
    #     "Error:",
    #     "Exception:",
    #     "APIError",
    #     "RateLimitError",
    # ]
    # if any(sig in result for sig in crash_signals):
    #     return 1
    #
    # ============================================================
    # 步骤 2: 检查完美处理信号 → 级别 3
    # ============================================================
    # good_signals = [
    #     "无法", "不支持", "请提供", "不是需求",
    #     "不是有效的", "无法解析", "不包含",
    #     "格式错误", "无内容", "内容为空",
    #     "无法识别", "无法处理",
    # ]
    # if any(sig in result for sig in good_signals):
    #     return 3
    #
    # ============================================================
    # 步骤 3: 检查降级处理信号 → 级别 2
    # ============================================================
    # # 有表格输出 = 尝试生成了用例
    # if "|" in result and "---" in result:
    #     return 2
    # # 有结构化字段
    # if any(kw in result for kw in ["feature", "type", "description"]):
    #     return 2
    # # 输出较长（>500 字符）= 至少尝试了
    # if len(result) > 500:
    #     return 2
    #
    # ============================================================
    # 步骤 4: 兜底 → 级别 2
    # ============================================================
    # return 2
    pass


# ================================================================
# TODO 11.3: eval_tool_failure — 工具故障恢复评测
# ================================================================
# 模拟工具返回 error，测试 Agent 的降级和恢复能力。
#
# 现有工具链中哪些环节会出错？
#   - parse_prd: 文件不存在 → error
#   - analyze_requirements: 输入格式错误 → error
#   - extract_features: 无匹配结果 → 返回空列表（不算 error，但算"无结果"）
#   - extract_rules: 同上
#   - generate_cases: features 或 rules 为空 → 可能返回空用例列表
#   - format_output: cases 为空 → 可能返回空表格
#
# 步骤：
#   1. 设计故障场景（3-4 个）：
#      a. 文件不存在：传入不存在的 file_path
#         → Agent 应该：识别错误，尝试用 content 参数代替，或提示用户
#      b. 中间工具返回空结果：extract_features 返回空列表
#         → Agent 应该：检查结果，决定是否重试或跳过
#      c. 上游工具失败后下游是否还能继续：
#         如果 parse_prd 失败，Agent 是否还能尝试做点什么？
#         → Agent 应该：不放弃，尝试用原始文本继续
#      d. 重复调用导致链路断裂：
#         同一个工具连续报错 2 次
#         → Agent 应该：停止循环，给出诊断信息
#
#   2. 实现故障注入的 2 种方式：
#      方式 A：直接在 agent.run() 之前修改工具注册表
#        - 暂存原始的工具函数引用
#        - 用 wrapper 替换目标工具函数
#        - wrapper 内部：第 1 次调用返回 error，后续恢复正常
#        - 调用 agent.run() 后恢复原始函数
#
#      方式 B：准备特殊的需求文档，内容会让工具返回 error
#        - 例如 file_path 指向不存在的文件
#        - 例如 prd_json 格式故意写错
#        - 这种方式更简单但不够灵活
#
#     推荐：先实现方式 A（更可控），后续补充方式 B（更真实）
#
#   3. 对每个故障场景：
#      a. 注入故障
#      b. 调用 agent.run(normal_input)
#      c. 收集结果和 trace
#      d. 恢复原始工具
#
#   4. 从 trace 中分析 Agent 的恢复行为：
#      - 是否重试了出错工具？（用修正后的参数）
#      - 是否换了替代方案？（如 file_path → content）
#      - 是否跳过了故障工具继续执行？
#      - 是否直接终止？
#
#   5. 打分：
#      - 成功恢复（重试成功或用替代方案完成）→ 1.0
#      - 优雅降级（跳过故障但给出了部分结果）→ 0.7
#      - 返回错误信息但未尝试恢复 → 0.3
#      - 直接崩溃 → 0.0
#      - 总分 = 各场景的平均分
#
#   6. 返回：
#      {
#          "score": float,
#          "total": int,
#          "results": [{scenario, score, recovery_action, trace_summary}, ...],
#      }
#
# 提示：
#   - 故障注入需要修改 tool_registry，测试完后务必恢复
#   - 如果 Agent 的 tool_registry 不好修改，可以改用方式 B
#   - 这是一个进阶评测，先实现基本版本即可
#
def eval_tool_failure(agent) -> dict:
    """
    评测 Agent 在工具故障时的恢复能力。

    参数：
    - agent: SimpleAgent 实例

    返回：
    - {"score": float, "total": int, "results": [...]}
    """
    # ============================================================
    # 步骤 1: 定义故障场景
    # ============================================================
    # 使用正常的需求文档作为输入（01_login.md）
    # normal_input_file = "data/eval/requirements/01_login.md"
    # normal_text = Path(normal_input_file).read_text(encoding="utf-8")
    # user_input = (
    #     f"请分析以下需求文档并生成测试用例。\n"
    #     f"文件路径: {normal_input_file}\n\n{normal_text}"
    # )
    #
    # ============================================================
    # 步骤 2: 方式 A — 工具 wrapper 故障注入
    # ============================================================
    # 示例：让 parse_prd 第一次调用返回 error
    #
    # from src.tools.setup import create_test_tool_registry
    #
    # def make_faulty_parse_prd(original_func):
    #     \"\"\"返回一个 wrapper：第一次调用报错，后续正常\"\"\"
    #     call_count = [0]  # 用 list 实现闭包可变计数
    #
    #     def wrapper(*args, **kwargs):
    #         call_count[0] += 1
    #         if call_count[0] == 1:
    #             return {"error": "模拟故障：文件读取失败"}
    #         return original_func(*args, **kwargs)
    #
    #     return wrapper
    #
    # # 注入故障
    # original_parse = agent.tool_registry.get("parse_prd")
    # agent.tool_registry.register("parse_prd", ..., func=make_faulty_parse_prd(original_parse))
    #
    # # 调用 Agent
    # try:
    #     result = agent.run(user_input)
    # except Exception as e:
    #     result = f"[CRASH] {e}"
    #
    # # 恢复原始工具
    # agent.tool_registry.register("parse_prd", ..., func=original_parse)
    #
    # ============================================================
    # 步骤 3: 分析恢复行为（从 trace 或 result 中）
    # ============================================================
    # 检查 trace 中的后续步骤：
    #   - 是否重试了 parse_prd？
    #   - 是否换了 content 参数？
    #   - 是否直接终止？
    #
    # ============================================================
    # 步骤 4: 打分并返回
    # ============================================================
    pass


# ================================================================
# TODO 11.4: run_robustness_eval — 汇总鲁棒性评测
# ================================================================
# 汇总异常输入 + 工具故障恢复。
#
# 步骤：
#   1. 依次调用 eval_abnormal_input、eval_tool_failure
#      每个调用包裹 try/except
#
#   2. 计算鲁棒性综合分：
#      - abnormal_score = abnormal 结果中的 score
#      - failure_score = tool_failure 结果中的 score
#      - overall = abnormal_score × 0.5 + failure_score × 0.5
#        如果 tool_failure 未实现（返回空），权重全给 abnormal
#
#   3. 生成文本报告
#
#   4. 返回：
#      {
#          "overall_score": float,
#          "dimensions": {
#              "abnormal_input": {...},
#              "tool_failure": {...},
#          },
#          "report": "格式化的文本报告",
#      }
#
def run_robustness_eval(agent) -> dict:
    """
    汇总所有鲁棒性评测。

    参数：
    - agent: SimpleAgent 实例

    返回：
    - {"overall_score": float, "dimensions": {...}, "report": "..."}
    """
    # ============================================================
    # 步骤 1: 运行异常输入评测
    # ============================================================
    # print("→ 运行异常输入评测...")
    # try:
    #     abnormal_result = eval_abnormal_input(agent)
    #     print(f"  异常输入: {abnormal_result['score']:.2f}")
    # except Exception as e:
    #     abnormal_result = {"score": 0, "error": str(e)}
    #     print(f"  异常输入异常: {e}")
    #
    # ============================================================
    # 步骤 2: 运行工具故障评测
    # ============================================================
    # print("→ 运行工具故障评测...")
    # try:
    #     failure_result = eval_tool_failure(agent)
    #     print(f"  工具故障: {failure_result['score']:.2f}")
    # except Exception as e:
    #     failure_result = {"score": 0, "error": str(e)}
    #     print(f"  工具故障异常: {e}")
    #
    # ============================================================
    # 步骤 3: 计算综合分
    # ============================================================
    # abnormal_score = abnormal_result.get("score", 0)
    # failure_score = failure_result.get("score", 0)
    #
    # # 如果 tool_failure 未实现，权重全给 abnormal
    # if "error" in failure_result and failure_result["error"]:
    #     overall = abnormal_score
    # else:
    #     overall = abnormal_score * 0.5 + failure_score * 0.5
    #
    # ============================================================
    # 步骤 4: 生成报告并返回
    # ============================================================
    # report_lines = [
    #     "=" * 50,
    #     "鲁棒性评测报告",
    #     "=" * 50,
    #     f"综合得分: {overall:.2f}",
    #     f"  异常输入: {abnormal_score:.2f}",
    #     f"  工具故障: {failure_score:.2f}",
    # ]
    #
    # return {
    #     "overall_score": round(overall, 2),
    #     "dimensions": {
    #         "abnormal_input": abnormal_result,
    #         "tool_failure": failure_result,
    #     },
    #     "report": "\n".join(report_lines),
    # }
    pass
