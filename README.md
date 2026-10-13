# CoEvo

人机交互驱动的小模型 Agent 持续适应与参数学习研究，分别测量指令管理 K、经验检索 R、模型参数 W 与训练候选选择 S 的贡献。

**当前状态：2026-10-13，用户已授权按方案开始推进，并从 GitHub 选择独立任务项目。** 当前建设 T00–T04，选择 Marko 并开展有界 D 任务试跑；新训练、多周期 RSI 和笔记本部署未启动。当前进度见[项目接入记录](experiments/project-tasks/progress.md)；此前暂停时点的[云端研究快照](experiments/workstation-rsi/review_snapshot.md)保留为历史证据。

已在 RTX 5090 D 上完成原始 Qwen3.5-4B 的一次实际 131072-token 定位、原生工具写入与多轮状态试跑。完成一次真实 BF16 LoRA 更新及独立重新加载，但候选旧任务复测从 3/3 降到 0/3，未提升为接受版本。三个连续周期尚未完成；没有真实用户自进化或能力提升结论。云端可查看 [实测结果](experiments/workstation-rsi/measured_results.json)、[成功轨迹](experiments/workstation-rsi/examples/baseline-success.json)、[退化轨迹](experiments/workstation-rsi/examples/candidate-regression.json) 和 [训练候选](experiments/workstation-rsi/examples/training-candidate.json)。

CoEvo 是研究系统的建设仓库。已选择独立 Marko 项目作为首个代码/文件/终端任务环境；实际用户任务与纠错来源、训练触发和周期反馈方式仍需继续明确。现有合成文件任务仅用于工程试跑，不能代替真实人机交互。参数训练仍是核心环节，外部适应和权重收益须分别评价。

研究文档入口为 [文档导航](docs/00_文档导航_v0.4.md)，开发约束见 [AGENTS.md](AGENTS.md)，工程约定见 [科研软件工作规范](docs/06_科研软件工作规范.md)。当前研究基线为 [研究方案 v0.5](docs/agent_model_coevolution_experiment_plan_v0.5.md) 与 [评估协议 v0.5](docs/02_评估与统计协议_v0.5.md)：Q1 跨层经验固化与撤回、Q2 参数独立收益、Q3 双向反馈归因。真实交互成为核心学习来源，经验与参数基线并行建立；共享候选池机制实验与真实闭环分别提供证据。四项主要优越性比较采用 Holm 控制并联合风险约束，三周期、两流仅为试点。研究设计更新不构成恢复实施授权。

下一阶段建议交付 T00–T04：v0.5 文档入库、独立真实任务与反馈、Pi 执行能力、交互数据链和 LoRA 退化诊断。Q1 与 Q2 并行建设，再进入 Q3；不继续原合成任务三周期。任务、依赖及完成依据见[项目现状与任务路线](docs/07_项目现状与任务路线_2026-10-13.md)。v0.5 文档随本批交付纳入本地版本控制，尚未推送远端；用户后续授权允许开展基础建设与有界任务执行。

源码采用 `src/coevo/`、`pyproject.toml` 和 `uv.lock`。本地组件包括真实模型接入、工具轨迹与结果记录、LoRA 训练、候选准入、版本状态和交互导出；完整用户产品与正式机制对照未完成。momo 接入复用其 Pi SDK；历史试点支持指定文件 read/write，新项目入口已实测受控 read/write/bash 与会话 fork。上游通用 CLI 和扩展没有完成验收。原始模拟训练/评价被禁用，补丁见 [momo-code-local.patch](patches/momo-code-local.patch)。

原始权重、源码归档、完整数据和产物留在 `/mnt/e/CoEvo/`，项目目录链接使用；活动代码、Python 环境与必要热副本在 Linux 文件系统。云端仅保存源码、协议、脱离私人材料的合成样例及结果摘要，不包含权重、凭据或本机环境。

CPU 检查与已有轨迹提取：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
.venv/bin/python -m coevo.extract --input artifacts/rsi-pilot/cycle-1 \
  --out data/exports/pilot-cycle-1 --origin synthetic-pilot
```

当前 11 项 CPU 检查通过（本地任务环境存在时含实际 Pi 与隔离执行检查）。提取保留模型输入输出、可见思考、工具调用与返回以及失败状态，独立导出合法训练候选；此次 thinking 关闭，未记录思考内容。数据提取不会调用训练。周期入口在缺少用户训练产物时返回 `awaiting_user_training`；真实训练 CLI 仅供用户明确调用，该手动交接边界暂保留；新训练策略尚未确定。

环境复现依赖本机权重与上游源码，详见 [环境记录](experiments/workstation-rsi/environment_notes.md)。首次安装可用 `UV_CACHE_DIR="$PWD/.cache/uv-install" uv sync --locked`；该命令需要下载依赖，当前已有 GPU 环境，无需重复安装。原始 [试跑计划](experiments/workstation-rsi/pilot_plan.md) 保留历史配方，不作为继续运行授权。

当前没有公开软件或模型 Release；项目许可证与第三方再分发范围尚未最终决定。
