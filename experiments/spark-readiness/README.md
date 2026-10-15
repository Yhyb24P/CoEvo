# Spark-X2.5-4B 接入与完整办公任务对照

2026-10-15 实测。[受控结果](measured-results.json)记录来源、有效预算、成本与工件核验；完整原生会话和请求保存在本地 `/mnt/e/CoEvo/runs/spark-readiness/20261015-office-models-v2`。这是既有 MCM D 来源的同题开发比较，不能视为独立迁移或参数学习证据。

## 实际结果

| 模型 | 执行耗时（单调时钟） | 工具调用 / 错误 | 实际交付与停止 |
| --- | --- | --- | --- |
| Spark-X2.5-4B | 1183.3 秒 | 23 / 8 | 无要求的交付文件；末次输出长度截断 |
| Qwen3.5-4B W0 | 1397.0 秒 | 63 / 12 | 全部 1435 条清理记录正确；缺工作簿和报告，期限停止 |

Spark 成功完成真实模型加载、原生 thinking 与工具交互，但在数据检查后转向工作簿内部关系及批注位置的反复推敲，没有进入完整交付。末次请求实际输入 126414、输出额度 8735，服务容量 139264；请求配额合法，但输出截断。精确计数防止请求溢出，不保证复杂工作完成。

Qwen 克服了部分读取和类型错误，保存了 `.work/olympic/prepare_audit.py` 和正确的 `clean_medals.csv`。Agent 末次修订未实际执行；在独立干净副本使用原始输入复跑，脚本生成正确清理表后，因 `summary_data` 未定义退出，仍无最终工作簿和报告。不能把保存源码追认为成功交付。

两组原始数据、模板与技能文件均未变。现有证据支持保留 Qwen W0 为接受底座，并保留 Spark 的候选身份；这一单题结果不支持模型通用优劣判断。后续学习可以利用核实的部分成果和真实纠错，但本次 D 轨迹不自动变成训练或永久经验来源。

## 比较条件与预算解释

两组使用同一份[完整任务](../olympic-office/task.txt)、三个 CSV、初始工作簿、Pi 1.2.0、spreadsheets Skill、离线工具与权限；初始文件哈希一致，均为全新原生会话。依次执行 Spark、Qwen，使用各自原生模板/工具解析器和官方推荐范围内的采样配置，因此同时改变了模型与其推理策略。

**实际请求预算均为 25 分钟、80 次工具调用、每轮最多 32768 输出 token、139264 上下文，关闭压缩。** 通用模型配置的 45 分钟/100 次被任务入口覆盖，不能用它解释本次结果。每次使用同一服务 `/tokenize` 分配可用输出，既有 SDK 更低的输出额度仍被保留。累计 API 输入分别为 1551497 / 2658113，输出为 75744 / 49358；反复携带历史不等于新增独立信息，API 零计价也不等于资源零成本。

本次执行的墙上时钟与单调时钟并不一致：Spark 为 1296.903 / 1182.293 秒，Qwen 为 1541.907 / 1396.527 秒（后者分别为适配器内部记录）。保护逻辑使用两者较大的已过时间，因此 Qwen 单调时钟未满 1500 秒也会按期限停止。不能据此给出严格速度排名。

## 来源及必要兼容修订

