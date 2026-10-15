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

此入口仅准备任务，保存 actor、来源、原始/适配 Skill 哈希、输入哈希、版本要求和原生请求。已准备的首次真实运行在 `/mnt/e/CoEvo/runs/pi-office/20261015-W0-workbook-v1`，本地 Qwen W0 服务就绪后复用 coevo.complete_work.run 执行，限制 30 分钟、100 次工具调用、每轮最多 32768 输出 token。原生请求、完整会话、实际版本/技能、结束分类、GPU 采样与工件留在本地；实测结果见下节。

正常结束只表示会话完成。有效部分可以成为经验或训练候选，但 D 身份、外部反馈和未经核实部分均保留，不自动写入持久经验或正向训练。

## 2026-10-15 实测与学习材料

受控汇总见 [measured-results.json](measured-results.json)。三段运行合计约 17.7 分钟：

| 运行 | 时间 / 工具调用 | 独立结果 |
| --- | --- | --- |
| 首次执行 | 951.3 秒 / 26 | 写错列并覆盖任务名；末轮思考耗尽 32768 输出 token，length 结束，任务失败 |
| 原生反馈续接 | 82.4 秒 / 8 | 读取 Skill 正文、修复工作簿，结构与语义核查通过 |
| 经验候选提炼 | 28.0 秒 / 3 | 笔记已生成，但含事实错误，未准入持久经验 |

续接从首轮末次工具结果节点 `329702c0` 分叉，保留 56 个会话条目，原始源文件未变、原生前缀相同。研究者指出实际错列与路径问题，没有代写修复代码；同时明确模型工作目录 `/workspace`。因此不能把改善单独归因于反馈或 Skill：路径提示和 Skill 正文读取也发生了变化。首轮末次输入 16436 token、输出 32768 token，证据指向单轮思考输出耗尽，而非上下文硬容量。

修复结果正确保留原始历史、公式、样式、批注与工作表结构，Software-W0 标为 failed、Science-W0 标为 reproducible partial；Notes 保留工具预算触发及统计问题，时长合计 52.3788569 分钟。检查覆盖文件状态与内容；未据此声称完成 Excel 图形界面或公式引擎重算。原始输入保持不变。

模型经验笔记错误地称原始 770.5 是字符串、iter_rows 返回对象无法识别列，又称任务未涉及样式批注；实际输入和 openpyxl Cell 对象均反驳这些说法。正确交付不保证反思正确，该候选仅保留为待修订材料。

原始请求、API payload、原生会话、工具结果、可见思考及工件在本地运行目录保留；三段交互按原始消息索引规范化，保留 D、辅助来源和训练未授权标记。反馈运行的旧执行摘要错误包含父会话成本并标记无辅助，修正解释另存 execution-reviewed.json；公开汇总采用新消息成本，不改写原始记录。

工程回归：80 项 Python 测试运行，4 项跳过，其余通过；Pi 适配器 JavaScript 语法与四项纯单元检查通过。这些是工程证据，经验迁移仍须后续完整任务检验。

## 从真实会话准备学习对照（2026-10-15）

[准备结果](learning-preparation.json)来自已核实的反馈修复：选取原生 Skill 读取、工作簿修复及最终数据检查三个实际工具调用。修复与检查命令在独立的原始状态副本中原样重放；输出行、公式及保真检查与已接受工件一致，其他文件未变。错误经验笔记与最终自述不在所选目标内。

[prepare-learning.py](prepare-learning.py)从相邻的实际 API 请求获取当时可见上下文、助手调用和工具返回，要求前缀与工具定义不变；不靠人工摘要或用未来工具结果重建提示。原始思考保留在本地原生上下文中。离线归一化补齐 vLLM 实际使用的 reasoning → reasoning_content 映射，三个目标提示的 token 数分别与实测 13672、15533、18567 一致；计数一致是必要校验，不单独作为整个服务逐 token 等价的证明。

同一 canonical 序列共 19243 token，两个 mask 的输入 token IDs 完全相同：output-only 仅监督正确修复，1031 token；reviewed-turns 再加入读取与检查，1749 token。监督区域覆盖所选助手动作，不覆盖工具观察、历史失败和未经核实的思考；这不是完整行为或思考链 SFT，也未匹配监督 token 总量。完整原生思考作为可追溯来源保留，可进一步研究其适用的学习方式。

复现准备（使用已有本地证据，输出必须为新目录）：

```bash
PYTHONPATH=src .venv/bin/python experiments/pi-office/prepare-learning.py --run FEEDBACK_RUN_DIR --out NEW_PREPARATION_DIR
```

脚本固定选择本次已核实调用，属于历史来源的学习准备，不是通用任务运行器。完整上下文和重放文件留在本地，仓库保存受控汇总。它继续继承 D 与反馈辅助身份，不通过修改来源标记绕开现有训练准入；下一轮参数研究还需要明确开发训练用途，并将后续任务评价与这些来源区分。

工程验证：84 项标准库测试运行，4 项因环境跳过，其余通过；另在本地冻结 tokenizer 环境执行两项真实模板检查通过，包括“思考保留在输入、动作 mask 不监督思考”的回归。
