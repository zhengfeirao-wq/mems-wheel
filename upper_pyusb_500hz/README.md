# Tactile500 V2 PyUSB 上位机（0.3.0）

**入口：[安装、接口示例与已知边界](docs/API_AND_INTEGRATION.md)。0.3.0 交付说明见
[docs/RELEASE_0_3_0.md](docs/RELEASE_0_3_0.md)。OSR256 在固件侧设置，原始 wheel 未重打包。
USB 重新枚举后需重启采集服务恢复；真实 Hub 热插拔尚不能承诺全部自动恢复。**

面向 G1 Ubuntu / Python 3.10 的四板触觉采集库。仅通过 PyUSB + libusb 访问 CH340
（VID `1a86` / PID `7523`），不依赖 ttyUSB、pyserial 或 ch341 内核模块。

**今晚测试入口：[四板查看与 wheel 交付](docs/RELEASE_0_3_0.md)。**
同一 wheel 提供 Python API、命令行原始采集，以及可选的 Windows 浏览器四板界面。
界面以10Hz读取缓存，原始采集和录制按板卡实际帧率运行。未启动 view 时不启动HTTP线程。

当前协议：`A5 5A` V2，12 路 80 字节，32 路 180 字节。旧 `BT` 数据不能直接混入 V2。
V2 修订 `0x21` 修复了 APM32F402 普通 DMA 通道未关闭导致的约 125Hz 发送问题。
配套固件在相邻目录 `嵌入式代码/Applications/Tactile500`。

## 安装与运行

这是 `py3-none-any.whl`，可安装到 Ubuntu aarch64；机器需要已有 `libusb-1.0`。
高速读取在 PyUSB 已打开的 libusb1 后端上预提交 32 个异步 Bulk IN 请求，避免 Python
解析期间没有在途 USB 请求。此适配层使用 PyUSB 内部结构，依赖固定为 `pyusb==1.3.1`。
升级 PyUSB 前须重新验证该适配层；同步 PyUSB 读取可用 `TactileSystem(usb_io="sync")`
作诊断对照。本次性能验证针对 Ubuntu aarch64，未验证 Windows USB 后端。
本次 G1 实机已确认 libusb 可用、CH340 未绑定内核驱动、普通用户有 USB 访问权限。
不要覆盖现有机器人应用的虚拟环境。示例在一个新目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheelhouse tactile500==0.3.0
.venv/bin/tactile500 scan
.venv/bin/tactile500 probe --seconds 30
.venv/bin/tactile500 capture --seconds 1800 --output captures/run001
.venv/bin/tactile500 inspect captures/run001
# G1 上运行，Windows 访问 G1 当前地址的8875端口：
.venv/bin/tactile500 view --bind 0.0.0.0 --port 8875 --output-root captures
# 无实物时的四板模拟，界面明确标示模拟数据：
.venv/bin/tactile500 view --simulate
```

`wheelhouse/` 同时提供本库和 PyUSB wheel。`scan` 只枚举；`probe/capture` 会配置
CH340 的 921600 8N1 和 DTR/RTS，然后读 Bulk IN，不向 MCU 发送启动或控制命令。
采集目录必须不存在，以防覆盖历史数据。Ctrl+C 会停止读取并排空录制队列。

若系统已有内核驱动或另一程序占用接口，本库报告该设备错误并持续重试，其他板继续工作。
权限配置属于实际操作系统部署事项；无需安装串口驱动，不自动抢占接口或复位 USB Hub。

## 接入大系统

原始帧订阅保持板子的真实发送频率。所有数组默认都是**固件已经排列好的通道顺序**。

```python
from tactile500 import TactileSystem

system = TactileSystem()
native = system.subscribe(capacity=8192)
system.open()
try:
    while True:
        item = native.get(timeout=1.0)
        frame = item.frame
        # frame.role: left_fingers / right_fingers / left_palm / right_palm
        consume(frame.role, frame.sequence, frame.sample_time_us,
                frame.temperature, frame.pressure, frame.fresh_mask,
                item.host_read_end_ns)
finally:
    system.close()
    native.close()
```

上层需要同一时刻的四板快照时：

```python
from tactile500 import TactileSystem

with TactileSystem() as system:
    for snapshot in system.snapshots(hz=500, delay_seconds=0.004):
        for role, slot in snapshot.slots.items():
            # state: updated / reused / stale / missing / offline / ambiguous
            if slot.value is not None:
                consume_snapshot(snapshot.target_ns, role, slot.state,
                                 slot.value.frame, slot.age_ns)
