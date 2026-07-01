"""
工具注册入口 — 将所有测试领域工具注册到 ToolRegistry
"""
from .registry import ToolRegistry
from .test_tools import parse_prd, extract_features, extract_rules, generate_cases, format_output


def create_test_tool_registry() -> ToolRegistry:
    """创建并注册所有测试工具"""
    registry = ToolRegistry()

    # 工具 1: 解析需求文档（已注册）
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

    # 工具 2: 提取功能点
    registry.register(
        name="extract_features",
        description="从解析后的需求文档中提取功能点列表，包括功能名称、描述和子功能。",
        parameters={
            "type": "object",
            "properties": {
                "prd_json": {
                    "type": "string",
                    "description": "parse_prd 工具输出的 JSON 字符串",
                },
            },
        },
        func=extract_features,
    )

    # 工具 3: 提取业务规则
    registry.register(
        name="extract_rules",
        description="从需求文档中提取业务规则、边界条件和约束。",
        parameters={
            "type": "object",
            "properties": {
                "prd_json": {
                    "type": "string",
                    "description": "parse_prd 工具输出的 JSON 字符串",
                },
            },
        },
        func=extract_rules,
    )

    # 工具 4: 生成用例框架
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

    # 工具 5: 格式化输出
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
