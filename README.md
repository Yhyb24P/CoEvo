# CoEvo

人机交互驱动的小模型 Agent 持续适应与参数学习研究。研究指令管理、可验证经验积累与选择性参数学习在可比较资源预算下的独立贡献、跨任务泛化和负迁移。

项目定位与助手约束见 [AGENTS.md](AGENTS.md)，工程工作方式见 [科研软件工作规范](docs/06_科研软件工作规范.md)，研究协议与实验记录模板见 [文档导航](docs/00_文档导航_v0.4.md)。工程以可追溯性为首要标准，以合理、充分且可维护为目标，按实际需求删减机制。

已建立研究协议、项目规则和记录模板，正在工作站阶段 A 建立 Python 包及依赖锁、下载上游源码与原始权重。尚无模型资格通过或训练收益结果；实际运行命令和产物随阶段推进补充，文档检查仅支持文档一致性。后续状态变化须附对应代码、测试或 run ID，不将合成样例成功写成泛化收益。

大量研究与开发在本机完成。RTX 5090 工作站是 A–C 的主实验平台，承担 Agent 推理、128K+ 资格、真实 LoRA 与周期 RSI；无独显、32 GB 内存笔记本可承担日常开发，最终部署验收后移到 D，当前用户要求暂不处理 D。基础模型与软件栈尚未最终确定，v0.4 中的具体配置为候选起点，实际状态需由运行证据确认。

当前采用 v0.4 实施修订 `workstation-128k-2026-10-13`：优先复用单一开源 Agent、任务运行器与检查器、本地训练组件，将主要开发投入用于经验管理、训练准入与选样、周期反馈。momo-code 为优先核查候选，Pi 为替代；Harbor 为评价复用候选，训练由独立 Transformers/PEFT 或 Unsloth 组件承担，均未完成本地验收。按 A 工作站环境与 128K+ 底座资格 → B 真实学习闭环 → C 至少三周期工作站 RSI → D 笔记本最终验收推进；先聚焦代码、文件和终端任务。闭环运行成功与科研收益分别记录，保留 K/R/W/S 对照及来源隔离。

当前已建立 `src/coevo/`、`scripts/`、`configs/`、`tests/` 和 `experiments/`，安装与真实后端验收进行中。实验配置、数据来源清单和结果报告应保留；原始私有数据、模型权重和大体积运行产物在版本控制外管理，并通过路径与哈希关联实验记录。

原始权重、上游源码归档、冷数据和运行产物放在 `/mnt/e/CoEvo/`，通过 `models/`、`upstream/`、`data/`、`artifacts/`、`runs/` 链接访问；活动代码和 Python 环境保留 Linux 文件系统。模型资格要求实际输入 128K+，短上下文诊断不能替代验收。实际运行入口随实现与运行结果在本文维护。正式实验使用 [冻结与运行记录模板](docs/05_实验记录模板_v0.4.md)，先核实来源隔离、完整配置快照及评价依据。

原创材料许可证、公开范围和引用署名尚未确定；第三方代码、数据与模型许可分别核查。当前没有公开软件或模型 Release。


工作站运行入口（依赖安装和原始权重下载完成后执行；实际阶段结果见 `experiments/workstation-rsi/`）：

```bash
UV_CACHE_DIR=/mnt/e/CoEvo/cache/uv uv sync --locked
bash scripts/serve_workstation.sh
# 在另一个终端运行真实 128K 资格；通过后停止该服务，再运行学习周期。
uv run --locked python -m coevo.qualification
uv run --locked python -m coevo.rsi --cycles 3 --out artifacts/rsi-pilot
```

CPU 契约检查入口为 `PYTHONPATH=src python3 -m unittest discover -s tests -v`。当前三项检查已通过，覆盖训练准入、错误目标排除、拒绝版本与持久化恢复；这些检查及 tokenizer 的131072 token 构造不证明 GPU 模型资格或学习收益。momo 的当前真实接口复用其现有 Pi 依赖并保存上游补丁，不运行原生模拟 fallback。试点范围和固定运行选择见 [工作站运行试点](experiments/workstation-rsi/pilot_plan.md)。

全流程入口为 `bash scripts/run_workstation_abc.sh`，顺序执行实际 A 资格和 B/C 三周期试点；不会处理 D。安装期间的活动解包缓存位于被忽略的 `.cache/uv-install/`，已完成缓存仍复用 E 盘内容。