- 模型：[XHToken/Spark-X2.5-4B](https://huggingface.co/XHToken/Spark-X2.5-4B/tree/0bcb35678590218655dff3765b9e61c83b35e9c4)，固定 revision `0bcb35678590218655dff3765b9e61c83b35e9c4`。五个 BF16 权重分片共 8224192408 字节，下载约 678 秒，分片大小与该 revision 元数据一致。
- 原生 vLLM 插件：[XHToken/Spark-plugin](https://github.com/XHToken/Spark-plugin/tree/3e1040e63a5907e4c748a485d6795d739dcd5bd6)，固定 `3e1040e63a5907e4c748a485d6795d739dcd5bd6`。原件保留，使用单独兼容副本。
- 当前环境为 vLLM 0.31.0、Transformers 5.17.0、Torch 2.13.0。只安装插件，不改变这些核心依赖。

官方插件的目标 vLLM 版本与本地不同。[补丁](plugin-vllm031.patch)处理三处接口差异：协议类型导入路径、Transformers 在分层 RoPE 中混入标量默认项、AutoWeightsLoader 已移除的 skip_prefixes 参数。最后一项在真实 GPU 首次加载时才暴露；首次失败位于本地 `20261015-office-models-v1`，任务尚未启动，日志保留。新副本保持上游模型层类型及原有 RoPE 数值，权重共享时先过滤 lm_head 再加载。这些是接口兼容改动，跨后端数值一致性仍待验证。

插件的两项官方 smoke 测试函数、配置构造及模型实现导入通过；随后完整任务验证了真实 GPU 执行。当前 `.venv` 无 pytest，这两项函数通过标准库直接调用，不表述为 pytest 全套通过。当前插件 `supports_lora` 为 false，原始 HF 配置在现有 Transformers 下也存在 RoPE 兼容问题。现有 LoRA 训练/回载路径对 Spark 尚需验证，这不等于模型不能训练。

## 本地复现

模型放于 `.cache/active-model/Spark-X2.5-4B`（可为符号链接），保留固定 revision 的配置、分词器、自定义源码与原生模板。插件原始副本之外另建兼容工作目录，在其中应用补丁并安装：

```bash
git -C PLUGIN_COMPAT_DIR apply /ABS/CoEvo/experiments/spark-readiness/plugin-vllm031.patch
uv pip install --python .venv/bin/python --no-deps -e PLUGIN_COMPAT_DIR
```

[模型配置](../../configs/complete-work-spark.json)显式选择官方模板、spark25 工具解析、qwen3 reasoning 和远程代码；不能沿用 Qwen 的工具协议。准备器复用既有 Office Skill 和任务环境缓存，要求 `.cache/pilotdeck`、`.cache/pi-1.2`、`.cache/pilotdeck-office-env`、`.cache/spreadsheets-skill-cache` 已按[原生 Office 记录](../pi-office/README.md)建立。Qwen 权重使用现有接受底座路径。

```bash
PYTHONPATH=src .cache/pilotdeck-office-env/bin/python experiments/spark-readiness/prepare-comparison.py \
  --data DATA_DIR --out NEW_COMPARISON_DIR
PYTHONPATH=src .venv/bin/python experiments/spark-readiness/run-comparison.py --out NEW_COMPARISON_DIR
```

第二条命令实际使用 GPU，按 Spark、Qwen 顺序管理服务和执行任务；端口已占用或已有运行证据时拒绝覆盖。运行器保留加载日志、请求、原生会话、工具观察、成本、GPU 采样及文件检查。检查器不代替内容审阅；模型保存的最终源码须在独立副本复跑。源码复用模板生成函数，仅为准备相同完整任务，不引入新的微型研究任务。

## 原生轨迹复核：执行为何未收敛（2026-10-15）

本节依据本地两组完整 transcript、全部工具调用与观察、六个 Qwen 脚本版本和既有独立复跑，补充行为分析。原始轨迹哈希见 measured-results.json；下述消息编号为 transcript.messages 的零基索引，工具序号从 1 开始。分析产生于运行后，不改变原任务结果。

**Spark：探索产生了一些正确事实，但没有转为可执行交付。** 工具 9 的表头当数字、工具 10 的不可哈希列表等错误后，工具 11 继续完成奖牌检查；项目表读取失败后也改变了读取与列名处理。工具 20 的观察已列出各年份项目数与逐项求和一致，说明它能纠正部分处理错误，不能概括为始终无效循环。工具 13–15、21–23 集中检查 XLSX 内部结构、批注和关系；工具 22 已确认 Summary 的 F7 批注往返保存不变，但它继续追查 Archive!B2 与 Summary!B2 的归属，消耗剩余额度。

末条 assistant（消息 45）输出 8735 token 后截断，仍未发出写入。其内容从批注疑问转向脚本、Quality 和报告的规划，并包含正确的 2020/2024 项目数。因此，“一直卡在批注”过于简化；可观察的失败是知道部分事实、反复规划交付，却没有把方案落实为要求的文件。计划中的数值也并非全对，不能把未运行的构想当作有效部分成果。

**Qwen：有实施与局部纠错，但修订成本高，调试没有走到末端。** 工具 17 就保存首版脚本；工具 18 暴露缺少 numpy，随后移除依赖再运行。其后在项目表的历史脚注上停留：工具 26–28、32、34 先后遇到 `0[s3]` 转整数错误，中间多次检查相同来源而未修复对应解析。最终能替换该脚注、处理冬奥注释并继续运行，但这段工作没有及时聚焦本次实际需要的 2020/2024 汇总。

六次 write 对应消息 27、31、55、101、115、119，分别输出约 484–494 行完整脚本。这六次 assistant 响应合计 36714 / 49358 输出 token（约 74.4%，含响应内其他内容），说明大规模重写占据了主要输出成本；它不是精确的脚本字符 token 占比。首版已有 `summary_data` 的未定义引用，六版均保留。模型实际执行被解析、依赖和深复制错误依次挡住，因此直到研究者独立复跑最后版本才暴露该引用。工具 62 因 deepcopy 工作簿失败后，工具 63 保存修订；紧接着期限保护终止，末版没有被 Agent 执行或验证。

**共同解释与限制。** 两组都没有形成“生成一份可运行的端到端交付，再据实际检查修订”的稳定工作节奏；Spark 偏向长时间探索/规划，Qwen 则偏向全量改写和局部报错追逐。这是轨迹支持的行为描述。不能仅凭这次运行确定其根因是模型规模、thinking 配置、Skill 内容、长历史还是期限，也不能断言延长预算必然成功。Qwen 的 1435 行清理能力在此前同题 R0 已被观察，本轮是重复观察，不是学习提升。

**研究取舍。** 当前不优先投入 Spark 训练适配，也不把同题继续修到成功作为下一项研究成果。转向[不同来源的完整工作](../bike-sharing/README.md)，以成果、可运行源码和真实反馈观察能否恢复并收敛。这里提炼的工作方式只是研究者候选解释，尚未成为 Agent 自主习得的策略、持久经验或训练样本；本轮仍为 D、train_authorized=false。

对应提交 aae5a2c 的 [GitHub CI 已通过](https://github.com/Yhyb24P/CoEvo/actions/runs/38698795357)；它确认工程回归，与上述任务失败分别记录。
