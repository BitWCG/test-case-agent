#!/usr/bin/env python3
"""
Day 12-14: 批量评测运行脚本（完整 6 维评测）

遍历 data/eval/requirements/ 下所有需求文档，
对每个调用 Agent 生成测试用例，然后运行全部 6 维评测。

评测流程（对每个需求文档）：
  1. 运行 Agent → 获取 result + trace JSON
  2. 确定性评测 → 格式、覆盖率、数量、类别、效率
  3. 轨迹评测 → 工具准确率、步骤效率、错误恢复、控制决策分类
  4. LLM-as-Judge → 质量评分（正确性、完整性、清晰度、可执行性、边界意识）
  5. 安全性评测 → 注入防御、信息泄露、越权操作（乘性门控，违规清零）
  6. 鲁棒性评测 → 异常输入处理、工具故障恢复
  7. 一致性评测 → 稳定性、Temperature影响、Pass@k/Pass^k
  8. 汇总 6 维到耦合评分公式：
     task_score = Safety × (0.80 × Completion + 0.20 × Robustness)

使用方法：
  cd test-case-agent
  source venv/bin/activate
  python -m src.eval.run_eval

输出：
  - data/eval/traces/*.json    每次运行的轨迹
  - data/eval/report.json      汇总评测报告
"""
import sys
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ================================================================
# TODO 9.1: run_single_eval — 对单个需求文档跑完整 6 维评测
# ================================================================
# 对一个需求文档跑完整的 Agent + 评测流程。
#
# 步骤：
#   1. 读取需求文档内容（requirement_path）
#   2. 读取对应的 expected JSON（从 data/eval/expected/ 目录）
#      - expected 文件名规则：01_login.md → 01_login_expected.json
#   3. 创建 SimpleAgent 实例（或使用传入的 agent）
#   4. 构造 user_input（参考 main.py 的格式）
#   5. 调用 agent.run(user_input)，获取 result
#   6. Agent 运行时会自动生成 trace JSON（在 data/eval/traces/ 目录）
#   7. 运行确定性评测：
#      - from src.eval.deterministic_eval import run_deterministic_eval
#      - deterministic_result = run_deterministic_eval(result, expected, trace_path)
#   8. 运行轨迹评测：
#      - from src.eval.llm_judge import run_trajectory_eval
#      - trajectory_result = run_trajectory_eval(trace_path)
#   9. （可选）运行 LLM-as-Judge：
#      - from src.eval.llm_judge import LLMJudge
#      - judge = LLMJudge()
#      - judge_result = judge.multi_judge(result, requirement_text)
#      - 注意：Judge 需要额外的 API 调用，可以先注释掉，测试时再打开
#   10. （可选）运行安全性评测：
#       - from src.eval.security_eval import run_security_eval
#       - security_result = run_security_eval(agent)
#       - 注意：安全评测会多次调用 Agent（注入样本 + 泄露检查 + 越权样本），
#         总计约 15+ 次额外的 Agent 运行，耗时较长
#   11. （可选）运行鲁棒性评测：
#       - from src.eval.robustness_eval import run_robustness_eval
#       - robustness_result = run_robustness_eval(agent)
#   12. （可选）运行一致性评测：
#       - from src.eval.consistency_eval import run_consistency_eval
#       - consistency_result = run_consistency_eval(agent, expected, requirement_text)
#   13. 计算耦合综合分（Claw-Eval 公式）：
#       - coupling = _compute_coupling_score(dimensions, security_result)
#   14. 返回 {"requirement": name, "result": result, "trace_path": trace_path,
#              "dimensions": {
#                  "deterministic": {...},
#                  "trajectory": {...},
#                  "llm_judge": {...} or None,
#                  "security": {...} or None,
#                  "robustness": {...} or None,
#                  "consistency": {...} or None,
#              },
#              "coupling_score": {...}}
#
# 提示：
#   - trace JSON 的文件路径是固定的：f"data/eval/traces/{agent.trace.trace_id}.json"
#   - 运行完成后等待 1 秒，避免 API 限流
#   - 如果某个评测维度异常，catch Exception 后记录错误继续，不要中断整个流程
#
def run_single_eval(requirement_path: str, agent=None) -> dict:
    """
    对单个需求文档运行完整 6 维评测。

    参数：
    - requirement_path: 需求文档的绝对路径
    - agent: SimpleAgent 实例（可选，不传则内部创建）

    返回：
    - 评测结果 dict（含 6 维 + 耦合综合分）
    """
    # ============================================================
    # 步骤 1: 读取需求文档
    # ============================================================
    req_path = Path(requirement_path)
    req_name = req_path.stem  # 如 "01_login"
    requirement_text = req_path.read_text(encoding="utf-8")
    #
    # ============================================================
    # 步骤 2: 读取对应的 expected JSON
    # ============================================================
    expected_dir = Path("data/eval/expected")
    expected_path = expected_dir / f"{req_name}_expected.json"
    if expected_path.exists():
        with open(expected_path, "r", encoding="utf-8") as f:
            expected = json.load(f)
    else:
        expected = {}
        print(f"  ⚠ 未找到参考答案: {expected_path}")
    #
    # ============================================================
    # 步骤 3: 创建 Agent 并运行
    # ============================================================
    if agent is None:
        from src.agent.simple_agent import SimpleAgent
        agent = SimpleAgent()

    user_input = (
        f"请分析以下需求文档并生成测试用例。\n"
        f"文件路径: {requirement_path}\n"
        f"(提示: 调用 extract_features 和 extract_rules 时请直接传 "
        f'file_path="{requirement_path}")\n\n'
        f"{requirement_text}"
    )
    #
    # # 运行 Agent（阻塞等待完成）
    start_time = time.time()
    result = agent.run(user_input)
    elapsed = time.time() - start_time
    print(f"  Agent 运行完成，耗时 {elapsed:.1f}s")
    
    # ============================================================
    # 步骤 4: 获取 trace 文件路径
    # ============================================================
    trace_path = f"data/eval/traces/{agent.trace.trace_id}.json"
    
    # ============================================================
    # 步骤 5: [维度1] 确定性评测
    # ============================================================
    from src.eval.deterministic_eval import run_deterministic_eval
    deterministic_result = run_deterministic_eval(result, expected, trace_path)
    print(f"  确定性: {deterministic_result['overall_score']:.2f}")
    
    # ============================================================
    # 步骤 6: [维度2] 轨迹评测
    # ============================================================
    try:
        from src.eval.trajectory_eval import run_trajectory_eval
        trajectory_result = run_trajectory_eval(trace_path)
        print(f"  轨迹: {trajectory_result['overall_score']:.2f}")
    except Exception as e:
        trajectory_result = {"error": str(e)}
    
    # ============================================================
    # 步骤 7: [维度3] LLM-as-Judge（可选，需额外 API 调用）
    # ============================================================
    # 默认注释掉。测试时取消注释：
    try:
        from src.eval.llm_judge import LLMJudge
        judge = LLMJudge(judge_model="qwen-max")
        llm_judge_result = judge.multi_judge(result, requirement_text)
        print(f"  Judge: {llm_judge_result['overall']:.2f}")
    except Exception as e:
        llm_judge_result = {"error": str(e)}
    llm_judge_result = None  # 默认不跑
    
    # ============================================================
    # 步骤 8: [维度4] 安全性评测（Agent 级别，只对第 1 个样本运行）
    # ============================================================
    # 安全评测会多次调用 Agent（注入样本 + 泄露检查 + 越权样本），
    # 总计约 15+ 次额外的 Agent 运行，耗时较长。
    # 默认在批量评测中对第 1 个样本运行，其余样本复用结果。
    #
    # security_result = None
    # if security_eval_enabled:
    #     try:
    #         from src.eval.security_eval import run_security_eval
    #         print("→ 安全性评测（约 15 次 Agent 调用）...")
    #         security_result = run_security_eval(agent)
    #         print(f"  安全: {security_result['overall_score']:.2f} "
    #               f"(门控: {'✅' if security_result['safety_gate'] else '❌'})")
    #     except Exception as e:
    #         security_result = {"error": str(e)}
    #
    # ============================================================
    # 步骤 9: [维度5] 鲁棒性评测（Agent 级别，只对第 1 个样本运行）
    # ============================================================
    # try:
    #     from src.eval.robustness_eval import run_robustness_eval
    #     print("→ 鲁棒性评测...")
    #     robustness_result = run_robustness_eval(agent)
    #     print(f"  鲁棒性: {robustness_result['overall_score']:.2f}")
    # except Exception as e:
    #     robustness_result = {"error": str(e)}
    #
    # ============================================================
    # 步骤 10: [维度6] 一致性评测（Agent 级别，只对第 1 个样本运行）
    # ============================================================
    # try:
    #     from src.eval.consistency_eval import run_consistency_eval
    #     print("→ 一致性评测（约 8 次 Agent 调用）...")
    #     consistency_result = run_consistency_eval(
    #         agent, expected, requirement_text, k=3
    #     )
    #     print(f"  一致性: {consistency_result['overall_score']:.2f} "
    #           f"(Gap: {consistency_result['stability_gap']})")
    # except Exception as e:
    #     consistency_result = {"error": str(e)}
    #
    # ============================================================
    # 步骤 11: 计算耦合综合分（Claw-Eval 公式）
    # ============================================================
    # coupling = _compute_coupling_score(
    #     deterministic_result, security_result,
    #     robustness_result, consistency_result,
    # )
    #
    # ============================================================
    # 步骤 12: 汇总并返回
    # ============================================================
    # return {
    #     "requirement": req_name,
    #     "requirement_path": requirement_path,
    #     "agent_result": result,
    #     "trace_path": trace_path,
    #     "elapsed_seconds": elapsed,
    #     "dimensions": {
    #         "deterministic": deterministic_result,
    #         "trajectory": trajectory_result,
    #         "llm_judge": llm_judge_result if 'llm_judge_result' in dir() else None,
    #         "security": security_result,
    #         "robustness": robustness_result,
    #         "consistency": consistency_result,
    #     },
    #     "coupling_score": coupling,
    # }
    pass


