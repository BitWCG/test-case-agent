"""
Day 1 — LLM 客户端

你需要理解的核心概念：
1. OpenAI SDK 的 chat.completions.create() 是最基础的调用方式
2. messages 列表是对话的核心数据结构：
   - {"role": "system", "content": "..."}  → 系统提示（角色设定）
   - {"role": "user",   "content": "..."}  → 用户输入
   - {"role": "assistant", "content": "..."} → 模型回复
3. response_format={"type": "json_object"} 可以强制模型输出合法 JSON
4. temperature 控制随机性：0 = 确定性输出，1 = 更有创意
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# 加载 .env 配置文件
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)


class LLMClient:
    """统一的 LLM 调用客户端"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "sk-no-key")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def list_models(self) -> list[str]:
        """
        查询 API 当前可用的模型列表。

        返回：模型 ID 列表（如 ['qwen-plus', 'qwen-max', 'qwen-turbo', ...]）
        如果接口不支持或报错，返回空列表。
        """
        try:
            models = self.client.models.list()
            model_ids = sorted([m.id for m in models.data])
            return model_ids
        except Exception as e:
            print(f"[WARN] 获取模型列表失败: {e}")
            return []

    # ================================================================
    # TODO 1.1: 实现普通对话调用
    # ================================================================
    # 提示：
    # - 调用 self.client.chat.completions.create()
    # - 传入 model, messages, temperature, max_tokens 参数
    # - 从 response.choices[0].message.content 提取文本
    #
    # 你需要理解：
    # - 为什么 messages 是 list 而不是单个 string？
    #   → 因为 LLM 需要完整的对话历史来理解上下文
    # - temperature=0.3 是什么含义？
    #   → 低温度 = 更确定的输出，适合结构化任务
    #
    def chat(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 4096) -> str:
        """普通对话调用，返回模型的文本回复"""
        # 提示：调用 OpenAI API，返回 response.choices[0].message.content
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        print(f"普通对话请求的响应为: {response}")
        print(f"文本回复的具体内容为: {response.choices[0].message.content}")
        return response.choices[0].message.content

    # ================================================================
    # TODO 1.2: 实现 JSON Mode 调用
    # ================================================================
    # 提示：
    # - 和 chat() 几乎一样，区别在于多一个参数：
    #   response_format={"type": "json_object"}
    # - 这个参数强制模型输出合法 JSON，非常适合结构化数据提取
    # - temperature 应该设得更低（0.1），因为我们要确定性输出
    #
    # 你需要理解：
    # - 为什么需要 JSON Mode？
    #   → 因为我们需要模型输出结构化的测试用例，而不是自由文本
    #   → 没有 JSON Mode，模型可能输出 "好的，以下是测试用例：..." 这样的废话
    #
    def chat_json(self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 4096) -> str:
        """JSON Mode 调用，强制模型输出合法 JSON"""
        # TODO: 在这里实现你的代码
        # 提示：和 chat() 类似，加上 response_format 参数
        response = self.client.chat.completions.create(
            model = self.model,
            messages = messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type":"json_object"}
        )
        print(f"JSON Mode 请求的响应为: {response}")
        print(f"JSON 数据的具体内容为: {response.choices[0].message.content}")
        return response.choices[0].message.content

    # ================================================================
    # 已实现：token 估算（供参考）
    # ================================================================
    def estimate_tokens(self, text: str) -> int:
        """粗略估算 token 数（中文约 1.5 字/token，英文约 4 字符/token）"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + english_chars / 4)

    def __repr__(self):
        return f"LLMClient(model={self.model}, base_url={self.base_url})"
