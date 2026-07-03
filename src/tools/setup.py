"""
工具注册入口 — 将所有测试领域工具注册到 ToolRegistry

【什么是工具注册？】
每个工具（函数）需要告诉 LLM 三件事，LLM 才能正确调用它：
  1. name        — 工具叫什么（LLM 通过名字选择工具）
  2. description — 工具干什么（LLM 通过描述判断何时使用）
  3. parameters  — 工具接受什么参数（LLM 通过参数说明生成正确的 arguments）

【parameters 为什么是 JSON Schema？】
OpenAI 的 Function Calling 协议要求用 JSON Schema 格式描述参数。
JSON Schema 是一种"描述 JSON 数据结构"的标准语法，告诉 LLM：
  - "type": "object"   → 参数整体是一个 {…} 对象（dict），这是固定写法
  - "properties": {…}  → 对象里有哪些字段
  - 每个字段的 "type"  → 字段类型（string/integer/boolean/array 等）
  - 每个字段的 "description" → 字段含义（LLM 靠这个理解怎么传参）

【工具串联（流水线）】
工具之间通过 JSON 字符串传递数据，形成流水线：
  parse_prd → extract_features ─┐
                                ├→ generate_cases → format_output
  parse_prd → extract_rules ────┘
每个工具的输出是下一个工具的输入，所以 description 里会写"XX 工具输出的 JSON 字符串"。
"""
from .registry import ToolRegistry
from .test_tools import parse_prd, extract_features, extract_rules, generate_cases, format_output


def create_test_tool_registry() -> ToolRegistry:
    """创建并注册所有测试工具"""
    registry = ToolRegistry()

    # ──────────────────────────────────────────────
    # 工具 1: parse_prd — 解析需求文档
    # 输入：文件路径 或 文本内容
    # 输出：{"title": "...", "sections": [...], "raw_text": "...", ...}
    # ──────────────────────────────────────────────
    registry.register(
        name="parse_prd",
        description="解析需求文档（Markdown 格式），提取标题、功能区块、子功能、API 接口定义等结构化信息。支持从文件路径读取或直接传入文本。",
        # parameters 用 JSON Schema 描述参数结构：
        # - "type": "object" 表示参数是一个 {…} 对象（固定写法，所有工具顶层都是 object）
        # - "properties" 列出对象里的每个字段及其类型
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",  # ← 告诉 LLM：file_path 是字符串
                    "description": "需求文档的文件路径（与 content 二选一）",
                },
                "content": {
                    "type": "string",  # ← 告诉 LLM：content 也是字符串
                    "description": "需求文档的文本内容（与 file_path 二选一）",
                },
            },
        },
        func=parse_prd,  # ← 绑定实际的 Python 函数
    )

    # ──────────────────────────────────────────────
    # 工具 2: extract_features — 提取功能点
    # 输入：parse_prd 的输出（JSON 字符串）
    # 输出：{"features": [{"name": "...", "description": "...", "sub_features": [...]}]}
    # ──────────────────────────────────────────────
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

    # ──────────────────────────────────────────────
    # 工具 3: extract_rules — 提取业务规则和边界条件
    # 输入：parse_prd 的输出（JSON 字符串）
    # 输出：{"rules": [{"rule": "...", "type": "业务规则|边界条件|约束", "source": "..."}]}
    # ──────────────────────────────────────────────
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

    # ──────────────────────────────────────────────
    # 工具 4: generate_cases — 生成测试用例框架
    # 输入：extract_features 的输出 + extract_rules 的输出
    # 输出：{"cases": [{"feature": "...", "type": "正向|反向|边界", "description": "..."}]}
    # ──────────────────────────────────────────────
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

    # ──────────────────────────────────────────────
    # 工具 5: format_output — 格式化输出为 Markdown 表格
    # 输入：generate_cases 的输出
    # 输出：{"markdown": "Markdown 表格字符串", "total": 用例总数}
    # ──────────────────────────────────────────────
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
