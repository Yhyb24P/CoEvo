# CoEvo · 真实工作驱动的 Agent 递归自我改进研究

**目标**：研究个人日常与科研助手能否从长期真实工作经历中提升任务能力，并逐渐更善于改进自身的经验、工作方法、Harness 和模型参数。**RSI 是核心科学问题；文档编辑、表格、工具调用、资料整理、科研分析与持续协作是主要应用；编程不是默认核心任务。**

**现行路线（2026-10-15）**：CoEvo **保持独立、可演化的 RSI Agent 架构**，选择性拆解吸收 [PilotDeck](https://github.com/OpenBMB/PilotDeck) 的 Office Skills、文件保真/恢复及白盒记忆思路，按任务需要采用 [Pi 1.2.0](https://pi.dev/changelog/releases/1.2.0) 的 SDK 改进；不整体移植 PilotDeck Gateway 或桌面 UI。当前 Pi SDK 适配器新增任务级 Skills、版本与中断结果记录，属于源码层的可审查改进，1.2.0 模型实测仍待实施。已有 [PilotDeck 独立 CLI/Transcript 实验入口](experiments/pilotdeck/README.md)保留为技术参照，不能误写为 CoEvo 已迁移或获得 RSI。

现役接受模型为 Qwen3.5-4B W0，Spark-X2.5-4B 仅为候选，无已晋升的学习权重；Pi thinking、工具执行与 BF16 LoRA 已实际运行。早期微型任务有局部收益但无长期 RSI 确认。[MCM](experiments/mcm-2025-c/README.md) 未完成有效科学预测；最近[跨领域完整工作](experiments/complete-work/README.md)中软件维护未解决核心冲突，科研分析可复现、部分数值正确但科学解释仍有实质错误。它们是应被保留并用于反馈学习的 D 证据。

当前研究关注：实际办公与科研交付、反馈后自主修订、条件化经验迁移、模型权重更新，以及 Agent 是否通过过去的修改结果逐渐提高未来自主改进的有效性。复用上游 Skills、更新 Pi 或调整执行器的 Harness 收益，须与 CoEvo 的 RSI 学习收益分别判断。

权威文档：[研究方案](docs/研究方案.md)（Q1/Q2/Q3、文献与路线）、[评价与统计](docs/评估与统计.md)（实际成果和 RSI 证据）、[实施与复现](docs/实施与复现.md)（上游能力、集成接口和权限）、[AGENTS.md](AGENTS.md)（科研开发约定）。实测在 [experiments/](experiments/) 保存，历史版本由 Git 追溯，不并行维护过时方案。

个人科研默认仅在 main 开发。训练资源为单 RTX 5090 D 32GiB、约 96GB RAM，32GB 无独显笔记本未验收；私人会话、凭据和权重不提交公开仓库。文档决策不自动授权安装、运行、训练或云端传输。
