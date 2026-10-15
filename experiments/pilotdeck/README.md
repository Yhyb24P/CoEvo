# PilotDeck 独立参考执行与证据提取

本目录是 PilotDeck 自身原生 CLI 的隔离评估与素材来源，**不是 CoEvo 主框架迁移**；相关已发生任务和本地记录保持事实身份，不因架构决定改变而重写。CoEvo 的原生 Pi 执行器与 RSI 学习主体保持独立。\n\n固定上游 [OpenBMB/PilotDeck@783499ff](https://github.com/OpenBMB/PilotDeck/tree/783499ffdb2d501bf590b2e035acd027a882df10)，许可证 AGPL-3.0，保留上游 LICENSE。冷源码在 `/mnt/e/CoEvo/upstream/PilotDeck`，活动源码归档在 `.cache/pilotdeck`；不提交上游代码与 node_modules。

## 已完成的本机准备

按上游锁文件安装 Node 22.23.3、pnpm 10.32.1 和所选 workspace 依赖。Node 官方二进制经 SHA256 校验，归档与校验记录保存在 `/mnt/e/CoEvo/cache/pilotdeck-runtime/`。源码检出及归档需设置 `GIT_LFS_SKIP_SMUDGE=1`，演示媒体不是任务依赖。

默认完整 build 会下载桌面 computer-use 驱动，本轮停止这部分构建，采用上游已有的 tsx 源码 CLI 入口；不声称桌面或完整发行构建成功。上游 memory-core 构建已完成。针对实际接点的 9 项上游 reasoning/Transcript 测试通过；CoEvo 的 2 项提取回归通过。本地模型配置 `configs/pilotdeck-local.yaml` 已由上游 loadPilotConfig 实际解析，diagnostics 为空。

本地模型仅配置 Qwen W0/vLLM，使用上游 qwen-local thinking 与 extraBody；关闭路由、自动委派、云端遥测及首轮持久经验，保持各自归因。首次任务通过原生 CLI/Workspace/Skills/Transcript 执行，不增加另一个 Agent Loop。`coevo.pilotdeck.cli_command` 只复用既有 bwrap 文件边界，额外挂载只读应用和 Node，以及本轮独立 PilotHome；网络命名空间共享以连接本地 vLLM，因此它不是网络断开的环境。任务明确禁止外部网络，原生联网和委派工具关闭/拒绝。宿主私人目录及凭据不挂载，代理环境不继承。

## 首个完整文件任务

实际资料来自两项 CoEvo W0 实验公开结果，研究者据此准备初始 XLSX 模板：更新实验账本，保留历史行、原有公式、样式、批注和说明表，区分正常结束、可复现、需求通过和科学交付。它是根据真实研究资料构造的办公任务，不冒称用户曾维护的历史工作簿。Agent 应自主查看原生 spreadsheets Skill、编辑副本并核对交付。单项资源上限 30 分钟，保留完整原生会话与文件检查点。

原始输入、独立 PilotHome 和运行产物放在忽略目录 `/mnt/e/CoEvo/runs/pilotdeck/20261015-research-workbook-v1/`。Python 文件环境为 `.cache/pilotdeck-office-env`，实际安装 openpyxl 3.1.5、et-xmlfile 2.0.0。成果应由工作簿内容、公式与未请求修改部分的保留检查确认，不能由 CLI 退出状态代替。

初次 CLI 启动暴露项目未登记与退出句柄未释放的问题，尚未进入模型工具工作；原始日志保留在 v1。薄封装 scripts/pilotdeck-task.mjs 使用原生路径函数建立本轮项目登记，调用原生 CliChannel，并在结束时调用原生 dispose；没有新增 Agent Loop 或修改模型/记忆路由。修正后的实际工作在 `20261015-research-workbook-v2`，保留相同输入重新执行，原生 thinking 流和工具执行随后实际成立。

实际参考结果见 [reference-results.json](reference-results.json)：首次工作 97.5 秒、11 次工具调用，数值与保留项通过检查，但结果标签及预算备注不完整。第一次原生反馈续接修正标签，仍遗漏一条备注；第二次补充反馈后备注正确，却清空原本正确的秒数、工具计数和停止字段。因此三次均不计完整任务成功。原始来源文件保持未变。首轮与续接的原生历史前缀一致，没有用研究者摘要替换会话。

这段经历保留作独立 RSI 系统的参考材料：有效部分、外部反馈后的修订、局部修订损坏已正确内容，以及研究者要求后产生的核对方法建议。方法建议尚未验证，不计自主提出或跨任务经验收益。后续不再围绕这套完整运行器增加生产功能；主要执行回到 CoEvo/Pi，选择性吸收独立 Office Skill。

可复用输入为 [fixtures/research-ledger.xlsx](fixtures/research-ledger.xlsx)、[任务要求](workbook-task.txt)及 [公开结果 JSON](../complete-work/first-W0-results.json)。将它们复制到独立 RUN_DIR 的 workspace/，将本地配置及仅授权本轮工具的 permissions.json 放入独立 pilot-home/，prompt.txt 保存任务要求。运行入口：

```bash
PYTHONPATH=src .venv/bin/python -m coevo.pilotdeck --run --out RUN_DIR --application .cache/pilotdeck --node-root NODE22_ROOT --environment .cache/pilotdeck-office-env --start-server --timeout 1800
```

该入口管理本轮进程和可选的本地 vLLM 服务，保存实际资源、原生 Transcript 和待复核片段。它不启动服务器 UI、桌面和后台自动任务。工作簿独立检查器在 Agent 工作区外：

```bash
.cache/pilotdeck-office-env/bin/python experiments/pilotdeck/check-workbook.py --original experiments/pilotdeck/fixtures/research-ledger.xlsx --submitted RUN_DIR/workspace/updated-research-ledger.xlsx --results experiments/complete-work/first-W0-results.json
```

检查数值、公式和未授权区域保留，输出实际状态与待审阅的语义要求；图形界面、Excel 实际重算和最终任务语义不由此自动确认。

## 接入 CoEvo 学习材料

```bash
PYTHONPATH=src .cache/task-env/bin/python -m coevo.pilotdeck --transcript NATIVE_JSONL --out NEW_LOCAL_EVIDENCE --source-cluster coevo-research-workbook --split D
```

入口只读取明确指定的一份原生 Transcript，保留原始字节、来源哈希、会话/轮次、工具调用与返回、文件及恢复边界；不扫描私人全局会话。不自动读取持久化工具输出引用所指向的其他文件。工具未报错、正常 turn_result 和文件存在不自动成为正向监督，导出的片段均待实质核实。控制/恢复边界保持原样，不把整个日志假装成当前有效会话分支。有效部分成果和纠错经历核实后，继续复用现有经验与训练代码。

## 技术吸收边界

后续优先挑选经任务需要证明有用的 Office Skills、源文件保真与会话/记忆方法，在 CoEvo 原生环境集成。Pi SDK 已支持通过明确工作区 `skill_dir` 选择原生 Skills，不要求把 PilotDeck Gateway 搬入 CoEvo。原生 PilotDeck 的 JSONL 与 Pi 的原生会话不能未经来源映射就拼成同一训练轨迹。对具体 PilotDeck 代码/脚本的复制及分发，应核查 AGPL-3.0 与相关文件的单独许可证；仅借鉴思想与复制实现不同。任何新研究收益以真实未来工作结果而非 CLI 引导、安装或技术复刻数量判断。
