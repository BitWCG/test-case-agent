# AI Agent 两周冲刺学习计划
## —— 构建"需求文档→测试用例生成"Agent

**时间**：16 天，每天 4-6 小时  
**技术栈**：Python 3.11+ / OpenAI SDK / SQLite+FTS5 / FastAPI  
**参考架构**：Hermes Agent（Python，3万行）+ OpenClaw（双层记忆+四层压缩）

---

## 核心架构

整个项目是一个**统一的 Agent 循环**，每天的学习是在这个循环上逐步增强能力：

```
while not done:
    thought = llm.think(messages)      # 思考
    if thought.has_tool_call:           # 需要行动？
        result = execute(tool_call)     # 行动（工具调用）
        messages.append(result)         # 观察
    else:
        done = True                     # 完成
```

- Day 1-3：Agent 循环 + 工具系统（基础能力）
- Day 4-5：给循环加 Memory（记忆能力）
- Day 6-7：给循环加 Skills（技能系统）
- Day 8-10：给循环加防护（压缩、防死循环、防漂移）
- Day 11：多个 Agent 循环协作
- Day 12-14：Agent 评测体系（6 维评测 + 反馈闭环）
- Day 15-16：工程化（API、回归测试、部署）

**统一入口**：`python main.py`

---

## Task 1：LLM 调用 + Agent 核心循环（Day 1-3）

### Day 1：项目骨架 + LLM 基础调用 ✅ 已完成
- [x] 创建 `test-case-agent/` 项目，配置虚拟环境
- [x] 实现 LLM API 调用（通义千问），理解 token 计算
- [x] 实现结构化输出（JSON Mode）
- [x] 设计 System Prompt，定义 Agent 角色和输出格式
- [x] 实现输出校验（_validate）
- **核心文件**：`src/agent/llm_client.py`、`src/agent/test_case_generator.py`

### Day 2：Function Calling + 工具系统 🔄 进行中
- [ ] TODO 3.1: `registry.py` → `execute()` 工具执行入口
- [ ] TODO 4.1: `test_tools.py` → `extract_features()` 提取功能点
- [ ] TODO 4.2: `test_tools.py` → `extract_rules()` 提取业务规则
- [ ] TODO 4.3: `test_tools.py` → `generate_cases()` 生成用例框架
- [ ] TODO 4.4: `test_tools.py` → `format_output()` 格式化输出
- [ ] TODO 5.1: `main.py` → `__init__()` 初始化 Agent
- [ ] TODO 5.2: `main.py` → `run()` Agent 主循环
- **实现顺序**：3.1 → 4.1 → 4.2 → 4.3 → 4.4 → 5.1 → 5.2
- **验收**：`python main.py` 能自主调用工具链完成全流程

### Day 3：Agent Loop 完善
- [ ] 将 `SimpleAgent` 从 `main.py` 抽离到 `src/agent/simple_agent.py`
- [ ] 拆分 `run()` 为 `think()` / `act()` / `observe()` 三方法
- [ ] 添加日志系统（每轮 trace log 写入文件）
- **实现顺序**：
  1. 创建 `src/agent/simple_agent.py`，把 main.py 的 SimpleAgent 类搬过去
  2. 把 `run()` 中的 LLM 调用抽成 `think()` → 返回 response
  3. 把工具执行抽成 `act()` → 执行 tool_calls，返回结果列表
  4. 把结果加入 messages 抽成 `observe()` → 追加到历史
  5. 在 `main.py` 中 import SimpleAgent，加 logging 初始化
  6. 测试：用不同需求文档跑，看日志是否完整记录推理过程
- **验收**：Agent 类可复用，日志可追溯完整推理过程

---

## Task 2：Memory 记忆系统（Day 4-5）