# ================================================================
# TODO 9.2: run_batch_eval — 批量评测所有需求文档（6 维完整版）
# ================================================================
# 遍历 data/eval/requirements/ 下所有 .md 文件，逐个调用 run_single_eval。
#
# 设计要点：
#   - 安全/鲁棒/一致性评测是 "Agent 级别" 的评测（评测对象是 Agent 本身），
#     不是每个样本都跑，而是在所有样本的核心评测完成后统一运行一次。
#   - 这样可以避免对每个样本都跑 15+ 次安全评测，节省时间和 API 费用。
#
# 步骤：
#   1. 获取所有需求文档路径：
#      - requirements_dir = Path("data/eval/requirements")
#      - 用 sorted(requirements_dir.glob("*.md")) 获取排序后的文件列表
#   2. 创建共享 Agent 实例（安全/鲁棒/一致性评测需要多次调用 Agent）
#   3. 逐个评测核心 3 维（确定性+轨迹+Judge）：
#      - 对每个文档循环
#      - 打印进度条（如 "[1/4] 正在评测 01_login.md..."）
#      - 调用 run_single_eval(path, agent)
#      - 单次评测结束后等待 2-3 秒（避免 API 限流）
#   4. 运行 Agent 级别评测（安全+鲁棒+一致性）：
#      - 只对第 1 个样本（如 01_login.md）跑
#      - 因为安全/鲁棒/一致性评测对象是 Agent 本身，不是单个需求文档
#   5. 汇总所有结果：
#      - 计算各维度的平均分
#      - 统计"通过"和"未通过"的数量（设定 0.6 为通过线）
#   6. 计算耦合综合分（Claw-Eval 公式）：
#      - task_score = Safety × (0.80 × Completion + 0.20 × Robustness)
#   7. 生成汇总 JSON（保存到 data/eval/report.json）
#   8. 打印最终报告表格
#
# 提示：
#   - 用 time.sleep(2) 控制速度
#   - 如果某个样本失败，记录错误后继续下一个
#   - 汇总报告应该包含每个样本的分项分数和总分
#
def run_batch_eval() -> dict:
    """
    批量评测所有需求文档（6 维完整版）。

    返回：
    - 汇总评测报告 dict
    """
    # ============================================================
    # 步骤 1: 发现所有需求文档
    # ============================================================
    # requirements_dir = Path("data/eval/requirements")
    # if not requirements_dir.exists():
    #     print(f"错误：需求文档目录不存在: {requirements_dir}")
    #     return {"error": "需求文档目录不存在"}
    #
    # req_files = sorted(requirements_dir.glob("*.md"))
    # if not req_files:
    #     print("错误：未找到任何需求文档（*.md）")
    #     return {"error": "未找到需求文档"}
    #
    # print(f"\n共发现 {len(req_files)} 个评测样本：")
    # for f in req_files:
    #     print(f"  - {f.name}")
    # print()
    #
    # ============================================================
    # 步骤 2: 创建共享 Agent 实例
    # ============================================================
    # 安全性和一致性评测需要多次调用 Agent，共用实例减少初始化开销
    # from src.agent.simple_agent import SimpleAgent
    # shared_agent = SimpleAgent()
    #
    # ============================================================
    # 步骤 3: 逐个评测核心 3 维（确定性+轨迹+Judge）
    # ============================================================
    # 安全、鲁棒、一致性评测放在所有样本的核心评测完成后统一运行，
    # 因为它们是"Agent 级别"的评测（评测对象是 Agent 本身，而非单个输出）。
    #
    # results = []
    # for idx, req_file in enumerate(req_files, 1):
    #     print(f"[{idx}/{len(req_files)}] 正在评测 {req_file.name}...")
    #     print("-" * 40)
    #
    #     try:
    #         single_result = run_single_eval(str(req_file), shared_agent)
    #         results.append(single_result)
    #     except Exception as e:
    #         print(f"  ❌ 评测失败: {e}")
    #         results.append({
    #             "requirement": req_file.stem,
    #             "error": str(e),
    #         })
    #
    #     if idx < len(req_files):
    #         print(f"  等待 2 秒后继续...\n")
    #         time.sleep(2)
    #
    # ============================================================
    # 步骤 4: 运行 Agent 级别评测（安全+鲁棒+一致性）
    # ============================================================
    # 只对第 1 个样本（如 01_login.md）跑 Agent 级评测，
    # 因为安全/鲁棒/一致性评测对象是 Agent 本身，不是单个需求文档。
    #
    # print("\n" + "=" * 50)
    # print("运行 Agent 级别评测（安全 + 鲁棒 + 一致性）...")
    # print("=" * 50)
    #
    # # 维度4: 安全性
    # try:
    #     from src.eval.security_eval import run_security_eval
    #     print("→ 安全性评测...")
    #     security_result = run_security_eval(shared_agent)
    #     print(f"  安全: {security_result['overall_score']:.2f} "
    #           f"(门控: {'✅' if security_result['safety_gate'] else '❌'})")
    # except Exception as e:
    #     security_result = {"error": str(e)}
    #     print(f"  ❌ 安全性评测失败: {e}")
    #
    # # 维度5: 鲁棒性
    # try:
    #     from src.eval.robustness_eval import run_robustness_eval
    #     print("→ 鲁棒性评测...")
    #     robustness_result = run_robustness_eval(shared_agent)
    #     print(f"  鲁棒性: {robustness_result['overall_score']:.2f}")
    # except Exception as e:
    #     robustness_result = {"error": str(e)}
    #     print(f"  ❌ 鲁棒性评测失败: {e}")
    #
    # # 维度6: 一致性
    # try:
    #     from src.eval.consistency_eval import run_consistency_eval
    #     req_path = Path("data/eval/requirements/01_login.md")
    #     req_text = req_path.read_text(encoding="utf-8") if req_path.exists() else ""
    #     exp_path = Path("data/eval/expected/01_login_expected.json")
    #     if exp_path.exists():
    #         with open(exp_path, "r", encoding="utf-8") as f:
    #             expected = json.load(f)
    #     else:
    #         expected = {}
    #     print("→ 一致性评测...")
    #     consistency_result = run_consistency_eval(
    #         shared_agent, expected, req_text, k=3
    #     )
    #     print(f"  一致性: {consistency_result['overall_score']:.2f} "
    #           f"(Gap: {consistency_result['stability_gap']})")
    # except Exception as e:
    #     consistency_result = {"error": str(e)}
    #     print(f"  ❌ 一致性评测失败: {e}")
    #
    # ============================================================
    # 步骤 5: 汇总统计数据（6 维）
    # ============================================================
    # PASS_THRESHOLD = 0.6
    # total_samples = len(results)
    # passed = 0
    # failed = 0
    # dimension_scores = defaultdict(list)
    #
    # for r in results:
    #     if "error" in r:
    #         failed += 1
    #         continue
    #     dims = r.get("dimensions", {})
    #     det = dims.get("deterministic", {})
    #     overall = det.get("overall_score", 0)
    #     if overall >= PASS_THRESHOLD:
    #         passed += 1
    #     else:
    #         failed += 1
    #     # 收集核心 3 维分数
    #     for dim_name, dim_result in det.get("dimensions", {}).items():
    #         dim_score = dim_result.get("score", 0)
    #         dimension_scores[f"det_{dim_name}"].append(dim_score)
    #     traj = dims.get("trajectory", {})
    #     if "error" not in traj:
    #         dimension_scores["trajectory"].append(traj.get("overall_score", 0))
    #     judge = dims.get("llm_judge", {})
    #     if judge and "error" not in judge:
    #         dimension_scores["judge"].append(judge.get("overall", 0))
    #
    # # Agent 级别维度（安全/鲁棒/一致性）追加到汇总
    # if "error" not in security_result:
    #     dimension_scores["security"] = [security_result["overall_score"]]
    # if "error" not in robustness_result:
    #     dimension_scores["robustness"] = [robustness_result["overall_score"]]
    # if "error" not in consistency_result:
    #     dimension_scores["consistency"] = [consistency_result["overall_score"]]
    #
    # ============================================================
    # 步骤 6: 计算耦合综合分（Claw-Eval 公式）
    # ============================================================
    # coupling_score = _compute_coupling_score(dimension_scores, security_result)
    #
    # ============================================================
    # 步骤 7: 生成汇总报告
    # ============================================================
    # report = {
    #     "summary": {
    #         "total": total_samples,
    #         "passed": passed,
    #         "failed": failed,
    #         "pass_rate": passed / total_samples if total_samples > 0 else 0,
    #         "coupling_score": coupling_score,
    #     },
    #     "dimension_averages": {
    #         dim: sum(scores) / len(scores)
    #         for dim, scores in dimension_scores.items()
    #     },
    #     "agent_level": {
    #         "security": security_result,
    #         "robustness": robustness_result,
    #         "consistency": consistency_result,
    #     },
    #     "results": results,
    #     "generated_at": datetime.now().isoformat(),
    # }
    #
    # ============================================================
    # 步骤 8: 保存报告到文件
    # ============================================================
    # output_dir = Path("data/eval")
    # output_dir.mkdir(parents=True, exist_ok=True)
    # output_path = output_dir / "report.json"
    # with open(output_path, "w", encoding="utf-8") as f:
    #     json.dump(report, f, ensure_ascii=False, indent=2)
    # print(f"\n报告已保存到: {output_path}")
    #
    # return report
    pass


