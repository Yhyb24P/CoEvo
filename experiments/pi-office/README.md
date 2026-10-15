# 独立 CoEvo / Pi 的 Office 任务

本路径保持 CoEvo 的独立执行和学习职责，运行器仍为 scripts/pi-project-agent.mjs。只吸收 PilotDeck 的 standalone spreadsheets Skill，不启动其 Gateway、CLI、桌面或记忆运行时。[PilotDeck 参考工作](../pilotdeck/reference-results.json)独立保留。

## 已取得的接口证据

已独立安装 `@earendil-works/pi-coding-agent@1.2.0` 到 `.cache/pi-1.2`，其 lockfile 留在本地，历史 1.1.0 环境不改写。任务明确要求 required_pi_version=1.2.0。实际 SDK 预览记录确认版本为 1.2.0、原生 loadSkillsFromDir 加载 spreadsheets，模型请求中出现对应 Skill 及任务内文件路径。预览由 onPayload 在 HTTP 发送前终止，completion=false、进程非零符合预期，不作为模型任务成功。

Skill 来源固定为 [PilotDeck@783499ff](https://github.com/OpenBMB/PilotDeck/tree/783499ffdb2d501bf590b2e035acd027a882df10) 的 skills/spreadsheets，保留 AGPL-3.0 LICENSE、原始文件哈希与适配后哈希。只将 Skill 根占位符和 PilotDeck 工作目录变量替换为任务工作区路径；其他指导及独立命令实现保持原样。选择范围为当前任务的 .skills/，不发现宿主全局技能。

独立命令 runtime 依原 package-lock 预安装在 `.cache/spreadsheets-skill-cache`，在任务沙箱中只读挂载到 /opt/skill-cache。实际沙箱执行 spreadsheet.sh check 退出 0，依赖就绪。此检查只确认环境，不替代真实工作簿修改、渲染或交付。任务运行时无网络、无宿主私人目录，也不授权安装依赖或修改技能。

## 真实完整任务

复用公开 CoEvo 实验记录和研究者准备的工作簿输入，仍属于 D 来源簇 coevo-research-workbook；不把更换运行器当作新 H 或学习收益。要求更新实验记录、保留历史、公式、样式和批注，并正确区分执行状态与科学结果。任务与外部检查器沿用 [参考输入与检查要求](../pilotdeck/README.md)，结果按实际工件核查。

```bash
PYTHONPATH=src .cache/task-env/bin/python -m coevo.pi_office --out NEW_RUN_DIR
```

此入口仅准备任务，保存 actor、来源、原始/适配 Skill 哈希、输入哈希、版本要求和原生请求。已准备的首次真实运行在 `/mnt/e/CoEvo/runs/pi-office/20261015-W0-workbook-v1`，本地 Qwen W0 服务就绪后复用 coevo.complete_work.run 执行，限制 30 分钟、100 次工具调用、每轮最多 32768 输出 token。原生请求、完整会话、实际版本/技能、结束分类、GPU 采样与工件留在本地；最终能力结果待独立检查。

正常结束只表示会话完成。有效部分可以成为经验或训练候选，但 D 身份、外部反馈和未经核实部分均保留，不自动写入持久经验或正向训练。
