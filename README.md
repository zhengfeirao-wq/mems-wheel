# Tactile500 — 四板触觉采集系统（500 Hz / PyUSB）

500 Hz 四通道触觉传感采集系统，用于 AgiBot G1 机械爪。包含 **APM32F402 固件**与
**Python 上位机**两部分，通过 CH340 USB-UART 桥接，基于 V2 二进制协议通信。

---

## 仓库结构

```
.
├── upper_pyusb_500hz/        上位机：Python 库 + CLI + 浏览器监视界面
│   ├── src/tactile500/       核心库
│   ├── tests/                单元测试（含独立 C 编码向量）
│   ├── tools/                诊断与基准工具
│   ├── docs/                 接口、协议、发布说明
│   └── wheelhouse/           离线 wheel（tactile500 + pyusb）
│
├── firmware_tactile500/      APM32F402 固件
│   ├── Source/               应用逻辑（main / 传感器 / 协议 / 流控）
│   ├── Include/              配置与头文件
│   ├── Config/               DAL 板级配置
│   ├── Project/              Keil 工程（6 个板型 Target）
│   └── docs/                 协议 V2、板型通道表
│
├── README_当前版本.md        版本入口索引
└── 今晚测试入口_嵌入式与wheel.md
```

---

## 硬件构型

四块独立采集板，每块通过一只 CH340（VID `1a86` / PID `7523`）接入主机：

| 板型 | 传感器点数 | 固件 identity | 说明 |
|---|---:|---|---|
| 左手 12 点（手指） | 12 | `0x08` | 无缆 |
| 右手 12 点（手指） | 12 | `0x09` | 无缆 |
| 左手 32 点（掌心） | 32 | `0x0E` | 短线 |
| 右手 32 点（掌心） | 32 | `0x0F` | 短线 |

另有长线旧版构型 `0x0C` / `0x0D`。

### 左右手如何区分

**左右手在烧录时确定，不是上电后自适应的。** `TACTILE_PROFILE` 是编译期宏，
由 Keil Target / GCC 构建目录选定，进而决定帧内的 `identity` 字节：

```
bit0    : 0=左手  1=右手
bit1    : 0=12点  1=32点
bit2    : 0=长线  1=短线（12点板恒为 0）
bit7:3  : 映射版本（当前 = 1）
```

固件每帧都携带该字节，上位机据此解出 `frame.role`
（`left_fingers` / `right_fingers` / `left_palm` / `right_palm`），
**不依赖 USB 端口位置**。USB 拓扑仅用于打开设备与诊断。

> ⚠️ 若把左右手固件烧反，上位机不会报错——它会按 USB 端口位置分配角色，
> 而 `identity` 会自相矛盾。现场联调时应用 `tactile500 scan` 核对该字节与物理位置。

---

## 协议要点（V2 / wire version `0x21`）

```
A5 5A | len | version | identity | status | sequence |
sample_time_us | fresh_mask | 温度×N(2B) | 压力×N(3B) | CRC16

12 点帧 =  80 字节      32 点帧 = 180 字节
UART   = 921600 8N1     帧率     = 500 Hz（周期 2 ms）
```

固件为**纯单向广播**：上电、等待约 1 秒完成传感器初始化，随后自动连续发送，
**不接收任何命令**（无握手、无校准写入）。

---

## 安装与运行（上位机）

主机需已安装 `libusb-1.0`。示例在新目录中执行，**不要覆盖机器人本体应用的虚拟环境**：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheelhouse tactile500==0.3.0

