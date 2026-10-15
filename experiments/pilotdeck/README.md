# PilotDeck 接入

固定上游 [OpenBMB/PilotDeck@783499ff](https://github.com/OpenBMB/PilotDeck/tree/783499ffdb2d501bf590b2e035acd027a882df10)，许可证 AGPL-3.0，保留上游 LICENSE。冷源码在 `/mnt/e/CoEvo/upstream/PilotDeck`，活动源码归档在 `.cache/pilotdeck`；不提交上游代码与 node_modules。

## 已完成的本机准备

按上游锁文件安装 Node 22.23.3、pnpm 10.32.1 和所选 workspace 依赖。Node 官方二进制经 SHA256 校验，归档与校验记录保存在 `/mnt/e/CoEvo/cache/pilotdeck-runtime/`。源码检出及归档需设置 `GIT_LFS_SKIP_SMUDGE=1`，演示媒体不是任务依赖。

默认完整 build 会下载桌面 computer-use 驱动，本轮停止这部分构建，采用上游已有的 tsx 源码 CLI 入口；不声称桌面或完整发行构建成功。上游 memory-core 构建已完成。针对实际接点的 9 项上游 reasoning/Transcript 测试通过；CoEvo 的 2 项提取回归通过。本地模型配置 `configs/pilotdeck-local.yaml` 已由上游 loadPilotConfig 实际解析，diagnostics 为空。

本地模型仅配置 Qwen W0/vLLM，使用上游 qwen-local thinking 与 extraBody；关闭路由、自动委派、云端遥测及首轮持久经验，保持各自归因。首次任务通过原生 CLI/Workspace/Skills/Transcript 执行，不增加另一个 Agent Loop。`coevo.pilotdeck.cli_command` 只复用既有 bwrap 文件边界，额外挂载只读应用和 Node，以及本轮独立 PilotHome；网络命名空间共享以连接本地 vLLM，因此它不是网络断开的环境。任务明确禁止外部网络，原生联网和委派工具关闭/拒绝。宿主私人目录及凭据不挂载，代理环境不继承。

## 首个完整文件任务

实际资料来自两项 CoEvo W0 实验公开结果，研究者据此准备初始 XLSX 模板：更新实验账本，保留历史行、原有公式、样式、批注和说明表，区分正常结束、可复现、需求通过和科学交付。它是根据真实研究资料构造的办公任务，不冒称用户曾维护的历史工作簿。Agent 应自主查看原生 spreadsheets Skill、编辑副本并核对交付。单项资源上限 30 分钟，保留完整原生会话与文件检查点。

原始输入、独立 PilotHome 和运行产物放在忽略目录 `/mnt/e/CoEvo/runs/pilotdeck/20261015-research-workbook-v1/`。Python 文件环境为 `.cache/pilotdeck-office-env`，实际安装 openpyxl 3.1.5、et-xmlfile 2.0.0。成果应由工作簿内容、公式与未请求修改部分的保留检查确认，不能由 CLI 退出状态代替。

## 接入 CoEvo 学习材料

```bash
PYTHONPATH=src .cache/task-env/bin/python -m coevo.pilotdeck --transcript NATIVE_JSONL --out NEW_LOCAL_EVIDENCE --source-cluster coevo-research-workbook --split D
```

入口只读取明确指定的一份原生 Transcript，保留原始字节、来源哈希、会话/轮次、工具调用与返回、文件及恢复边界；不扫描私人全局会话。不自动读取持久化工具输出引用所指向的其他文件。工具未报错、正常 turn_result 和文件存在不自动成为正向监督，导出的片段均待实质核实。控制/恢复边界保持原样，不把整个日志假装成当前有效会话分支。有效部分成果和纠错经历核实后，继续复用现有经验与训练代码。
