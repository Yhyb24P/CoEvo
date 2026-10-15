# 跨领域完整工作案例

这两个公开 GitHub 来源均为 D 开发案例，有预训练污染可能，不是封存泛化集。任务提示由研究者制定，Agent 自主选择实现和分析方法。源码、原始数据及原生交互留在本地；仓库只保存任务定义和复现入口。

## 软件维护

来源：[python-frontmatter](https://github.com/eyeseast/python-frontmatter)，MIT；固定提交 `d2977d71638cb451bc06f2af3bb48e09e0dbe8c6`。真实需求来自[问题 #96](https://github.com/eyeseast/python-frontmatter/issues/96)。工作包括定位元数据与构造参数冲突、跨 YAML/JSON/TOML 修复、保持 API 兼容、增加测试与文档、交付工作报告，详见 software-task.txt。

成果检查：在独立副本中，用原始冻结 tests/ 检查回归，再用 check-software.py 检查需求；另外运行模型提交的测试并审阅补丁、文档和报告。冻结测试不得由模型修改后替代。研究者检查脚本放在工作区外。基线实际运行已有 56 项上游测试通过；需求检查的三个格式均因 content 冲突报错，构造兼容检查通过，原始日志保存在本地 complete-work 运行目录。

## 科研分析

来源：[palmerpenguins](https://github.com/allisonhorst/palmerpenguins)，固定提交 `8957207b78d6ccd1b4654a9dd9c9041b657478ab`，数据 CC0。原始观测涵盖形态、性别、岛屿、年份和同位素；使用原始和简化两表。任务研究体重和同位素的 pooled/adjusted 关联，要求缺失审查、数据对应、统计不确定性、敏感性分析和可复现报告，详见 science-task.txt。

成果检查：在新副本删除 results/ 后离线执行 analysis.py，比较重建表格与报告；独立核对原始行数、缺失与分组数量、所用分析样本、主要估计和不确定性。审阅 species/island 重叠、重复个体和缺失处理是否影响结论，不能以图表存在或退出码代替科学判断。不规定唯一统计模型，不向 Agent 提供参考估计或答案。

## 共用入口与预算

下载两仓库到指定 sources 根目录，核对固定提交。复用既有 .cache/task-env（软件）与 .cache/mcm-env（科研）。在仓库根运行：

```bash
PYTHONPATH=src .cache/task-env/bin/python scripts/prepare-complete-work.py --case software --sources /mnt/e/CoEvo/data/complete-work-sources --out /mnt/e/CoEvo/runs/complete-work/NEW-software --environment .cache/task-env
PYTHONPATH=src .cache/mcm-env/bin/python scripts/prepare-complete-work.py --case science --sources /mnt/e/CoEvo/data/complete-work-sources --out /mnt/e/CoEvo/runs/complete-work/NEW-science --environment .cache/mcm-env
```

输出 workspace、输入哈希、task.json、原生 Pi agent_request.json 和实际模型配置。模型服务可用时，以 COEVO_REQUEST_FILE 指向请求文件，运行既有 scripts/pi-project-agent.mjs；运行前后记录服务、环境、源码和 GPU 使用。准备入口本身不启动模型服务。

共享实现为 src/coevo/complete_work.py，脚本只作薄入口。Qwen 配置为 configs/complete-work-qwen.json。服务就绪后 `PYTHONPATH=src .cache/task-env/bin/python -m coevo.complete_work run --out RUN_DIR` 记录实际原生 session、停止原因、token、工具及工件；它连接已有服务。服务版本/模板、模型修订和 GPU 实际采样仍随运行保存。独立复核入口为：

```bash
PYTHONPATH=src .cache/task-env/bin/python -m coevo.complete_work verify --out SOFTWARE_RUN_DIR --sources SOURCES_ROOT --environment .cache/task-env
PYTHONPATH=src .cache/mcm-env/bin/python -m coevo.complete_work verify --out SCIENCE_RUN_DIR --sources SOURCES_ROOT --environment .cache/mcm-env
```

复核副本和日志保存在各轮 review/，不改变 Agent 提交工作区；同一轮不覆盖既有复核。科研入口删除旧 results/ 后重建，并输出独立输入事实。自动证据与实质结论分开保存，具体复核和学习安排见[成果复核与后续学习](review-and-learning.md)。

底座条件见 [model-comparison.json](model-comparison.json)。Spark 官方模型配置为 Spark2_5ForCausalLM，工具解析 spark25；当前安装的 vLLM 0.31 注册表没有该原生实现，因此需对[官方插件](https://github.com/XHToken/Spark-plugin)进行实际接入，而不是直接更换模型路径。已核对官方 metadata 和推荐采样，候选准备状态与真实资格结果分开记录。

每模型每任务 45 分钟、100 次工具调用、每轮最多 32768 输出 token，bash 单次最多 120 秒；上下文采用服务实际容量，保持原生会话，不启用压缩。两模型各从相同初始文件开始，使用各自原生模板/解析和推荐采样，公开差异。首轮两模型两任务至多 3 小时任务时间，服务启动另记。预计单项 20–45 分钟，运行时采用预计完成时间休眠，而非循环轮询。预算中止和无效重复保护不算模型恢复成功。

Q1 比较未来完整工作中原始经历/提炼经验的帮助；Q2 可采用本轮经核实的有效部分和纠错作为候选，保留辅助来源；Q3 记录 Agent 自主提出的工作方法，在另一来源的未来任务检验。两个初始案例只能建立能力与材料基础，不能单独证明长期学习。后续交互与训练许可按实际授权记录，不从数据公开自动推导。

## 首轮 W0 实际结果

用户确认后，使用 main@f965d66 顺序执行两项原生 thinking 工作，总任务时间 52.4 分钟。结果见 [first-W0-results.json](first-W0-results.json)。软件任务 27.3 分钟后触发 100 次工具额度：冻结上游 56 项通过，但 handler 元数据仍冲突，新测试因重复 content 关键字无法收集，也没有工作报告。记录的计数器为 101，包含触发额度保护的调用尝试，不等于执行了 101 次有效工具操作。

科研任务 25.1 分钟、69 次工具调用，正常结束，生成源码、报告、图和统计表。独立清空结果复跑成功，结果字节一致；原始数据未改变。独立重算确认 324 个完整样本、体重分组均值和报告的 OLS 系数/R²。实质复核发现，观测分位数被标为均值置信区间，各组自身协变量下的拟合均值被称为共同条件调整均值，同位素缺失并集实际为 14 人而非报告的 27 人，重复编号也不足以确认同一个体。岛屿调整、同位素调整与采样敏感性仍不充分。因此它提供可验证的部分工作，不能算完整科学交付。
