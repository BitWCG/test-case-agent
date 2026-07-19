"""
轨迹评测模块

分析 Agent 的执行轨迹（trace JSON），评估 Agent 的"做事方式"，
而非只看最终输出。评测维度包括工具选择、参数正确性、步骤效率、
失败恢复能力、以及控制决策分类（Act/Ask/Refuse/Stop/Confirm/Recover）。

输入：TraceRecorder 生成的 trace JSON
输出：每个维度一个分数 + 汇总报告
"""
import json
from pathlib import Path


# ================================================================
# TODO 8.4: eval_tool_accuracy — 工具选择准确率
# ================================================================
# 评估 Agent 是否选择了正确的工具，以及参数是否正确。
#
# 步骤：
#   1. 从 trace JSON 的 steps 中提取所有 tool_call 事件
#   2. 对每次工具调用检查：
#      a. 工具名称是否在预期工具列表中（如 parse_prd、extract_features 等）
#      b. 工具调用顺序是否合理：
#         - parse_prd 必须在 extract_features / extract_rules 之前
#         - generate_cases 必须在 extract_features + extract_rules 之后
#         - format_output 必须在 generate_cases 之后
#      c. 参数是否合理：
#         - file_path 是否指向存在的文件
#         - 必填参数是否都有值（不为空字符串、不为 null）
#   3. 计算准确率 = 正确的工具调用次数 / 总工具调用次数
#   4. 如果某次工具调用返回了 error，扣分
#   5. 返回 {"score": float, "correct": int, "total": int, "errors": [...]}
#
# 提示：
#   - 不要用硬编码的工具顺序，用"规则表"（expected_order 列表）
#   - 参数检查：只要必填字段有值即可，不需要验证值的具体内容
#   - 文件中转：file_path 参数的值无法在评测时验证文件是否存在（可能文件已删除），跳过文件存在性检查
#
def eval_tool_accuracy(trace: dict) -> dict:
    """
    评估工具选择和参数正确性。

    参数：
    - trace: TraceRecorder 生成的 trace dict

    返回：
    - {"score": float, "correct": int, "total": int, "errors": [...]}
    """
    # ============================================================
    # 步骤 1: 从 trace 中提取所有 tool_call 事件
    # ============================================================
    steps = trace.get("steps", [])
    tool_calls = [s for s in steps if s.get("type") == "tool_call"]
    if not tool_calls:
        return {"score": 0.0, "correct": 0, "total": 0, "errors": ["无工具调用记录"]}
    
    # ============================================================
    # 步骤 2: 定义合法工具集和推荐顺序
    # ============================================================
    valid_tools = {"parse_prd", "analyze_requirements", "extract_features",
                   "extract_rules", "generate_cases", "format_output"}
    # 偏序规则：只约束关键前后关系，不约束无依赖的工具顺序
    # 例如 extract_features 和 extract_rules 之间无依赖，谁先谁后都合法
    order_rules = [
        ("parse_prd", "analyze_requirements"),   # parse 必须在 analyze 之前
        ("parse_prd", "extract_features"),        # parse 必须在 extract 之前
        ("parse_prd", "extract_rules"),           # parse 必须在 extract 之前
        ("analyze_requirements", "extract_features"),
        ("analyze_requirements", "extract_rules"),
        ("extract_features", "generate_cases"),   # extract 必须在 generate 之前
        ("extract_rules", "generate_cases"),      # extract 必须在 generate 之前
        ("generate_cases", "format_output"),      # generate 必须在 format 之前
    ]
    
    # ============================================================
    # 步骤 3: 逐次检查每个工具调用
    # ============================================================
    correct = 0
    errors = []
    called_tools = []  # 记录已调用的工具名（用于检查顺序）
    
    for i, tc in enumerate(tool_calls):
        tool_name = tc.get("tool_name", "")
        params = tc.get("arguments", {})
        call_ok = True
    
        # 3a. 检查工具名是否合法
        if tool_name not in valid_tools:
            errors.append(f"步骤{i}: 未知工具 '{tool_name}'")
            call_ok = False
    
        # 3b. 检查工具调用顺序（偏序规则）
        #     当前工具的所有前置工具必须已经调用过
        prereqs = [pre for pre, t in order_rules if t == tool_name]
        for prereq in prereqs:
            if prereq not in called_tools:
                # 前置工具在整个 trace 中存在但还没被调用 → 顺序异常
                all_called = {tc.get("tool_name", "") for tc in tool_calls}
                if prereq in all_called:
                    errors.append(
                        f"步骤{i}: 顺序异常 '{tool_name}' 应在 '{prereq}' 之后"
                    )
                    call_ok = False
                    break
        called_tools.append(tool_name)
    
        # 3c. 检查参数完整性（必填字段是否有值）
        #     每个工具有多种合法参数组合（如 file_path 或 prd_json 都行）
        #     只要满足任一组合即可通过
        required_params_alternatives = {
            "parse_prd": [["file_path"], ["content"]],
            "analyze_requirements": [["prd_json"], ["file_path"]],
            "extract_features": [["prd_json"], ["file_path"]],
            "extract_rules": [["prd_json"], ["file_path"]],
            "generate_cases": [["features_json", "rules_json"], ["file_path"]],
            "format_output": [["cases_json"], ["file_path"]],
        }
        alternatives = required_params_alternatives.get(tool_name, [[]])
        # 只要满足任意一组参数组合，就算通过
        param_ok = False
        for alt in alternatives:
            if all(p in params and params[p] for p in alt):
                param_ok = True
                break
        if not param_ok and alternatives != [[]]:
            alt_desc = " 或 ".join([str(a) for a in alternatives])
            errors.append(f"步骤{i}: {tool_name} 缺少必填参数（需要 {alt_desc} 之一）")
            call_ok = False
    
        if call_ok:
            correct += 1
    
    # ============================================================
    # 步骤 4: 计算分数并返回
    # ============================================================
    total = len(tool_calls)
    score = correct / total if total > 0 else 0.0
    return {"score": round(score, 2), "correct": correct, "total": total, "errors": errors}
    # pass


