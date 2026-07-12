"""
工具注册入口 — 将所有测试领域工具注册到 ToolRegistry

工具流水线：
  parse_prd → analyze_requirements → extract_features ↘
                                                        → generate_cases → format_output
  parse_prd → analyze_requirements → extract_rules    ↗
"""
from .registry import ToolRegistry
from .test_tools import parse_prd, analyze_requirements, extract_features, extract_rules, generate_cases, format_output


def create_test_tool_registry() -> ToolRegistry:
    """创建并注册所有测试工具"""
    registry = ToolRegistry()

    # ─── 工具 1: parse_prd ───
    registry.register(
        name="parse_prd",
        description="解析需求文档（Markdown 格式），提取标题、功能区块、子功能、API 接口定义等结构化信息。支持从文件路径读取或直接传入文本。",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "需求文档的文件路径（与 content 二选一）",
                },
                "content": {
                    "type": "string",
                    "description": "需求文档的文本内容（与 file_path 二选一）",
                },
            },
        },
        func=parse_prd,
    )

    # ─── 工具 2: analyze_requirements ───
    registry.register(
        name="analyze_requirements",
        description="结构化拆解需求文档，提取所有功能模块、业务规则、API 接口和数字约束清单。在 parse_prd 之后调用此工具，建立完整的检查清单，确保不遗漏任何需求点。",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "需求文档的文本内容（与 file_path 二选一）",
                },
                "file_path": {
                    "type": "string",
                    "description": "需求文档的文件路径（与 content 二选一）",
                },
            },
        },
        func=analyze_requirements,
    )

    # ─── 工具 3: extract_features ───
    registry.register(
        name="extract_features",
        description="从解析后的需求文档中提取功能点列表，包括功能名称、描述和子功能。推荐直接传 file_path，工具会自动读取并解析文件。",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "需求文档的文件路径（推荐，工具会自动读取并解析，避免传递大段 JSON）",
                },
                "prd_json": {
                    "type": "string",
                    "description": "parse_prd 工具输出的 JSON 字符串（备选，不推荐因为内容可能很大）",
                },
            },
        },
        func=extract_features,
    )

    # ─── 工具 4: extract_rules ───
    registry.register(
        name="extract_rules",
        description="从需求文档中提取业务规则、边界条件和约束。推荐直接传 file_path，工具会自动读取并解析文件。",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "需求文档的文件路径（推荐，工具会自动读取并解析，避免传递大段 JSON）",
                },
                "prd_json": {
                    "type": "string",
                    "description": "parse_prd 工具输出的 JSON 字符串（备选，不推荐因为内容可能很大）",
                },
            },
        },
        func=extract_rules,
    )

    # ─── 工具 5: generate_cases ───
    registry.register(
        name="generate_cases",
        description="根据功能点和业务规则生成测试用例框架。",
        parameters={
            "type": "object",
            "properties": {
                "features_json": {
                    "type": "string",
                    "description": "extract_features 工具输出的 JSON 字符串",
                },
                "rules_json": {
                    "type": "string",
                    "description": "extract_rules 工具输出的 JSON 字符串",
                },
            },
        },
        func=generate_cases,
    )

    # ─── 工具 6: format_output ───
    registry.register(
        name="format_output",
        description="将测试用例格式化为可读的 Markdown 表格。",
        parameters={
            "type": "object",
            "properties": {
                "cases_json": {
                    "type": "string",
                    "description": "generate_cases 工具输出的 JSON 字符串",
                },
            },
        },
        func=format_output,
    )

    return registry
