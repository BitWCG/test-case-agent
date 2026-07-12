"""
Day 3: Agent 日志系统

职责：记录 Agent 每一轮的完整轨迹（trace），写入文件。
为什么需要？
- 调试：出问题时能回溯完整推理过程
- 评测：后续 Day 11-14 做评测时需要轨迹数据
- 可观测性：生产环境中必须能追溯 Agent 的行为

日志文件位置：logs/agent_trace_{timestamp}.jsonl
每行一个 JSON 对象，记录一轮的完整信息。
"""
import json
import logging
from datetime import datetime
from pathlib import Path


class AgentLogger:
    """
    Agent 轨迹日志记录器
    
    每条日志是一个 JSON 对象，包含：
    - round: 轮次号
    - event: 事件类型（think / act / observe / completion / timeout）
    - data: 事件相关数据
    - timestamp: 时间戳
    """

    def __init__(self, log_dir: str = "logs"):
        # 1. 创建日志目录
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 2. 生成日志文件名：logs/agent_trace_{timestamp}.jsonl
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = self.log_dir / f"agent_trace_{timestamp}.jsonl"

        # 3. 打开文件（追加模式）
        self.log_file = open(self.log_file_path, "a", encoding="utf-8")

        # 4. 配置 Python logging（控制台输出）
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        logging.info(f"日志文件: {self.log_file_path}")

    def log_think(self, round_num: int, finish_reason: str, 
                  tool_calls: list | None, usage: dict):
        """
        记录 think 阶段的关键信息
        
        参数：
        - round_num: 轮次号
        - finish_reason: "stop" / "tool_calls" / "length"
        - tool_calls: 工具调用列表（可能为 None）
        - usage: token 用量 {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
        """
        entry = {
            "round": round_num,
            "event": "think",
            "data": {
                "finish_reason": finish_reason,
                "tool_call_count": len(tool_calls) if tool_calls else 0,
                "usage": usage,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._write(entry)
        logging.info(f"[Think] round={round_num}, finish={finish_reason}, tools={entry['data']['tool_call_count']}, tokens={usage.get('total_tokens', '?')}")

    def log_act(self, round_num: int, tool_name: str, 
                tool_args: dict, result: dict):
        """
        记录 act 阶段的工具执行信息
        
        参数：
        - round_num: 轮次号
        - tool_name: 工具名称
        - tool_args: 工具参数
        - result: 工具返回结果
        """
        entry = {
            "round": round_num,
            "event": "act",
            "data": {
                "tool_name": tool_name,
                "tool_args": self._truncate(tool_args),
                "result": self._truncate(result),
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._write(entry)
        logging.info(f"[Act] round={round_num}, tool={tool_name}")

    def log_completion(self, round_num: int, content: str):
        """记录任务完成"""
        entry = {
            "round": round_num,
            "event": "completion",
            "data": {
                "content_length": len(content) if content else 0,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._write(entry)
        logging.info(f"[完成] round={round_num}, content_length={len(content) if content else 0}")

    def log_timeout(self, max_rounds: int):
        """记录达到最大轮次限制"""
        entry = {
            "event": "timeout",
            "data": {
                "max_rounds": max_rounds,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._write(entry)
        logging.warning(f"[超时] 达到最大轮次限制: {max_rounds}")

    # ================================================================
    # 内部方法（已实现，不需要修改）
    # ================================================================

    def _write(self, entry: dict):
        """将日志条目写入 JSONL 文件"""
        if hasattr(self, 'log_file') and self.log_file:
            # self.log_file 是 __init__ 中已打开的文件句柄（TextIOWrapper）
            # 直接写入即可，不需要再次 open()
            self.log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self.log_file.flush()  # 立即刷新缓冲区，确保日志不丢失

    def _truncate(self, obj, max_len: int = 200) -> str:
        """截断过长的数据，避免日志膨胀"""
        s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
        return s[:max_len] + "..." if len(s) > max_len else s

    def close(self):
        """关闭日志文件"""
        if hasattr(self, 'log_file') and self.log_file:
            self.log_file.close()