# ================================================================
# TODO 8.5: eval_step_efficiency — 步骤效率
# ================================================================
# 评估 Agent 是否有冗余的工具调用。
#
# 步骤：
#   1. 从 trace 中提取所有 tool_call 事件
#   2. 检测冗余模式：
#      a. 重复调用：同一个工具+相同参数连续调用 >= 2 次，从第 2 次开始计为冗余
#      b. 不必要的调用：调用了工具但结果未被使用（比如调了 extract_features 但没传给 generate_cases）
#      c. 最小必要步骤：理想情况下，一个需求文档需要 5-7 次工具调用（parse→analyze→features→rules→generate→format）
#   3. 计算效率分数：
#      - 如果实际步骤在理想范围 (5-8) 内：score = 1.0
#      - 如果实际步骤超出理想范围：score = 理想上限 / 实际步骤数
#      - 如果实际步骤少于理想下限：score = 实际步骤数 / 理想下限（说明可能跳过了关键步骤）
#   4. 返回 {"score": float, "actual_steps": int, "ideal_range": [min, max], "redundant": [...]}
#
# 提示：
#   - 理想范围不是硬编码，而是根据工具的"最小必要链"计算
#   - 最小必要链：parse_prd → extract_features → extract_rules → generate_cases → format_output = 5 步
#   - 如果 Agent 还调用了 analyze_requirements，那就是 6 步
#   - 超过 8 步基本可以确定有冗余
#
def eval_step_efficiency(trace: dict) -> dict:
    """
    评估步骤是否存在冗余调用。

    参数：
    - trace: TraceRecorder 生成的 trace dict

    返回：
    - {"score": float, "actual_steps": int, "ideal_range": [int, int], "redundant": [...]}
    """
    # ============================================================
    # 步骤 1: 提取所有工具调用
    # ============================================================
    steps = trace.get("steps", [])
    tool_calls = [s for s in steps if s.get("type") == "tool_call"]
    actual_steps = len(tool_calls)
    if actual_steps == 0:
        return {"score": 0.0, "actual_steps": 0, "ideal_range": [5, 8], "redundant": []}
    
    # ============================================================
    # 步骤 2: 检测冗余模式
    # ============================================================
    redundant = []
    #
    # 2a. 检测重复调用：同一个工具+相同参数连续 >= 2 次
    for i in range(1, len(tool_calls)):
        prev = tool_calls[i-1]
        curr = tool_calls[i]
        if (prev.get("tool_name") == curr.get("tool_name") and
                prev.get("arguments") == curr.get("arguments")):
            redundant.append({
                "step": i,
                "tool": curr.get("tool_name"),
                "reason": "重复调用（相同工具+相同参数）",
            })
    
    # 2b. 检测未被使用的调用（高级，可先跳过）：
    #     例如调了 extract_features 但结果没传给 generate_cases
    #     实现思路：检查后续步骤的参数中是否引用了前面步骤的结果
    #
    # ============================================================
    # 步骤 3: 确定理想范围
    # ============================================================
    # 最小必要链（所有 6 个工具）：parse_prd → analyze_requirements →
    #   extract_features → extract_rules → generate_cases → format_output
    min_ideal = 6
    max_ideal = 8  # 允许 2 次额外的合理调用（如失败重试）
    
    # ============================================================
    # 步骤 4: 计算效率分数
    # ============================================================
    if min_ideal <= actual_steps <= max_ideal:
        score = 1.0
    elif actual_steps > max_ideal:
        score = max_ideal / actual_steps  # 步骤越多分越低
    else:
        score = actual_steps / min_ideal  # 步骤太少可能跳过了关键步骤
    
    return {
        "score": round(score, 2),
        "actual_steps": actual_steps,
        "ideal_range": [min_ideal, max_ideal],
        "redundant": redundant,
    }


