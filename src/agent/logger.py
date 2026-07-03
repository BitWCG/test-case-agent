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
        # ================================================================
        # TODO 6.4: 初始化日志系统
        # ================================================================
        # 你需要：
        # 1. 创建 logs/ 目录（如果不存在）
        # 2. 生成日志文件名：logs/agent_trace_{时间戳}.jsonl
        # 3. 打开文件（追加模式），保存为 self.log_file
        # 4. 同时配置 Python logging（控制台输出 INFO 级别）
        #
        # 提示：
        #   - 时间戳格式：datetime.now().strftime("%Y%m%d_%H%M%S")
        #   - Path(log_dir).mkdir(parents=True, exist_ok=True)
        #   - logging.basicConfig(level=logging.INFO, format="...")
        #
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现

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
        # ================================================================
        # TODO 6.5: 实现 think 日志记录
        # ================================================================
        # 你需要：
        # 1. 构造日志条目（dict），包含 round、event="think"、data、timestamp
        # 2. data 中记录：finish_reason、tool_call_count、token 用量
        # 3. 调用 self._write(entry) 写入文件
        # 4. 用 logging.info() 输出到控制台
        #
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现

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
        # ================================================================
        # TODO 6.6: 实现 act 日志记录
        # ================================================================
        # 你需要：
        # 1. 构造日志条目，event="act"
        # 2. data 中记录：tool_name、tool_args（截断到 200 字符）、result（截断到 200 字符）
        # 3. 调用 self._write(entry) 写入文件
        # 4. 用 logging.info() 输出到控制台
        #
        # 为什么要截断？
        #   工具结果可能非常大（比如整个 PRD 解析结果），
        #   全部写入日志文件会很大，保留关键信息即可。
        #
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现

    def log_completion(self, round_num: int, content: str):
        """记录任务完成"""
        # TODO 6.7: 实现 completion 日志记录
        # event="completion"，记录 round_num 和 content 长度
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现

    def log_timeout(self, max_rounds: int):
        """记录达到最大轮次限制"""
        # TODO 6.8: 实现 timeout 日志记录
        # event="timeout"，记录 max_rounds
        # TODO: 在这里实现你的代码
        pass  # ← 删掉这行，写你的实现

    # ================================================================
    # 内部方法（已实现，不需要修改）
    # ================================================================

    def _write(self, entry: dict):
        """将日志条目写入 JSONL 文件"""
        if hasattr(self, 'log_file') and self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _truncate(self, obj, max_len: int = 200) -> str:
        """截断过长的数据，避免日志膨胀"""
        s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
        return s[:max_len] + "..." if len(s) > max_len else s

    def close(self):
        """关闭日志文件"""
        if hasattr(self, 'log_file') and self.log_file:
            self.log_file.close()
