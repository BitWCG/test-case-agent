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
from src.eval.trace_recorder import TraceRecorder
from src.tools.setup import create_test_tool_registry

# 获取评测 logger（如果已配置则共享落盘，否则只走 stdout）
_eval_logger = logging.getLogger("eval")


def _log(msg: str):
    """Agent 内部日志：同时写评测日志文件 + stdout。"""
    if _eval_logger.handlers:
        _eval_logger.info(msg)
    else:
        _log(msg)


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
        # # 1. 动态估算 max_tokens：根据对话历史总字符数，防止工具参数被截断    
        input_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        max_tokens = max(8092, int(input_chars * 2) + 4096)

        # # 2. 调用 LLM
        # print(f"[DEBUG] 当前 messages 条数: {len(self.messages)}")
        # print(f"[DEBUG] 对话历史总字符数: {input_chars}, 估算 max_tokens: {max_tokens}")
        # print(f"[DEBUG] 正在调用 LLM...")
        response = self.llm.client.chat.completions.create(
            model=self.llm.model,
            messages=self.messages,
            tools=self.registry.get_schemas(),
            tool_choice="auto",
            temperature=0.3,
            max_tokens=max_tokens,
        )
        assistant_msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        usage = response.usage

        # # 4. 日志记录
        # print(f"[DEBUG] finish_reason: {finish_reason}")
        # print(f"[DEBUG] token 用量: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")
        # print(f"[DEBUG] assistant_msg.content (全文):")
        # print(assistant_msg.content or '(空)')
        # print(f"[DEBUG] tool_calls 数量: {len(assistant_msg.tool_calls) if assistant_msg.tool_calls else 0}")
        # if assistant_msg.tool_calls:
        #     for i, tc in enumerate(assistant_msg.tool_calls):
        #         print(f"[DEBUG]   tool_call[{i}]: id={tc.id}, name={tc.function.name}")
        #         print(f"[DEBUG]   tool_call[{i}].arguments (全文): {tc.function.arguments}")

        # # 5. 截断自动重试：finish_reason=="length" 说明输出被 max_tokens 截断
        if finish_reason == "length":
            max_tokens *= 2
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=self.messages,
                tools=self.registry.get_schemas(),
                tool_choice="auto",
                temperature=0.3,
                max_tokens=max_tokens,
            )
        assistant_msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        usage = response.usage  # 重试后更新 usage，确保 logger 记录的是最终结果的 token 用量
        _log(f"[Think] finish_reason={finish_reason}, tokens={usage.total_tokens if usage else 0}")

        # 6. 用 logger 记录
        tool_calls_list = assistant_msg.tool_calls
        usage_dict = {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens, "total_tokens": usage.total_tokens}
        self.logger.log_think(round_num, finish_reason, tool_calls_list, usage_dict)

        return assistant_msg, finish_reason, usage_dict
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
        
        职责：
        1. 把 assistant_msg 序列化后存入 messages（OpenAI 协议要求）
        2. 执行每个 tool_call 对应的工具函数
        3. 返回结果列表供 observe() 使用
        
        返回：[(tool_call_id, result_dict), ...]
        """
        # ── 步骤 1：把 assistant 消息存入 messages 历史 ──
        # 为什么必须存？
        #   OpenAI API 协议要求：assistant 的 tool_calls 和后续的 tool 结果必须配对出现。
        #   如果不存，下一轮 API 调用时模型不知道为什么要调用这些工具。
        #
        # model_dump() 把 Pydantic 对象转成 dict：
        #   {
        #     "role": "assistant",
        #     "content": "...",
        #     "tool_calls": [{"id": "call_xxx", "type": "function", "function": {"name": "...", "arguments": "..."}}]
        #   }
        assistant_msg = assistant_msg.model_dump()

        # ── 防御性校验：检查 tool_calls 中的 arguments 是否是合法 JSON ──
        # 为什么必须校验？
        #   LLM 输出可能被截断（达到 max_tokens 上限），导致 arguments 是不完整的 JSON。
        #   如果不合法直接存入 messages，下一轮 API 调用会报 400 错误：
        #   "The 'function.arguments' parameter must be in JSON format"
        #   而且这个错误无法恢复，整个对话就废了。

        for tc in assistant_msg.get("tool_calls", []):
            args_str = tc.get("function", {}).get("arguments")
            try:
                json.loads(args_str)
            except json.JSONDecodeError:
                _log(f"[WARN] tool_call {tc['id']} 的 arguments 不是合法 JSON，已清空为 '{{}}'")
                tc["function"]["arguments"] = "{}"

        self.messages.append(assistant_msg)

        # # ── 步骤 2：遍历 tool_calls，逐个执行工具 ──
        result = []
        for tc in assistant_msg.get("tool_calls", []):
            tool_name = tc.get("function", {}).get("name")
            tool_id = tc.get("id")
            args_str = json.loads(tc.get("function", {}).get("arguments"))
            tool_result = self.registry.execute(tool_name, args_str)
            # 记录工具执行日志
            self.logger.log_act(
                round_num=0,
                tool_name=tool_name,
                tool_args=args_str,
                result=tool_result,
            )
            result.append((tool_id, tool_result))
        return result

        # results = []
        # for tool_call in assistant_msg.tool_calls:
        #     tool_name = tool_call.function.name
        #     tool_call_id = tool_call.id

        #     # 2a. 解析参数
        #     try:
        #         tool_args = json.loads(tool_call.function.arguments)
        #     except json.JSONDecodeError as e:
        #         # 参数解析失败（上面已经修复了 messages 中的值，这里再尝试一次）
        #         print(f"[ERROR] {tool_name} 参数 JSON 解析失败: {e}")
        #         # 把错误信息作为工具结果返回给 LLM，让它自行修正
        #         results.append((tool_call_id, {"error": f"参数 JSON 解析失败: {e}"}))
        #         continue

        #     # 2b. 执行工具
        #     print(f"  [调用] {tool_name}({tool_args})")
        #     result = self.registry.execute(tool_name, tool_args)
        #     print(f"  [结果] {str(result)[:200]}...")

        #     # 2c. 记录日志
        #     self.logger.log_act(
        #         round_num=0,  # act() 不知道当前轮次，传 0 由 observe 补充
        #         tool_name=tool_name,
        #         tool_args=tool_args,
        #         result=result,
        #     )

        #     # 2d. 收集结果
        #     results.append((tool_call_id, result))

        # return results

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
        
        职责：
        1. 把每个工具结果格式化为 OpenAI 要求的 tool role 消息
        2. 追加到 self.messages，供下一轮 LLM 调用使用
        3. 记录日志
        
        参数：
        - results: act() 返回的 [(tool_call_id, result_dict), ...]
        
        为什么单独拆出来？
          因为未来你可能想在这里加：
          - 上下文压缩（工具结果太大时截断，防止 context window 溢出）
          - 轨迹记录（完整保存每轮执行路径）
          - 记忆提取（从结果中提取关键信息存入长期记忆）
        """
        for tool_call_id, result_dict in results:
            # ── 把工具结果格式化为 OpenAI 协议要求的格式 ──
            # OpenAI 要求 tool 消息必须包含：
            #   - role: "tool"       （固定值，告诉 API 这是工具返回的结果）
            #   - tool_call_id: xxx  （对应 assistant_msg 中 tool_call 的 id）
            #                        API 靠这个 id 把结果和请求配对
            #   - content: JSON 字符串（工具返回的内容，必须是字符串）
            #
            # 为什么 content 是 JSON 字符串而不是 dict？
            #   因为 OpenAI API 规定 tool 消息的 content 字段类型是 string。
            #   模型会解析这个 JSON 字符串来理解工具返回了什么。
            content_str = json.dumps(result_dict, ensure_ascii=False)

            tool_message = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content_str,
            }
            self.messages.append(tool_message)

        _log(f"[Observe] 写入 {len(results)} 条工具结果")

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
        _log(f"[INFO] 已加载工具: {self.registry.list_tools()}")

        # 初始化对话历史
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        # 初始化 TraceRecorder（评测用轨迹记录）
        self.trace = TraceRecorder(input_text=user_input[:500])

        for round_num in range(1, max_rounds + 1):
            _log(f"\n{'='*50}")
            _log(f"--- 第 {round_num} 轮 ---")

            # 开始新一轮 trace
            self.trace.start_round()

            # ── ① Reasoning：调用 LLM 思考 ──
            assistant_msg, finish_reason, usage_dict = self.think(round_num)

            # 记录 think 到 trace（usage_dict 直接从 think() 获取）
            self.trace.record_think(
                content=assistant_msg.content or "",
                finish_reason=finish_reason,
                tool_call_count=len(assistant_msg.tool_calls) if assistant_msg.tool_calls else 0,
                usage=usage_dict,
            )

            # ── ② 判断是否完成 ──
            if finish_reason == "stop" or not assistant_msg.tool_calls:
                _log(f"[完成] 第 {round_num} 轮, finish_reason={finish_reason}, "
                      f"输出 {len(assistant_msg.content or '')} 字符")
                self.logger.log_completion(round_num, assistant_msg.content)
                self.trace.finish(output=assistant_msg.content)
                self.trace.save(f"data/eval/traces/{self.trace.trace_id}.json")
                return assistant_msg.content

            # ── ③ Acting：执行工具调用 ──
            # 先打印本轮要调用的工具
            for tc in assistant_msg.tool_calls or []:
                try:
                    args_preview = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args_preview = {"_error": "参数 JSON 截断"}
                # 参数摘要：过长的值截断显示
                args_short = {}
                for k, v in args_preview.items():
                    v_str = str(v)
                    args_short[k] = v_str[:80] + "..." if len(v_str) > 80 else v_str
                _log(f"[调用] {tc.function.name}({args_short})")

            tool_results = self.act(assistant_msg)

            # 打印工具返回结果摘要
            for tc in assistant_msg.tool_calls or []:
                tool_name = tc.function.name
                for tid, tr in tool_results:
                    if tid == tc.id:
                        result_str = json.dumps(tr, ensure_ascii=False) if isinstance(tr, dict) else str(tr)
                        preview = result_str[:120] + "..." if len(result_str) > 120 else result_str
                        _log(f"[结果] {tool_name} → {preview}")
                        break

            # 记录工具调用到 trace
            for tc in assistant_msg.tool_calls or []:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}
                # 找到对应的结果
                tool_result = None
                for tid, tr in tool_results:
                    if tid == tc.id:
                        tool_result = tr
                        break
                if tool_result is not None:
                    self.trace.record_tool_call(
                        tool_name=tool_name,
                        arguments=tool_args,
                        result=tool_result,
                    )

            # ── ④ Observe：把结果写回记忆 ──
            self.observe(tool_results)

        _log("[WARN] 达到最大轮次限制")
        self.logger.log_timeout(max_rounds)
        self.trace.finish(output=None)
        self.trace.save(f"data/eval/traces/{self.trace.trace_id}.json")
        return None
