# CoEvo 科研软件开发约定

CoEvo 研究真实日常/科研 Agent 如何从长期经历中提升工作效果并递归改进自身策略。Q1 外部经历与指令生命周期、Q2 模型参数学习、Q3 学会如何改进 Harness/经验选择/学习策略；必须从实际成果与未来任务辨认收益，不以训练运行、CI、工具保护、文件数量和 Agent 自述冒充 RSI。

**现状（2026-10-15）**：在 main 开发；接受版 Qwen3.5-4B W0，Spark 未实测，无已晋升 W1。Pi 工具、thinking、BF16 LoRA 已实测；MCM 未完成预测，两项跨领域 D 工作分别为软件核心需求未修复、科研分析可复现但统计解释错误。原始事实见 [完整工作记录](experiments/complete-work/README.md)。优先复用 [PilotDeck](https://github.com/OpenBMB/PilotDeck) 通用 Workspace、Office Skills、MCP、会话恢复与记忆；**它尚未在本项目部署，不能声称已迁移或完成 RSI。**

执行规则：

- 优先完成有实际意义的完整工作和可用文件交付；编程只是需要时的辅助能力，不再以微型程序族和大量单步检查代替真实任务。
- 站在开源系统基础上工作：首先使用 PilotDeck 的原生 Skills、Hooks、插件/MCP、Workspace 与会话；只有实际接口不够且阻碍研究时才修改上游。源码中磁盘插件不能注入任意内部函数，FileChanged hook 仍为待实现，不应假定它们可用。
- 保留真实失败、有效部分成果、反馈及来源；区分首次独立成功、当次反馈后的修订、研究者/强模型辅助、外部经验收益、权重学习及后续自主改进能力。未核实的错误产物和临时指令不自动进入持久经验或正向训练。
- 只对真正改变科学解释或保护安全、来源、权限的事项做必要验证；不为每个错误新增实验、重复工具审核或兼容架构。允许负结果、放弃无效机制和合理重构。
- Harness/Skill 的自主改进不得扩大授权、修改独立评分器或抹除原始证据。PilotDeck 迁移首先算执行环境改变，不可冒称 CoEvo 的 RSI 增益。
- 单 main 直接提交、同步 GitHub，不默认建立 PR/审批流程；权威 docs 各司其职，历史实验结果留在 experiments。受影响路径的常规测试属于软件维护而不是科研评价。
- **用户本轮授权研究与更新文档，不包括实际安装/迁移 PilotDeck、推理、训练、底座变更、自动 RSI 周期或上传私人数据。**

现行依据：[研究方案](docs/研究方案.md)、[评价与统计](docs/评估与统计.md)、[实施与复现](docs/实施与复现.md)。旧 Pi 日常 CPU 入口：`PYTHONPATH=src python -m unittest discover -s tests -v`；JS 语法入口：`node --check scripts/pi-project-agent.mjs`。
