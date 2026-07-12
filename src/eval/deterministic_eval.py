"""
Day 12: 确定性评测器

评测维度（全部基于代码可自动判断，不需要 LLM）：
  1. 格式合规 — JSON schema 校验、必填字段检查
  2. 功能覆盖率 — 输出的测试用例是否覆盖了 expected_modules 中的各模块
  3. 场景覆盖率 — 输出的测试用例是否覆盖了每个模块下的 key_scenarios
  4. 用例数量 — 是否达到 min_test_cases
  5. 类别覆盖 — 是否包含正向/反向/边界等类别
  6. 效率指标 — 工具调用次数、总 token、运行时长

输入：
  - result: Agent 的最终输出（Markdown 或 JSON 字符串）
  - expected: 参考答案（data/eval/expected/*.json，层级结构 expected_modules）
  - trace: TraceRecorder 生成的 trace JSON（data/eval/traces/*.json）

输出：
  - 每个维度一个分数（0.0 ~ 1.0）
  - 汇总报告
"""
import json
import re
from pathlib import Path


# ================================================================
# TODO 7.1: eval_format — JSON schema 格式合规检查
# ================================================================
# 检查 Agent 输出的测试用例是否符合约定的 JSON 结构。
#
# 步骤：
#   1. 尝试从 result 中提取测试用例 JSON：
#      - 如果 result 本身是 JSON 字符串，直接 parse
#      - 如果 result 是 Markdown，用正则从表格中解析出测试用例列表
#      - 如果都不行，返回 0 分
#   2. 对每条用例检查必填字段（feature、type、description）
#   3. 检查 type 字段的值是否在合法集合中（正向、反向、边界、安全、性能等）
#   4. 返回 (score, details)
#      - score = 合规的用例数 / 总用例数
#      - details 包含每条不合规用例的具体问题
#
# 提示：
#   - 用 isinstance() 判断数据类型
#   - 用 try/except json.JSONDecodeError 处理解析失败
#   - Markdown 表格解析：按行 split，找 | 分隔的列
#
def eval_format(result: str) -> dict:
    """
    检查 Agent 输出的格式合规性。

    参数：
    - result: Agent 最终输出的文本（可能是 JSON 或 Markdown）

    返回：
    - {"score": float, "details": {...}, "total_cases": int, "valid_cases": int}
    """
    # 提取用例列表
    cases = _extract_cases(result)
    if not cases:
        return {"score": 0.0, "total_cases": 0, "valid_cases": 0,
                "details": {"issues": [], "error": "无法从输出中解析出用例"}}

    # 定义必填字段和合法 type 值
    required_fields = ["feature", "type", "description"]
    valid_types = {"正向", "反向", "边界", "安全", "性能", "兼容性"}
    
    # 逐条检查
    valid_cases = 0
    issues = []  # 记录每条不合规用例的问题
    for i, case in enumerate(cases):
        case_issues = []
        # 3a. 检查是否包含所有必填字段（用 isinstance(case, dict) 判断）
        for field in required_fields:
            if field not in case:
                case_issues.append(f"缺少字段 '{field}'")
        # 3b. 检查必填字段是否有值（不为空字符串、不为 None）
        for field in required_fields:
            if field in case and not case[field]:
                case_issues.append(f"字段 '{field}' 为空")
        # 3c. 检查 type 字段是否在合法集合中
        if "type" in case and case["type"] not in valid_types:
            case_issues.append(f"类型 '{case['type']}' 不在 {valid_types} 中")
        # 统计
        if not case_issues:
            valid_cases += 1
        else:
            issues.append({"index": i, "case": case, "issues": case_issues})
    
    # 计算分数并返回
    total_cases = len(cases)
    score = valid_cases / total_cases if total_cases > 0 else 0.0
    return {
        "score": round(score, 2),
        "total_cases": total_cases,
        "valid_cases": valid_cases,
        "details": {"issues": issues, "required_fields": required_fields},
    }


