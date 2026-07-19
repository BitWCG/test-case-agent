# 开发过程中遇到的问题记录

## 问题 1：ModuleNotFoundError: No module named 'dotenv'

### 错误信息
```
ModuleNotFoundError: No module named 'dotenv'
```

### 原因
Qoder IDE 使用的是**系统 Python**（`/opt/homebrew/.../python3.13`），而不是项目的 venv 虚拟环境。系统 Python 没有安装项目依赖。

### 解决方案
1. 创建 `.vscode/settings.json`，指定 venv 解释器路径：
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
    "python.terminal.activateEnvironment": true
}
```
2. 创建 `.vscode/launch.json`，配置运行和调试配置

### 教训
- IDE 的执行按钮默认用系统 Python，需要手动配置
- venv 中的包不会自动被系统 Python 识别

---

## 问题 2：AttributeError: 'NoneType' object has no attribute 'get'

### 错误信息
```
AttributeError: 'NoneType' object has no attribute 'get'
```

### 原因
`test_case_generator.py` 的 `generate()` 方法还是 TODO 状态（只有 `pass`），返回 `None`。后续代码调用 `result.get("test_cases")` 时崩溃。

### 解决方案
实现 `generate()` 方法的完整逻辑，确保返回有效的 dict。

### 教训
- TODO 未实现时，函数默认返回 `None`
- 调用方应该对返回值做防御性检查

---

## 问题 3：JSON 截断 — test_case_generator.py

### 错误信息
```
json.decoder.JSONDecodeError: Unterminated string starting at: line 376 column 5
```

### 原因
LLM 生成的 JSON 超过 `max_tokens=4096` 限制，输出被截断，导致 JSON 不完整（有开头没结尾）。

### 解决方案
在 `generate()` 方法中实现：
1. **动态计算 max_tokens**：根据输入长度估算输出需要的 token 数
2. **递增重试**：如果 JSON 解析失败，增大 max_tokens 重试
3. **JSON 解析异常处理**：捕获 `JSONDecodeError`，给出清晰的错误信息

```python
input_tokens = self.llm.estimate_tokens(requirement_text)
estimated_output_tokens = min(input_tokens * 5, 16000)
base_max_tokens = max(4096, estimated_output_tokens)
# 每次重试 max_tokens = base_max_tokens * attempt
```

### 教训
- LLM 输出长度不可控，必须预留足够的 max_tokens
- 永远不要信任 LLM 的输出，必须校验和异常处理

---

## 问题 4：JSON 截断 — main.py 工具调用参数

### 错误信息
```
json.decoder.JSONDecodeError: Expecting ',' delimiter: line 1 column 1880 (char 1879)
```

### 原因
与问题 3 同类，但发生在**工具调用参数**层面。LLM 调用 `extract_features` 工具时，把 `parse_prd` 的完整输出（含 `raw_text` 整篇文档）作为 JSON 字符串塞进 `prd_json` 参数。JSON 套 JSON + 转义字符，参数长度达到 ~1880 字符，超过模型单次输出上限被截断。

### 解决方案（三层防护）
1. **动态 max_tokens**：根据对话历史长度自动计算
2. **截断自动重试**：检查 `finish_reason == "length"`，自动翻倍 max_tokens 重试
3. **JSON 解析兜底**：捕获 `JSONDecodeError`，把错误信息返回给 LLM 让它自行修正

### 根本修复
修改工具接口，让 `extract_features` 和 `extract_rules` 支持直接传 `file_path`，工具内部自己读取文件，避免 LLM 传递大段 JSON：

```python
# 之前：LLM 必须传递整个 JSON（容易截断）
extract_features(prd_json="{...整个文档...}")

# 之后：LLM 只传一个短路径（不会截断）
extract_features(file_path="/path/to/login_requirement.md")
```

### 教训
- 工具之间传递数据时，**优先传引用（文件路径）而不是传值（完整内容）**
- LLM 的单次输出有硬上限（qwen-plus 约 4096 token），大参数必然被截断

---

## 问题 5：API 400 错误 — 无效的 function.arguments

### 错误信息
```
openai.BadRequestError: Error code: 400 - 'The "function.arguments" parameter of the code model must be in JSON format.'
```

### 原因
问题 4 中截断的 `arguments`（不合法 JSON）被 `model_dump()` 存入 `self.messages`。下一轮调用 API 时，API 发现 `arguments` 不是合法 JSON，直接报 400 错误。

### 解决方案
在存入 `self.messages` **之前**，校验每个 `tool_call` 的 `arguments` 是否为合法 JSON。如果不是，清空为 `{}`：

```python
for tc in assistant_dict.get("tool_calls", []):
    args_str = tc["function"]["arguments"]
    try:
        json.loads(args_str)
    except json.JSONDecodeError:
        tc["function"]["arguments"] = "{}"  # 清空，防止 API 报 400
