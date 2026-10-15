# CoEvo · 真实工作驱动的 Agent 递归自我改进研究

**目标**：研究个人日常与科研助手能否从长期真实工作经历中提升任务能力，并逐渐更善于改进自身的经验、工作方法、Harness 和模型参数。**RSI 是核心科学问题；文档编辑、表格、工具调用、资料整理、科研分析与持续协作是主要应用；编程不是默认核心任务。**

**现行路线（2026-10-15）**：优先复用 [PilotDeck](https://github.com/OpenBMB/PilotDeck) 的 Workspace、Office Skills、MCP/插件、长期会话、记忆与文件恢复等成熟能力，CoEvo 保留真实经历提取、行为学习、BF16 LoRA、策略改进和科学评价。**PilotDeck 源码运行环境与本地模型配置已就绪，首个原生文件任务正在验证。** 接入与实际结果见 [PilotDeck 记录](experiments/pilotdeck/README.md)。 旧 Pi 用于既有实验复现，不继续重复建设通用 Agent 桌面系统。

现役接受模型为 Qwen3.5-4B W0，Spark-X2.5-4B 仅为候选，无已晋升的学习权重；Pi thinking、工具执行与 BF16 LoRA 已实际运行。早期微型任务有局部收益但无长期 RSI 确认。[MCM](experiments/mcm-2025-c/README.md) 未完成有效科学预测；最近[跨领域完整工作](experiments/complete-work/README.md)中软件维护未解决核心冲突，科研分析可复现、部分数值正确但科学解释仍有实质错误。它们是应被保留并用于反馈学习的 D 证据。

当前研究关注：实际办公与科研交付、反馈后自主修订、条件化经验迁移、模型权重更新，以及 Agent 是否通过过去的修改结果逐渐提高未来自主改进的有效性。迁移 PilotDeck 导致的产品能力变化应与 CoEvo 的 RSI 学习收益分别判断。

权威文档：[研究方案](docs/研究方案.md)（Q1/Q2/Q3、文献与路线）、[评价与统计](docs/评估与统计.md)（实际成果和 RSI 证据）、[实施与复现](docs/实施与复现.md)（上游能力、集成接口和权限）、[AGENTS.md](AGENTS.md)（科研开发约定）。实测在 [experiments/](experiments/) 保存，历史版本由 Git 追溯，不并行维护过时方案。

个人科研默认仅在 main 开发。训练资源为单 RTX 5090 D 32GiB、约 96GB RAM，32GB 无独显笔记本未验收；私人会话、凭据和权重不提交公开仓库。文档决策不自动授权安装、运行、训练或云端传输。
