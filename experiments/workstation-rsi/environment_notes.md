# 工作站环境记录（2026-10-13）

WSL Ubuntu 24.04，RTX 5090 D 32 GB。当前安装成功：Python 3.13、Torch 2.13.0+cu130、vLLM 0.31.0、Transformers 5.17.0、PEFT 0.21.2；GPU BF16 64×64 矩阵乘法实际返回 64.0。版本以 uv.lock 为准。

用户更新网络配置为 mirrored 模式、autoProxy=false，统一 HTTP 代理入口 http://127.0.0.1:28080；该入口访问 GitHub 实测 HTTP 200。18080 为 SOCKS 入口，不作为 HTTP 代理。localhost 模型服务绕过代理。

本次安装：PyPI 经过原代理约 300–400 KB/s；files.pythonhosted.org 直连 16 MB 实测约 0.7 秒，大体积 GPU 依赖随后约两分钟下载完成。仅本次包安装进程增加 PyPI 域名到 no_proxy，不修改系统网络或用户配置。HF 下载沿用现有认证位置，不覆盖 HF_HOME，原始权重固定版本已完成下载。

冷文件与权重在 /mnt/e/CoEvo，通过项目链接使用；活动 Python 环境、包解包缓存在 Linux 文件系统。跨盘缓存目录链接不能直接交给 uv 安装器：本次报 Not a directory，随后移除本地缓存链接并重取小包，安装完成，E 盘原缓存保留。

阶段 A/B 实测及当前暂停状态见 [云端研究快照](review_snapshot.md)。上述环境检查本身不证明能力提升。

模型首次加载成功，但 127.0.0.1:8000 的连接停留 SYN-SENT；18000 与 29871 的本地监听/连接实测正常。服务改用 127.0.0.1:18000，并从 endpoint 统一推导绑定地址/端口。未修改 Windows 或 WSL 防火墙。原失败服务日志保留在 artifacts/rsi-pilot/stage-A-port8000-failed.log。

9P 上强制预取比原始加载更慢，已撤回；原始版本仍在 E 盘，当前推理/训练另用 .cache/active-model/Qwen3.5-4B 活动副本以减少多周期随机读取。该副本不进入版本控制，原始版本与 coevo_source.json 一并保持。