### Day 4：三层记忆架构
- [ ] 实现 `MemoryManager` 类（工作记忆 + 语义记忆 + 情节记忆）
- [ ] 实现 `add_memory()` 和 `search_memory()`（FTS5 全文检索）
- **实现顺序**：
  1. 创建 `src/memory/memory_manager.py`，定义 `MemoryManager` 类
  2. 实现 `__init__()`：初始化 SQLite 连接 + 创建 FTS5 虚拟表
  3. 实现 `add_semantic()`：写入 `memory.md`（测试规范、模板）
  4. 实现 `add_episodic()`：写入 SQLite（历史操作记录）
  5. 实现 `search_memory(query)`：FTS5 全文检索，返回相关记忆
  6. 写个 `if __name__ == "__main__"` 测试块，验证增删查改
- **验收**：能存入记忆、能按关键词检索出来

### Day 5：记忆集成 + 混合检索
- [ ] Agent 启动时自动加载相关记忆到上下文
- [ ] 每次生成用例后，将结果写入情节记忆
- [ ] 实现混合检索：FTS5 关键词 + 简单相关性排序
- **实现顺序**：
  1. 在 `simple_agent.py` 的 `__init__()` 中初始化 `MemoryManager`
  2. 在 `run()` 开头调用 `search_memory(user_input)` 加载相关记忆
  3. 把检索结果插入 messages 的 system 部分（作为背景知识）
  4. 在 `run()` 结尾（完成后）调用 `add_episodic()` 存入本次操作
  5. 在 `memory.md` 中预置测试用例模板、常见遗漏清单
  6. 测试：跑两次同一个需求，看第二次是否参考了第一次的经验
- **验收**：Agent 能跨会话记住历史用例

---

## Task 3：Skills 技能系统（Day 6-7）

### Day 6：Skill 定义与加载
- [ ] 创建 5 个 SKILL.md 文件
- [ ] 实现 `SkillLoader`：匹配 + 加载 Skill
- **实现顺序**：
  1. 创建 `skills/` 目录，写 5 个 SKILL.md（需求分析、测试策略、功能用例、API 用例、用例评审）
  2. 创建 `src/skills/skill_loader.py`，定义 `SkillLoader` 类
  3. 实现 `__init__()`：扫描 `skills/` 目录，解析每个 SKILL.md 的元数据（名称、触发关键词）
  4. 实现 `match(task_type)`：根据关键词匹配最相关的 Skill
  5. 实现 `load(skill_name)`：读取 SKILL.md 内容，返回结构化 Skill 对象
  6. 在 `simple_agent.py` 中集成：`run()` 开头根据用户输入匹配 Skill，注入 system prompt
- **验收**：新 Skill 放入 skills/ 目录即可被识别

### Day 7：自动提炼 + Hooks
- [ ] 实现 Hooks 机制（3 个钩子）
- [ ] 实现简单自动提炼
- **实现顺序**：
  1. 在 `simple_agent.py` 中定义 hooks 字典：`self.hooks = {}`
  2. 实现 `register_hook(event, callback)`：注册事件回调
  3. 实现 `emit(event, data)`：触发事件，执行所有回调
  4. 注册 3 个钩子：
     - `on_requirement_received` → 自动解析文档格式（Markdown/Word/纯文本）
     - `on_case_generated` → 自动格式校验（JSON schema 检查）
     - `on_session_end` → 提炼经验写入 Memory
  5. 在 `run()` 的关键节点调用 `emit()`
  6. 实现自动提炼：记录工具调用轨迹，超过 5 步时尝试抽象为 Skill
- **验收**：Agent 能根据需求类型选择对应 Skill，钩子自动触发

---

## Task 4：上下文压缩 + 防护体系（Day 8-10）

