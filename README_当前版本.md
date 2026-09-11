# 版本与入口索引

本仓库为 **Tactile500 四板 500 Hz 触觉采集系统**（固件 + PyUSB 上位机）。
完整介绍见 [README.md](README.md)。

## 当前版本

| 组件 | 版本 | 位置 |
|---|---|---|
| 上位机 | tactile500 **0.3.0** | [upper_pyusb_500hz](upper_pyusb_500hz) |
| 固件 | wire version **0x21**（OSR256） | [firmware_tactile500](firmware_tactile500) |
| 协议 | V2，帧头 `A5 5A` | [PROTOCOL_V2.md](firmware_tactile500/docs/PROTOCOL_V2.md) |

帧率 500 Hz；12 点帧 80 字节、32 点帧 180 字节；UART 921600 8N1。

## 快速入口

| 需求 | 打开 |
|---|---|
| 系统总览与架构 | [README.md](README.md) |
| 安装 wheel 与接口示例 | [API_AND_INTEGRATION.md](upper_pyusb_500hz/docs/API_AND_INTEGRATION.md) |
| 二进制协议与录制格式 | [PROTOCOL_AND_RECORDING.md](upper_pyusb_500hz/docs/PROTOCOL_AND_RECORDING.md) |
| 0.3.0 交付与启动步骤 | [RELEASE_0_3_0.md](upper_pyusb_500hz/docs/RELEASE_0_3_0.md) |
| 离线 wheel（含 PyUSB） | [upper_pyusb_500hz/wheelhouse](upper_pyusb_500hz/wheelhouse) |
| 四板烧录选型 | [先读我_四板首次烧录.md](firmware_tactile500/先读我_四板首次烧录.md) |
| OSR256 固件与烧录 | [先读我_OSR256烧录.md](firmware_tactile500/烧录_OSR256_20260910/先读我_OSR256烧录.md) |
| 板型与通道映射表 | [BOARD_VARIANTS_AND_CHANNEL_MAP.md](firmware_tactile500/docs/BOARD_VARIANTS_AND_CHANNEL_MAP.md) |
| Keil 工程 | [Tactile500.uvprojx](firmware_tactile500/Project/MDK/Tactile500.uvprojx) |
| 固件主程序 | [main.c](firmware_tactile500/Source/main.c) |

## 本仓库包含与不包含

**包含**：上位机源码 / 测试 / 工具 / 文档 / 离线 wheel；固件源码 / Keil 与 GCC 工程 /
板级配置 / 6 份烧录 HEX（左·右手 × 12·32 点 × 长·短线）。

**不包含**（体积原因，留在原始工作区）：历史 `reports/` 审计图、`out/` 汇报材料、
`备份/` 旧版归档、厂商 SDK、PCB 源文件与 3D 模型、采集数据与构建中间产物。
`.gitignore` 已排除这些类别，重新生成不会误入库。

## 已知限制

实测确认的边界详见 [README.md](README.md) 的「已知限制」章节，摘要如下：

1. **`fresh_mask` 恒为 0** —— DRDY 轮询取不到新转换证据；不等于读数无效，
   判定依据是 `status` 其它位（仅 `not_all_fresh` 表示链路正常）。
2. **左手 12 点板 ch6 偶发满量程跳变**（±943718）。软件校零无法解决（实测改善 0.0%）。
3. **Hub 供电共担** —— 无逐端口限流保护，物理短路会导致整 Hub 掉电。
4. **跨板时间戳不可直接相减** —— MCU 各自从上电计时。
5. **平台验证范围为 Ubuntu aarch64** —— Windows USB 后端未验证。

## 版本演进摘要

- **0.3.0** —— V2 协议、自动发现、故障隔离、四板快照、浏览器监视界面。
- **0.2.0** —— 早期实验版本，目录已归档。
- **0.1.0** —— 100 Hz 串口方案（pyserial），已被本 PyUSB 方案取代。

OSR 设置演变：OSR2048（对比基线） → **OSR256（当前）**。
