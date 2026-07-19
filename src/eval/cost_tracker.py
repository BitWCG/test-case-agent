"""
成本与延迟度量

生产级 Agent 必须追踪：
- Token 消耗（输入/输出分开计）
- 每次运行的延迟（端到端 + 各步骤）
- 成本估算（按厂商定价）
- 成本预算熔断（超预算停止）

参考：Anthropic "monitor cost per task" + Confident AI "latency as a first-class metric"
"""
import json
from pathlib import Path


# 通义千问定价（每百万 token，元）
PRICING = {
    "qwen-plus": {"input": 0.8, "output": 2.0},
    "qwen-max": {"input": 2.4, "output": 9.6},
    "qwen-turbo": {"input": 0.3, "output": 0.6},
    "qwen-long": {"input": 0.5, "output": 2.0},
    "qwen-flash": {"input": 0.0, "output": 0.0},  # 免费
    "qwen3.5-plus": {"input": 1.0, "output": 3.0},
    "qwen3.5-flash": {"input": 0.0, "output": 0.0},
    "qwen3.6-flash": {"input": 0.0, "output": 0.0},
    "qwen3.6-plus": {"input": 1.0, "output": 3.0},
    "qwen3.7-plus": {"input": 1.0, "output": 4.0},
    "qwen3.7-max": {"input": 2.0, "output": 8.0},
    "deepseek-v3": {"input": 1.0, "output": 2.0},
    "deepseek-r1": {"input": 1.0, "output": 4.0},
    # 默认（未知模型）
    "_default": {"input": 1.0, "output": 3.0},
}


class CostTracker:
    """
    追踪 Agent 运行的 Token 消耗和成本。

    用法：
        tracker = CostTracker(model="qwen3.7-plus")
        tracker.record(prompt_tokens=1800, completion_tokens=200)
        tracker.record(prompt_tokens=3000, completion_tokens=500)
        report = tracker.get_report()
    """

    def __init__(self, model: str = "qwen-plus", budget_yuan: float = 1.0):
        self.model = model
        self.budget_yuan = budget_yuan
        self.calls: list[dict] = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def record(self, prompt_tokens: int, completion_tokens: int, latency_ms: float = 0):
        """记录一次 API 调用。"""
        self.calls.append({
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
        })
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

    def record_from_trace(self, trace: dict):
        """从 trace JSON 中提取所有 token 用量。"""
        for step in trace.get("steps", []):
            if step.get("type") == "think":
                usage = step.get("usage", {})
                self.record(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    @property
    def estimated_cost_yuan(self) -> float:
        """估算成本（元）。"""
        pricing = PRICING.get(self.model, PRICING["_default"])
        input_cost = self.total_prompt_tokens / 1_000_000 * pricing["input"]
        output_cost = self.total_completion_tokens / 1_000_000 * pricing["output"]
        return input_cost + output_cost

    @property
    def is_over_budget(self) -> bool:
        return self.estimated_cost_yuan > self.budget_yuan

    def get_report(self) -> dict:
        """生成成本报告。"""
        avg_latency = 0
        if self.calls:
            latencies = [c["latency_ms"] for c in self.calls if c.get("latency_ms", 0) > 0]
            avg_latency = sum(latencies) / len(latencies) if latencies else 0

        return {
            "model": self.model,
            "total_calls": len(self.calls),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_yuan": round(self.estimated_cost_yuan, 4),
            "budget_yuan": self.budget_yuan,
            "over_budget": self.is_over_budget,
            "avg_latency_ms": round(avg_latency, 1),
        }

    def format_report(self) -> str:
        """格式化成本报告为可读文本。"""
        r = self.get_report()
        lines = [
            f"  成本与延迟度量",
            f"  ├─ 模型: {r['model']}",
            f"  ├─ API 调用次数: {r['total_calls']}",
            f"  ├─ Token 消耗: {r['total_prompt_tokens']} (输入) + {r['total_completion_tokens']} (输出) = {r['total_tokens']}",
            f"  ├─ 估算成本: ¥{r['estimated_cost_yuan']:.4f}",
            f"  ├─ 预算: ¥{r['budget_yuan']} {'✅ 未超' if not r['over_budget'] else '❌ 已超!'}",
        ]
        if r["avg_latency_ms"] > 0:
            lines.append(f"  └─ 平均延迟: {r['avg_latency_ms']:.0f}ms")
        else:
            lines.append(f"  └─ 平均延迟: (未记录)")
        return "\n".join(lines)