# ================================================================
# TODO 7.2: eval_feature_coverage — 功能点覆盖率
# ================================================================
# 检查 Agent 生成的测试用例是否覆盖了参考答案中的所有功能点。
#
# 步骤：
#   1. 从 expected 中读取 expected_features 列表
#   2. 从 result 中提取所有用例的 feature 字段值（去重）
#   3. 对每个 expected_feature：
#      - 在用例的 feature 列表中做模糊匹配（包含关系即可，不需要完全相等）
#      - 例如 expected="登录流程" 能匹配 feature="1. 登录流程" 或 "登录"
#      - 如果匹配到至少 1 条用例，视为已覆盖
#   4. 计算覆盖率 = 已覆盖的功能点数 / 总功能点数
#   5. 返回 (score, covered_features, uncovered_features)
#
# 提示：
#   - 模糊匹配：用 in 或字符串相似度（去除空格和标点后比较）
#   - 不要要求完全相等，Agent 对功能点的命名可能略有不同
#
def eval_feature_coverage(result: str, expected: dict) -> dict:
    """
    检查功能点覆盖率。
    从 expected_modules 的 keys 提取期望的功能模块名。

    参数：
    - result: Agent 最终输出
    - expected: 参考答案 dict（含 expected_modules 字段）

    返回：
    - {"score": float, "covered": [...], "uncovered": [...], "total_expected": int}
    """
    # 从层级结构中读取模块名（expected_modules 的 keys）
    modules = expected.get("expected_modules", {})
    expected_features = list(modules.keys()) if modules else expected.get("expected_features", [])
    if not expected_features:
        return {"score": 1.0, "covered": [], "uncovered": [], "total_expected": 0}
    
    # 提取 Agent 输出中的所有 feature 值（去重）
    cases = _extract_cases(result)
    actual_features = set()
    for case in cases:
        feature = case.get("feature", "")
        if feature:
            actual_features.add(feature.strip())
    
    # 模糊匹配：去除空格和标点后做双向包含判断
    def normalize(s):
        return re.sub(r"[\s\d\.\-\u3001\uff0c\u3002]", "", s).lower()
    
    covered = []
    uncovered = []
    for ef in expected_features:
        ef_norm = normalize(ef)
        matched = False
        for af in actual_features:
            af_norm = normalize(af)
            if ef_norm in af_norm or af_norm in ef_norm:
                matched = True
                break
        if matched:
            covered.append(ef)
        else:
            uncovered.append(ef)
    
    total = len(expected_features)
    score = len(covered) / total if total > 0 else 1.0
    return {
        "score": round(score, 2),
        "covered": covered,
        "uncovered": uncovered,
        "total_expected": total,
    }


