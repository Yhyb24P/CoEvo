# CoEvo · 真实工作驱动的 Agent 递归自我改进研究

**目标**：研究个人日常与科研助手能否从长期真实工作经历中提升任务能力，并逐渐更善于改进自身的经验、工作方法、Harness 和模型参数。**RSI 是核心科学问题；文档编辑、表格、工具调用、资料整理、科研分析与持续协作是主要应用；编程不是默认核心任务。**

**现行路线（2026-10-15）**：CoEvo **保持独立、可演化的 RSI Agent 架构**，选择性拆解吸收 [PilotDeck](https://github.com/OpenBMB/PilotDeck) 的 Office Skills、文件保真/恢复及白盒记忆思路，按任务需要采用 [Pi 1.2.0](https://pi.dev/changelog/releases/1.2.0) 的 SDK 改进；不整体移植 PilotDeck Gateway 或桌面 UI。Pi 1.2.0 已完成真实任务验证：原生 Skills 加载可用，工作簿首轮失败后经原生反馈续接修复；[实测与限制](experiments/pi-office/README.md)保留失败、辅助条件及未通过的经验候选。已有 [PilotDeck 独立 CLI/Transcript 实验入口](experiments/pilotdeck/README.md)保留为技术参照，不能误写为 CoEvo 已迁移或获得 RSI。

现役接受模型为 Qwen3.5-4B W0，Spark-X2.5-4B 仅为候选，无已晋升的学习权重；Pi thinking、工具执行与 BF16 LoRA 已实际运行。早期微型任务有局部收益但无长期 RSI 确认。[MCM](experiments/mcm-2025-c/README.md) 未完成有效科学预测；最近[跨领域完整工作](experiments/complete-work/README.md)中软件维护未解决核心冲突，科研分析可复现、部分数值正确但科学解释仍有实质错误。它们是应被保留并用于反馈学习的 D 证据。

最新[奥运表格原生经历比较](experiments/olympic-office/README.md)中，两组均未完整交付；无历史组获得逐条核实的 1435 条清理表，跨任务原生经历收益仍未确认。

最新 [Spark/Qwen 完整办公对照](experiments/spark-readiness/README.md)已完成：Spark 接入后未生成要求的交付，Qwen 取得正确清理表但完整任务仍失败；当前继续保留 Qwen W0，Spark 的训练/回载兼容性尚待验证。[原生轨迹分析](experiments/spark-readiness/README.md#原生轨迹复核执行为何未收敛2026-10-15)进一步识别了持续探索与全量改写的行为瓶颈；后续[不同来源共享单车工作](experiments/bike-sharing/README.md)也已实际执行：仅留下源码，数据语义与环境问题叠加，完整交付仍失败。

当前研究关注：实际办公与科研交付、反馈后自主修订、条件化经验迁移、模型权重更新，以及 Agent 是否通过过去的修改结果逐渐提高未来自主改进的有效性。复用上游 Skills、更新 Pi 或调整执行器的 Harness 收益，须与 CoEvo 的 RSI 学习收益分别判断。

权威文档：[研究方案](docs/研究方案.md)（Q1/Q2/Q3、文献与路线）、[评价与统计](docs/评估与统计.md)（实际成果和 RSI 证据）、[实施与复现](docs/实施与复现.md)（上游能力、集成接口和权限）、[AGENTS.md](AGENTS.md)（科研开发约定）。实测在 [experiments/](experiments/) 保存，历史版本由 Git 追溯，不并行维护过时方案。

个人科研默认仅在 main 开发。训练资源为单 RTX 5090 D 32GiB、约 96GB RAM，32GB 无独显笔记本未验收；私人会话、凭据和权重不提交公开仓库。文档决策不自动授权安装、运行、训练或云端传输。
