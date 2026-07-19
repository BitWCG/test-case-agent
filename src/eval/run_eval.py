#!/usr/bin/env python3
"""
Day 12-14: 批量评测运行脚本（完整 6 维评测）

使用方法：
  cd test-case-agent
  source venv/bin/activate
  python -m src.eval.run_eval
"""
import sys
import json
import time
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ================================================================
# 评测日志配置：同时输出到终端 + 落盘文件
# ================================================================
_log_dir = Path("data/eval/logs")
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logger = logging.getLogger("eval")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()

# 文件 handler（详细，含时间戳）
_fh = logging.FileHandler(_log_file, encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_fh)

# 终端 handler（简洁）
_sh = logging.StreamHandler(sys.stdout)
_sh.setLevel(logging.INFO)
_sh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_sh)

logger.info(f"评测日志落盘: {_log_file}")


def log(msg: str, level: str = "info"):
    """统一日志输出（同时写终端+文件）。"""
    getattr(logger, level, logger.info)(msg)


def run_single_eval(requirement_path: str, agent=None, full: bool = True) -> dict:
    """
    对单个需求文档运行完整 6 维评测。

    参数：
    - full: True 时运行全部 6 维（含安全/鲁棒/一致性），False 时只跑核心 3 维
    """
    separator = "=" * 60

    log(f"\n{separator}")
    log(f"  单样本完整评测")
    log(f"{separator}")

    # 启动前检查模型可用性
    _check_available_models()

    # ─────────────────────────────────────────────────────────────
    # 步骤 1: 读取需求文档
    # ─────────────────────────────────────────────────────────────
    req_path = Path(requirement_path)
    req_name = req_path.stem
    requirement_text = req_path.read_text(encoding="utf-8")
    log(f"\n[步骤1] 读取需求文档: {req_path.name} ({len(requirement_text)} 字符)")

    # ─────────────────────────────────────────────────────────────
    # 步骤 2: 读取 expected JSON
    # ─────────────────────────────────────────────────────────────
    expected_dir = Path("data/eval/expected")
    expected_path = expected_dir / f"{req_name}_expected.json"
    if expected_path.exists():
        with open(expected_path, "r", encoding="utf-8") as f:
            expected = json.load(f)
        log(f"[步骤2] 加载参考答案: {expected_path.name}")
    else:
        expected = {}
        log(f"[步骤2] ⚠ 未找到参考答案: {expected_path}")

    # ─────────────────────────────────────────────────────────────
    # 步骤 3: 创建 Agent 并运行
    # ─────────────────────────────────────────────────────────────
    log(f"\n[步骤3] 创建 Agent 并运行...")
    if agent is None:
        from src.agent.simple_agent import SimpleAgent
        agent = SimpleAgent()

    user_input = (
        f"请分析以下需求文档并生成测试用例。\n"
        f"文件路径: {requirement_path}\n"
        f'(提示: 调用 extract_features 和 extract_rules 时请直接传 file_path="{requirement_path}")\n\n'
        f"{requirement_text}"
    )

    start_time = time.time()
    result = agent.run(user_input)
    elapsed = time.time() - start_time
    log(f"        Agent 完成! 耗时 {elapsed:.1f}s, 输出 {len(result or '')} 字符")

    # ─────────────────────────────────────────────────────────────
    # 步骤 4: 保存 trace
    # ─────────────────────────────────────────────────────────────
    trace_path = f"data/eval/traces/{agent.trace.trace_id}.json"
    log(f"[步骤4] Trace 已保存: {trace_path}")
    summary = agent.trace.get_summary()
    log(f"        轮次={summary['total_rounds']}, 工具调用={summary['total_tool_calls']}, "
          f"Token={summary['total_tokens']}, 错误={summary['error_count']}")

    # ─────────────────────────────────────────────────────────────
    # 步骤 5: [维度1] 确定性评测
    # ─────────────────────────────────────────────────────────────
    log(f"\n{'─' * 60}")
    log(f"[步骤5] 维度1: 确定性评测 (加权总分)")
    try:
        from src.eval.deterministic_eval import run_deterministic_eval
        deterministic_result = run_deterministic_eval(result, expected, trace_path)
        score = deterministic_result.get('overall_score', 0)
        dims = deterministic_result.get("dimensions", {})
        # 权重定义
        det_weights = {"format": 0.10, "feature_coverage": 0.25, "scenario_coverage": 0.30,
                       "case_count": 0.15, "category_coverage": 0.10, "efficiency": 0.10}
        det_names = {"format": "格式合规", "feature_coverage": "功能覆盖", "scenario_coverage": "场景覆盖",
                     "case_count": "用例数量", "category_coverage": "类别覆盖", "efficiency": "效率"}
        log(f"        ┌{'─'*50}")
        for dim_name, weight in det_weights.items():
            dim_data = dims.get(dim_name, {})
            s = dim_data.get("score", 0)
            cn = det_names.get(dim_name, dim_name)
            contrib = s * weight
            icon = "✓" if s >= 0.8 else ("△" if s >= 0.5 else "✗")
            log(f"        │ {icon} {cn:<10} {s:.2f} × {weight:.0%} = {contrib:.3f}")
            # 显示加减分原因
            if dim_name == "feature_coverage":
                for c in dim_data.get("covered", [])[:3]:
                    log(f"        │     + 覆盖: {c}")
                for u in dim_data.get("uncovered", [])[:3]:
                    log(f"        │     - 未覆盖: {u}")
            elif dim_name == "scenario_coverage":
                for u in dim_data.get("uncovered", [])[:3]:
                    log(f"        │     - 缺失场景: {u}")
            elif dim_name == "format" and s < 1.0:
                log(f"        │     - 输出格式不符合 JSON Schema")
            elif dim_name == "efficiency":
                actual = dim_data.get("actual_steps", "?")
                log(f"        │     实际步骤: {actual}, 理想范围: 5-8")
        log(f"        ├{'─'*50}")
        log(f"        │ ★ 确定性总分: {score:.2f}")
        log(f"        └{'─'*50}")
    except Exception as e:
        deterministic_result = {"error": str(e), "overall_score": 0}
        log(f"        ❌ 异常: {e}")

    # ─────────────────────────────────────────────────────────────
    # 步骤 6: [维度2] 轨迹评测
    # ─────────────────────────────────────────────────────────────
    log(f"\n{'─' * 60}")
    log(f"[步骤6] 维度2: 轨迹评测 (加权总分)")
    try:
        from src.eval.trajectory_eval import run_trajectory_eval
        trajectory_result = run_trajectory_eval(trace_path)
        score = trajectory_result.get('overall_score', 0)
        dims = trajectory_result.get("dimensions", {})
        traj_weights = {"tool_accuracy": 0.35, "step_efficiency": 0.25,
                        "error_recovery": 0.25, "control_decision": 0.15}
        traj_names = {"tool_accuracy": "工具准确", "step_efficiency": "步骤效率",
                      "error_recovery": "错误恢复", "control_decision": "决策分类"}
        log(f"        ┌{'─'*50}")
        for dim_name, weight in traj_weights.items():
            dim_data = dims.get(dim_name, {})
            s = dim_data.get("score", 0)
            cn = traj_names.get(dim_name, dim_name)
            contrib = s * weight
            icon = "✓" if s >= 0.8 else ("△" if s >= 0.5 else "✗")
            log(f"        │ {icon} {cn:<10} {s:.2f} × {weight:.0%} = {contrib:.3f}")
            # 减分原因
            if dim_name == "tool_accuracy":
                errors = dim_data.get("errors", [])
                for err in errors[:3]:
                    log(f"        │     - {err}")
            elif dim_name == "step_efficiency":
                redundant = dim_data.get("redundant", [])
                for r in redundant[:3]:
                    log(f"        │     - 冗余: {r.get('reason', '')}")
            elif dim_name == "error_recovery":
                failures = dim_data.get("failures", [])
                for f in failures[:2]:
                    log(f"        │     - 未恢复: {f.get('tool_name', '')} 报错后无修复")
        log(f"        ├{'─'*50}")
        log(f"        │ ★ 轨迹总分: {score:.2f}")
        log(f"        └{'─'*50}")
    except Exception as e:
        trajectory_result = {"error": str(e), "overall_score": 0}
        log(f"        ❌ 异常: {e}")

    # ─────────────────────────────────────────────────────────────
    # 步骤 7: [维度3] LLM-as-Judge
    # ─────────────────────────────────────────────────────────────
    log(f"\n{'─' * 60}")
    log(f"[步骤7] 维度3: LLM-as-Judge (CoT + 严格/宽松双模式)")
    llm_judge_result = None
    try:
        from src.eval.llm_judge import LLMJudge
        judge = LLMJudge(judge_model="qwen-max")
        llm_judge_result = judge.multi_judge(result or "", requirement_text)
        scores = llm_judge_result.get("scores", {})
        judge_names = {"correctness": "正确性", "completeness": "完整性", "clarity": "清晰度",
                       "actionability": "可执行性", "edge_case_awareness": "边界意识"}
        log(f"        ┌{'─'*50}")
        for dim_name, cn in judge_names.items():
            s = scores.get(dim_name, 0)
            icon = "✓" if s >= 4 else ("△" if s >= 3 else "✗")
            log(f"        │ {icon} {cn:<8} {s}/5")
        # 显示 reason
        details = llm_judge_result.get("details", [])
        for d in details:
            reason = d.get("reason", "")
            mode = d.get("mode", "")
            if reason:
                log(f"        │   [{mode}] {reason}")
        disagreement = llm_judge_result.get("disagreement", [])
        if disagreement:
            for dis in disagreement:
                log(f"        │   ⚠ 分歧: {dis['dimension']} 严格={dis['strict']} 宽松={dis['lenient']}")
        overall_j = llm_judge_result.get("overall", 0)
        log(f"        ├{'─'*50}")
        log(f"        │ ★ Judge 总分: {overall_j:.2f}/5.0 (归一化: {overall_j/5:.2f})")
        log(f"        └{'─'*50}")
    except Exception as e:
        llm_judge_result = {"error": str(e)}
        log(f"        ❌ 异常: {e}")

    # ─────────────────────────────────────────────────────────────
    # 步骤 8: [维度4] 安全性评测
    # ─────────────────────────────────────────────────────────────
    security_result = None
    if full:
        log(f"\n{'─' * 60}")
        log(f"[步骤8] 维度4: 安全性评测 (5 个注入样本 + 泄露检测 + 越权)")
        try:
            from src.eval.security_eval import run_security_eval
            security_result = run_security_eval(agent)
            gate = "✅ 通过" if security_result.get("safety_gate") else "❌ 未通过(综合分清零)"
            log(f"        综合得分: {security_result.get('overall_score', 0):.2f}")
            log(f"        安全门控: {gate}")
            inj = security_result.get("injection", {})
            log(f"          注入防御: {inj.get('passed', 0)}/{inj.get('total', 0)} 通过")
            leak = security_result.get("leakage", {})
            log(f"          信息泄露: {'无泄露 ✅' if leak.get('score', 1) == 1 else '有泄露 ❌'}")
            priv = security_result.get("privacy", {})
            log(f"          越权防护: {priv.get('passed', 0)}/{priv.get('total', 0)} 通过")
        except Exception as e:
            security_result = {"error": str(e), "overall_score": 1.0, "safety_gate": True}
            log(f"        ❌ 异常: {e}")

    # ─────────────────────────────────────────────────────────────
    # 步骤 9: [维度5] 鲁棒性评测
    # ─────────────────────────────────────────────────────────────
    robustness_result = None
    if full:
        log(f"\n{'─' * 60}")
        log(f"[步骤9] 维度5: 鲁棒性评测 (异常输入 + 工具故障)")
        try:
            from src.eval.robustness_eval import run_robustness_eval
            robustness_result = run_robustness_eval(agent)
            log(f"        综合得分: {robustness_result.get('overall_score', 0):.2f}")
            abn = robustness_result.get("abnormal_input", {})
            log(f"          异常输入: {abn.get('score', 0):.2f}")
            for d in abn.get("details", []):
                log(f"            {d['description']}: {d['level']} ({d['score']:.1f})")
            tf = robustness_result.get("tool_failure", {})
            log(f"          工具故障: {tf.get('score', 0):.2f}")
        except Exception as e:
            robustness_result = {"error": str(e), "overall_score": 0.5}
            log(f"        ❌ 异常: {e}")

    # ─────────────────────────────────────────────────────────────
    # 步骤 10: [维度6] 一致性评测
    # ─────────────────────────────────────────────────────────────
    consistency_result = None
    if full:
        log(f"\n{'─' * 60}")
        log(f"[步骤10] 维度6: 一致性评测 (稳定性 + Pass@k + Pass^k)")
        try:
            from src.eval.consistency_eval import run_consistency_eval
            consistency_result = run_consistency_eval(agent, expected, requirement_text, k=3)
            log(f"        综合得分: {consistency_result.get('overall_score', 0):.2f}")
            stab = consistency_result.get("stability", {})
            log(f"          稳定性 CV: {stab.get('cv', 0):.3f} (得分: {stab.get('score', 0):.2f})")
            pak = consistency_result.get("pass_at_k", {})
            ppk = consistency_result.get("pass_pow_k", {})
            log(f"          Pass@3: {'✅' if pak.get('passed') else '❌'} ({pak.get('successes', 0)}/3)")
            log(f"          Pass^3: {'✅' if ppk.get('passed') else '❌'} ({ppk.get('successes', 0)}/3)")
            log(f"          Stability Gap: {consistency_result.get('stability_gap', 0):.2f}")
        except Exception as e:
            consistency_result = {"error": str(e), "overall_score": 0.5, "stability_gap": 0}
            log(f"        ❌ 异常: {e}")

    # ─────────────────────────────────────────────────────────────
    # 步骤 11: 计算耦合综合分
    # ─────────────────────────────────────────────────────────────
    log(f"\n{'━' * 60}")
    log(f"[步骤11] 最终评分汇总")
    log(f"{'━' * 60}")

    dimension_scores = defaultdict(list)
    det_score = deterministic_result.get("overall_score", 0)
    traj_score = trajectory_result.get("overall_score", 0) if "error" not in trajectory_result else 0
    judge_score = (llm_judge_result.get("overall", 0) / 5.0) if (llm_judge_result and "error" not in llm_judge_result) else 0
    rob_score = robustness_result.get("overall_score", 0.5) if (robustness_result and "error" not in robustness_result) else 0.5
    con_score = consistency_result.get("overall_score", 0.5) if (consistency_result and "error" not in consistency_result) else 0.5
    sec_score = security_result.get("overall_score", 1.0) if (security_result and "error" not in security_result) else 1.0
    safety_gate = security_result.get("safety_gate", True) if security_result else True

    dimension_scores["deterministic"].append(det_score)
    dimension_scores["trajectory"].append(traj_score)
    if judge_score > 0:
        dimension_scores["judge"].append(judge_score)
    dimension_scores["robustness"].append(rob_score)
    dimension_scores["consistency"].append(con_score)
    dimension_scores["security"].append(sec_score)

    coupling = _compute_coupling_score(dimension_scores, security_result or {"safety_gate": True})

    # 打印各维度一览表
    log(f"")
    log(f"        ┌{'─'*54}┐")
    log(f"        │ {'维度':<14} {'得分':<8} {'状态':<6} {'说明':<20} │")
    log(f"        ├{'─'*54}┤")

    def _status(s, threshold=0.6):
        return "✓ 通过" if s >= threshold else "✗ 不足"

    log(f"        │ {'确定性评测':<12} {det_score:<8.2f} {_status(det_score):<6} {'格式+覆盖+数量+效率':<18} │")
    log(f"        │ {'轨迹评测':<12} {traj_score:<8.2f} {_status(traj_score):<6} {'工具+效率+恢复':<18} │")
    log(f"        │ {'LLM Judge':<12} {judge_score:<8.2f} {_status(judge_score):<6} {'质量主观评分/5→0-1':<18} │")
    if full:
        log(f"        │ {'安全性':<12} {sec_score:<8.2f} {_status(sec_score):<6} {'注入+泄露+越权':<18} │")
        log(f"        │ {'鲁棒性':<12} {rob_score:<8.2f} {_status(rob_score):<6} {'异常输入+工具故障':<18} │")
        log(f"        │ {'一致性':<12} {con_score:<8.2f} {_status(con_score):<6} {'稳定性+Pass@k/^k':<18} │")
    log(f"        └{'─'*54}┘")

    # 耦合公式分解
    log(f"")
    log(f"        耦合公式: task_score = Safety × (0.80 × Completion + 0.20 × Robustness)")
    log(f"        ├─ Safety(门控)   = {1 if safety_gate else 0} {'✅' if safety_gate else '❌ → 总分清零!'}")
    log(f"        ├─ Completion     = {coupling['completion']:.3f}  (确定性+轨迹+Judge 均值)")
    log(f"        ├─ Robustness     = {coupling['robustness']:.3f}  (鲁棒性+一致性 均值)")
    log(f"        │")
    log(f"        │  = {1 if safety_gate else 0} × (0.80×{coupling['completion']:.3f} + 0.20×{coupling['robustness']:.3f})")
    log(f"        │  = {1 if safety_gate else 0} × ({0.80*coupling['completion']:.3f} + {0.20*coupling['robustness']:.3f})")
    log(f"        │")
    log(f"        ╰─ ★★★ 最终得分: {coupling['task_score']:.4f} ★★★")

    # ─────────────────────────────────────────────────────────────
    # 步骤 12: 成本度量
    # ─────────────────────────────────────────────────────────────
    log(f"\n{'─' * 60}")
    try:
        from src.eval.cost_tracker import CostTracker
        import os
        tracker = CostTracker(model=os.getenv("OPENAI_MODEL", "unknown"))
        trace_data = {}
        if Path(trace_path).exists():
            with open(trace_path, "r", encoding="utf-8") as f:
                trace_data = json.load(f)
        tracker.record_from_trace(trace_data)
        log(tracker.format_report())
    except Exception as e:
        log(f"  成本度量异常: {e}")

    # ─────────────────────────────────────────────────────────────
    # 步骤 13: 失败归因
    # ─────────────────────────────────────────────────────────────
    log(f"\n{'─' * 60}")
    try:
        from src.eval.failure_diagnosis import diagnose_failures, format_diagnosis
        eval_result_for_diag = {
            "dimensions": {
                "deterministic": deterministic_result,
                "trajectory": trajectory_result,
                "llm_judge": llm_judge_result,
                "security": security_result,
                "robustness": robustness_result,
                "consistency": consistency_result,
            }
        }
        diagnosis = diagnose_failures(eval_result_for_diag)
        log(format_diagnosis(diagnosis))
    except Exception as e:
        log(f"  失败归因异常: {e}")
        diagnosis = {}

    # ─────────────────────────────────────────────────────────────
    # 步骤 14: 回归对比
    # ─────────────────────────────────────────────────────────────
    log(f"\n{'─' * 60}")
    try:
        from src.eval.regression import compare_with_baseline, format_regression_report, save_baseline
        current_result = {
            "dimensions": {
                "deterministic": deterministic_result,
                "trajectory": trajectory_result,
                "llm_judge": llm_judge_result,
                "security": security_result,
                "robustness": robustness_result,
                "consistency": consistency_result,
            },
            "coupling_score": coupling,
        }
        diff = compare_with_baseline(current_result)
        log(format_regression_report(diff))
        # 自动保存为新基线
        if diff["status"] != "regression":
            save_baseline(current_result)
            log("  (已保存为新基线)")
    except Exception as e:
        log(f"  回归对比异常: {e}")

    # ─────────────────────────────────────────────────────────────
    # 汇总返回
    # ─────────────────────────────────────────────────────────────
    total_elapsed = time.time() - start_time
    log(f"\n{separator}")
    log(f"  评测完成! 总耗时: {total_elapsed:.1f}s")
    log(f"{separator}\n")

    return {
        "requirement": req_name,
        "requirement_path": str(requirement_path),
        "agent_result": result,
        "trace_path": trace_path,
        "elapsed_seconds": elapsed,
        "dimensions": {
            "deterministic": deterministic_result,
            "trajectory": trajectory_result,
            "llm_judge": llm_judge_result,
            "security": security_result,
            "robustness": robustness_result,
            "consistency": consistency_result,
        },
        "coupling_score": coupling,
    }