# ================================================================
# TODO 8.6: eval_error_recovery — 错误恢复能力
# ================================================================
# 评估 Agent 在工具调用失败后是否能正确恢复。
#
# 步骤：
#   1. 从 trace 中找出所有工具调用返回 error 的事件
#   2. 对每个 error，检查 Agent 的反应：
#      a. 是否重试了该工具（用相同或修正后的参数）？→ +1 分
#      b. 是否换了另一种方式完成目标（如换 file_path 代替 prd_json）？→ +1 分
#      c. 是否忽略了错误继续执行？→ +0 分
#      d. 是否因错误直接终止？→ -1 分
#   3. 计算恢复分数：
#      - 如果没有错误：score = 1.0（没有犯错就是最好的恢复）
#      - 如果有错误：score = (成功恢复次数 + 1) / (总错误次数 + 1)
#   4. 返回 {"score": float, "error_count": int, "recovered": int, "failures": [...]}
#
# 提示：
#   - trace 中的 tool_call 事件包含 result 字段，检查 result 中是否包含 "error" key
#   - "恢复"的定义：错误发生后，后续步骤中包含了修正动作
#   - 这是一个比较高级的评测，先实现基本版本即可
#
def eval_error_recovery(trace: dict) -> dict:
    """
    评估 Agent 的错误恢复能力。

    参数：
    - trace: TraceRecorder 生成的 trace dict

    返回：
    - {"score": float, "error_count": int, "recovered": int, "failures": [...]}
    """
    # ============================================================
    # 步骤 1: 找出所有返回 error 的工具调用
    # ============================================================
    steps = trace.get("steps", [])
    error_events = []
    for i, step in enumerate(steps):
        step_type = step.get("type")

        # 情况 A: 专门的 error 事件（TraceRecorder.record_error 记录，type="error"）
        if step_type == "error":
            error_events.append({
                "step_index": i,
                "tool_name": step.get("tool_name", "unknown"),
                "error": step.get("error", ""),
            })

        # 情况 B: tool_call 事件的 result 里带 error（工具内部返回错误）
        elif step_type == "tool_call":
            result = step.get("result", {})
            # 检查 result 是否为 dict 且包含 "error" key
            if isinstance(result, dict) and "error" in result:
                error_events.append({
                    "step_index": i,
                    "tool_name": step.get("tool_name", "unknown"),
                    "error": result["error"],
                })
            # 也可能 result 是字符串（JSON 解析失败后的原始文本）
            elif not isinstance(result, dict) and "error" in str(result).lower():
                error_events.append({
                    "step_index": i,
                    "tool_name": step.get("tool_name", "unknown"),
                    "error": str(result)[:200],  # 截取前 200 字符
                })
    
    # ============================================================
    # 步骤 2: 分析每个 error 后 Agent 的反应
    # ============================================================
    recovered = 0
    failures = []
    for err in error_events:
        err_idx = err["step_index"]
        # 查看 error 之后的步骤
        subsequent = steps[err_idx + 1:]
    
        # 检查是否重试了同一工具（可能修正了参数）
        retried = any(
            s.get("type") == "tool_call" and s.get("tool_name") == err["tool_name"]
            for s in subsequent[:3]  # 只看后续 3 步
        )
        # 检查是否换了方式（如 file_path 失败后改用 content）
        alternative = any(
            s.get("type") == "tool_call"
            for s in subsequent[:3]
        ) and not retried
    
        if retried:
            # 重试成功（假设重试后没再报错）
            recovered += 1
        elif alternative:
            recovered += 1
        else:
            failures.append(err)
    
    # ============================================================
    # 步骤 3: 计算恢复分数
    # ============================================================
    error_count = len(error_events)
    if error_count == 0:
        score = 1.0  # 没有错误就是最好的恢复
    else:
        # (恢复数 + 1) / (错误总数 + 1) —— 平滑处理，避免 0/1 = 0
        score = (recovered + 1) / (error_count + 1)
    
    return {
        "score": round(score, 2),
        "error_count": error_count,
        "recovered": recovered,
        "failures": failures,
    }