.venv/bin/tactile500 scan                      # 只枚举，不打开设备
.venv/bin/tactile500 probe --seconds 30        # 收帧并报告实际速率
.venv/bin/tactile500 capture --seconds 1800 --output captures/run001
.venv/bin/tactile500 inspect captures/run001
.venv/bin/tactile500 view --bind 0.0.0.0 --port 8875 --output-root captures
.venv/bin/tactile500 view --simulate           # 无实物时的四板模拟
```

高速读取在已打开的 libusb1 后端上预提交 32 个异步 Bulk IN 请求。
该适配层使用 PyUSB 内部结构，**依赖固定为 `pyusb==1.3.1`**；
升级前须重新验证。同步读取可用于诊断对照：`TactileSystem(usb_io="sync")`。

---

## 接入上层系统

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

需要同一时刻的四板快照时使用 `system.snapshots(hz=500, delay_seconds=0.004)`，
其状态为 `updated / reused / stale / missing / offline / ambiguous`。
快照采用同一主机单调时钟，不插值、不使用未来数据。

**单位说明**：`temperature` 为 0.1 °C；`pressure` 为旧固件的有符号 `raw * 9 / 80` 尺度，
**未经标定，不应称为 Pa 或 N**。

完整接口见 [`upper_pyusb_500hz/docs/API_AND_INTEGRATION.md`](upper_pyusb_500hz/docs/API_AND_INTEGRATION.md)，
二进制格式见 [`PROTOCOL_AND_RECORDING.md`](upper_pyusb_500hz/docs/PROTOCOL_AND_RECORDING.md)。

---

## 已知限制

以下为实测确认的边界，**读取与判别接口稳定可用**，但这些现象客观存在：

### 1. `fresh_mask` 恒为 0

100% 的帧带 `not_all_fresh` 状态，`per_channel_fresh_fraction` 全为 0。
这意味着固件的 DRDY 轮询在当前 OSR 配置下取不到「新转换」证据。

**这不等于断线或读数无效。** 判定依据是 `status` 的其它位：

| `fresh_mask` | `status` 其它位 | 含义 |
|---|---|---|
| 0 | 仅 `not_all_fresh` | SPI 通、传感器无故障、初始化成功；仅缺新鲜度证据 |
| 0 | 含 `spi_error` | SPI 通信故障 |
| 0 | 含 `sensor_error` | 传感器报故障（`ready & 0xFC`） |
| 0 | 含 `init_error` | 上电配置回读失败 |

实测四板的 `status` 仅含 `not_all_fresh`，且各通道数值持续变化、温度正常漂移，
证明数据有效。**USB 拔插不会改变该状态**（已实测验证：仅 CH340 重新枚举，
MCU 未复位，DRDY 行为不变）。

**根因（2026-09-11 查明）**：原固件初始化末尾写 `0xA5 = 0x88`，把 bit7 `DAC_on` 置 1。
按 NSA2302 datasheet Rev1.2 第 11 页，该位为 *Enable voltage output mode*；第 17 页 6.3 节说明
`DAC_on=1` 即进入 **analog output mode**（"no matter what 'CMD' registers contents"），
自主执行 64 次压力 + 1 次温度转换；而第 18–19 页 6.5.1 节的 INT/DRDY 行为只在
**命令驱动**的四种工作模式下定义。该模式不属于其中，故 DRDY 永不置位。

**修复固件**：`firmware_tactile500/烧录_DRDY修复_20260911/`。保持 `DAC_on=0`，
改用 `0x30` COMMAND 寄存器触发单次转换，并做流水线采集（读完即触发下一轮，
转换在帧间隔内完成）；SPI 由 1.875 MHz 提至 7.5 MHz（手册上限 10 MHz）。
协议与上位机均无需改动。**该修复尚待实物验证。**

### 2. 通道存在偶发满量程跳变

左手 12 点板（`identity 0x08`）的 **ch6** 出现 `±943718` 的跳变
（≈ 24 位满量程的符号异常），极差达 1,887,436。其余三板无此现象。

**软件基线扣除（校零）无法解决此问题**——已实测验证，减去静置均值后极差
改善率为 **0.0%**。因为校零只能平移波形，不能压缩幅度。该校零处理更适合
消除通道间静态偏置与温漂基线，不是此类数字异常的解法。

### 3. Hub 供电共担

Hub 由机器人 USB 总线供电。软件可隔离单设备通信故障，
**无法阻止物理短路导致整个 Hub 掉电**；如需该级别的故障隔离，
需要具备逐端口限流保护的供电硬件。

### 4. 跨板时间戳不可直接相减

MCU 时间戳各自从上电开始计。本版本固件不接收启动命令，
因此软件**无法让独立 MCU 的 ADC 硬件同时启动**。
4 ms 快照延迟提供选择缓冲，但不消除 USB 调度抖动或传感器转换相位差。

### 5. 平台验证范围

性能验证针对 **Ubuntu aarch64**（AgiBot G1 实机，Python 3.10）。
Windows USB 后端未验证。

---

## 测试

```bash
cd upper_pyusb_500hz
python -m pytest -q
```

覆盖独立 C 编码向量、CRC/碎片/噪声恢复、序号与时间戳回绕、
四板故障与换口、快照因果性、慢消费者与录制损坏检查。

固件侧另有 6 种板型的 GCC/Keil 双构建与 C 核心向量测试，
以及 12 份 HEX 的校验和 / Flash 范围 / 启动与中断向量检查。

---

## 部署到 AgiBot G1

```bash
cd ~
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheelhouse tactile500==0.3.0

.venv/bin/tactile500 scan
.venv/bin/tactile500 view --bind 0.0.0.0 --port 8875 --output-root captures
```

随后在 Windows 浏览器打开 `http://<G1地址>:8875`。

> G1 的当前日历时钟与工作电脑日期可能不一致。UTC 字段保留 G1 原始值；
> 所有速率、超时与软件对齐均使用单调时钟，不依赖该日历时间。

---

## 来源与许可

固件基于 Geehy APM32F4xx DAL 示例；厂商许可条款见
`firmware_tactile500/` 内相关声明文件。CH340 控制传输序列与传输基础类
来自已归档的旧版上位机项目；V2 解析、自动发现、故障隔离、快照与录制
为本项目实现。

本 Python 库**不依赖机械臂/机器人控制 SDK，也不发送运动命令**。