# ================================================================
# eval_scenario_coverage — 场景覆盖率
# ================================================================
def eval_scenario_coverage(result: str, expected: dict) -> dict:
    """
    检查场景覆盖率。
    从 expected_modules 中收集所有模块的 key_scenarios，
    检查 Agent 输出的用例描述是否覆盖了这些预期场景。

    参数：
    - result: Agent 最终输出
    - expected: 参考答案 dict（含 expected_modules 字段）

    返回：
    - {"score": float, "covered": [...], "uncovered": [...], "total_scenarios": int,
       "by_module": {模块名: {"covered": [...], "uncovered": [...]}}}
    """
    modules = expected.get("expected_modules", {})
    if not modules:
        return {"score": 1.0, "covered": [], "uncovered": [], "total_scenarios": 0, "by_module": {}}

    # 提取 Agent 输出中所有用例的 feature + description（合并为一段文本）
    cases = _extract_cases(result)
    all_text = " ".join(
        f"{c.get('feature', '')} {c.get('description', '')}" for c in cases
    ).lower()

    all_covered = []
    all_uncovered = []
    by_module = {}

    def extract_scenario_keywords(scenario: str) -> list[str]:
        """
        从场景描述中提取关键匹配片段。
        策略：提取数字、错误码、核心动作词，只要 Agent 输出包含这些片段就算匹配。
        例："第 4 次失败后不锁定" → ["4次", "失败", "不锁定", "锁定"]
        """
        keywords = []
        # 1. 数字+单位（去掉空格，如 "4次"、"30分钟"）
        num_unit = re.findall(r"\d+\s*([\u6b21\u4e2a\u4f4d\u5206\u949f\u5c0f\u65f6\u5929\u5e74])", scenario)
        for m in re.finditer(r"(\d+)\s*([\u6b21\u4e2a\u4f4d\u5206\u949f\u5c0f\u65f6\u5929\u5e74]+)", scenario):
            keywords.append(m.group(1) + m.group(2))  # "4次" not "4 次"
        # 2. 独立数字（如场景中的 "3"、"5"、"10"）
        keywords.extend(re.findall(r"\b\d+\b", scenario))
        # 3. 错误码（如 401、423、429）
        keywords.extend(re.findall(r"\b[3-5]\d{2}\b", scenario))
        # 4. 核心动作词/否定词（"锁定"、"不锁定"、"拒绝"、"被拒绝"、"成功"、"失败"、"过期"、"失效"）
        action_words = re.findall(r"[\u4e0d]?[\u9501\u5b9a\u62d2\u7edd\u6210\u529f\u5931\u8d25\u89e3\u9501\u8fc7\u671f\u5931\u6548\u9650\u6d41\u8fd4\u56de]+", scenario)
        keywords.extend(action_words)
        # 5. 如果没提取到任何关键词，用场景中最长的中文片段（>= 2 字符）
        if not keywords:
            segments = re.findall(r"[\u4e00-\u9fff]{2,}", scenario)
            if segments:
                keywords.append(max(segments, key=len))
            else:
                keywords.append(scenario.replace(" ", ""))
        # 去重保序
        seen = set()
        unique = []
        for kw in keywords:
            kw_clean = kw.strip()
            if kw_clean and kw_clean not in seen:
                seen.add(kw_clean)
                unique.append(kw_clean)
        return unique

    for mod_name, mod_data in modules.items():
        scenarios = mod_data.get("key_scenarios", [])
        mod_covered = []
        mod_uncovered = []
        for scenario in scenarios:
            # 关键词匹配：只要 Agent 输出中包含场景的关键片段，就算覆盖
            keywords = extract_scenario_keywords(scenario)
            # 至少要有 1 个关键词命中（数字/错误码/动作词任一匹配即可）
            matched = any(kw in all_text for kw in keywords) if keywords else False
            if matched:
                mod_covered.append(scenario)
            else:
                mod_uncovered.append(scenario)
        all_covered.extend(mod_covered)
        all_uncovered.extend(mod_uncovered)
        by_module[mod_name] = {"covered": mod_covered, "uncovered": mod_uncovered}

    total = len(all_covered) + len(all_uncovered)
    score = len(all_covered) / total if total > 0 else 1.0
    return {
        "score": round(score, 2),
        "covered": all_covered,
        "uncovered": all_uncovered,
        "total_scenarios": total,
        "by_module": by_module,
    }


# ================================================================
# TODO 7.4: eval_case_count — 用例数量检查
# ================================================================
# 检查 Agent 生成的测试用例数量是否达标。
#
# 步骤：
#   1. 从 expected 中读取 min_test_cases
#   2. 统计 result 中的用例总数
#   3. 计算分数：
#      - 如果实际数 >= 最小数：score = 1.0
#      - 否则：score = 实际数 / 最小数（线性衰减）
#      - 如果实际数为 0：score = 0.0
#   4. 返回 (score, actual_count, expected_min)
#
def eval_case_count(result: str, expected: dict) -> dict:
    """
    检查用例数量是否达标。

    参数：
    - result: Agent 最终输出
    - expected: 参考答案 dict（含 min_test_cases 字段）

    返回：
    - {"score": float, "actual": int, "expected_min": int}
    """
    min_expected = expected.get("min_test_cases", 0)
    if min_expected == 0:
        return {"score": 1.0, "actual": 0, "expected_min": 0}

    cases = _extract_cases(result)
    actual_count = len(cases)

    if actual_count >= min_expected:
        score = 1.0
    elif actual_count == 0:
        score = 0.0
    else:
        score = actual_count / min_expected

    return {
        "score": round(score, 2),
        "actual": actual_count,
        "expected_min": min_expected,
    }


