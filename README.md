# Test Case Agent 🧪

基于 LLM 的智能测试用例生成 Agent，能够从需求文档自动生成结构化的测试用例。

## ✨ 特性

-  **AI 驱动**：利用大语言模型理解需求并生成测试用例
- 📋 **结构化输出**：生成符合标准的 JSON 格式测试用例
-  **自动校验**：内置输出验证机制，确保数据完整性
- 🔄 **智能重试**：自动处理 API 截断、格式错误等异常
- 🛠️ **工具扩展**：支持自定义工具函数增强能力
- 💰 **成本优化**：动态调整 token 使用，节省 API 费用

## 🚀 快速开始

### 前置要求

- Python 3.10+
- 虚拟环境（venv）
- LLM API Key（支持 OpenAI、通义千问等兼容 OpenAI 格式的厂商）

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/BitWCG/test-case-agent.git
cd test-case-agent

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key
```

### 配置环境变量

编辑 `.env` 文件：

```env
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus
```

支持的 LLM 厂商：
- OpenAI (gpt-4, gpt-3.5-turbo)
- 阿里云通义千问 (qwen-plus, qwen-max)
- 百度文心一言
- 智谱 GLM
- DeepSeek
- 任何兼容 OpenAI API 格式的服务

### 运行示例

```bash
# 使用默认示例文档
python main.py

# 指定自定义需求文档
python main.py data/custom_requirement.md

# 或使用 --input 参数
python main.py --input data/custom_requirement.md
```

##  项目结构

```
test-case-agent/
├── main.py                    # 主入口文件
├── requirements.txt           # 依赖列表
├── .env                       # 环境变量（需自行创建）
├── .env.example              # 环境变量示例
├── .gitignore                # Git 忽略规则
├── README.md                 # 本文档
│
├── src/                      # 源代码
│   ├── agent/               # Agent 核心逻辑
│   │   ├── __init__.py
│   │   ├── llm_client.py    # LLM 客户端封装
│   │   └── test_case_generator.py  # 测试用例生成器
│   ├── tools/               # 工具函数
│   │   ├── __init__.py
│   │   ├── registry.py      # 工具注册表
│   │   ├── setup.py         # 工具初始化
│   │   └── test_tools.py    # 测试工具实现
│   ├── compressor/          # 上下文压缩（预留）
│   ├── guards/              # 安全防护（预留）
│   ├── memory/              # 记忆模块（预留）
│   └── skills/              # 技能模块（预留）
│
├── data/                     # 数据目录
│   ├── sample_docs/         # 示例需求文档
│   │   └── login_requirement.md
│   └── output/              # 输出目录（gitignore）
│
└── tests/                    # 测试用例（预留）
```

##  核心功能

### 1. LLM 客户端 (`src/agent/llm_client.py`)

统一的 LLM 调用接口，支持：
- 普通对话模式
- JSON Mode（强制输出合法 JSON）
- Token 估算
- 多厂商兼容

```python
from src.agent.llm_client import LLMClient

llm = LLMClient()
response = llm.chat([
    {"role": "user", "content": "你好"}
])
```

### 2. 测试用例生成器 (`src/agent/test_case_generator.py`)

从需求文档生成结构化测试用例：
- 动态计算 max_tokens
- 自动重试机制（最多 3 次）
- 严格的输出校验
- 详细的错误提示

```python
from src.agent.test_case_generator import TestCaseGenerator

generator = TestCaseGenerator()
result = generator.generate_from_file("requirement.md")
```

### 3. 工具系统 (`src/tools/`)

可扩展的工具函数库：
- `parse_prd`: 解析需求文档
- `extract_features`: 提取功能点
- `extract_rules`: 提取业务规则
- `generate_cases`: 生成测试用例
- `format_output`: 格式化输出

##  输出格式

生成的测试用例采用标准 JSON 格式：

```json
{
  "module": "登录模块",
  "total_cases": 15,
  "test_cases": [
    {
      "id": "TC001",
      "name": "正常登录",
      "category": "功能测试",
      "priority": "P0",
      "preconditions": ["用户已注册", "账号未锁定"],
      "steps": [
        "打开登录页面",
        "输入正确的用户名",
        "输入正确的密码",
        "点击登录按钮"
      ],
      "expected_result": "登录成功，跳转到首页",
      "source_reference": "需求文档第 3.1 节"
    }
  ],
  "coverage_summary": {
    "functional": 8,
    "security": 3,
    "performance": 2,
    "edge_cases": 2
  }
}
```

## 🛡️ 错误处理

项目内置多层防御机制：

1. **JSON 解析保护**：捕获格式错误，提供详细上下文
2. **输出校验**：验证必需字段、数据类型、非空检查
3. **智能重试**：自动增加 max_tokens 应对截断问题
4. **清晰报错**：友好的错误信息，指导用户修复

## 🎓 学习路径

本项目设计为渐进式学习框架：

- **Day 1**: LLM 基础调用 + 测试用例生成
- **Day 2**: 工具系统集成 + Agent 循环
- **Day 3**: 上下文管理 + 记忆模块
- **Day 4**: 安全防护 + Guardrails
- **Day 5**: 性能优化 + 生产部署

查看 [LEARNING_PLAN.md](LEARNING_PLAN.md) 了解详细学习计划。

##  贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发环境设置

```bash
# 1. Fork 本仓库
# 2. 克隆到本地
git clone https://github.com/YOUR_USERNAME/test-case-agent.git

# 3. 创建特性分支
git checkout -b feature/amazing-feature

# 4. 提交更改
git commit -m "Add some amazing feature"

# 5. 推送到 GitHub
git push origin feature/amazing-feature

# 6. 开启 Pull Request
```

### 代码规范

- 遵循 PEP 8 编码风格
- 添加必要的注释和文档字符串
- 编写单元测试（tests/ 目录）
- 更新 README 和相关文档

##  许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

##  致谢

- OpenAI SDK - 提供统一的 LLM 调用接口
- 通义千问 - 中文场景下的优秀表现
- Python 社区 - 丰富的生态系统

##  联系方式

- 项目地址: https://github.com/BitWCG/test-case-agent
- 问题反馈: [Issues](https://github.com/BitWCG/test-case-agent/issues)

---

Made with ❤️ by BitWCG Team
