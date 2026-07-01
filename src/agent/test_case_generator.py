"""
Day 1 — 需求文档 → 测试用例生成器

你需要理解的核心概念：
1. System Prompt 是 Agent 的"灵魂"——它定义了 Agent 的角色、能力和输出格式
2. JSON Mode 保证输出可以被程序解析
3. 校验（validate）很重要——永远不要信任模型的输出

你的任务：
- 完成 TODO 2.1: 设计 System Prompt（这是整个 Agent 最核心的部分）
- 完成 TODO 2.2: 实现 generate() 方法
- 完成 TODO 2.3: 实现输出校验
"""
import json
from pathlib import Path
from .llm_client import LLMClient


# ================================================================
# TODO 2.1: 设计 System Prompt
# ================================================================
# 这是整个 Agent 最重要的部分！System Prompt 决定了：
# - Agent 扮演什么角色
# - 输出什么格式的数据
# - 遵循什么设计原则
#
# 好的 System Prompt 应该：
# 1. 明确角色：你是一位资深测试工程师...
# 2. 明确输出格式：必须以 JSON 格式输出，结构如下...
# 3. 明确设计原则：正向/反向/边界/安全都要覆盖...
# 4. 明确约束：每个用例必须标注来源...
#
# 思考题：
# - 如果不指定 JSON 格式，模型会输出什么？
# - 如果不要求 source_reference，会出现什么问题？（提示：幻觉）
# - 为什么 priority 字段很重要？
#
SYSTEM_PROMPT = """你是一位资深测试工程师，擅长根据需求文档生成全面的测试用例。

## 你的职责
根据用户提供的需求文档，生成完整、高质量的测试用例集合。

## 覆盖维度
你必须从以下维度全面覆盖：
- 正向测试：正常流程能跑通
- 反向测试：非法输入、错误操作能正确处理
- 边界测试：边界值（最大/最小/空/临界值）
- 安全测试：权限、注入、越权、敏感信息泄露

## 输出格式
必须且只能输出 JSON，不要任何其他文字。JSON 结构如下：
{
  "module": "模块名称",
  "total_cases": 数字,
  "test_cases": [
    {
      "id": "TC-001",
      "name": "用例名称",
      "category": "正向|反向|边界|安全",
      "priority": "高|中|低",
      "preconditions": "前置条件",
      "steps": ["步骤1", "步骤2"],
      "expected_result": "预期结果",
      "source_reference": "来源：引用需求文档中的具体描述"
    }
  ]
}

## 约束
1. 每个用例必须有 source_reference，标注该用例来源于需求的哪一段
2. 如果某个功能点无法溯源到需求文档，标记为 [待确认]
3. priority 根据功能重要程度和风险判断
4. steps 必须具体、可执行，不能含糊
"""