# ================================================================
# TODO 7.5: eval_category_coverage — 类别覆盖检查
# ================================================================
# 检查 Agent 生成的用例是否涵盖了所有必须的测试类别。
#
# 步骤：
#   1. 从 expected 中读取 must_cover_categories（如 ["正向","反向","边界"]）
#   2. 统计 result 中每条用例的 type 字段，记录出现了哪些类别
#   3. 计算覆盖率 = 已覆盖的类别数 / 必须覆盖的类别数
#   4. 返回 (score, covered_categories, missing_categories)
#
def eval_category_coverage(result: str, expected: dict) -> dict:
    """
    检查测试类别覆盖率。

    参数：
    - result: Agent 最终输出
    - expected: 参考答案 dict（含 must_cover_categories 字段）

    返回：
    - {"score": float, "covered": [...], "missing": [...], "required": [...]}
    """
    required = expected.get("must_cover_categories", [])
    if not required:
        required = ["正向", "反向", "边界"]

    cases = _extract_cases(result)
    actual_categories = set()
    for case in cases:
        ctype = case.get("type", "")
        if ctype:
            actual_categories.add(ctype.strip())

    # 模糊匹配：类别名可能有细微差异（如 "反向用例" vs "反向"）
    covered = []
    missing = []
    for req_cat in required:
        matched = any(req_cat in act_cat or act_cat in req_cat
                       for act_cat in actual_categories)
        if matched:
            covered.append(req_cat)
        else:
            missing.append(req_cat)

    total = len(required)
    score = len(covered) / total if total > 0 else 1.0
    return {
        "score": round(score, 2),
        "covered": covered,
        "missing": missing,
        "required": required,
    }


# ================================================================
# TODO 7.6: eval_efficiency — 效率指标评测
# ================================================================
# 评估 Agent 执行过程的效率。
#
# 步骤：
#   1. 从 trace JSON 中读取以下数据：
#      - tool_call_count: 工具调用总次数
#      - total_tokens: 消耗的总 token 数
#      - elapsed_seconds: 总运行时长（从 trace 的 started_at 到 finished_at）
#   2. 为每个指标打分：
#      - 工具调用次数：<= 8 次 = 1.0，8-15 = 0.7，> 15 = 0.3
#      - Token 消耗：<= 10000 = 1.0，10000-30000 = 0.7，> 30000 = 0.3
#      - 运行时长：<= 30 秒 = 1.0，30-90 = 0.7，> 90 = 0.3
#   3. 综合分数 = 三个指标的平均值
#   4. 返回 (score, breakdown)
#
# 提示：
#   - trace JSON 的结构由 TraceRecorder.save() 定义，需要先看一下 trace 的输出格式
#   - 如果 trace 中缺少某个字段，该维度给默认分 0.5（中性）
#   - 效率是"越低越好"，所以打分逻辑是反向的
#
def eval_efficiency(trace_path: str) -> dict:
    """
    评估 Agent 执行效率。

    参数：
    - trace_path: trace JSON 文件路径

    返回：
    - {"score": float, "breakdown": {"tool_calls": {...}, "tokens": {...}, "time": {...}}}
    """
    if not trace_path or not Path(trace_path).exists():
        return {"score": 0.5, "breakdown": {}, "error": "trace 文件不存在"}
    with open(trace_path, "r", encoding="utf-8") as f:
        trace = json.load(f)

    # 提取效率指标
    steps = trace.get("steps", [])
    tool_call_count = sum(1 for s in steps if s.get("type") == "tool_call")
    thinks = [s for s in steps if s.get("type") == "think"]
    total_tokens = sum(s.get("usage", {}).get("total_tokens", 0) for s in thinks)

    # 运行时长
    elapsed_seconds = 0
    started_at = trace.get("started_at", "")
    finished_at = trace.get("finished_at", "")
    if started_at and finished_at:
        from datetime import datetime
        try:
            start = datetime.fromisoformat(started_at)
            end = datetime.fromisoformat(finished_at)
            elapsed_seconds = (end - start).total_seconds()
        except ValueError:
            elapsed_seconds = 0

    # 按阈值打分
    def score_by_threshold(value, thresholds):
        for threshold, sc in thresholds:
            if value <= threshold:
                return sc
        return thresholds[-1][1]

    tool_score = score_by_threshold(tool_call_count, [(8, 1.0), (15, 0.7), (float("inf"), 0.3)])
    token_score = score_by_threshold(total_tokens, [(10000, 1.0), (30000, 0.7), (float("inf"), 0.3)])
    time_score = score_by_threshold(elapsed_seconds, [(30, 1.0), (90, 0.7), (float("inf"), 0.3)])

    overall = (tool_score + token_score + time_score) / 3
    return {
        "score": round(overall, 2),
        "breakdown": {
            "tool_calls": {"value": tool_call_count, "score": tool_score},
            "tokens": {"value": total_tokens, "score": token_score},
            "time": {"value": round(elapsed_seconds, 1), "score": time_score},
        },
    }


