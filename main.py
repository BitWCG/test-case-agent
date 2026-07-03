#!/usr/bin/env python3
"""
测试用例生成 Agent — 统一入口

Day 3 重构后，main.py 只负责：
1. 解析命令行参数
2. 读取需求文档
3. 创建 Agent 并运行

Agent 核心逻辑在 src/agent/simple_agent.py 中。
日志系统在 src/agent/logger.py 中。

使用方法：
    cd test-case-agent
    source venv/bin/activate
    python main.py
    python main.py --input path/to/your/requirement.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.agent.llm_client import LLMClient
from src.agent.simple_agent import SimpleAgent


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
    user_input = (
        f"请分析以下需求文档并生成测试用例。\n"
        f"文件路径: {input_path}\n"
        f'(提示: 调用 extract_features 和 extract_rules 时请直接传 file_path="{input_path}")\n\n'
        f"{requirement_text}"
    )

    # 创建 Agent 并运行
    agent = SimpleAgent()
    result = agent.run(user_input)

    if result:
        print(f"\n{'=' * 60}")
        print("Agent 运行完成！")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