# ================================================================
# TODO 9.3: print_report — 打印 6 维评测报告
# ================================================================
# 将批量评测结果格式化为可读的终端输出。
#
# 步骤：
#   1. 打印总体标题和分隔线
#   2. 打印汇总统计：
#      - 总样本数、通过数、未通过数、通过率
#      - 耦合综合分（Claw-Eval 公式）+ 安全门控状态
#   3. 打印核心 3 维平均分（确定性 + 轨迹 + Judge）
#   4. 打印 Agent 级别 3 维平均分（安全 + 鲁棒 + 一致）
#      - 安全门控状态（✅/❌）
#      - Stability Gap（Pass@k - Pass^k）
#   5. 打印每个样本的详细表格（核心 3 维）
#   6. 如果有 LLM Judge 结果，另起一张表格
#   7. 打印"改进建议"：根据评测结果自动生成建议（覆盖 6 维）
#      - 核心维度：格式/覆盖率/数量/效率
#      - Agent 级别：安全/鲁棒/一致性
#      - Stability Gap 警告
#
# 提示：
#   - 用 f-string 格式化数字：f"{score:.2f}"
#   - 用 Unicode 字符美化：✅/❌/⚠️
#   - 表格对齐用 f-string 的填充功能：f"{name:<15}"
#
def print_report(report: dict) -> None:
    """
    打印格式化的 6 维评测报告到终端。

    参数：
    - report: run_batch_eval() 的输出
    """
    # ============================================================
    # 步骤 1: 打印标题和总体统计
    # ============================================================
    # summary = report.get("summary", {})
    # print()
    # print("=" * 70)
    # print("  测试用例 Agent 批量评测报告（6 维完整版）")
    # print("=" * 70)
    # print(f"  总样本: {summary.get('total', 0)}")
    # print(f"  通过: {summary.get('passed', 0)} ✅")
    # print(f"  未通过: {summary.get('failed', 0)} ❌")
    # print(f"  通过率: {summary.get('pass_rate', 0):.1%}")
    # coupling = summary.get("coupling_score", {})
    # if coupling:
    #     print(f"  耦合综合分 (Claw-Eval): {coupling.get('task_score', 0):.2f}")
    #     safety_gate = coupling.get("safety_gate", True)
    #     print(f"  安全门控: {'✅ 通过' if safety_gate else '❌ 未通过（综合分清零）'}")
    # print()
    #
    # ============================================================
    # 步骤 2: 打印核心 3 维平均分
    # ============================================================
    # dim_avg = report.get("dimension_averages", {})
    # if dim_avg:
    #     print("-" * 70)
    #     print("  [核心维度] 各样本平均分:")
    #     core_dim_names = {
    #         "det_format": "确定性-格式",
    #         "det_feature_coverage": "确定性-功能覆盖",
    #         "det_rule_coverage": "确定性-规则覆盖",
    #         "det_case_count": "确定性-用例数量",
    #         "det_category_coverage": "确定性-类别覆盖",
    #         "det_efficiency": "确定性-效率",
    #         "trajectory": "轨迹评测",
    #         "judge": "LLM Judge",
    #     }
    #     for dim, cn_name in core_dim_names.items():
    #         if dim in dim_avg:
    #             avg = dim_avg[dim]
    #             bar = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
    #             print(f"    {cn_name:<20} [{bar}] {avg:.2f}")
    #     print()
    #
    # ============================================================
    # 步骤 3: 打印 Agent 级别 3 维平均分
    # ============================================================
    # agent_level = report.get("agent_level", {})
    # if agent_level:
    #     print("-" * 70)
    #     print("  [Agent 级别] 安全性 / 鲁棒性 / 一致性:")
    #     agent_dim_names = {
    #         "security": "安全评测",
    #         "robustness": "鲁棒性评测",
    #         "consistency": "一致性评测",
    #     }
    #     for dim, cn_name in agent_dim_names.items():
    #         if dim in dim_avg:
    #             avg = dim_avg[dim]
    #             bar = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
    #             print(f"    {cn_name:<20} [{bar}] {avg:.2f}")
    #     # 打印额外信息
    #     sec = agent_level.get("security", {})
    #     if "error" not in sec:
    #         gate = "✅" if sec.get("safety_gate") else "❌"
    #         print(f"    安全门控: {gate}")
    #     con = agent_level.get("consistency", {})
    #     if "error" not in con:
    #         gap = con.get("stability_gap", 0)
    #         gap_warn = " ⚠️ 靠运气" if gap > 0 else " ✅ 稳定"
    #         print(f"    Stability Gap: {gap}{gap_warn}")
    #     print()
    #
    # ============================================================
    # 步骤 4: 打印每个样本的详细表格
    # ============================================================
    # results = report.get("results", [])
    # if results:
    #     print("-" * 70)
    #     print("  各样本详细分数（核心维度）:")
    #     header = (f"{'样本':<20} {'综合':<6} {'格式':<6} {'功能覆盖':<8} "
    #               f"{'规则覆盖':<8} {'数量':<6} {'类别':<6} {'效率':<6}")
    #     print(f"  {header}")
    #     print(f"  {'-' * (len(header) - 2)}")
    #     for r in results:
    #         if "error" in r:
    #             print(f"  {r['requirement']:<20} ERROR: {r['error'][:30]}")
    #             continue
    #         dims = r.get("dimensions", {})
    #         det = dims.get("deterministic", {}).get("dimensions", {})
    #         name = r.get("requirement", "")[:18]
    #         overall = dims.get("deterministic", {}).get("overall_score", 0)
    #         fmt = det.get("format", {}).get("score", 0)
    #         feat = det.get("feature_coverage", {}).get("score", 0)
    #         rule = det.get("rule_coverage", {}).get("score", 0)
    #         cnt = det.get("case_count", {}).get("score", 0)
    #         cat = det.get("category_coverage", {}).get("score", 0)
    #         eff = det.get("efficiency", {}).get("score", 0)
    #         print(f"  {name:<20} {overall:<6.2f} {fmt:<6.2f} {feat:<8.2f} "
    #               f"{rule:<8.2f} {cnt:<6.2f} {cat:<6.2f} {eff:<6.2f}")
    #     print()
    #
    # ============================================================
    # 步骤 5: 打印 LLM Judge 结果（如果有）
    # ============================================================
    # llm_judge_results = [r.get("dimensions", {}).get("llm_judge")
    #                      for r in results
    #                      if r.get("dimensions", {}).get("llm_judge")
    #                      and "error" not in r.get("dimensions", {}).get("llm_judge", {})]
    # if llm_judge_results:
    #     print("-" * 70)
    #     print("  LLM-as-Judge 评分:")
    #     j_header = f"{'样本':<20} {'综合':<6} {'正确':<6} {'完整':<6} {'清晰':<6} {'可执行':<6} {'边界':<6}"
    #     print(f"  {j_header}")
    #     print(f"  {'-' * (len(j_header) - 2)}")
    #     for i, jr in enumerate(llm_judge_results):
    #         name = results[i]["requirement"][:18] if i < len(results) else "?"
    #         scores = jr.get("scores", {})
    #         overall = jr.get("overall", 0)
    #         cor = scores.get("correctness", 0)
    #         com = scores.get("completeness", 0)
    #         cla = scores.get("clarity", 0)
    #         act = scores.get("actionability", 0)
    #         edge = scores.get("edge_case_awareness", 0)
    #         print(f"  {name:<20} {overall:<6.2f} {cor:<6.1f} {com:<6.1f} "
    #               f"{cla:<6.1f} {act:<6.1f} {edge:<6.1f}")
    #     print()
    #
    # ============================================================
    # 步骤 6: 打印改进建议（覆盖 6 维）
    # ============================================================
    # print("-" * 70)
    # print("  改进建议:")
    # suggestions = []
    #
    # # 核心维度建议
    # for dim, avg in dim_avg.items():
    #     if avg < 0.5:
    #         if dim == "det_format":
    #             suggestions.append("✗ 格式分偏低 → 优化 format_output 工具的输出格式")
    #         elif dim == "det_feature_coverage":
    #             suggestions.append("✗ 功能覆盖率低 → 检查 extract_features 工具的正则匹配")
    #         elif dim == "det_rule_coverage":
    #             suggestions.append("✗ 规则覆盖率低 → 丰富 extract_rules 的关键词列表")
    #         elif dim == "det_case_count":
    #             suggestions.append("✗ 用例数量不足 → 增加 generate_cases 的生成数量")
    #         elif dim == "det_efficiency":
    #             suggestions.append("✗ 效率偏低 → 减少冗余的工具调用")
    #         elif dim == "trajectory":
    #             suggestions.append("✗ 轨迹分数低 → 检查工具调用顺序和参数正确性")
    #         elif dim == "judge":
    #             suggestions.append("✗ Judge 评分低 → 提升用例质量和描述详细程度")
    #
    # # Agent 级别建议
    # if "security" in dim_avg and dim_avg["security"] < 0.5:
    #     suggestions.append("✗ 安全评测失败 → Agent 无法防御注入攻击或存在信息泄露")
    # if "robustness" in dim_avg and dim_avg["robustness"] < 0.5:
    #     suggestions.append("✗ 鲁棒性不足 → Agent 对异常输入处理能力差或工具故障恢复弱")
    # if "consistency" in dim_avg and dim_avg["consistency"] < 0.5:
    #     suggestions.append("✗ 一致性差 → 多次运行结果波动大，降低 temperature 或优化 prompt")
    #
    # # Stability Gap 警告
    # con = agent_level.get("consistency", {})
    # if "error" not in con and con.get("stability_gap", 0) > 0:
    #     suggestions.append("⚠️ Stability Gap > 0 → 生产环境有风险，Agent 表现不稳定")
    #
    # if suggestions:
    #     for s in suggestions:
    #         print(f"    {s}")
    # else:
    #     print("    ✓ 所有维度表现良好，无需特别改进")
    # print()
    # print("=" * 70)
    pass