# ================================================================
# TODO 7.7: run_all — 汇总所有确定性评测
# ================================================================
# 把上面 6 个评测函数的结果汇总成一个完整报告。
#
# 步骤：
#   1. 依次调用 eval_format、eval_feature_coverage、eval_rule_coverage、
#      eval_case_count、eval_category_coverage、eval_efficiency
#   2. 把每个维度的 score 汇总为一个总分数
#   3. 计算加权总分（各维度权重见下方注释）
#   4. 打印格式化的评测报告
#   5. 返回完整的结果 dict
#
# 权重设计（可以根据实际需要调整）：
#   - 格式合规: 10%
#   - 功能覆盖率: 25%（没覆盖模块就是没用的用例）
#   - 场景覆盖率: 30%（最重要——检查关键场景是否被覆盖）
#   - 用例数量: 15%
#   - 类别覆盖: 10%
#   - 效率: 10%
#
# 提示：
#   - 如果 expected 中缺少某个字段（如没有 expected_rules），跳过对应维度
#   - 打印报告时用 Unicode 字符美化（如 ✓ ✗ ⚠）
#   - 最终返回的 dict 应该同时包含分项分数和总分数
#
def run_deterministic_eval(result: str, expected: dict, trace_path: str = None) -> dict:
    """
    运行所有确定性评测并输出报告。

    参数：
    - result: Agent 最终输出文本
    - expected: 参考答案 dict
    - trace_path: trace JSON 文件路径（可选，用于效率评测）

    返回：
    - {
        "overall_score": float,
        "dimensions": {
          "format": {...},
          "feature_coverage": {...},
          "scenario_coverage": {...},
          "case_count": {...},
          "category_coverage": {...},
          "efficiency": {...}
        },
        "report": "格式化的文本报告"
      }
    """
    # 依次运行所有评测维度（每个包裹在 try/except 中）
    results = {}

    try:
        results["format"] = eval_format(result)
    except Exception as e:
        results["format"] = {"score": 0, "error": str(e)}

    try:
        results["feature_coverage"] = eval_feature_coverage(result, expected)
    except Exception as e:
        results["feature_coverage"] = {"score": 0, "error": str(e)}

    try:
        results["scenario_coverage"] = eval_scenario_coverage(result, expected)
    except Exception as e:
        results["scenario_coverage"] = {"score": 0, "error": str(e)}

    try:
        results["case_count"] = eval_case_count(result, expected)
    except Exception as e:
        results["case_count"] = {"score": 0, "error": str(e)}

    try:
        results["category_coverage"] = eval_category_coverage(result, expected)
    except Exception as e:
        results["category_coverage"] = {"score": 0, "error": str(e)}

    try:
        results["efficiency"] = eval_efficiency(trace_path)
    except Exception as e:
        results["efficiency"] = {"score": 0.5, "error": str(e)}

    # 加权总分（6 个维度）
    weights = {
        "format": 0.10,
        "feature_coverage": 0.25,
        "scenario_coverage": 0.30,
        "case_count": 0.15,
        "category_coverage": 0.10,
        "efficiency": 0.10,
    }
    overall = 0.0
    for dim, weight in weights.items():
        if dim in results:
            overall += results[dim].get("score", 0) * weight

    # 生成文本报告
    report_lines = [
        "=" * 60,
        "  确定性评测报告",
        "=" * 60,
        f"  综合得分: {overall:.2f} (加权)",
        "",
    ]
    dim_names = {
        "format": "格式合规",
        "feature_coverage": "功能覆盖率",
        "scenario_coverage": "场景覆盖率",
        "case_count": "用例数量",
        "category_coverage": "类别覆盖",
        "efficiency": "效率指标",
    }
    for dim, cn_name in dim_names.items():
        r = results.get(dim, {})
        sc = r.get("score", 0)
        bar = "\u2588" * int(sc * 20) + "\u2591" * (20 - int(sc * 20))
        report_lines.append(f"    {cn_name:<12} [{bar}] {sc:.2f}")
        # 覆盖率类维度追加详情
        if dim == "feature_coverage":
            for c in r.get("covered", []):
                report_lines.append(f"      \u2713 {c}")
            for u in r.get("uncovered", []):
                report_lines.append(f"      \u2717 {u}")
        elif dim == "scenario_coverage":
            for u in r.get("uncovered", []):
                report_lines.append(f"      \u2717 {u}")
    report_lines.append("=" * 60)
    report = "\n".join(report_lines)

    return {
        "overall_score": round(overall, 2),
        "dimensions": results,
        "report": report,
    }


