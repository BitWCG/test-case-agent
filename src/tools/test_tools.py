"""
Day 2 — 5 个测试领域工具

你需要理解的核心概念：
1. 每个工具都是一个纯函数（输入 dict → 输出 dict）
2. 工具之间可以串联：parse_prd → extract_features → extract_rules → generate_cases → format_output
3. 工具的设计应该"单一职责"——每个工具只做一件事

你的任务：
- parse_prd 已实现（作为参考）
- 完成 TODO 4.1 ~ 4.4：实现剩余 4 个工具
"""
import json
import re
from pathlib import Path


# ================================================================
# 已实现：工具 1 — 解析需求文档
# ================================================================
def parse_prd(file_path: str = "", content: str = "") -> dict:
    """
    解析需求文档，提取结构化信息。
    支持从文件路径读取或直接传入文本内容。
    """
    if file_path:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}
        text = path.read_text(encoding="utf-8")
    elif content:
        text = content
    else:
        return {"error": "必须提供 file_path 或 content 参数"}

    # 提取标题
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1) if title_match else "未知模块"

    # 提取二级标题作为功能区块
    sections = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)

    # 提取三级标题作为子功能
    subsections = re.findall(r"^###\s+(.+)$", text, re.MULTILINE)

    # 提取列表项（- 开头）
    list_items = re.findall(r"^[-*]\s+(.+)$", text, re.MULTILINE)

    # 提取 API 接口（包含 /api/ 或 HTTP 方法）
    api_refs = re.findall(r"(?:GET|POST|PUT|DELETE|PATCH)\s+(/\S+)", text, re.IGNORECASE)

    return {
        "title": title,
        "sections": sections,
        "subsections": subsections,
        "list_items_count": len(list_items),
        "api_refs": api_refs,
        "total_chars": len(text),
        "raw_text": text,  # 保留原文，供后续工具使用
    }


# ================================================================
# TODO 4.1: 工具 2 — 提取功能点
# ================================================================
# 输入：parse_prd 的输出
# 输出：{"features": [{"name": "...", "description": "...", "sub_features": [...]}]}
#
# 你需要：
# 1. 从 prd_data["subsections"] 中提取每个子功能名称
# 2. 从 prd_data["list_items_count"] 判断需求复杂度
# 3. 用 prd_data["raw_text"] 中的内容，为每个功能点生成简要描述
#
# 提示：
# - 用正则提取每个 ### 标题下的文本段落
# - 每个功能点的描述取前 200 字符即可
# - 如果一个功能下有子列表（- 开头的行），提取为 sub_features
#
def extract_features(file_path: str = "", prd_json: str = "", prd_data: dict = None) -> dict:
    """
    从解析后的需求文档中提取功能点列表。
    
    参数：
    - file_path: 需求文档的文件路径（推荐，工具会自动读取并解析）
    - prd_json: parse_prd 输出的 JSON 字符串（备选）
    - prd_data: 或者直接传 dict（代码内部调用）
    
    返回：
    - {"features": [{"name": "...", "description": "...", "sub_features": [...]}]}
    """
    # 如果传入了 file_path，直接读取文件并解析（避免 LLM 传递大段 JSON）
    if file_path and not prd_data:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}
        # 直接调用 parse_prd 获取结构化数据
        prd_data = parse_prd(file_path=file_path)
        if "error" in prd_data:
            return prd_data
    elif prd_json and not prd_data:
        prd_data = json.loads(prd_json) if isinstance(prd_json, str) else prd_json
    
    if not prd_data:
        return {"error": "必须提供 file_path、prd_json 或 prd_data 参数"}

    raw_text = prd_data.get("raw_text", "")
    subsections = prd_data.get("subsections", [])

    if not subsections:
        return {"features": [], "warning": "未找到任何子功能（### 标题）"}

    features = []
    for subsection in subsections:
        # 在 raw_text 中定位 ### 标题，提取其下的内容块
        pattern = rf"^###\s+{re.escape(subsection)}\s*$(.*?)(?=^###?\s|\Z)"
        match = re.search(pattern, raw_text, re.MULTILINE | re.DOTALL)

        if match:
            block = match.group(1).strip()
        else:
            block = ""

        # 提取子列表项（- 开头的行）作为 sub_features
        sub_items = re.findall(r"^[-*]\s+(.+)$", block, re.MULTILINE)

        # 描述：取第一个子列表项之前的文本，或整个 block 的前 200 字符
        first_list_idx = block.find("\n-")
        if first_list_idx > 0:
            desc = block[:first_list_idx].strip()
        else:
            desc = block[:200].strip()

        features.append({
            "name": subsection,
            "description": desc if desc else subsection,
            "sub_features": sub_items,
        })

    return {"features": features}


