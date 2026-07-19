"""
工具函数 — 测试用例生成 Agent 工具链（6 个工具）

工具流水线：
  parse_prd → analyze_requirements → extract_features → extract_rules → generate_cases → format_output
"""
import json
import re
from pathlib import Path


# ================================================================
# 工具 1: parse_prd — 解析需求文档
# ================================================================
def parse_prd(file_path: str = "", content: str = "") -> dict:
    """
    解析需求文档（Markdown 格式），提取标题、功能区块、子功能、API 接口定义等结构化信息。
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

    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1) if title_match else "未知模块"

    sections = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
    subsections = re.findall(r"^###\s+(.+)$", text, re.MULTILINE)
    list_items = re.findall(r"^[-*]\s+(.+)$", text, re.MULTILINE)
    api_refs = re.findall(r"(?:GET|POST|PUT|DELETE|PATCH)\s+(/\S+)", text, re.IGNORECASE)

    return {
        "title": title,
        "sections": sections,
        "subsections": subsections,
        "list_items_count": len(list_items),
        "api_refs": api_refs,
        "total_chars": len(text),
        "raw_text": text,
    }


# ================================================================
# 工具 2: analyze_requirements — 结构化扫描需求文档
# ================================================================
# LLM 能理解需求，但容易"凭感觉"遗漏模块。
# 这个工具用确定性方法（标题层级 + 关键词 + 数字正则）做一遍完整扫描，
# 给 LLM 一个"检查清单"，防止遗漏模块、规则或接口。
def analyze_requirements(content: str = "", file_path: str = "") -> dict:
    """
    结构化拆解需求文档，提取模块、规则、接口和数字约束清单。
    在生成测试用例前调用，确保不遗漏任何需求点。
    """
    if file_path and not content:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}
        text = path.read_text(encoding="utf-8")
    elif content:
        text = content
    else:
        return {"error": "必须提供 content 或 file_path"}

    # 1. 提取模块（## 和 ### 标题）
    modules = []
    for line in text.split("\n"):
        h2 = re.match(r"^##\s+(.+)$", line)
        h3 = re.match(r"^###\s+(.+)$", line)
        if h2:
            modules.append({"name": h2.group(1).strip(), "sub_modules": [], "level": 2})
        elif h3 and modules:
            modules[-1]["sub_modules"].append(h3.group(1).strip())

    # 2. 提取规则性文本（含数字约束、条件判断、强制词）
    rules = []
    number_pattern = r"\d+[\s\-~]*\d*\s*(个|次|分钟|小时|位|字符|天|秒|年|月|周|MB|GB|KB|条|项)"
    rule_keywords = ["必须", "不允许", "禁止", "需要", "应该", "应当", "不得"]
    boundary_keywords = ["最大", "最小", "不超过", "超过", "至少", "至多", "上限", "下限", "最多"]

    current_section = ""
    seen = set()
    for line in text.split("\n"):
        ls = line.strip()
        if not ls:
            continue
        sec_match = re.match(r"^##\s+(.+)$", ls)
        if sec_match:
            current_section = sec_match.group(1).strip()
            continue
        if ls.startswith("#"):
            continue

        has_number = re.search(number_pattern, ls)
        is_rule = any(kw in ls for kw in rule_keywords)
        is_boundary = any(kw in ls for kw in boundary_keywords)

        if (has_number or is_rule or is_boundary) and ls not in seen:
            seen.add(ls)
            rule_type = "边界条件" if (is_boundary or (has_number and not is_rule)) else ("业务规则" if is_rule else "约束")
            rules.append({"text": ls, "type": rule_type, "section": current_section or "未分类"})

    # 3. 提取 API 接口
    apis = []
    seen_apis = set()
    for match in re.finditer(r"(GET|POST|PUT|DELETE|PATCH)\s+(/\S+)", text, re.IGNORECASE):
        endpoint = f"{match.group(1).upper()} {match.group(2)}"
        if endpoint not in seen_apis:
            seen_apis.add(endpoint)
            apis.append({"endpoint": endpoint, "method": match.group(1).upper(), "path": match.group(2)})

    # 4. 提取数字约束
    numbers = []
    for match in re.finditer(number_pattern, text):
        ctx_start = max(0, match.start() - 30)
        ctx_end = min(len(text), match.end() + 30)
        numbers.append({"value": match.group(0), "context": text[ctx_start:ctx_end].replace("\n", " ").strip()})

    return {
        "modules": modules,
        "rules": rules,
        "apis": apis,
        "numbers": numbers,
        "summary": {
            "module_count": len(modules),
            "sub_module_count": sum(len(m["sub_modules"]) for m in modules),
            "rule_count": len(rules),
            "api_count": len(apis),
            "number_count": len(numbers),
        },
    }


# ================================================================
# 工具 3: extract_features — 提取功能点
# ================================================================
def extract_features(file_path: str = "", prd_json: str = "", prd_data: dict = None) -> dict:
    """
    从解析后的需求文档中提取功能点列表。
    """
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
    subsections = prd_data.get("subsections", [])

    if not subsections:
        return {"features": [], "warning": "未找到任何子功能（### 标题）"}

    features = []
    for subsection in subsections:
        pattern = rf"^###\s+{re.escape(subsection)}\s*$(.*?)(?=^###?\s|\Z)"
        match = re.search(pattern, raw_text, re.MULTILINE | re.DOTALL)
        block = match.group(1).strip() if match else ""

        sub_items = re.findall(r"^[-*]\s+(.+)$", block, re.MULTILINE)

        first_list_idx = block.find("\n-")
        desc = block[:first_list_idx].strip() if first_list_idx > 0 else block[:200].strip()

        features.append({
            "name": subsection,
            "description": desc if desc else subsection,
            "sub_features": sub_items,
        })

    return {"features": features}


# ================================================================
# 工具 4: extract_rules — 提取业务规则和边界条件
# ================================================================
def extract_rules(file_path: str = "", prd_json: str = "", prd_data: dict = None) -> dict:
    """
    从需求文档中提取业务规则和边界条件。
    """
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

    boundary_keywords = ["最大", "最小", "不超过", "超过", "至少", "至多", "上限", "下限"]
    business_keywords = ["必须", "不允许", "禁止", "需要", "应该", "应当"]
    constraint_keywords = ["限制", "约束", "要求", "条件", "仅", "只"]

    rules = []
    seen_rules = set()
    current_section = ""

    for line in raw_text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        section_match = re.match(r"^##\s+(.+)$", line_stripped)
        if section_match:
            current_section = section_match.group(1).strip()
            continue
        if line_stripped.startswith("#"):
            continue

        has_number = re.search(r"\d+[\s\-~]*\d*\s*(个|次|分钟|小时|位|字符|天|秒|年|月|周|MB|GB|KB)", line_stripped)
        is_business = any(kw in line_stripped for kw in business_keywords)
        is_boundary = any(kw in line_stripped for kw in boundary_keywords)
        is_constraint = any(kw in line_stripped for kw in constraint_keywords)

        if (has_number or is_business or is_boundary or is_constraint) and line_stripped not in seen_rules:
            seen_rules.add(line_stripped)

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
# 工具 5: generate_cases — 生成测试用例框架
# ================================================================
def generate_cases(features_json: str = "", rules_json: str = "") -> dict:
    """
    根据功能点和规则生成测试用例框架。
    """
    features_data = json.loads(features_json) if features_json else {"features": []}
    rules_data = json.loads(rules_json) if rules_json else {"rules": []}

    cases = []
    seen = set()

    # 1. 为每个功能点生成正向用例
    for feature in features_data.get("features", []):
        name = feature.get("name", "未知功能")
        desc = feature.get("description", "")
        sub_features = feature.get("sub_features", [])

        case_key = (name, "正向", f"验证{name}功能正常工作")
        if case_key not in seen:
            seen.add(case_key)
            cases.append({
                "feature": name,
                "type": "正向",
                "description": f"验证{name}功能正常工作：{desc[:100]}" if desc else f"验证{name}功能正常工作",
            })

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
        else:
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
# 工具 6: format_output — 格式化输出为 Markdown 表格
# ================================================================
def format_output(cases_json: str = "") -> dict:
    """
    将测试用例格式化为可读的 Markdown 表格。
    """
    cases_data = json.loads(cases_json) if cases_json else {"cases": []}
    cases = cases_data.get("cases", [])

    if not cases:
        return {"markdown": "无测试用例", "total": 0}

    def get_priority(case_type: str) -> str:
        if case_type in ("边界", "安全"):
            return "高"
        elif case_type == "反向":
            return "中"
        else:
            return "低"

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

    return {"markdown": "\n".join(lines), "total": len(cases)}