# ================================================================
# 辅助函数
# ================================================================

# TODO 7.8: _extract_cases — 从 Agent 输出中提取用例列表
# 这是一个会被多个评测函数复用的辅助函数。
#
# 步骤：
#   1. 尝试将 result 作为 JSON 解析：
#      - 如果解析成功且是 list，直接返回
#      - 如果解析成功且是 dict，尝试取 "cases" 字段
#   2. 如果 JSON 解析失败，尝试从 Markdown 表格中提取：
#      - 按行 split，找 | 分隔的行
#      - 跳过表头行（包含 --- 的行）
#      - 每一行解析出：ID、功能模块(feature)、类型(type)、优先级、描述(description)
#      - 返回解析出的用例 list
#   3. 如果都失败，返回空列表
#
# 提示：
#   - Markdown 表格的列顺序：| ID | 功能 | 类型 | 优先级 | 描述 |
#   - 注意处理表格中的转义字符
#   - 返回的每条用例是一个 dict：{"feature": "...", "type": "...", "description": "..."}
#
def _extract_cases(result: str) -> list[dict]:
    """
    从 Agent 输出中提取测试用例列表。

    参数：
    - result: Agent 最终输出（JSON 或 Markdown 表格）

    返回：
    - [{feature, type, description}, ...]
    """
    if not result:
        return []

    # ============================================================
    # 策略 1: 尝试 JSON 解析
    # ============================================================
    try:
        data = json.loads(result)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # 尝试常见的 key: "cases", "test_cases", "data"
            for key in ["cases", "test_cases", "data"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
            # 如果只有一个 key 且值是 list，直接取
            values = [v for v in data.values() if isinstance(v, list)]
            if len(values) == 1:
                return values[0]
    except (json.JSONDecodeError, TypeError):
        pass  # 不是 JSON，尝试 Markdown 解析

    # ============================================================
    # 策略 2: Markdown 表格解析
    # ============================================================
    lines = result.strip().split("\n")
    cases = []
    headers = []

    for line in lines:
        line = line.strip()
        if not line or "|" not in line:
            continue
        cols = [c.strip() for c in line.split("|")]
        cols = [c for c in cols if c]
        if not cols:
            continue
        # 跳过表头分隔行（包含 --- 或 :-- 等）
        if all(re.match(r"^[-:]+$", c) for c in cols):
            continue
        # 第一行有效表格行 = 表头
        if not headers:
            headers = [h.lower().strip() for h in cols]
            continue
        # 数据行：按表头映射到字典
        if len(cols) >= len(headers):
            case = {}
            for i, header in enumerate(headers):
                if i < len(cols):
                    if any(kw in header for kw in ["id", "序号", "编号"]):
                        case["id"] = cols[i]
                    elif any(kw in header for kw in ["功能", "模块", "feature"]):
                        case["feature"] = cols[i]
                    elif any(kw in header for kw in ["类型", "type", "分类"]):
                        case["type"] = cols[i]
                    elif any(kw in header for kw in ["优先级", "priority"]):
                        case["priority"] = cols[i]
                    elif any(kw in header for kw in ["描述", "说明", "description", "用例", "测试点"]):
                        case["description"] = cols[i]
            # 只有包含了 feature 或 description 的才算有效用例
            if case.get("feature") or case.get("description"):
                cases.append(case)

    return cases