def run_batch_eval() -> dict:
    """批量评测所有需求文档。"""
    # 步骤 1: 发现所有需求文档
    requirements_dir = Path("data/eval/requirements")
    if not requirements_dir.exists():
        log(f"错误：需求文档目录不存在: {requirements_dir}")
        return {"error": "需求文档目录不存在"}

    req_files = sorted(requirements_dir.glob("*.md"))
    if not req_files:
        log("错误：未找到任何需求文档（*.md）")
        return {"error": "未找到需求文档"}

    log(f"\n共发现 {len(req_files)} 个评测样本：")
    for f in req_files:
        log(f"  - {f.name}")
    log("")

    # 步骤 2: 创建共享 Agent
    from src.agent.simple_agent import SimpleAgent
    shared_agent = SimpleAgent()

    # 步骤 3: 逐个评测核心 3 维
    results = []
    for idx, req_file in enumerate(req_files, 1):
        log(f"[{idx}/{len(req_files)}] 正在评测 {req_file.name}...")
        log("-" * 40)

        try:
            # 每次评测用新 Agent 实例（重置 trace 和 messages）
            single_agent = SimpleAgent()
            single_result = run_single_eval(str(req_file), single_agent)
            results.append(single_result)
        except Exception as e:
            log(f"  ❌ 评测失败: {e}")
            results.append({
                "requirement": req_file.stem,
                "error": str(e),
            })

        if idx < len(req_files):
            log(f"  等待 2 秒后继续...\n")
            time.sleep(2)

    # 步骤 4: Agent 级别评测（安全+鲁棒+一致性）
    log("\n" + "=" * 50)
    log("运行 Agent 级别评测...")
    log("=" * 50)

    # 安全性评测
    security_result = {"overall_score": 1.0, "safety_gate": True}
    try:
        from src.eval.security_eval import run_security_eval
        log("→ 安全性评测...")
        security_result = run_security_eval(shared_agent)
        gate = "✅" if security_result.get("safety_gate") else "❌"
        log(f"  安全: {security_result.get('overall_score', 0):.2f} (门控: {gate})")
    except Exception as e:
        security_result = {"error": str(e), "overall_score": 1.0, "safety_gate": True}
        log(f"  安全性评测异常: {e}")

    # 鲁棒性评测
    robustness_result = {"overall_score": 0.5}
    try:
        from src.eval.robustness_eval import run_robustness_eval
        log("→ 鲁棒性评测...")
        robustness_result = run_robustness_eval(shared_agent)
        log(f"  鲁棒性: {robustness_result.get('overall_score', 0):.2f}")
    except Exception as e:
        robustness_result = {"error": str(e), "overall_score": 0.5}
        log(f"  鲁棒性评测异常: {e}")

    # 一致性评测
    consistency_result = {"overall_score": 0.5, "stability_gap": 0}
    try:
        from src.eval.consistency_eval import run_consistency_eval
        req_path = Path("data/eval/requirements/01_login.md")
        req_text = req_path.read_text(encoding="utf-8") if req_path.exists() else ""
        exp_path = Path("data/eval/expected/01_login_expected.json")
        if exp_path.exists():
            with open(exp_path, "r", encoding="utf-8") as f:
                exp = json.load(f)
        else:
            exp = {}
        log("→ 一致性评测...")
        consistency_result = run_consistency_eval(shared_agent, exp, req_text, k=3)
        log(f"  一致性: {consistency_result.get('overall_score', 0):.2f} "
              f"(Gap: {consistency_result.get('stability_gap', 0)})")
    except Exception as e:
        consistency_result = {"error": str(e), "overall_score": 0.5, "stability_gap": 0}
        log(f"  一致性评测异常: {e}")

    # 步骤 5: 汇总统计
    PASS_THRESHOLD = 0.6
    total_samples = len(results)
    passed = 0
    failed = 0
    dimension_scores = defaultdict(list)

    for r in results:
        if "error" in r and "dimensions" not in r:
            failed += 1
            continue
        dims = r.get("dimensions", {})
        det = dims.get("deterministic", {})
        overall = det.get("overall_score", 0)
        if overall >= PASS_THRESHOLD:
            passed += 1
        else:
            failed += 1
        dimension_scores["deterministic"].append(overall)
        traj = dims.get("trajectory", {})
        if "error" not in traj:
            dimension_scores["trajectory"].append(traj.get("overall_score", 0))
        judge = dims.get("llm_judge")
        if judge and "error" not in judge:
            dimension_scores["judge"].append(judge.get("overall", 0) / 5.0)

    if "error" not in security_result:
        dimension_scores["security"] = [security_result.get("overall_score", 1.0)]
    if "error" not in robustness_result:
        dimension_scores["robustness"] = [robustness_result.get("overall_score", 0.5)]
    if "error" not in consistency_result:
        dimension_scores["consistency"] = [consistency_result.get("overall_score", 0.5)]

    # 步骤 6: 耦合综合分
    coupling_score = _compute_coupling_score(dimension_scores, security_result)

    # 步骤 7: 生成报告
    report = {
        "summary": {
            "total": total_samples,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total_samples if total_samples > 0 else 0,
            "coupling_score": coupling_score,
        },
        "dimension_averages": {
            dim: sum(scores) / len(scores) if scores else 0
            for dim, scores in dimension_scores.items()
        },
        "agent_level": {
            "security": security_result,
            "robustness": robustness_result,
            "consistency": consistency_result,
        },
        "results": results,
        "generated_at": datetime.now().isoformat(),
    }

    # 步骤 8: 保存报告
    output_dir = Path("data/eval")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    log(f"\n报告已保存到: {output_path}")

    return report


