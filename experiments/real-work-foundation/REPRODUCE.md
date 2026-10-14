# 2026-10-14 开发批次：证据与复现入口

此页整理先前分散在 `docs/监督覆盖对照与复现.md`、`docs/原生上下文与经验表示对照.md`、`docs/经验反馈修订对照.md` 的**操作入口**。科学结果以同目录的 JSON/阶段报告为准；此页不创建新实验、也不授权恢复运行。所有私人原文、工作目录、权重和详细请求保留在本地受控存储，不因仓库只有摘要而宣称可公开完全复现。

## 实验记录索引

| 开发实验 | 结果 | 原始记录 |
|---|---|---|
| 同轨迹局部/完整行为与 Replay 六组 | D 中 W0=6/16，同曝光组均 8/16；仅同族实例，单 seed | [配对评价](supervision-trial-results.json)、[训练参数](supervision-trial-training.json) |
| 新 L 池 SF / SU-proxy / SR 同池交叉重训 | 三组均 8/16，未晋升 | [训练](q3-selector-training.json)、[未来 D](q3-selector-results.json)、[零增量诊断](q3-zero-delta-control.json) |
| 原生续接/完整记录/自由笔记 | 11/12、11/12、7/12；无历史 7/12 | [表示对照](context-representation-results.json) |
| 仅自审与反馈驱动笔记修订 | 11/12、7/12；旧笔记 7/12、完整历史 11/12、无历史 5/12 | [笔记修订](note-revision-results.json) |

总记录与失败归因：[阶段更新](stage-update-2026-10-14.md)、[历史开发过程](progress.md)。所有对照均属 D/G 开发结果，非 H 或长期 RSI 证据；只有哈希族观察到局部参数改善。SU-proxy 不是已接受的 SU；后续不同模型的训练数据、来源和教师参与情况必须按记录分开。

## 复现说明（须另行授权后才执行）

入口均基于已存在的本地工作站配置、模型路径、实际 Pi 环境和私有 L/轨迹目录。不能直接用公开 JSON 摘要重建私人完整训练。冻结输入、目标 mask、原生模板、配置、源码快照和输出目录；已有运行目录不被静默覆盖。命令中的变量需由操作者根据已有本地产物设置，不能把占位符理解为有效路径。

~~~bash
PYTHONPATH=src python -m unittest discover -s tests -v
node --check scripts/pi-project-agent.mjs
~~~

**监督覆盖**：`coevo.supervision` 建立同 messages/tools 的 output-only/full/full-replay 目标与训练配额；`coevo.supervision_trial` 冻结及执行矩阵。same-exposure 不等于等监督 token，token-matched 不等于等计算。只对已核验 Assistant 行动/回答施加 loss，错误调用和工具结果只是上下文。最长训练样本按当时配置拒绝越界，不隐式截断。

~~~bash
PYTHONPATH=src "$COEVO_PYTHON" -m coevo.supervision_trial \
  --matrix "$COEVO_MATRIX" --config "$COEVO_CONFIG" --out "$COEVO_TRIAL"
# 仅在新授权、确认冻结和资源条件后执行：
PYTHONPATH=src "$COEVO_PYTHON" -m coevo.supervision_trial --out "$COEVO_TRIAL" --run
~~~

**同池选样**：`coevo.selector_trial` 从已核验候选文件构成共享池，SF、SU-proxy 与 SR 保持可追溯来源和预算，经过公共匹配算法从同一个 W0 训练。第一次容量拦截是失败历史，不用后来成功覆盖；最终三组 2340 监督 token、12 次更新，但上下文计算与选中源簇不同。

~~~bash
PYTHONPATH=src "$COEVO_PYTHON" -m coevo.selector_trial \
  --config "$COEVO_CONFIG" --cohort "$COEVO_COHORT" \
  --feedback "$COEVO_FEEDBACK" --updated "$COEVO_SELECTOR_ADAPTER" \
  --out "$COEVO_SELECTOR_TRIAL"
# 同上：仅在恢复研究并重新检查冻结输入后运行
PYTHONPATH=src "$COEVO_PYTHON" -m coevo.selector_trial --out "$COEVO_SELECTOR_TRIAL" --run
~~~

**原生/外部经历**：`coevo.context_trial` 直接 fork 真实 Pi 会话，并保留外部完整记录与模型自由笔记的对照。仅首轮请求 token 匹配，内容/角色与后续总计算不相等。SDK 预览在 HTTP 前中止，不计模型响应。

~~~bash
PYTHONPATH=src "$COEVO_PYTHON" -m coevo.context_trial \
  --config "$COEVO_CONFIG" --cohort "$COEVO_COHORT" \
  --feedback "$COEVO_FEEDBACK" --out "$COEVO_CONTEXT_OUT"
~~~

**反馈修订**：`coevo.note_revision` 在同一原生笔记会话上派生 self-review 与 feedback-review。反馈来源于已暴露的 D 任务，不含检查器答案；修订笔记属于 D、`train_authorized=false`，不得回填 L。

~~~bash
PYTHONPATH=src "$COEVO_PYTHON" -m coevo.note_revision \
  --config "$COEVO_CONFIG" --parent "$COEVO_CONTEXT_PARENT" \
  --out "$COEVO_REVISION_OUT"
~~~

这一批所有模型仍为原始 W0 接受版，当前阶段性暂停。旧复现说明如需逐字追溯，在[清理前 Git 固定快照](https://github.com/Yhyb24P/CoEvo/tree/960cabc9af8dd914f76e149866d7bef768bb6022/docs)中可读取；阶段报告和原结果未随说明迁移而更改。
