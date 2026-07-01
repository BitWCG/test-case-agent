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
def extract_features(prd_json: str = "", prd_data: dict = None) -> dict:
    """
    从解析后的需求文档中提取功能点列表。
    
    参数：
    - prd_json: parse_prd 输出的 JSON 字符串（模型会传这个）
    - prd_data: 或者直接传 dict（代码内部调用）
    
    返回：
    - {"features": [{"name": "...", "description": "...", "sub_features": [...]}]}
    """
    # 解析输入（兼容 JSON 字符串和 dict）
    if prd_json and not prd_data:
        prd_data = json.loads(prd_json) if isinstance(prd_json, str) else prd_json
    
    if not prd_data:
        return {"error": "必须提供 prd_json 或 prd_data 参数"}

    # TODO: 在这里实现你的代码
    # 
    # 思路：
    # features = []
    # for subsection in prd_data.get("subsections", []):
    #     # 从 raw_text 中找到这个 subsection 下面的内容
    #     # 提取描述和子功能
    #     features.append({...})
    # return {"features": features}
    pass  # ← 删掉这行，写你的实现


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
def extract_rules(prd_json: str = "", prd_data: dict = None) -> dict:
    """
    从需求文档中提取业务规则和边界条件。
    
    返回：
    - {"rules": [{"rule": "...", "type": "业务规则|边界条件|约束", "source": "..."}]}
    """
    if prd_json and not prd_data:
        prd_data = json.loads(prd_json) if isinstance(prd_json, str) else prd_json
    
    if not prd_data:
        return {"error": "必须提供 prd_json 或 prd_data 参数"}

    # TODO: 在这里实现你的代码
    pass  # ← 删掉这行，写你的实现


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

    # TODO: 在这里实现你的代码
    pass  # ← 删掉这行，写你的实现


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

    # TODO: 在这里实现你的代码
    pass  # ← 删掉这行，写你的实现