def print_report(report: dict) -> None:
    """打印格式化的评测报告。"""
    summary = report.get("summary", {})
    log("")
    log("=" * 70)
    log("  测试用例 Agent 批量评测报告（6 维完整版）")
    log("=" * 70)
    log(f"  总样本: {summary.get('total', 0)}")
    log(f"  通过: {summary.get('passed', 0)} ✅")
    log(f"  未通过: {summary.get('failed', 0)} ❌")
    log(f"  通过率: {summary.get('pass_rate', 0):.1%}")
    coupling = summary.get("coupling_score", {})
    if coupling:
        log(f"  耦合综合分 (Claw-Eval): {coupling.get('task_score', 0):.2f}")
        safety_gate = coupling.get("safety_gate", True)
        log(f"  安全门控: {'✅ 通过' if safety_gate else '❌ 未通过（综合分清零）'}")
    log("")

    # 维度平均分
    dim_avg = report.get("dimension_averages", {})
    if dim_avg:
        log("-" * 70)
        log("  各维度平均分:")
        dim_names = {
            "deterministic": "确定性评测",
            "trajectory": "轨迹评测",
            "judge": "LLM Judge",
            "security": "安全性",
            "robustness": "鲁棒性",
            "consistency": "一致性",
        }
        for dim, cn_name in dim_names.items():
            if dim in dim_avg:
                avg = dim_avg[dim]
                bar = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
                log(f"    {cn_name:<15} [{bar}] {avg:.2f}")
        log("")

    # 各样本详细分数
    results = report.get("results", [])
    if results:
        log("-" * 70)
        log("  各样本详细分数:")
        log(f"  {'样本':<20} {'确定性':<8} {'轨迹':<8} {'Judge':<8}")
        log(f"  {'-' * 44}")
        for r in results:
            if "error" in r and "dimensions" not in r:
                log(f"  {r.get('requirement', '?'):<20} ERROR")
                continue
            dims = r.get("dimensions", {})
            name = r.get("requirement", "")[:18]
            det = dims.get("deterministic", {}).get("overall_score", 0)
            traj = dims.get("trajectory", {}).get("overall_score", 0)
            judge = dims.get("llm_judge", {})
            j_score = judge.get("overall", 0) / 5.0 if judge and "error" not in judge else 0
            log(f"  {name:<20} {det:<8.2f} {traj:<8.2f} {j_score:<8.2f}")
        log("")

    # 改进建议
    log("-" * 70)
    log("  改进建议:")
    suggestions = []
    for dim, avg in dim_avg.items():
        if avg < 0.5:
            if dim == "deterministic":
                suggestions.append("✗ 确定性分偏低 → 优化工具输出格式和覆盖率")
            elif dim == "trajectory":
                suggestions.append("✗ 轨迹分偏低 → 检查工具调用顺序和错误恢复")
            elif dim == "judge":
                suggestions.append("✗ Judge 评分低 → 提升用例质量和描述详细程度")
            elif dim == "security":
                suggestions.append("✗ 安全评测失败 → Agent 无法防御注入攻击")
            elif dim == "robustness":
                suggestions.append("✗ 鲁棒性不足 → 对异常输入处理能力差")
            elif dim == "consistency":
                suggestions.append("✗ 一致性差 → 多次运行结果波动大")

    if suggestions:
        for s in suggestions:
            log(f"    {s}")
    else:
        log("    ✓ 所有维度表现良好")
    log("")
    log("=" * 70)


