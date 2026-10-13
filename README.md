# CoEvo

人机交互驱动的小模型 Agent 持续适应与参数学习研究，分别测量指令管理 K、经验检索 R、模型参数 W 与训练候选选择 S 的贡献。

**当前状态：2026-10-13，用户要求暂停实施，先在云端调研确认研究路线。** 复核从 [云端研究快照](experiments/workstation-rsi/review_snapshot.md) 开始；它区分实际结果、工程边界与待讨论问题。当前没有运行中的推理或训练周期，不自动恢复实验，阶段 D 暂不处理。

已在 RTX 5090 D 上完成原始 Qwen3.5-4B 的一次实际 131072-token 定位、原生工具写入与多轮状态试跑。完成一次真实 BF16 LoRA 更新及独立重新加载，但候选旧任务复测从 3/3 降到 0/3，未提升为接受版本。三个连续周期尚未完成；没有真实用户自进化或能力提升结论。云端可查看 [实测结果](experiments/workstation-rsi/measured_results.json)、[成功轨迹](experiments/workstation-rsi/examples/baseline-success.json)、[退化轨迹](experiments/workstation-rsi/examples/candidate-regression.json) 和 [训练候选](experiments/workstation-rsi/examples/training-candidate.json)。

CoEvo 是研究系统的建设仓库。被研究 Agent 的独立真实使用场景、交互来源、训练触发和周期反馈方式仍待确认。现有合成文件任务仅用于工程试跑，不能代替真实人机交互。参数训练仍是核心环节，外部适应和权重收益须分别评价。

研究文档入口为 [文档导航](docs/00_文档导航_v0.4.md)，开发约束见 [AGENTS.md](AGENTS.md)，工程约定见 [科研软件工作规范](docs/06_科研软件工作规范.md)。当前 v0.4 工作站 A→B→C→D 路线及 K/R/W/S、数据隔离协议保留，尚未把最新讨论写成正式设计决定。

源码采用 `src/coevo/`、`pyproject.toml` 和 `uv.lock`。本地组件包括真实模型接入、工具轨迹与结果记录、LoRA 训练、候选准入、版本状态和交互导出；完整用户产品与正式机制对照未完成。momo 接入复用其 Pi SDK，当前试点只支持指定文件 read/write；上游通用 CLI 和扩展没有完成验收。原始模拟训练/评价被禁用，补丁见 [momo-code-local.patch](patches/momo-code-local.patch)。

原始权重、源码归档、完整数据和产物留在 `/mnt/e/CoEvo/`，项目目录链接使用；活动代码、Python 环境与必要热副本在 Linux 文件系统。云端仅保存源码、协议、脱离私人材料的合成样例及结果摘要，不包含权重、凭据或本机环境。

CPU 检查与已有轨迹提取：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
.venv/bin/python -m coevo.extract --input artifacts/rsi-pilot/cycle-1 \
  --out data/exports/pilot-cycle-1 --origin synthetic-pilot
```

当前 6 项 CPU 检查通过。提取保留模型输入输出、可见思考、工具调用与返回以及失败状态，独立导出合法训练候选；此次 thinking 关闭，未记录思考内容。数据提取不会调用训练。周期入口在缺少用户训练产物时返回 `awaiting_user_training`；真实训练 CLI 仅供用户明确调用，暂停期间不执行。

环境复现依赖本机权重与上游源码，详见 [环境记录](experiments/workstation-rsi/environment_notes.md)。首次安装可用 `UV_CACHE_DIR="$PWD/.cache/uv-install" uv sync --locked`；该命令需要下载依赖，不是当前暂停状态下的必要操作。原始 [试跑计划](experiments/workstation-rsi/pilot_plan.md) 保留历史配方，不作为继续运行授权。

当前没有公开软件或模型 Release；项目许可证与第三方再分发范围尚未最终决定。
