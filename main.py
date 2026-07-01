#!/usr/bin/env python3
"""
测试用例生成 Agent — 统一入口

核心理念：Agent 就是一个循环 —— 思考 → 调用工具 → 观察 → 再思考 → ... → 完成
Day 1 和 Day 2 不是两种模式，而是同一个 Agent 拥有不同数量的工具：
- Day 1：Agent 只有 1 个工具（generate_test_cases）
- Day 2：Agent 有 5 个工具（parse → extract → generate → format）
- 后续：逐步加入 Memory、Skills、Guards 等能力

使用方法：
    cd test-case-agent
    source venv/bin/activate
    python main.py
    python main.py --input path/to/your/requirement.md
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.agent.llm_client import LLMClient
from src.tools.setup import create_test_tool_registry


# ================================================================
# Agent 的核心：System Prompt
# 这里定义了 Agent 是谁、能做什么、怎么做
# ================================================================
SYSTEM_PROMPT = """你是一位资深测试工程师，擅长根据需求文档生成全面的测试用例。

## 你的工作方式
你拥有多个工具，请按以下流程处理需求文档：
1. 先用 parse_prd 解析文档结构
2. 用 extract_features 提取功能点
3. 用 extract_rules 提取业务规则和边界条件
4. 用 generate_cases 生成测试用例框架
5. 用 format_output 格式化最终结果

## 重要原则
- 每次只调用一个工具，等拿到结果后再决定下一步
- 如果工具返回错误，分析原因并尝试修正
- 最终输出必须包含完整的测试用例列表
"""


class SimpleAgent:
    """
    最简 Agent 实现
    
    这就是整个项目的核心。请仔细阅读 run() 方法中的循环逻辑。
    
    Agent 的本质就是一个 while 循环：
    while not done:
        thought = llm.think(messages)      # 思考
        if thought.has_tool_call:           # 需要行动？
            result = execute(tool_call)     # 行动
            messages.append(result)         # 观察
        else:
            done = True                     # 完成
    """

    # ================================================================
    # TODO 5.1: 实现 Agent 初始化
    # ================================================================
    # 你需要：
    # 1. 创建 LLMClient 实例 → self.llm
    # 2. 创建工具注册表 → self.registry（用 create_test_tool_registry()）
    # 3. 初始化对话历史列表 → self.messages
    #
    def __init__(self):
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现

    # ================================================================
    # TODO 5.2: 实现 Agent 主循环
    # ================================================================
    # 这是整个项目最核心的代码。你需要实现一个循环：
    #
    # 每一轮做三件事：
    #   ① 【思考】调用 LLM，传入 messages + tools schema
    #   ② 【判断】检查模型是否想调用工具
    #      - 如果 finish_reason == "stop" 或没有 tool_calls → 完成，返回 content
    #      - 否则 → 继续执行工具
    #   ③ 【行动】执行工具调用：
    #      a. 先把 assistant 消息（含 tool_calls）加入 messages
    #      b. 遍历每个 tool_call，执行工具
    #      c. 把每个工具结果作为 "tool" role 消息加入 messages
    #
    # 关键 API 调用方式：
    #   response = self.llm.client.chat.completions.create(
    #       model=self.llm.model,
    #       messages=self.messages,
    #       tools=self.registry.get_schemas(),   # 告诉模型有哪些工具
    #       tool_choice="auto",                  # 模型自主决定
    #       temperature=0.3,
    #   )
    #
    # 工具执行：
    #   tool_name = tool_call.function.name
    #   tool_args = json.loads(tool_call.function.arguments)
    #   result = self.registry.execute(tool_name, tool_args)
    #
    # messages 中三种角色：
    #   {"role": "system",    "content": "..."}
    #   {"role": "user",      "content": "..."}
    #   {"role": "assistant", "content": "...", "tool_calls": [...]}
    #   {"role": "tool",      "tool_call_id": "...", "content": "JSON 结果"}
    #
    def run(self, user_input: str, max_rounds: int = 10) -> str | None:
        """
        Agent 主循环
        
        参数：
        - user_input: 用户的输入（需求文档）
        - max_rounds: 最大循环轮次（防止死循环）
        
        返回：
        - 最终回复文本，或 None（超时）
        """
        print(f"[INFO] 已加载工具: {self.registry.list_tools()}")
        print()

        # 初始化对话历史
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        # TODO: 在这里实现你的核心循环代码
        #
        # 伪代码参考：
        # for round_num in range(1, max_rounds + 1):
        #     print(f"--- 第 {round_num} 轮 ---")
        #
        #     # ① 思考：调用 LLM
        #     response = ...
        #     assistant_msg = response.choices[0].message
        #     finish_reason = response.choices[0].finish_reason
        #
        #     # ② 判断：完成了吗？
        #     if finish_reason == "stop" or not assistant_msg.tool_calls:
        #         print(assistant_msg.content)
        #         return assistant_msg.content
        #
        #     # ③ 行动：执行工具
        #     # a. 把 assistant 消息加入历史（注意要包含 tool_calls）
        #     self.messages.append({
        #         "role": "assistant",
        #         "content": ...,
        #         "tool_calls": [
        #             {"id": tc.id, "type": "function",
        #              "function": {"name": tc.function.name,
        #                           "arguments": tc.function.arguments}}
        #             for tc in assistant_msg.tool_calls
        #         ],
        #     })
        #
        #     # b. 逐个执行工具
        #     for tool_call in assistant_msg.tool_calls:
        #         tool_name = ...
        #         tool_args = ...
        #         print(f"  [调用] {tool_name}(...)")
        #
        #         result = self.registry.execute(tool_name, tool_args)
        #         print(f"  [结果] {json.dumps(result, ...)[:150]}...")
        #
        #         # c. 把工具结果加入历史
        #         self.messages.append({
        #             "role": "tool",
        #             "tool_call_id": tool_call.id,
        #             "content": json.dumps(result, ensure_ascii=False),
        #         })
        #
        #     print()
        #
        # print("[WARN] 达到最大轮次限制")
        # return None
        pass  # ← 删掉这行，写你的实现


def main():
    # 解析参数
    input_path = None
    if len(sys.argv) > 1 and sys.argv[1] != "--input":
        input_path = sys.argv[1]
    elif "--input" in sys.argv:
        idx = sys.argv.index("--input")
        if idx + 1 < len(sys.argv):
            input_path = sys.argv[idx + 1]

    # 默认使用示例文档
    sample_path = Path(__file__).parent / "data" / "sample_docs" / "login_requirement.md"
    input_path = input_path or str(sample_path)

    print("=" * 60)
    print("  测试用例生成 Agent")
    print("=" * 60)
    print(f"\n[INFO] 需求文档: {input_path}")
    print(f"[INFO] LLM: {LLMClient()}")
    print()

    # 读取需求文档
    req_path = Path(input_path)
    if not req_path.exists():
        print(f"[ERROR] 文件不存在: {input_path}")
        return

    requirement_text = req_path.read_text(encoding="utf-8")
    user_input = f"请分析以下需求文档并生成测试用例：\n\n{requirement_text}"

    # 创建 Agent 并运行
    agent = SimpleAgent()
    result = agent.run(user_input)

    if result:
        print(f"\n{'=' * 60}")
        print("Agent 运行完成！")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