```

### 教训
- 存入 messages 的数据必须保证格式合法
- 防御性校验要在**写入前**做，而不是在**读取后**做

---

## 问题 6：死循环 — LLM 反复尝试同样的失败方式

### 现象
Agent 连续 10 轮调用 `extract_features`，每轮都传同样的大参数，每轮都被截断，每轮都失败。

### 原因
1. LLM 收到错误提示后，尝试"重新调用"，但方式完全一样
2. System Prompt 没有引导 LLM 使用更简洁的参数传递方式
3. 没有"连续失败 N 次后换策略"的机制

### 解决方案
1. **更新 System Prompt**：明确告诉 LLM 优先使用 `file_path` 参数
2. **更新 user_input**：在输入中直接给出文件路径和使用提示
3. **更新工具 description**：标注"推荐传 file_path，不推荐传 prd_json"

### 教训
- LLM 不会自动"创新"，如果一种方式失败了，它可能反复尝试同样的方式
- 需要在 Prompt 中明确引导正确的行为方式
- 考虑加入"连续失败 N 次后提示换策略"的机制

---

## 问题总结

| # | 问题 | 根因 | 关键修复 |
|---|------|------|----------|
| 1 | dotenv 找不到 | 系统 Python vs venv | 配置 IDE 解释器路径 |
| 2 | NoneType 错误 | TODO 未实现 | 实现函数逻辑 |
| 3 | JSON 截断（生成器） | max_tokens 太小 | 动态 max_tokens + 重试 |
| 4 | JSON 截断（工具参数） | 参数太大超出上限 | 传 file_path 而非 JSON |
| 5 | API 400 错误 | 截断的 JSON 存入 messages | 写入前校验并修复 |
| 6 | 死循环 | LLM 反复尝试同样方式 | Prompt 引导 + 工具设计优化 |

## 核心经验

1. **永远不要信任 LLM 的输出** — 必须校验、必须有异常处理
2. **工具之间传引用，不传值** — 文件路径比完整内容可靠得多
3. **防御性编程** — 在数据写入前校验，而不是在读取后补救
4. **Prompt 是行为引导的关键** — LLM 不会自己"创新"，需要明确引导
5. **日志是调试的基础** — 详细的 DEBUG 日志让问题定位效率提升 10 倍
6. **评测器和 Agent 要同步迭代** — Agent 优化后评测规则必须跟着更新（见问题 7）

---

## 问题 7：评测器参数检查表与 Agent 实际接口不一致

### 现象
轨迹评测中 `eval_tool_accuracy` 报大量"缺少参数 prd_json"错误，工具准确率被拉到 0.40，但 Agent 实际运行完全正常。

### 原因
`PROBLEMS.md` 问题 4 修复后，Agent 已改为传 `file_path`（而非 `prd_json`）调用 `extract_features`/`extract_rules` 等工具。但评测器的 `required_params` 表还是旧版，只认 `prd_json` 为合法参数。

**评测器落后于 Agent 的迭代版本。**

### 解决方案
将 `required_params` 从"单一必填列表"改为"多组合替代方案"：

```python
required_params_alternatives = {
    "extract_features": [["prd_json"], ["file_path"]],  # 任一组合合法
    "extract_rules": [["prd_json"], ["file_path"]],
    ...
}
```

只要满足任意一组参数组合，就算通过检查。

### 教训
- Agent 接口变了，评测规则必须同步更新
- 评测器也是代码，也需要"回归测试"
- 最好在工具定义（`setup.py`）中维护"合法参数组合"的 source of truth，评测器从中读取而非硬编码

---

## 问题 8：control_decision 打分逻辑——"无错误"时反而得 0 分

### 现象
Agent 顺利完成任务（无错误、无需恢复），但 `control_decision` 维度得分为 0.00。

### 原因
原始打分逻辑：
```python
recover_ratio = stats.get("Recover", {}).get("ratio", 0)
dim_score = min(1.0, recover_ratio * 5)
```

设计意图是"Recover 越多说明错误恢复能力越强"，但忽略了**没有错误发生时 Recover = 0**的情况。一个从不犯错的 Agent 反而被判为"恢复能力为零"。

### 解决方案
```python
if error_steps == 0:
    dim_score = 1.0  # 无错误 = 不需要恢复 = 满分
else:
    dim_score = min(1.0, recover_count / max(1, error_steps))
```

### 教训
- 评测指标要区分"能力未被测试"和"能力不足"
- `0` 分应该表示"失败了"，而不是"没有机会展示"
- 设计评测打分逻辑时，先列出所有边界情况：空 trace、无错误、全错误、部分恢复