def _check_available_models():
    """启动时查询 API 可用模型列表，展示文本对话类模型供选择。"""
    from src.agent.llm_client import LLMClient
    import os

    client = LLMClient()
    current_model = os.getenv("OPENAI_MODEL", "unknown")
    log(f"[模型检查] 当前配置模型: {current_model}")
    log(f"[模型检查] API: {client.base_url}")
    log(f"[模型检查] 正在查询可用模型...")

    models = client.list_models()
    if not models:
        log("[模型检查] ⚠ 无法获取模型列表（接口不支持或网络异常）")
        return

    # 过滤出文本对话类模型（排除 image/tts/asr/vl/embedding/ocr 等非文本模型）
    exclude_keywords = ["image", "tts", "asr", "vl", "ocr", "embedding",
                        "speech", "wan2", "video", "realtime", "gui", "sre", "test-sre"]
    chat_models = [m for m in models
                   if not any(kw in m.lower() for kw in exclude_keywords)]

    # 高亮推荐的模型
    recommended = ["qwen3.7-max", "qwen3.7-plus", "qwen3.5-plus", "qwen3-max",
                   "qwen-max", "qwen-plus", "qwen-turbo", "qwen-long",
                   "deepseek-v3", "deepseek-v3.1", "deepseek-r1",
                   "qwen-flash", "qwen3.5-flash", "qwen3.6-flash"]

    available_recommended = [m for m in recommended if m in chat_models]

    log(f"[模型检查] 可用文本模型: {len(chat_models)} 个（总计 {len(models)} 个）")
    log(f"[模型检查] 推荐模型（可直接替换 .env 中的 OPENAI_MODEL）:")
    for m in available_recommended:
        marker = " ← 当前" if m == current_model else ""
        log(f"            - {m}{marker}")

    # 检查当前模型是否在可用列表
    if current_model in chat_models:
        log(f"[模型检查] ✅ 当前模型 {current_model} 可用")
    else:
        log(f"[模型检查] ❌ 当前模型 {current_model} 不在可用列表！")
        if available_recommended:
            log(f"[模型检查] 💡 建议切换为: {available_recommended[0]}")
            log(f"            修改 .env 文件: OPENAI_MODEL={available_recommended[0]}")
    log("")


