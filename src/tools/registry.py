"""
Day 2 — 工具注册表

你需要理解的核心概念：
1. Agent 的能力来自"工具"——每个工具是一个 Python 函数，有名称、描述、参数 schema
2. OpenAI 的 Function Calling 机制：
   - 你把工具列表（schema）传给 API
   - 模型决定是否需要调用工具，如果需要，返回工具名 + 参数
   - 你执行工具，把结果返回给模型
   - 模型根据工具结果继续推理
3. ToolRegistry 就是管理这些工具的"注册中心"

你的任务：完成 TODO 3.1（执行工具）
"""
import json
from typing import Callable


class ToolRegistry:
    """工具注册表：注册、查询、执行工具"""

    def __init__(self):
        self._tools: dict[str, dict] = {}  # name -> {schema, func}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
    ):
        """注册一个工具"""
        self._tools[name] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "func": func,
        }

    def get_schemas(self) -> list[dict]:
        """获取所有工具的 schema 列表（传给 API 的格式）"""
        return [t["schema"] for t in self._tools.values()]

    def list_tools(self) -> list[str]:
        """列出所有已注册的工具名"""
        return list(self._tools.keys())

    # ================================================================
    # TODO 3.1: 实现工具执行
    # ================================================================
    # 这个方法接收工具名和参数字典，找到对应函数并执行
    #
    # 你需要考虑：
    # - 工具名不存在怎么办？
    # - 工具执行抛异常怎么办？
    # - 返回值应该是什么类型？（提示：统一返回 dict，方便序列化为 JSON）
    #
    # 提示：
    # 1. 从 self._tools 中找到对应工具
    # 2. 调用 func(**arguments)
    # 3. 如果结果不是 dict，包装成 {"result": result}
    # 4. 异常时返回 {"error": str(e)}
    #
    def execute(self, tool_name: str, arguments: dict) -> dict:
        """执行指定工具，返回结果字典"""
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现