# ================================================================
# TODO 8.7: classify_control_decision — 控制决策六态分类
# ================================================================
# 对 trace 中的每一步做控制决策分类（参考 AgentAtlas 论文）。
#
# 六种状态：
#   - Act: 信息充分，可安全执行（正常路径，期望的决策）
#   - Ask: 任务欠指定，应先澄清（盲目开干 = 失败）
#   - Refuse: 越权/有害请求应拒绝（错误放行 = 失败）
#   - Stop: 已完成或应终止（无限循环 = 失败）
#   - Confirm: 不可逆操作需确认（直接执行 = 失败）
#   - Recover: 失败后应修复而非硬闯（无视错误 = 失败）
#
# 步骤：
#   1. 遍历 trace 中的每一步（注意 TraceRecorder 的 type 只有 think / tool_call / error）：
#      - think 事件：检查 LLM 内容，判断是否包含确认请求、是否宣布完成
#      - tool_call 事件：检查工具名和参数，判断是否需要确认、是否安全；
#        工具内部错误藏在该事件的 result 字段里（result 为 dict 且含 "error" key）
#      - error 事件：工具调用报错（record_error 记录），检查后续是否尝试修复
#   2. 对每一步分配状态：
#      - 大部分工具调用都是 Act（正常）
#      - 如果 LLM 在 think 中问"请确认..."、"是否..." → Ask
#      - 如果 LLM 在 think 中说"已完成"、"已生成" → Stop
#      - 如果 LLM 遇到 error 后改变了工具或参数 → Recover
#      - Refuse 和 Confirm 在当前场景较少出现（需求文档分析不涉及越权操作）
#   3. 统计各状态的数量和比例
#   4. 返回 {"classification": [{step, state, reason}], "stats": {state: count}}
#
# 提示：
#   - 这是一个概念性评测，不需要完美的分类准确率
#   - 重点识别 Recover 和 Stop 状态（对 Agent 迭代最有价值）
#   - 如果分类不准确，在注释中标注"估算"
#
def classify_control_decision(trace: dict) -> dict:
    """
    对 trace 中每一步做控制决策分类。

    参数：
    - trace: TraceRecorder 生成的 trace dict

    返回：
    - {"classification": [{step_num, event_type, state, reason}], "stats": {state: count}}
    """
    # ============================================================
    # 步骤 1: 初始化分类计数
    # ============================================================
    states = {"Act": 0, "Ask": 0, "Refuse": 0, "Stop": 0, "Confirm": 0, "Recover": 0}
    classification = []
    steps = trace.get("steps", [])
    
    # ============================================================
    # 步骤 2: 逐步分类
    # ============================================================
    prev_was_error = False  # 跟踪上一步是否是 error
    
    for i, step in enumerate(steps):
        event_type = step.get("type", "")
        state = "Act"  # 默认状态
        reason = ""
    
        if event_type == "think":
            content = step.get("content", "")
            # 检查是否包含确认请求关键词
            if any(kw in content for kw in ["请确认", "是否", "确认吗", "你确定"]):
                state = "Ask"
                reason = "LLM 请求用户确认"
            # 检查是否宣布完成
            elif any(kw in content for kw in ["已完成", "已生成", "全部完成", "总结"]):
                state = "Stop"
                reason = "LLM 宣布任务完成"
            else:
                state = "Act"
                reason = "LLM 进行分析并决定下一步"
    
        elif event_type == "tool_call":
            # 如果上一步出错，当前调用视为 Recover（错误后的修复动作）
            if prev_was_error:
                state = "Recover"
                reason = f"上一步出错后尝试恢复（调用 {step.get('tool_name', '')}）"
            else:
                state = "Act"
                reason = f"调用工具 {step.get('tool_name', '')}"
            # 工具内部错误藏在本步的 result 里，更新标记供下一步判断是否 Recover
            result = step.get("result", {})
            prev_was_error = isinstance(result, dict) and "error" in result

        elif event_type == "error":
            # 独立的 error 事件（TraceRecorder.record_error 记录）
            prev_was_error = True
            state = "Act"  # 错误本身不算一次决策，仅作为下一步 Recover 的触发条件
            reason = "工具调用报错"
    
        states[state] += 1
        classification.append({
            "step_num": i,
            "event_type": event_type,
            "state": state,
            "reason": reason,
        })
    
    # ============================================================
    # 步骤 3: 计算统计信息
    # ============================================================
    total = sum(states.values())
    stats = {
        state: {"count": count, "ratio": round(count / total, 2) if total > 0 else 0}
        for state, count in states.items()
    }
    return {"classification": classification, "stats": stats}