### Day 8：上下文压缩
- [ ] 实现 `ContextCompressor` 四层管线
- **实现顺序**：
  1. 创建 `src/compressor/context_compressor.py`，定义 `ContextCompressor` 类
  2. 实现 `__init__(max_tokens=8000)`：设置阈值
  3. 实现 L3 `tool_result_budget(messages)`：大工具结果截断为 200 字预览 + "[已落盘]"
  4. 实现 L1 `snip_compact(messages)`：超阈值时裁掉中间对话，保留头 3 条 + 尾 5 条
  5. 实现 L2 `micro_compact(messages)`：旧 tool 消息替换为 `[工具结果已压缩]`
  6. 实现 L4 `compact_history(messages, llm)`：调用 LLM 对旧消息做摘要
  7. 实现 `compress(messages)`：按 L3→L1→L2→L4 顺序执行管线
  8. 在 `simple_agent.py` 的 `run()` 每轮开头调用 `compress()`
- **验收**：50 页文档不崩溃，Token 始终在阈值内

### Day 9：死循环 + 目标漂移防护
- [ ] 实现 `AgentGuard`（死循环防护）
- [ ] 实现 `GoalAnchor`（目标锚定）
- **实现顺序**：
  1. 创建 `src/guards/agent_guard.py`，定义 `AgentGuard` 类
  2. 实现 `__init__()`：初始化计数器（轮次、工具调用次数、调用哈希集合）
  3. 实现 `check(round_num, tool_name, tool_args)` → 返回 (是否通过, 原因)
  4. 实现硬限制检查：轮次 > 10 或工具调用 > 30 → 拦截
  5. 实现重复检测：`hash(tool_name + json.dumps(args))` 去重，连续 2 次相同 → 拦截
  6. 创建 `src/guards/goal_anchor.py`，定义 `GoalAnchor` 类
  7. 实现 `anchor(original_goal)`：固定原始目标
  8. 实现 `inject_anchor(messages)`：每轮在 system prompt 注入原始目标
  9. 实现 `check_drift(messages)`：让 LLM 判断当前是否偏离目标
  10. 在 `simple_agent.py` 的 `run()` 中集成 Guard 和 Anchor
- **验收**：死循环 100% 拦截；目标漂移能检测并纠正

### Day 10：幻觉 + 溢出 + 成本防护
- [ ] 幻觉防护：Prompt 约束 + source_reference 校验
- [ ] 溢出处理：检测 → 压缩 → 重试 → 紧急压缩
- [ ] 成本防护：Token 预算上限 + 熔断
- **实现顺序**：
  1. 修改 `SYSTEM_PROMPT`：加入"只使用提供的需求内容，无法溯源标记 [待确认]"
  2. 在 `simple_agent.py` 的 `run()` 完成后加后处理：检查每个用例的 source_reference
  3. 创建 `_handle_overflow(error)` 方法：
     - 识别溢出错误模式（各厂商不同）
     - 调用 compressor.compress() → 重试
     - 再次溢出 → 紧急压缩（只保留最近 3 条）
  4. 实现 `CostTracker`：记录每次 API 调用的 Token 消耗
  5. 实现熔断：总消耗超过预算 → 停止并报告
  6. 在 `run()` 中集成：每轮检查成本，溢出时调用 `_handle_overflow()`
- **验收**：50 页文档不崩溃；幻觉用例标记为 `[待确认]`；成本可控

---

## Task 5：多 Agent 协作（Day 11）

### Day 11：多 Agent 架构
- [ ] 设计 3 个专职 Agent + Orchestrator
- **实现顺序**：
  1. 创建 `src/agent/orchestrator.py`，定义 `AgentOrchestrator` 类
  2. 复用 `SimpleAgent` 作为基类，创建 3 个子类：
     - `AnalystAgent`：工具只有 parse_prd + extract_features + extract_rules
     - `GeneratorAgent`：工具只有 generate_cases + format_output
     - `ReviewerAgent`：工具是新的 review_cases（检查覆盖率、一致性）
  3. 实现 `orchestrate(user_input)`：按顺序调用 Analyst → Generator → Reviewer
  4. 实现反馈循环：Reviewer 发现问题 → 回退给 Generator 重新生成（最多 2 次）
  5. 测试：对比单 Agent 和多 Agent 的输出质量
