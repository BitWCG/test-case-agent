"""
Day 3: Agent 核心循环重构 — ReAct 模式显式化

把 Day 2 的 run() 大方法拆成三个正交方法：
  - think()   → Reasoning：调用 LLM 思考
  - act()     → Acting：执行工具调用
  - observe() → Observe：把结果写回消息历史

这样后续加 Memory、Guards、Skills 时，每个能力都有明确的挂载点。
"""
import json
import logging
from pathlib import Path

from src.agent.llm_client import LLMClient
from src.agent.logger import AgentLogger
from src.tools.setup import create_test_tool_registry


# ================================================================
# System Prompt — Agent 是谁、能做什么、怎么做
# ================================================================
SYSTEM_PROMPT = """你是一位资深测试工程师，擅长根据需求文档生成全面的测试用例。

## 你的工作方式
你拥有多个工具，请按以下流程处理需求文档：
1. 先用 parse_prd 解析文档结构（传入 file_path 或 content）
2. 用 extract_features 提取功能点（传入 file_path，不要传 prd_json）
3. 用 extract_rules 提取业务规则和边界条件（传入 file_path，不要传 prd_json）
4. 用 generate_cases 生成测试用例框架（传入前两步结果的 JSON）
5. 用 format_output 格式化最终结果

## 重要原则
- 每次只调用一个工具，等拿到结果后再决定下一步
- 如果工具返回错误，分析原因并尝试修正
- extract_features 和 extract_rules 支持直接传 file_path，优先使用 file_path 而不是 prd_json，因为 prd_json 内容太大容易导致截断
- 最终输出必须包含完整的测试用例列表
"""