# ================================================================
# TODO 8.8: run_trajectory_eval — 汇总轨迹评测
# ================================================================
# 把上面 4 个轨迹评测函数汇总为一个完整报告。
#
# 步骤：
#   1. 加载 trace JSON 文件 → dict
#   2. 依次调用 eval_tool_accuracy、eval_step_efficiency、eval_error_recovery、classify_control_decision
#   3. 计算加权总分：
#      - 工具准确率: 35%
#      - 步骤效率: 25%
#      - 错误恢复: 25%
#      - 控制决策: 15%（统计层面的分数，比如 Recover 占比越高越好）
#   4. 打印格式化的轨迹评测报告
#   5. 返回完整结果 dict
#
def run_trajectory_eval(trace_path: str) -> dict:
    """
    汇总轨迹评测。

    参数：
    - trace_path: trace JSON 文件路径

    返回：
    - {"overall_score": float, "dimensions": {...}, "report": "..."}
    """
    # ============================================================
    # 步骤 1: 加载 trace JSON
    # ============================================================
    if not trace_path or not Path(trace_path).exists():
        return {"overall_score": 0, "error": "trace 文件不存在"}
    with open(trace_path, "r", encoding="utf-8") as f:
        trace = json.load(f)
    
    # ============================================================
    # 步骤 2: 运行 4 个轨迹评测维度
    # ============================================================
    # 每个维度包裹 try/except
    results = {}
    
    try:
        results["tool_accuracy"] = eval_tool_accuracy(trace)
    except Exception as e:
        results["tool_accuracy"] = {"score": 0, "error": str(e)}
    
    try:
        results["step_efficiency"] = eval_step_efficiency(trace)
    except Exception as e:
        results["step_efficiency"] = {"score": 0, "error": str(e)}
    
    try:
        results["error_recovery"] = eval_error_recovery(trace)
    except Exception as e:
        results["error_recovery"] = {"score": 0, "error": str(e)}
    
    try:
        results["control_decision"] = classify_control_decision(trace)
    except Exception as e:
        results["control_decision"] = {"stats": {}, "error": str(e)}
    
    # ============================================================
    # 步骤 3: 计算加权总分
    # ============================================================
    weights = {
        "tool_accuracy": 0.35,
        "step_efficiency": 0.25,
        "error_recovery": 0.25,
        "control_decision": 0.15,
    }
    overall = 0.0
    for dim, weight in weights.items():
        if dim in results:
            dim_score = results[dim].get("score", 0)
            # control_decision 没有 score 字段，需要从 stats 计算
            if dim == "control_decision":
                stats = results[dim].get("stats", {})
                total_steps = sum(s.get("count", 0) for s in stats.values())
                recover_count = stats.get("Recover", {}).get("count", 0)
                error_steps = recover_count  # 有 Recover 说明之前有错误
                if total_steps == 0:
                    dim_score = 1.0  # 无步骤，不扣分
                elif error_steps == 0:
                    dim_score = 1.0  # 无错误发生，不需要 Recover = 完美
                else:
                    # 有错误且有恢复 = 好；有错误但无恢复 = 差
                    dim_score = min(1.0, recover_count / max(1, error_steps))
            overall += dim_score * weight
    
    # ============================================================
    # 步骤 4: 生成文本报告并返回
    # ============================================================
    report_lines = [
        "=" * 50,
        "轨迹评测报告",
        "=" * 50,
        f"综合得分: {overall:.2f}",
    ]
    # ...逐维度追加
    
    return {
        "overall_score": round(overall, 2),
        "dimensions": results,
        "report": "\n".join(report_lines),
    }