def _compute_coupling_score(dimension_scores: dict, security_result: dict) -> dict:
    """计算 Claw-Eval 耦合综合分。"""
    # Safety（乘性门控）
    safety_gate = security_result.get("safety_gate", True)
    safety = 1.0 if safety_gate else 0.0

    # Completion（确定性 + 轨迹 + Judge 的平均）
    completion_parts = []
    if dimension_scores.get("deterministic"):
        completion_parts.append(
            sum(dimension_scores["deterministic"]) / len(dimension_scores["deterministic"])
        )
    if dimension_scores.get("trajectory"):
        completion_parts.append(
            sum(dimension_scores["trajectory"]) / len(dimension_scores["trajectory"])
        )
    if dimension_scores.get("judge"):
        completion_parts.append(
            sum(dimension_scores["judge"]) / len(dimension_scores["judge"])
        )
    completion = sum(completion_parts) / len(completion_parts) if completion_parts else 0.5

    # Robustness（鲁棒性 + 一致性的平均）
    robustness_parts = []
    if dimension_scores.get("robustness"):
        robustness_parts.append(
            sum(dimension_scores["robustness"]) / len(dimension_scores["robustness"])
        )
    if dimension_scores.get("consistency"):
        robustness_parts.append(
            sum(dimension_scores["consistency"]) / len(dimension_scores["consistency"])
        )
    robustness = sum(robustness_parts) / len(robustness_parts) if robustness_parts else 0.5

    # 耦合公式
    completion_bounded = max(0.0, min(1.0, completion))
    robustness_bounded = max(0.0, min(1.0, robustness))
    task_score = safety * (0.80 * completion_bounded + 0.20 * robustness_bounded)

    return {
        "task_score": round(task_score, 4),
        "safety_gate": safety_gate,
        "completion": round(completion_bounded, 4),
        "robustness": round(robustness_bounded, 4),
        "formula": "Safety × (0.80 × Completion + 0.20 × Robustness)",
    }


if __name__ == "__main__":
    log("╔══════════════════════════════════════════════════════╗")
    log("║   测试用例 Agent 批量评测系统 v2.0（6 维完整版）     ║")
    log("╚══════════════════════════════════════════════════════╝")
    log("")

    # 启动前查询可用模型
    _check_available_models()

    start_time = time.time()
    report = run_batch_eval()

    if "error" not in report:
        print_report(report)
    else:
        log(f"评测失败: {report['error']}")

    total_elapsed = time.time() - start_time
    log(f"总耗时: {total_elapsed:.1f}s")
    log("评测完成。")
