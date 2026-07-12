"""
TraceRecorder — 评测轨迹记录器

与 AgentLogger 的区别：
- AgentLogger：调试用，数据截断，JSONL 格式
- TraceRecorder：评测用，数据完整，结构化 JSON，可编程读取

Day 12 评测体系的基础设施。每次 Agent 运行生成一个完整的 trace，
评测器可以直接加载 trace JSON 进行分析。

参考：Claw-Eval 三通道证据中的 execution trace 通道
"""
import json
import uuid
from datetime import datetime
from pathlib import Path


class TraceRecorder:
    """
    评测轨迹记录器
    
    一次完整的 Agent 运行 = 一个 trace。
    trace 包含：
    - trace_id: 唯一标识
    - started_at / finished_at: 时间范围
    - input: 用户输入
    - output: Agent 最终输出
    - steps: 每一步的详细记录（思考/工具调用/工具结果）
    - summary: 汇总统计（总轮次、总 token、工具调用次数等）
    """

    def __init__(self, input_text: str = ""):
        # ================================================================
        # 初始化 trace 结构
        # ================================================================
        self.trace_id = f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.started_at = datetime.now().isoformat()
        self.finished_at = None
        self.input_text = input_text
        self.output_text = None
        
        # 步骤列表：每个元素是一个 dict，记录一轮的完整信息
        self.steps: list[dict] = []
        
        # 当前轮次计数器
        self._current_round = 0

    def start_round(self):
        """开始新一轮，返回轮次号"""
        self._current_round += 1
        return self._current_round

    def record_think(self, content: str, finish_reason: str, 
                     tool_call_count: int = 0, usage: dict | None = None):
        """
        记录思考阶段
        
        参数：
        - content: LLM 的文本回复（可能为空）
        - finish_reason: "stop" / "tool_calls" / "length"
        - tool_call_count: 本轮工具调用数量
        - usage: token 用量 {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
        """
        step = {
            "round": self._current_round,
            "type": "think",
            "content": content,
            "finish_reason": finish_reason,
            "tool_call_count": tool_call_count,
            "usage": usage or {},
            "timestamp": datetime.now().isoformat(),
        }
        self.steps.append(step)

    def record_tool_call(self, tool_name: str, arguments: dict, 
                         result: dict, tokens: int = 0):
        """
        记录工具调用（完整数据，不截断）
        
        参数：
        - tool_name: 工具名称
        - arguments: 工具参数（完整 dict）
        - result: 工具返回结果（完整 dict）
        - tokens: 该次调用消耗的 token（可选）
        """
        step = {
            "round": self._current_round,
            "type": "tool_call",
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "tokens": tokens,
            "timestamp": datetime.now().isoformat(),
        }
        self.steps.append(step)

    def record_error(self, tool_name: str, error: str):
        """记录工具调用错误"""
        step = {
            "round": self._current_round,
            "type": "error",
            "tool_name": tool_name,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }
        self.steps.append(step)

    def finish(self, output: str | None):
        """标记 trace 结束"""
        self.finished_at = datetime.now().isoformat()
        self.output_text = output

    def get_summary(self) -> dict:
        """
        生成 trace 汇总统计
        
        返回：
        - total_rounds: 总轮次
        - total_tool_calls: 工具调用总次数
        - total_tokens: 总 token 消耗
        - tool_names: 使用过的工具列表
        - errors: 错误列表
        - duration_seconds: 运行时长（秒）
        """
        tool_calls = [s for s in self.steps if s["type"] == "tool_call"]
        thinks = [s for s in self.steps if s["type"] == "think"]
        errors = [s for s in self.steps if s["type"] == "error"]
        
        total_tokens = sum(s.get("usage", {}).get("total_tokens", 0) for s in thinks)
        
        # 计算运行时长
        duration = None
        if self.started_at and self.finished_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.finished_at)
            duration = (end - start).total_seconds()
        
        return {
            "total_rounds": self._current_round,
            "total_tool_calls": len(tool_calls),
            "total_tokens": total_tokens,
            "tool_names": list(set(s["tool_name"] for s in tool_calls)),
            "error_count": len(errors),
            "errors": [s["error"] for s in errors],
            "duration_seconds": duration,
        }

    def to_dict(self) -> dict:
        """导出为完整 dict"""
        return {
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "input": self.input_text[:500] + "..." if len(self.input_text) > 500 else self.input_text,
            "output": self.output_text,
            "steps": self.steps,
            "summary": self.get_summary(),
        }

    def save(self, path: str | Path):
        """
        保存 trace 到 JSON 文件
        
        参数：
        - path: 文件路径（如 "data/eval/traces/trace_xxx.json"）
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        
        print(f"[TRACE] 已保存: {path} ({len(self.steps)} 步, {self.get_summary()['total_tool_calls']} 次工具调用)")
        return str(path)