class TestCaseGenerator:
    """需求文档 → 测试用例生成器"""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    # ================================================================
    # TODO 2.2: 实现 generate() 方法
    # ================================================================
    # 这个方法需要做三件事：
    #
    # 第一步：构造 messages 列表
    #   messages = [
    #       {"role": "system", "content": SYSTEM_PROMPT},
    #       {"role": "user",   "content": f"请根据以下需求文档生成测试用例：\n\n{requirement_text}"},
    #   ]
    #
    # 第二步：调用 LLM 的 JSON Mode
    #   raw_output = self.llm.chat_json(messages)
    #
    # 第三步：解析 JSON 并校验
    #   result = json.loads(raw_output)
    #   self._validate(result)
    #   return result
    #
    # 思考题：
    # - 如果 json.loads 失败了怎么办？需要 try-except 吗？
    # - 为什么 temperature 要设得很低（0.1）？
    #
    def generate(self, requirement_text: str, max_retries: int = 3) -> dict:
        """
        输入需求文档文本，返回测试用例字典
        
        Args:
            requirement_text: 需求文档的完整文本
            max_retries: 最大重试次数（默认 3 次）
            
        Returns:
            dict: 结构化的测试用例集合
            
        Raises:
            ValueError: JSON 解析失败或校验失败
            RuntimeError: 多次重试后仍然失败
        """
        # 第一步：根据需求文档长度动态计算 max_tokens
        # 经验公式：输出长度 ≈ 输入长度 × 3~5 倍（测试用例通常比需求文档长）
        input_tokens = self.llm.estimate_tokens(requirement_text)
        estimated_output_tokens = min(input_tokens * 5, 16000)  # 上限 16K
        base_max_tokens = max(4096, estimated_output_tokens)  # 下限 4K
        
        print(f"[INFO] 输入约 {input_tokens} tokens，预估输出 {estimated_output_tokens} tokens")
        print(f"[INFO] 设置 max_tokens = {base_max_tokens}")
        
        # 第二步：带重试的生成逻辑
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                # 每次重试增加 max_tokens（应对截断问题）
                current_max_tokens = base_max_tokens * attempt
                print(f"\n[尝试 {attempt}/{max_retries}] max_tokens = {current_max_tokens}")
                
                messages = [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"请根据以下需求文档生成测试用例：\n\n{requirement_text}"
                    }
                ]
                
                # 调用 LLM（传入动态计算的 max_tokens）
                context = self.llm.chat_json(messages, max_tokens=current_max_tokens)
                print(f"[OK] 收到响应，长度: {len(context)} 字符")
                
                # 第三步：JSON 解析 + 异常处理
                try:
                    result = json.loads(context)
                except json.JSONDecodeError as e:
                    # 提取错误位置的上下文，帮助调试
                    error_pos = e.pos
                    start = max(0, error_pos - 50)
                    end = min(len(context), error_pos + 50)
                    error_context = context[start:end]
                    
                    raise ValueError(
                        f"❌ JSON 解析失败！\n"
                        f"错误位置: 第 {e.lineno} 行, 第 {e.colno} 列 (字符位置 {error_pos})\n"
                        f"错误类型: {e.msg}\n"
                        f"错误上下文: ...{error_context}...\n\n"
                        f"可能原因:\n"
                        f"1. 模型输出被截断（max_tokens={current_max_tokens} 可能太小）\n"
                        f"2. 模型生成了不完整的 JSON\n"
                        f"3. Prompt 中未明确要求输出纯 JSON\n\n"
                        f"建议:\n"
                        f"- 检查 SYSTEM_PROMPT 是否强调'只输出 JSON，不要其他文字'\n"
                        f"- 继续重试会自动增加 max_tokens"
                    ) from e
                
                # 第四步：输出校验
                self._validate(result)
                
                # ✅ 成功！返回结果
                print(f"[SUCCESS] 测试用例生成成功！")
                return result
                
            except (ValueError, KeyError, TypeError) as e:
                last_error = e
                print(f"[WARN] 第 {attempt} 次尝试失败: {str(e)[:200]}...")
                
                if attempt < max_retries:
                    print(f"[INFO] 准备重试...")
                    continue  # 重试
                else:
                    # 所有重试都失败了
                    break
        
        # 所有重试都失败了，抛出最终错误
        raise RuntimeError(
            f"经过 {max_retries} 次尝试仍无法生成有效的测试用例\n"
            f"最后一次错误: {last_error}"
        ) from last_error

    # ================================================================
    # TODO 2.3: 实现输出校验
    # ================================================================
    # 为什么校验很重要？
    # → 模型的输出是不可靠的，可能缺少字段、格式不对、甚至为空
    # → 在真实项目中，不校验就会导致下游系统崩溃
    #
    # 你需要校验：
    # 1. result 中必须有 "test_cases" 字段
    # 2. test_cases 不能为空
    # 3. 每个 test_case 必须包含：id, name, category, priority, steps, expected_result
    #
    # 提示：用 assert 或 raise ValueError
    #
    def _validate(self, result: dict):
        """校验输出结构是否合法"""
        # 1. 检查顶层结构
        if not isinstance(result, dict):
            raise ValueError(f"输出应为 dict，实际为 {type(result).__name__}")

        # 2. 检查 test_cases 字段存在
        if "test_cases" not in result:
            raise ValueError("输出缺少 'test_cases' 字段")

        test_cases = result["test_cases"]

        # 3. 检查不能为空
        if not isinstance(test_cases, list) or len(test_cases) == 0:
            raise ValueError("'test_cases' 不能为空列表")

        # 4. 检查每个用例的必要字段
        required_fields = {"id", "name", "category", "priority", "steps", "expected_result"}
        for i, tc in enumerate(test_cases):
            missing = required_fields - set(tc.keys())
            if missing:
                raise ValueError(
                    f"第 {i+1} 个用例缺少字段: {missing}"
                )
            if not isinstance(tc["steps"], list) or len(tc["steps"]) == 0:
                raise ValueError(f"用例 {tc.get('id', i+1)} 的 steps 不能为空")

    # ================================================================
    # 已实现：辅助方法（你可以直接使用）
    # ================================================================
    def generate_from_file(self, file_path: str) -> dict:
        """从文件读取需求文档并生成测试用例"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"需求文档不存在: {file_path}")
        text = path.read_text(encoding="utf-8")
        return self.generate(text)

    def save_result(self, result: dict, output_path: str):
        """将测试用例结果保存为 JSON 文件"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[OK] 测试用例已保存至: {output_path}")

    def print_summary(self, result: dict):
        """打印测试用例摘要"""
        print(f"\n{'='*60}")
        print(f"模块: {result.get('module', '未知')}")
        print(f"总用例数: {result.get('total_cases', len(result.get('test_cases', [])))}")

        categories = {}
        priorities = {}
        for tc in result.get("test_cases", []):
            cat = tc.get("category", "未知")
            pri = tc.get("priority", "未知")
            categories[cat] = categories.get(cat, 0) + 1
            priorities[pri] = priorities.get(pri, 0) + 1

        print(f"\n按类别:")
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count}")
        print(f"\n按优先级:")
        for pri, count in sorted(priorities.items()):
            print(f"  {pri}: {count}")
        print(f"{'='*60}\n")