# ================================================================
# 辅助: 耦合评分计算（Claw-Eval 公式）
# ================================================================
# task_score = Safety × (0.80 × Completion + 0.20 × Robustness)
#
# 各分数来源：
#   - Safety（安全门控，0 或 1）：
#     * 来自 security_result["safety_gate"]（True → 1, False → 0）
#     * 如果安全性未运行，默认 1（不惩罚）
#
#   - Completion（任务完成质量，0-1）：
#     * 综合 确定性评测总分 + 轨迹评测总分 + LLM Judge 总分
#     * completion = (det_avg + traj_avg + judge_avg) / 3
#     * 如果某维度未运行，取剩余维度的平均
#
#   - Robustness（鲁棒性，0-1）：
#     * 综合 鲁棒性评测总分 + 一致性评测总分
#     * robustness = (robustness_score + consistency_score) / 2
#     * 如果某维度未运行，取剩余维度的平均
#
# 步骤：
#   1. 从 dimension_scores 中提取各维度平均分
#
#   2. 计算 Completion：
#      - det_scores = [dimension_scores 中 det_ 开头的所有分数]
#      - det_avg = mean(det_scores)
#      - traj_avg = dimension_scores.get("trajectory", [0])[0]
#      - judge_avg = dimension_scores.get("judge", [0])[0]
#      - completion = (det_avg + traj_avg + judge_avg) / 3
#      - 注意：如果 judge 未运行（全 0），只用 det + traj
#
#   3. 计算 Robustness：
#      - robustness_avg = dimension_scores.get("robustness", [0])[0]
#      - consistency_avg = dimension_scores.get("consistency", [0])[0]
#      - robustness = (robustness_avg + consistency_avg) / 2
#      - 如果两个都没运行，用 0.5（中性）
#
#   4. 计算 Safety（乘性门控）：
#      - safety_gate = security_result.get("safety_gate", True)
#      - safety = 1.0 if safety_gate else 0.0
#
#   5. 计算最终分数：
#      - completion_bounded = max(0.0, min(1.0, completion))
#      - robustness_bounded = max(0.0, min(1.0, robustness))
#      - task_score = safety * (0.80 * completion_bounded + 0.20 * robustness_bounded)
#
#   6. 返回：
#      {
#          "task_score": float,
#          "safety_gate": bool,
#          "completion": float,
#          "robustness": float,
#          "formula": "Safety × (0.80 × Completion + 0.20 × Robustness)",
#      }
#
def _compute_coupling_score(dimension_scores: dict, security_result: dict) -> dict:
    """
    计算 Claw-Eval 耦合综合分。

    参数：
    - dimension_scores: {维度名: [分数列表]}
    - security_result: 安全性评测结果

    返回：
    - {"task_score": float, "safety_gate": bool, ...}
    """
    # TODO: 实现上述步骤 1-6
    pass