```

快照采用同一主机单调时钟，挑选目标时刻之前最近收到的帧，不插值、不用未来数据。
慢消费者跳过过期快照，`skipped_ticks` 记录跳过数量，不补发密集的历史快照。
`receive_skew_ns` 是选中帧的主机接收时间差，不是 ADC 采样同时性的证明。
MCU 的时间戳各自从上电开始，不能直接跨板相减；本版本没有 MCU 接收启动命令，
因此软件不能让独立 MCU 的 ADC 硬件同时启动。4ms 的快照延迟提供选择缓冲，
不能消除 USB 调度抖动或传感器自身转换相位差。

`frame.temperature` 单位为 0.1°C；`frame.pressure` 保留旧固件的有符号 `raw * 9 / 80`
尺度，未经额外标定不称为 Pa 或 N。`fresh_mask` 仅表示读取前看到了 DRDY 且读取成功。
实测修订 0x21 的连续 DAC 模式能读到变化数值，但 DRDY 始终为 0，因此该位当前无法证明
每个通道 500 次/秒新转换；0 不自动等于断线或读数无效。温度在此模式下刷新较慢。
硬件错误查看 SPI、sensor、init 位；主机断线/过期状态单独在 `system.status()` 中报告。

`TactileHand` 是 `TactileSystem` 的别名，便于使用旧入口名称。数据结构已改为 V2，
不承诺与旧 DeepSeek 的帧对象或 T500 录制格式兼容。完整接口见
[API_AND_INTEGRATION.md](docs/API_AND_INTEGRATION.md)。

## 自动识别、换口与隔离

- 从帧身份字节识别四个角色：左/右手 × 12/32 路；短/长线和映射修订随帧保留。
- USB 拓扑只用于打开设备和诊断。换 Hub 口后重新识别，不把旧口号当角色。
- 同角色两块板同时在线时报告 `ambiguous`，不任意选一块供上层使用；原始帧仍按路径录制。
- 每个设备独立 USB 读取线程和解析线程；持续重连，单板打开失败或拔出不停止其他板。
- 输入、订阅和录制队列均有上限；超过上限公开记录丢弃数量，不阻塞其他采集。
- Hub 当前由机器人 USB 总线供电。软件可以隔离单设备通信故障，无法阻止物理短路导致
  整个 Hub 掉电；若要求这种故障也隔离，需要具有逐端口限流保护的供电硬件。

32 路短线物理位置表沿用用户已确认的旧上位机表。调用
`tactile500.mapping.physical_values(frame)` 会同时变换温度、压力和 fresh 位。
长线物理布局未确认时拒绝自动转物理位置，仍可正常接收其固件通道顺序。
不要再次应用 MCU 的片选排列。

## 录制、测试与来源

录制文件保存原始 V2 字节、CRC、序号、MCU 时间戳以及主机读取时间。
`session.json` / `report.json` 保存丢包、坏帧、队列丢弃和运行状态。
起始截断候选与稳定流中的坏帧分别计数。G1 当前日历时钟与工作电脑日期不一致，
UTC 字段保留 G1 原始值；所有速率、超时和软件对齐都使用单调时钟，不依赖该日历时间。
具体二进制格式见 [PROTOCOL_AND_RECORDING.md](docs/PROTOCOL_AND_RECORDING.md)。

```bash
python -m pytest -q
python -m pip wheel --no-build-isolation --no-deps . -w wheelhouse
```

测试包括独立 C 编码向量、CRC/碎片/噪声恢复、序号与时间戳回绕、四板故障和换口、
快照因果性、慢消费者和录制损坏检查。实物结果与限制见 `reports/` 和验收报告。
四板模拟不能替代四块实物同时运行；已先后测试左12/左32短线和右12/右32长线两套。
OSR2048与OSR256的60秒主对比均来自同一套右12/右32长线，完整证据在上面的out入口。

来源：CH340 控制传输序列和传输基础类来自已归档的
`备份/旧版上位机/deepseek-tactile500_pyusb上位机`（相对本工作区主目录），
协议依据本项目 V2 固件；V2 解析、自动发现、故障隔离、快照与录制实现位于此目录。
原 DeepSeek 项目未被修改。该 Python 库不依赖机械臂/机器人控制 SDK，也不发送运动命令。