# ================================================================
# TODO 4.2: 工具 3 — 提取业务规则和边界条件
# ================================================================
# 输入：parse_prd 的输出
# 输出：{"rules": [{"rule": "...", "type": "业务规则|边界条件|约束", "source": "..."}]}
#
# 你需要：
# 1. 从 raw_text 中识别"规则性"文本，特征包括：
#    - 包含数字约束（如"4-20 个字符"、"5 次"、"30 分钟"）
#    - 包含条件判断（如"如果...则..."、"必须"、"不允许"）
#    - 包含边界值（如"最大"、"最小"、"不超过"）
# 2. 为每条规则分类：业务规则 / 边界条件 / 约束
# 3. 标注来源（来自哪个 section）
#
# 提示：
# - 用正则匹配数字+单位模式（如 \d+\s*(个|次|分钟|小时|位|字符)）
# - 用关键词匹配规则类型（"必须"/"不允许" → 业务规则，"最大"/"最小" → 边界条件）
#
def extract_rules(file_path: str = "", prd_json: str = "", prd_data: dict = None) -> dict:
    """
    从需求文档中提取业务规则和边界条件。
    
    参数：
    - file_path: 需求文档的文件路径（推荐，工具会自动读取并解析）
    - prd_json: parse_prd 输出的 JSON 字符串（备选）
    - prd_data: 或者直接传 dict（代码内部调用）
    
    返回：
    - {"rules": [{"rule": "...", "type": "业务规则|边界条件|约束", "source": "..."}]}
    """
    # 如果传入了 file_path，直接读取文件并解析（避免 LLM 传递大段 JSON）
    if file_path and not prd_data:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}
        prd_data = parse_prd(file_path=file_path)
        if "error" in prd_data:
            return prd_data
    elif prd_json and not prd_data:
        prd_data = json.loads(prd_json) if isinstance(prd_json, str) else prd_json
    
    if not prd_data:
        return {"error": "必须提供 file_path、prd_json 或 prd_data 参数"}

    raw_text = prd_data.get("raw_text", "")
    sections = prd_data.get("sections", [])

    # 规则关键词 → 类型映射
    boundary_keywords = ["最大", "最小", "不超过", "超过", "至少", "至多", "上限", "下限"]
    business_keywords = ["必须", "不允许", "不允许", "禁止", "需要", "应该", "应当"]
    constraint_keywords = ["限制", "约束", "要求", "条件", "仅", "只"]

    rules = []
    seen_rules = set()  # 去重

    # 逐行扫描 raw_text，寻找规则性文本
    # 同时追踪当前所在的 section
    current_section = ""
    for line in raw_text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # 追踪当前 section（## 标题）
        section_match = re.match(r"^##\s+(.+)$", line_stripped)
        if section_match:
            current_section = section_match.group(1).strip()
            continue

        # 跳过标题行本身
        if line_stripped.startswith("#"):
            continue

        # 检查是否包含数字约束（如 4-20 个字符、5 次、30 分钟）
        has_number = re.search(r"\d+[\s\-~]*\d*\s*(个|次|分钟|小时|位|字符|天|秒|年|月|周|MB|GB|KB)", line_stripped)

        # 检查是否包含规则关键词
        is_business = any(kw in line_stripped for kw in business_keywords)
        is_boundary = any(kw in line_stripped for kw in boundary_keywords)
        is_constraint = any(kw in line_stripped for kw in constraint_keywords)

        # 判断是否为规则行
        if has_number or is_business or is_boundary or is_constraint:
            # 去重：同一行不重复添加
            if line_stripped in seen_rules:
                continue
            seen_rules.add(line_stripped)

            # 分类：边界条件 > 业务规则 > 约束
            if is_boundary or (has_number and not is_business):
                rule_type = "边界条件"
            elif is_business:
                rule_type = "业务规则"
            else:
                rule_type = "约束"

            rules.append({
                "rule": line_stripped,
                "type": rule_type,
                "source": current_section or "未分类",
            })

    return {"rules": rules}


