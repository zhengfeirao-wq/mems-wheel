# DRDY 修复固件（2026-09-11）

**目的：修复 `fresh_mask` 恒为 0**，让 DRDY 重新工作，`fresh_mask` 变成真实可信的新数据标志。

**协议没有任何改动**：仍是 V2 / `A5 5A` / wire version `0x21`，帧长不变（12点 80 字节、32点 180 字节）。
**上位机不需要任何修改**，直接兼容。

---

## 根因

原固件在初始化末尾写了 `0xA5 = 0x88`，把 bit7 `DAC_on` 置 1。

依据 NSA2302 datasheet Rev1.2：

| 依据 | 内容 |
|---|---|
| 第 11 页寄存器表 | `0xA5` bit7 `DAC_on`：**1 = Enable voltage output mode** |
| 第 17 页 6.3 节 | "Set 'DAC_on'=1 to get into the **analog output mode**（**no matter what 'CMD' registers contents**）。自主执行 64 次压力 + 1 次温度转换" |
| 第 18-19 页 6.5.1 节 | INT/DRDY 只在**命令驱动**的四种工作模式下定义；模拟输出模式不在其中 |

所以芯片确实在转换（数值一直在更新），但 **DRDY 永不置位** → 固件不敢标记任何通道为「新转换」→ `fresh_mask = 0`。

---

## 修复方式

1. **初始化保持 `0xA5 = 0x08`**（`DAC_on = 0`，`bit3 Regulator_sel=1` 保留，**VEXT 仍为 2.4V**，
   传感器激励与读数标度不变）。删除了原来那次 `0x88` 写入。
2. **改用 `0x30` COMMAND 寄存器触发单次转换**：写 `0x30 = 0x09`（`Sco=1`, `CMD=001`）。
3. **流水线采集**：每帧「先读上一轮结果、读完立刻触发下一轮」。转换在 2ms 帧间隔里自己跑完，
   不占用扫描预算。
4. **只在 DRDY=1 时读数据**：满足手册 6.5.1 节「不要在 Data_out 寄存器刷新途中读取」的要求。
5. **SPI 从 1.875MHz 提到 7.5MHz**：每帧 SPI 字节数由 320 增至 416，
   1.875MHz 需 1.78ms（超过 1.75ms 扫描预算），7.5MHz 只需 0.44ms。
   依据 datasheet 第 23 页 Table 7.2：`f_sclk` 上限 **10MHz**。
6. **温度刷新**：单次传感器转换不更新温度寄存器，故每 64 帧改用一次组合转换（`0x30 = 0x0A`）刷新温度。

---

## 改动文件（仅固件，3 个）

| 文件 | 改动 |
|---|---|
| `Include/tactile_config.h` | SPI 分频、`0xA5` 期望值、命令寄存器宏、温度/补触发参数 |
| `Include/tactile_sensor.h` | 新增 `TactileDiag` 诊断结构 |
| `Source/tactile_sensor.c` | 初始化去掉 `DAC_on`、新增触发与上电预热、`Collect` 改为流水线两阶段 |

协议文件、流控、定时器、通道映射、main.c **均未改动**；上位机**完全未改动**。

---

## 按实物选 HEX

| 板子 | 文件 |
|---|---|
| 左手 12 点 | `DRDYfix_Tactile500_Left_Fingers12.hex` |
| 右手 12 点 | `DRDYfix_Tactile500_Right_Fingers12.hex` |
| 左手 32 点短线 | `DRDYfix_Tactile500_Left_Palm32_Short.hex` |
| 右手 32 点短线 | `DRDYfix_Tactile500_Right_Palm32_Short.hex` |
| 左手 32 点长线 | `DRDYfix_Tactile500_Left_Palm32_Long.hex` |
| 右手 32 点长线 | `DRDYfix_Tactile500_Right_Palm32_Long.hex` |

Keil Target 名分别为 `Tactile500_Left_Fingers12` 等，与本目录文件名对应。
六种板型已全部用 ArmCC V5.06 update 6 重建，**0 Errors / 0 Errors(warning 仅为原项目已有的 C4008W)**。

Flash 算法 `APM32F402_128.FLM`，起始地址 `0x08000000`。

---

## 烧录后如何验证

### 1. 上位机观察 `fresh_mask`（最关键）

```bash
cd ~/tactile
.venv/bin/tactile500 probe --seconds 10
```

**期望**：`full_fresh_frame_fraction` 由 **0.0 变为接近 1.0**，
`per_channel_fresh_fraction` 由全 0 变为**非 0**。

### 2. Keil 调试器观察诊断量

Watch 窗口添加 `g_tactile_diag`：

| 字段 | 含义 | 期望 |
|---|---|---|
| `prime_conversion_us` | **NSA2302 真实转换时间**（触发到 DRDY 置位的微秒数） | 需实测；< 2000 则 500Hz 流水线成立 |
| `prime_timeout` | 1 = 上电等待超时，有通道未就绪 | 应为 **0** |
| `full_fresh_frames` / `total_frames` | `fresh_mask` 全满的帧占比 | 接近 1:1 |
| `drdy_misses` | DRDY 未就绪的通道次数 | 越小越好 |
| `retriggers` | 补触发次数 | 应为 0（非 0 说明有触发丢失） |

`prime_conversion_us` 是本次最有价值的数字——它是首次能直接测到的芯片真实转换时间。

### 3. 其他必须仍然正常的项

| 检查 | 期望 |
|---|---|
| 帧率 | 仍约 500 Hz |
| `missing_slots` / `duplicates` | 0 / 0 |
| `status` | 无 `spi_error` / `sensor_error` / `init_error` |
| 数值量级 | 与烧录前一致（同一 VEXT，标度不变） |
| 左手 12 点 ch6 | 观察满量程跳变是否减少（**预期改善，但非承诺**） |

---

## 需要留意的边界

- 若 `prime_timeout = 1`：说明 20ms 内仍有通道未就绪，需要检查 SPI 速率或该通道接线。
- 若 `fresh_mask` 仍为 0：说明本方案的前提不成立，需回退并重新分析（此时帧流仍在，不会失联）。
- 若 32 点板出现 `sweep_late`：说明 7.5MHz 下扫描仍超预算，可把 SPI 再提高（上限 10MHz）。
- 组合转换那一帧（每 64 帧一次）可能因温度+压力两次转换耗时较长而出现 1 帧 `fresh_mask` 不满，属预期。

---

## 回退方式

旧的 OSR256 固件在同级目录 [`../烧录_OSR256_20260910`](../烧录_OSR256_20260910/先读我_OSR256烧录.md)，
未被覆盖。重新烧回即可恢复原行为（`fresh_mask` 将回到恒 0）。