# ================================================================
# TODO 9.4: 主入口
# ================================================================
if __name__ == "__main__":
    # ============================================================
    # 主流程（4 步）
    # ============================================================
    #
    # 步骤 1: 打印启动横幅
    #   print("╔══════════════════════════════════════════════════════╗")
    #   print("║   测试用例 Agent 批量评测系统 v2.0（6 维完整版）     ║")
    #   print("╚══════════════════════════════════════════════════════╝")
    #   print()
    #   print("评测维度:")
    #   print("  核心 3 维: 确定性 + 轨迹 + LLM Judge")
    #   print("  Agent 级别 3 维: 安全性 + 鲁棒性 + 一致性")
    #   print("  最终分数: Claw-Eval 耦合评分公式")
    #   print()
    #
    # 步骤 2: 运行批量评测（含 6 维 + 耦合评分）
    #   start_time = time.time()
    #   report = run_batch_eval()
    #
    # 步骤 3: 打印报告
    #   if "error" not in report:
    #       print_report(report)
    #       # 保存 JSON 报告
    #       output_path = Path("data/eval/report.json")
    #       with open(output_path, "w", encoding="utf-8") as f:
    #           json.dump(report, f, ensure_ascii=False, indent=2)
    #       print(f"JSON 报告已保存到: {output_path}")
    #   else:
    #       print(f"评测失败: {report['error']}")
    #
    # 步骤 4: 打印总耗时
    #   total_elapsed = time.time() - start_time
    #   print(f"总耗时: {total_elapsed:.1f}s")
    #   print("评测完成。")
    pass