# ================================================================
# TODO 4.3: 工具 4 — 生成测试用例框架
# ================================================================
# 输入：features + rules 的合并结果
# 输出：{"cases": [{"feature": "...", "type": "正向|反向|边界", "description": "..."}]}
#
# 你需要：
# 1. 遍历每个功能点，为它生成正向用例（正常流程）
# 2. 遍历每条规则，为它生成反向/边界用例
# 3. 合并去重
#
# 提示：
# - 每个 feature 至少生成 1 个正向用例
# - 每条"边界条件"类型的 rule 生成 1 个边界用例
# - 每条"业务规则"类型的 rule 生成 1 个反向用例
#
def generate_cases(features_json: str = "", rules_json: str = "") -> dict:
    """
    根据功能点和规则生成测试用例框架。
    
    参数：
    - features_json: extract_features 输出的 JSON 字符串
    - rules_json: extract_rules 输出的 JSON 字符串
    
    返回：
    - {"cases": [{"feature": "...", "type": "正向|反向|边界", "description": "..."}]}
    """
    features_data = json.loads(features_json) if features_json else {"features": []}
    rules_data = json.loads(rules_json) if rules_json else {"rules": []}

    cases = []
    seen = set()  # 去重

    # 1. 为每个功能点生成正向用例
    for feature in features_data.get("features", []):
        name = feature.get("name", "未知功能")
        desc = feature.get("description", "")
        sub_features = feature.get("sub_features", [])

        # 主功能正向用例
        case_key = (name, "正向", f"验证{name}功能正常工作")
        if case_key not in seen:
            seen.add(case_key)
            cases.append({
                "feature": name,
                "type": "正向",
                "description": f"验证{name}功能正常工作：{desc[:100]}" if desc else f"验证{name}功能正常工作",
            })

        # 为每个子功能生成正向用例
        for sub in sub_features:
            case_key = (name, "正向", f"验证{name} - {sub}")
            if case_key not in seen:
                seen.add(case_key)
                cases.append({
                    "feature": name,
                    "type": "正向",
                    "description": f"验证{name} - {sub}",
                })

    # 2. 为每条规则生成反向/边界用例
    for rule in rules_data.get("rules", []):
        rule_text = rule.get("rule", "")
        rule_type = rule.get("type", "")
        source = rule.get("source", "")

        if rule_type == "边界条件":
            case_key = (source, "边界", rule_text)
            if case_key not in seen:
                seen.add(case_key)
                cases.append({
                    "feature": source,
                    "type": "边界",
                    "description": f"边界测试：{rule_text}",
                })
        elif rule_type == "业务规则":
            case_key = (source, "反向", rule_text)
            if case_key not in seen:
                seen.add(case_key)
                cases.append({
                    "feature": source,
                    "type": "反向",
                    "description": f"反向测试：{rule_text}",
                })
        else:  # 约束
            case_key = (source, "反向", rule_text)
            if case_key not in seen:
                seen.add(case_key)
                cases.append({
                    "feature": source,
                    "type": "反向",
                    "description": f"约束验证：{rule_text}",
                })

    return {"cases": cases}


# ================================================================
# TODO 4.4: 工具 5 — 格式化输出
# ================================================================
# 输入：generate_cases 的输出
# 输出：最终的格式化字符串（Markdown 表格或 JSON）
#
# 你需要：
# 1. 为每个用例分配唯一 ID（TC-001, TC-002...）
# 2. 为每个用例分配优先级（边界/安全 → 高，反向 → 中，正向 → 低）
# 3. 输出为 Markdown 表格格式，方便人类阅读
#
# 提示：
# - Markdown 表格格式：| ID | 功能 | 类型 | 优先级 | 描述 |
# - 用 enumerate 生成 ID
#
def format_output(cases_json: str = "") -> dict:
    """
    将测试用例框架格式化为可读的 Markdown 表格。
    
    返回：
    - {"markdown": "Markdown 表格字符串", "total": 用例总数}
    """
    cases_data = json.loads(cases_json) if cases_json else {"cases": []}
    cases = cases_data.get("cases", [])

    if not cases:
        return {"markdown": "无测试用例", "total": 0}

    # 优先级映射
    def get_priority(case_type: str) -> str:
        if case_type in ("边界", "安全"):
            return "高"
        elif case_type == "反向":
            return "中"
        else:
            return "低"

    # 构建 Markdown 表格
    lines = [
        "| ID | 功能 | 类型 | 优先级 | 描述 |",
        "|------|------|------|--------|------|",
    ]

    for idx, case in enumerate(cases, start=1):
        case_id = f"TC-{idx:03d}"
        feature = case.get("feature", "未知")
        case_type = case.get("type", "未知")
        priority = get_priority(case_type)
        desc = case.get("description", "")

        lines.append(f"| {case_id} | {feature} | {case_type} | {priority} | {desc} |")

    markdown = "\n".join(lines)

    return {"markdown": markdown, "total": len(cases)}