- **验收**：3 个 Agent 协作完成全流程，质量优于单 Agent

---

## Task 6：Agent 评测体系（Day 12-14）

> 对应岗位：AI Agent 评测工程师（字节、平安、智谱等均在招聘）
> 核心能力：不是"会用评测工具"，而是"能设计评测体系 + 用评测驱动 Agent 迭代"
> 评测对象：你的 test-case-agent 这个完整系统（LLM + 工具 + 循环 + 记忆），不是单测 LLM
>
> **参考论文**（2026 前沿范式）：
> - IBM+Yale 综述：[Survey on Evaluation of LLM-based Agents](https://arxiv.org/abs/2503.16416)（v2, 2026-04）
> - AgentAtlas（2605.20530）：控制决策六态 + 轨迹失败九类
> - Claw-Eval（2604.06132）：三通道轨迹审计 + 耦合评分公式
> - LiveAgentBench（2603.02586）：真实场景动态评测
>
> **核心认知**：Agent 评测不能沿用"答对没有"范式，要看"在动态环境里能不能通过一连串决策把事做成"。
> 评分公式（Claw-Eval）：`task_score = Safety × (0.80 × Completion + 0.20 × Robustness)`
> Safety 是乘性门控——安全违规直接清零，不是扣分。
>
> **重要概念：解耦 LLM vs Harness（脚手架）**
> 一次 Agent 跑分混了三样东西：Backbone LLM（模型本身）、Agent Harness（编排框架/重试策略）、工具与环境。
> 排行榜越来越像"系统工程分"而非纯模型分。你做评测时，要意识到分数变化是模型引起的还是框架引起的。
> 📖 这是了解即可的概念——你目前只测一个 Agent，暂不涉及横评，但面试可能会问。

### Day 12：评测基础设施 + 确定性评测

**目标**：建立评测的"水电煤"——数据集、记录器、基础指标

- [ ] 构建评测数据集（`data/eval/`）
- [ ] 实现 Trace 记录器
- [ ] 实现确定性评测器
- **实现顺序**：
  1. 准备 15 个标注好的需求文档，放入 `data/eval/`（含 expected_features 作为参考答案）
  2. 创建 `src/eval/trace_recorder.py`：
     - `__init__()`：初始化 trace_id、记录列表
     - `record_think(content)`：记录每轮思考
     - `record_tool_call(name, args, result, tokens)`：记录工具调用
     - `save(path)`：导出为 JSON
     - > 📖 **延伸阅读**：Claw-Eval 的三通道证据（execution trace + audit log + env snapshot）
       > 你目前只实现 trace 通道，已够用。三通道交叉验证是生产级要求，了解即可。
  3. 在 `simple_agent.py` 的 `run()` 中集成 TraceRecorder
  4. 创建 `src/eval/deterministic_eval.py`：
     - `eval_format(result)`：JSON schema 校验
     - `eval_coverage(result, expected)`：功能覆盖率
     - `eval_traceability(result)`：溯源率
     - `eval_diversity(result)`：类别比例
     - `eval_efficiency(trace)`：工具调用次数、Token、时间
     - `run_all(result, expected, trace)`：汇总报告
  5. 写个测试脚本跑通 5 个样本
- **验收**：每个样本输出 trace JSON + 确定性评测报告

### Day 13：LLM-as-Judge + 轨迹评测

**目标**：加入"主观质量"评测——确定性断言只能检查"对不对"，Judge 检查"好不好"

- [ ] 实现 LLM-as-Judge
- [ ] 实现轨迹评测
- **实现顺序**：
  1. 创建 `src/eval/llm_judge.py`：
     - 定义 Rubric（1-5 分，每个分数的标准）
     - 实现 `judge(result, requirement)` → 返回 `{score, reason}`
     - 用另一个 LLM 模型做 Judge（不能用 Agent 同一个模型）
     - 实现多 Judge 投票：2 个不同 prompt 风格，取中位数
  2. 创建 `src/eval/trajectory_eval.py`：
     - `eval_tool_accuracy(trace)`：工具是否选对、参数是否正确
     - `eval_step_efficiency(trace)`：有无冗余调用
     - `eval_error_recovery(trace)`：工具报错后 Agent 怎么处理
     - `eval_planning(trace)`：工具调用顺序是否合理
     - **控制决策六态检查**（参考 AgentAtlas）：
       对 trace 中每一步分类为 Act/Ask/Refuse/Stop/Confirm/Recover 之一
       - Act：信息充分，可安全执行（正常路径）
       - Ask：任务欠指定，应先澄清（盲目开干 = 失败）
       - Refuse：越权/有害请求应拒绝（错误放行 = 失败）
       - Stop：已完成或应终止（无限循环 = 失败）
       - Confirm：不可逆操作需确认（直接执行 = 失败）
       - Recover：失败后应修复而非硬闯（无视错误 = 失败）
     - **轨迹失败分类**（简化版，参考 AgentAtlas 九类）：
       - 规划失败：工具选择错误、步骤顺序错误、遗漏关键步骤
       - 执行失败：参数错误、工具调用失败、结果解析失败
       - 决策失败：该 Ask 却 Act、该 Refuse 却执行、该 Stop 却继续
       - 恢复失败：重试策略错误、错误后硬闯、无法从失败中恢复
  3. 对 Day 12 的 5 个 trace 跑评测
- **验收**：输出 Judge 评分报告 + 轨迹分析报告（含控制决策分类 + 失败归因）

### Day 14：安全性 + 鲁棒性 + 一致性 + 反馈闭环

**目标**：补全生产级评测的三大维度，并建立评测→优化闭环

- [ ] 实现安全性评测
- [ ] 实现鲁棒性评测
- [ ] 实现一致性评测
- [ ] 实现评测→优化反馈闭环
- **实现顺序**：
  1. 创建 `src/eval/security_eval.py`：
     - 准备 5 个注入样本（恶意指令、越权请求、信息窃取）
     - `eval_injection(agent, samples)` → 是否拒绝恶意指令
     - `eval_leakage(agent)` → 输出中是否包含敏感信息
  2. 创建 `src/eval/robustness_eval.py`：
     - 准备异常样本（空文档、乱码、超长文档）
     - `eval_abnormal_input(agent, samples)` → 是否优雅处理
     - `eval_tool_failure(agent)` → 模拟工具报错，Agent 能否恢复
  3. 创建 `src/eval/consistency_eval.py`：
     - `eval_stability(agent, input, runs=5)` → 同一输入跑 5 次，计算波动率
     - `eval_temperature_impact(agent, input)` → 对比 temp=0 和 temp=0.7
     - **Pass@k vs Pass^k**（参考 Claw-Eval，2026 核心指标）：
       - Pass@3：3 次里成功 1 次就算过 → 测**能力上限**（理论上能跑通）
       - Pass^3：3 次全部成功才算过 → 测**生产可靠性**（稳定可用）
       - 实现：`eval_pass_at_k(agent, input, k=3)` 和 `eval_pass_pow_k(agent, input, k=3)`
       - Stability Gap = Pass@k - Pass^k：Gap 大说明靠运气，不适合生产
  4. 实现**耦合评分**（参考 Claw-Eval 公式）：
     - 综合分 = Safety_score × (0.80 × Completion_score + 0.20 × Robustness_score)
     - Safety 是乘性门控：安全违规 → 综合分直接清零
     - 在反馈闭环中用耦合评分作为最终排名指标
  5. 实现反馈闭环：
     - 汇总 6 维评测结果 + 耦合综合分，自动识别失败模式
     - 生成诊断报告（按严重程度排序，含轨迹失败分类统计）
     - 根据报告自动调整 System Prompt，重新跑评测验证
- **验收**：完整 6 维评测报告 + 耦合综合分 + Pass@k/Pass^k + 诊断报告 + 优化后重新验证的结果

---

## Task 7：工程化 + 回归（Day 15-16）

### Day 15：API 服务化 + 可观测性
- [ ] 用 FastAPI 封装 Agent 为 REST API
- [ ] 接入 Langfuse（可选）
- **实现顺序**：
  1. 创建 `src/api/server.py`，初始化 FastAPI 应用
  2. 实现 `POST /generate`：接收需求文档文本，调用 Agent，返回测试用例 JSON
  3. 实现 `GET /history`：从 SQLite 查询历史生成记录
  4. 实现 `POST /eval`：调用评测系统，返回评测报告
  5. 实现 `GET /eval/{trace_id}`：返回某次评测的完整 trace
  6. 添加异步处理：长文档生成不阻塞（`BackgroundTasks`）
  7. （可选）接入 Langfuse：pip install langfuse，初始化追踪
  8. 测试：用 curl 或浏览器调用每个接口
- **验收**：API 能正常调用，返回正确结果

### Day 16：回归测试 + 总结
- [ ] 实现 CI 回归测试
- [ ] 完整评测流程 + 总结
- **实现顺序**：
  1. 创建 `tests/test_regression.py`：
     - 加载 `data/eval/` 中的评测数据集
     - 跑完整 6 维评测
     - 与基线分数对比，检测退化
  2. 保存当前版本的分数为基线（`data/eval/baseline.json`）
  3. （可选）配置 promptfoo：写 YAML 定义测试用例和预期
  4. 跑一遍完整评测流程，生成最终报告
  5. 总结学习收获，整理项目代码
  6. **评测集动态刷新**（参考 LiveAgentBench SPDG 流程）：
     - 预留接口：`data/eval/` 支持新增样本而不改代码
     - 每季度补充 3-5 个新样本，检测评测集是否饱和
     - 记录每次刷新的分数变化，监控 Agent 能力漂移
- **验收**：可演示的 API + 完整 6 维评测报告（含耦合评分） + 回归测试套件 + 评测集刷新机制

---

## 项目结构

```
test-case-agent/
├── main.py                    # 统一入口
├── requirements.txt           # 依赖
├── .env                       # 配置（API Key 等）
├── src/
│   ├── agent/
│   │   ├── llm_client.py          # LLM 客户端（Day 1）
│   │   ├── test_case_generator.py # 直接生成器（Day 1）
│   │   ├── simple_agent.py        # Agent 循环（Day 3）
│   │   └── orchestrator.py        # 多 Agent 协调（Day 11）
│   ├── tools/
│   │   ├── registry.py            # 工具注册表（Day 2）
│   │   ├── test_tools.py          # 测试工具实现（Day 2）
│   │   └── setup.py               # 工具注册入口（Day 2）
│   ├── memory/
│   │   └── memory_manager.py      # 记忆管理（Day 4-5）
│   ├── skills/
│   │   └── skill_loader.py        # 技能加载器（Day 6-7）
│   ├── compressor/
│   │   └── context_compressor.py  # 上下文压缩（Day 8）
│   ├── guards/
│   │   ├── agent_guard.py         # 死循环防护（Day 9）
│   │   └── goal_anchor.py         # 目标锚定（Day 9）
│   ├── eval/
│   │   ├── trace_recorder.py      # Trace 记录器（Day 12）
│   │   ├── deterministic_eval.py  # 确定性评测（Day 12）
│   │   ├── llm_judge.py           # LLM-as-Judge 评测（Day 13）
│   │   ├── trajectory_eval.py     # 轨迹评测（Day 13）
│   │   ├── security_eval.py       # 安全性评测（Day 14）
│   │   ├── robustness_eval.py     # 鲁棒性评测（Day 14）
│   │   └── consistency_eval.py    # 一致性评测（Day 14）
│   └── api/
│       └── server.py              # FastAPI 服务（Day 15）
├── skills/                        # Skill 定义文件（Day 6）
├── data/
│   ├── sample_docs/               # 示例需求文档
│   ├── eval/                      # 评测数据集（Day 12）
│   └── output/                    # 生成结果
└── tests/
    └── test_regression.py         # 回归测试（Day 16）
```

---

## 当前进度

| 阶段 | 状态 | 备注 |
|------|------|------|
| Day 1: LLM 基础调用 | ✅ 完成 | 24 个测试用例生成成功 |
| Day 2: Function Calling | 🔄 进行中 | 待完成 5 个 TODO |
| Day 3-16 | ⏳ 待开始 | |

---

## 能力对标（来自招聘 JD 反推）

| 能力层级 | 对应学习阶段 | 对应岗位要求 |
|---|---|---|
| L1: Python + LLM 调用 + Prompt | Day 1-2 | "熟练掌握 Python，熟悉主流大模型生态" |
| L2: Agent 架构理解 | Day 3-7 | "快速理解复杂 Agent 逻辑，Agent 流程设计" |
| L3: 评测工程实现 | Day 12-13 | "评测工具开发、自动化评测、评测集构建" |
| L4: 评测体系设计 | Day 14（6 维评测+闭环） | "端到端 Agent 评测体系，多维度多指标" |
| L5: 业务场景落地 | Day 15-16（API + 回归） | "懂业务比纯技术多拿 70%" |

---

## Agent 评测 6 维模型（生产级）

```
                    ┌──────────────┐
                    │  ① 确定性评测  │  格式对不对？覆盖全不全？
                    │  (Day 12)     │  ← 零成本，最先跑
                    ├──────────────┤
                    │  ② LLM Judge  │  用例质量好不好？
                    │  (Day 13)     │  ← 有成本，评"主观质量"
                    ├──────────────┤
                    │  ③ 轨迹评测    │  工具用对了吗？路径合理吗？
                    │  (Day 13)     │  ← 评"过程"而非"结果"
                    ├──────────────┤
                    │  ④ 安全性评测  │  会不会被注入？泄露信息？
                    │  (Day 14)     │  ← 生产环境必须过
                    ├──────────────┤
                    │  ⑤ 鲁棒性评测  │  异常输入会不会崩溃？
                    │  (Day 14)     │  ← 生产环境必须过
                    ├──────────────┤
                    │  ⑥ 一致性评测  │  多次运行结果稳定吗？
                    │  (Day 14)     │  ← Pass@k vs Pass^k
                    └──────────────┘
                            ↓
                    ┌──────────────┐
                    │  耦合综合分    │  Safety × (0.8×Completion + 0.2×Robustness)
                    │  (Day 14)     │  Safety 违规 → 综合分清零
                    ├──────────────┤
                    │  反馈闭环      │  失败模式 → 诊断报告 → 优化建议
                    │  (Day 14)     │  → 改 Prompt → 重新评测验证
                    └──────────────┘
```

**耦合评分公式**（参考 Claw-Eval）：
```
综合分 = Safety × (0.80 × Completion + 0.20 × Robustness)
  - Safety 是乘性门控：违规 → 综合分清零
  - Completion 是主分：任务完成度
  - Robustness 是辅助分：异常恢复能力
```

**可靠性指标**（参考 Claw-Eval）：
```
Pass@k ：k 次里成功 1 次 → 能力上限（理论上能跑通）
Pass^k ：k 次全部成功     → 生产可靠性（稳定可用）
Stability Gap = Pass@k - Pass^k
  - Gap 大 → 靠运气，需加熔断/降级
  - Gap 小 → 结果稳定，可放心部署
```

**生产环境上线门槛**：
- ①④⑤⑥ 必须全部通过（Safety 乘性门控 = 违规直接拦截）
- ②③ 达到基线分数
- Pass^3 ≥ 80%（生产可靠性下限）
- Stability Gap ≤ 10pp（结果稳定性上限）
