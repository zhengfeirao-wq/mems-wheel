# 测试入口：固件 0x21 + tactile500 0.3.0

一个 wheel 提供两种入口：Python 采集 API / CLI，以及 Windows 浏览器四板查看。
采集与原始录制保持每板实际 500 Hz 接收；查看约 10 Hz。

## 快速链接

1. **烧录工程**：[Tactile500.uvprojx](firmware_tactile500/Project/MDK/Tactile500.uvprojx)
2. **main.c**：[Source/main.c](firmware_tactile500/Source/main.c)
3. **按实物选 Target/HEX**：[四板烧录说明](firmware_tactile500/先读我_四板首次烧录.md)
4. **OSR256 固件与步骤**：[先读我_OSR256烧录.md](firmware_tactile500/烧录_OSR256_20260910/先读我_OSR256烧录.md)
5. **Python wheel**：[tactile500-0.3.0-py3-none-any.whl](upper_pyusb_500hz/wheelhouse/tactile500-0.3.0-py3-none-any.whl)
6. **启动与录制步骤**：[0.3.0 交付说明](upper_pyusb_500hz/docs/RELEASE_0_3_0.md)
7. **完整通信协议**：[PROTOCOL_V2.md](firmware_tactile500/docs/PROTOCOL_V2.md)

## 板型与 identity 对照

短线 = 新版，长线 = 旧版。左12、右12、左32短、右32短应分别显示 **08、09、0E、0F**。

| 板型 | identity | 帧长 |
|---|---|---|
| 左手 12 点 | `0x08` | 80 字节 |
| 右手 12 点 | `0x09` | 80 字节 |
| 左手 32 点短线 | `0x0E` | 180 字节 |
| 右手 32 点短线 | `0x0F` | 180 字节 |

## 在 G1 上启动

```bash
cd /home/agi/tactile500_release_20260910_03
.venv/bin/tactile500 scan
.venv/bin/tactile500 view --bind 0.0.0.0 --port 8875 --output-root captures
```

随后 Windows 打开 `http://<G1-IP>:8875`（把 `<G1-IP>` 换成机器人当前实际地址）。
也可执行上位机目录的[打开G1四板查看.ps1](upper_pyusb_500hz/打开G1四板查看.ps1)。
服务未启动时显示无法连接是正常的；无需重新安装或先运行旧版网页程序。

## 验收状态

四板模拟已测。实物测试结果与已知限制以仓库根目录
[README.md](README.md) 的「已知限制」章节为准，摘要：

- 每板约 500 Hz，序号缺口、稳态坏帧、USB 输入队列丢块、录制丢弃均为 **0**。
- `fresh_mask` 恒为 0（DRDY 取不到新转换证据），但各通道数值持续变化，数据有效。
- 左手 12 点板 ch6 存在 ±943718 偶发满量程跳变；软件校零无法解决。
