# Tactile500 固件（APM32F402RB）

**最新调整（2026-09-10，OSR256试验）：压力/温度OSR均已改为256（A6=0x40、A7=0x80），六板型已重新编译，等待用户烧录后测量。当前烧录文件与步骤见[OSR256入口](烧录_OSR256_20260910/先读我_OSR256烧录.md)。以下早先实测记录对应OSR2048，不能作为256档实测结果。**

本目录是触觉板固件的唯一应用入口。目标：由 MCU 硬件定时器原生按 2 ms 周期发送；每帧携带左/右、12/32 通道、32 通道长/短线、映射版本、固件修订、序号、采集时间和有效性信息。

**本轮用户确认：左12、左32、右12、右32四板经同一Hub接入；先烧录32点短线新版。
第一阶段验收每板500完整帧/秒，ADC新转换率另测。** 短线=新版（原NEW_HARDWARE=1），
长线=旧版（=0）。先看[首次烧录说明](先读我_四板首次烧录.md)与[板型和用户实测位置表](docs/BOARD_VARIANTS_AND_CHANNEL_MAP.md)。

**交付状态（2026-09-10）：当前固件修订 0x21，六种板型已用 Arm GNU Toolchain 重建。用户通过 Keil 重建并烧录左12和左32短线；G1 已收到两板原生约500帧/秒及温度/压力数值。首次实物反馈后的 DMA 修正见 [修订21说明](docs/REVISION_21_HARDWARE_FIX.md)。当前 DRDY 全0，仍未证明每通道500Hz新ADC转换，也未做示波器时序验证。**

## 入口与板型

- Keil 工程：[Project/MDK/Tactile500.uvprojx](Project/MDK/Tactile500.uvprojx)
- 已构建固件：[build/gcc](烧录_OSR256_20260910)，选择与实际板子一致的目录，不要把六份依次烧到同一块板。
- 固件参数：[Include/tactile_config.h](Include/tactile_config.h)
- 协议及上位机对接：[docs/PROTOCOL_V2.md](docs/PROTOCOL_V2.md)
- 改动、DMA 配置、烧录与验收：[docs/CHANGELOG_AND_BENCH_PLAN.md](docs/CHANGELOG_AND_BENCH_PLAN.md)

| 板型 | Keil Target 后缀 | GNU 固件目录 | 身份字节 |
|---|---|---|---|
| 左手 12 点 | Left_Fingers12 | left_fingers12 | 0x08 |
| 右手 12 点 | Right_Fingers12 | right_fingers12 | 0x09 |
| 左手 32 点长线 | Left_Palm32_Long | left_palm32_long | 0x0A |
| 右手 32 点长线 | Right_Palm32_Long | right_palm32_long | 0x0B |
| 左手 32 点短线 | Left_Palm32_Short | left_palm32_short | 0x0E |
| 右手 32 点短线 | Right_Palm32_Short | right_palm32_short | 0x0F |

所有 Keil Target 均以 `Tactile500_` 开头。默认选择右手 32 点短线，与原工程宏设置对应。左右和线缆身份由烧录的 Target 决定，不是自动识别接线；烧错固件会报告错误身份。同型多块板目前用 USB 设备路径区分，协议未加入唯一芯片序列号。

## 构建及离线验证

从本目录执行，Python 需要 3.10 或更高版本：

```powershell
python tools/build_firmware.py --profile all
# 如编译器不在 PATH，可指定：
python tools/build_firmware.py --profile right_palm32_short --cc C:/Toolchains/bin/arm-none-eabi-gcc.exe
# Windows 已装 MSVC 时，一次运行 C 测试及独立解码测试：
powershell -ExecutionPolicy Bypass -File tools/test_core.ps1 -Python python
# 检查上位机保存的原始 UART 字节，不是 CSV 或旧版 BT 帧：
python tools/protocol_v2.py capture.bin --output capture_report.json
```

GNU 构建工具自动复制所需源文件到临时目录，适配当前中文路径；输出到 `build/gcc/<profile>/`。构建清单包含源码和固件 SHA-256，见 `build/gcc/build_manifest.json`。该工具只编译，不操作烧录器。

本轮已在本机用Keil 5.27.1 + Arm Compiler 5.06 update 6 (build 750) 与
Geehy.APM32F4xx_DFP.1.0.7支持包重建全部六个Target：均为0错误、27条相同的C4008W编译选项提示。
GNU 14.3.Rel1也已重建六种固件。两套共12份HEX的校验、Flash范围和启动/中断向量检查通过，
SHA-256与检查记录见[本轮构建清单](烧录_OSR256_20260910/先读我_OSR256烧录.md)。本轮未烧录硬件。

## 源文件职责

| 文件 | 职责 |
|---|---|
| Source/main.c | 主循环采集组帧、定时发送、异常恢复 |
| Source/tactile_time.c | DWT 微秒时基、TMR2 500 Hz 触发 |
| Source/tactile_stream.c | 两个帧缓冲区的归属、丢帧和恢复 |
| Source/tactile_protocol.c | 帧编码、CRC-16 |
| Source/tactile_sensor.c | NSA2302 初始化、限时 SPI 读取和新数据标记 |
| Source/tactile_channels.c | 12 点与 32 点长/短线片选顺序 |
| Config/Source/apm32f4xx_*_cfg.c | 芯片时钟、GPIO、SPI、USART2、NVIC |
| tools/protocol_v2.py | 无第三方依赖的独立字节流解码与采集文件统计 |

旧版 `I2C_TwoBoardsPolling` 应用已迁移为 `Applications/Tactile500`。误导性的旧 I2C 工程、旧操作说明、备用 main、旧 EEPROM 命令路径移入上位目录的 `备份/legacy_project_files_20260910`；原应用修改前完整 ZIP 在 `备份/TactileFirmware_before_500Hz_20260910_141543.zip`。SDK 的 Libraries、Boards、Documents 保持原厂名称与内容。

V2 帧替换旧 BT 温度/压力双帧；旧上位机需要按协议适配。没有修改或提前审阅正在由 DeepSeek 编写的上位机。