class SimpleAgent:
    """
    ReAct Agent 实现
    
    核心循环：
        for round in range(max_rounds):
            msg, finish = self.think()       # Reasoning — LLM 思考
            if done: return content
            results = self.act(msg)           # Acting    — 执行工具
            self.observe(results)             # Observe   — 写回记忆
    
    为什么拆成三个方法？
    - think()  是未来加 Memory 注入、Prompt 模板的挂载点
    - act()    是未来加 Guards 安全检查、工具权限控制的挂载点
    - observe() 是未来加轨迹记录、上下文压缩的挂载点
    """

    def __init__(self):
        self.llm = LLMClient()
        self.registry = create_test_tool_registry()
        self.messages: list[dict] = []
        # Day 3 新增：Agent 日志记录器（用于轨迹追踪和调试）
        self.logger = AgentLogger()

    # ================================================================
    # TODO 6.1: 实现 think() — Reasoning
    # ================================================================
    # 职责：调用 LLM，让它根据当前 messages 历史决定下一步
    #
    # 你需要：
    # 1. 动态估算 max_tokens（根据 messages 总长度，防止工具参数被截断）
    # 2. 调用 self.llm.client.chat.completions.create()，传入：
    #    - messages=self.messages
    #    - tools=self.registry.get_schemas()   ← 告诉模型有哪些工具可用
    #    - tool_choice="auto"                  ← 让模型自主决定是否调用工具
    #    - temperature=0.3
    #    - max_tokens=你估算的值
    # 3. 从 response 中提取 assistant_msg 和 finish_reason
    # 4. 如果 finish_reason == "length"（被截断），增大 max_tokens 重试一次
    # 5. 用 self.logger 记录本轮的关键信息（token 用量、tool_calls 等）
    # 6. 返回 (assistant_msg, finish_reason)
    #
    # 返回值类型说明：
    #   assistant_msg: ChatCompletionMessage 对象（OpenAI SDK）
    #   finish_reason: str，"stop" 表示模型认为任务完成，
    #                  "tool_calls" 表示模型想调用工具，
    #                  "length" 表示输出被截断
    #
    def think(self, round_num: int):
        """
        Reasoning 阶段：调用 LLM 思考
        
        返回：(assistant_msg, finish_reason)
        """
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现

    # ================================================================
    # TODO 6.2: 实现 act() — Acting
    # ================================================================
    # 职责：执行 assistant_msg 中的所有 tool_calls
    #
    # 你需要：
    # 1. 先把 assistant_msg 序列化（model_dump()）并加入 self.messages
    #    注意：存入前要校验 tool_calls 中的 arguments 是否是合法 JSON
    #    如果不是，修复为 "{}"（否则下一轮 API 调用会报 400 错误）
    # 2. 遍历 assistant_msg.tool_calls，对每个 tool_call：
    #    a. 解析参数：json.loads(tool_call.function.arguments)
    #    b. 如果解析失败，把错误信息作为工具结果返回给 LLM（让它自行修正）
    #    c. 调用 self.registry.execute(tool_name, tool_args) 执行工具
    #    d. 收集结果
    # 3. 返回结果列表：[(tool_call_id, result_dict), ...]
    #
    # 关键：这一步只负责"执行"，不负责"记录"
    #       记录是 observe() 的事 — 这就是拆分的意义
    #
    def act(self, assistant_msg):
        """
        Acting 阶段：执行工具调用
        
        返回：[(tool_call_id, result_dict), ...]
        """
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现

    # ================================================================
    # TODO 6.3: 实现 observe() — Observe
    # ================================================================
    # 职责：把 act() 返回的工具结果写入 messages 历史
    #
    # 你需要：
    # 1. 遍历 results 列表，每个元素是 (tool_call_id, result_dict)
    # 2. 把每个结果格式化为 tool role 消息：
    #    {"role": "tool", "tool_call_id": id, "content": json字符串}
    # 3. 追加到 self.messages
    # 4. 用 self.logger 记录观察结果
    #
    # 为什么单独拆出来？
    #   因为未来你可能想在这里加：
    #   - 上下文压缩（工具结果太大时截断）
    #   - 轨迹记录（完整保存每轮执行路径）
    #   - 记忆提取（从结果中提取关键信息存入长期记忆）
    #
    def observe(self, results: list[tuple[str, dict]]):
        """
        Observe 阶段：把工具结果写回消息历史
        
        参数：
        - results: act() 返回的 [(tool_call_id, result_dict), ...]
        """
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现

    # ================================================================
    # run() — 主循环（框架已实现，你不需要改这个方法）
    # ================================================================
    # 这就是 ReAct 循环的完整体现。
    # 对比 Day 2 的 run()，你会发现逻辑完全一样，
    # 只是每个步骤被拆到了独立方法里。
    # 这就是重构的本质：行为不变，结构更清晰。
    #
    def run(self, user_input: str, max_rounds: int = 10) -> str | None:
        """
        Agent 主循环 — ReAct 模式
        
        参数：
        - user_input: 用户的输入（需求文档）
        - max_rounds: 最大循环轮次（防止死循环）
        
        返回：
        - 最终回复文本，或 None（超时）
        """
        print(f"[INFO] 已加载工具: {self.registry.list_tools()}")

        # 初始化对话历史
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        for round_num in range(1, max_rounds + 1):
            print(f"\n{'='*50}")
            print(f"--- 第 {round_num} 轮 ---")

            # ── ① Reasoning：调用 LLM 思考 ──
            assistant_msg, finish_reason = self.think(round_num)

            # ── ② 判断是否完成 ──
            # finish_reason == "stop" → 模型认为任务完成
            # 没有 tool_calls → 模型只想回复文本，不想调用工具
            if finish_reason == "stop" or not assistant_msg.tool_calls:
                print(f"[DEBUG] 任务完成（finish_reason={finish_reason}）")
                print(assistant_msg.content)
                self.logger.log_completion(round_num, assistant_msg.content)
                return assistant_msg.content

            # ── ③ Acting：执行工具调用 ──
            tool_results = self.act(assistant_msg)

            # ── ④ Observe：把结果写回记忆 ──
            self.observe(tool_results)

            print(f"[DEBUG] 本轮结束后 messages 条数: {len(self.messages)}")

        print("[WARN] 达到最大轮次限制")
        self.logger.log_timeout(max_rounds)
        return None
