# DRDY 修复固件（2026-09-11）

**目的：修复 `fresh_mask` 恒为 0**，让 DRDY 重新工作，`fresh_mask` 变成真实可信的新数据标志。

**协议没有任何改动**：仍是 V2 / `A5 5A` / wire version `0x21`，帧长不变（12点 80 字节、32点 180 字节）。
**上位机不需要任何修改**。

---

## 版本与实测结果

| 版本 | SPI | 实测结果 |
|---|---|---|
| **v1**（`v1_7p5MHz_*`） | 7.5 MHz | ⚠️ **DRDY 修复成功**，但 SPI1 侧通道（`channel < COUNT/2`）初始化成片失败 |
| **v2**（`v2_3p75MHz_*`） | **3.75 MHz** | 待测。SPI 降速修复 v1 的初始化失败，并新增初始化诊断 |

### v1 实机结果（G2，四板，120 秒）

**✅ DRDY 修复本身成功**：凡通过初始化的通道，`fresh_mask` 不再恒为 0。

**📊 最重要的实测发现**：所有工作通道的 fresh 比例**精确等于 0.5000**。

```
右32点 ch8-31  全部 = 0.5000
左12点 ch7-11  全部 = 0.5000
左32点 ch8-31  全部 = 0.5000
右12点 ch6-11  全部 = 0.5000
```

0.5 意味着**每隔一帧才有一次新转换**：

```
帧N   : DRDY=1 → 读数 → 触发转换
帧N+1 : DRDY=0（仍在转换）→ 跳过
帧N+2 : DRDY=1 → 读数 → 触发
```

**推论：单次转换模式下一次完整转换（含每次 power-up）耗时在 2~4 ms 之间。**

这解释了为什么"模拟输出模式"下能到 ~489 次/秒：那是**自主连续转换、没有每次上电开销**，
但代价是 DRDY 永不置位。**两者是本质权衡，不能同时要。**

**⚠️ v1 的问题**：`init_error` 出现在所有板，失败集中在 `channel < COUNT/2`（即 SPI1 侧）：

| 板 | 失败通道 |
|---|---|
| 右12点 | ch0-5（正好 SPI1 的 6 个） |
| 左12点 | ch0-6 |
| 右32点 | ch0-7 |
| 左32点 | ch0-7 |

判定为 32 片并联总线在 7.5 MHz 下信号完整性不足，故 v2 降到 3.75 MHz（仍为原速 2 倍）。

---

## 根因（v1 已确证）

原固件在初始化末尾写了 `0xA5 = 0x88`，把 bit7 `DAC_on` 置 1。

依据 NSA2302 datasheet Rev1.2：

| 依据 | 内容 |
|---|---|
| 第 11 页寄存器表 | `0xA5` bit7 `DAC_on`：**1 = Enable voltage output mode** |
| 第 17 页 6.3 节 | "Set 'DAC_on'=1 to get into the **analog output mode**（**no matter what 'CMD' registers contents**）。自主执行 64 次压力 + 1 次温度转换" |
| 第 18-19 页 6.5.1 节 | INT/DRDY 只在**命令驱动**的四种工作模式下定义；模拟输出模式不在其中 |

实测完全印证：修复后 DRDY 立即开始工作。

---

## 修复方式

1. **`0xA5` 保持 `0x08`**（`DAC_on = 0`），`bit3 Regulator_sel=1` 保留 → **VEXT 仍 2.4V，读数标度不变**。
2. **改用 `0x30` COMMAND 寄存器触发单次转换**：写 `0x30 = 0x09`（`Sco=1`, `CMD=001`）。
3. **流水线采集**：每帧「读上一轮结果 → 读完立刻触发下一轮」，转换在帧间隔里跑。
4. **只在 DRDY=1 时读数据**：满足手册 6.5.1 节「勿在 Data_out 刷新途中读取」。
5. **SPI 提速**：1.875 → **3.75 MHz**（v2）。每帧 SPI 字节数由 320 增至 416，
   1.875 MHz 需 1.78 ms（超 1.75 ms 预算），3.75 MHz 只需 0.89 ms。
   上限依据 datasheet 第 23 页 Table 7.2：`f_sclk` 最大 **10 MHz**。
6. **温度刷新**：单次传感器转换不更新温度寄存器，每 64 帧改用一次组合转换（`0x30 = 0x0A`）。

---

## 改动文件（仅固件，3 个）

| 文件 | 改动 |
|---|---|
| `Include/tactile_config.h` | SPI 分频、`0xA5` 期望值、命令寄存器宏、温度/补触发参数 |
| `Include/tactile_sensor.h` | 新增 `TactileDiag`（含初始化诊断） |
| `Source/tactile_sensor.c` | 去掉 `DAC_on`、触发函数、上电预热、流水线 `Collect`、初始化回读留存 |

协议文件、流控、定时器、通道映射、main.c **均未改动**；上位机**完全未改动**。

---

## 按实物选 HEX（推荐 v2）

| 板子 | Keil Target | v2 文件（推荐） |
|---|---|---|
| 左手 12 点 | `Tactile500_Left_Fingers12` | `v2_3p75MHz_Left_Fingers12.hex` |
| 右手 12 点 | `Tactile500_Right_Fingers12` | `v2_3p75MHz_Right_Fingers12.hex` |
| 左手 32 点短线 | `Tactile500_Left_Palm32_Short` | `v2_3p75MHz_Left_Palm32_Short.hex` |
| 右手 32 点短线 | `Tactile500_Right_Palm32_Short` | `v2_3p75MHz_Right_Palm32_Short.hex` |
| 左手 32 点长线 | `Tactile500_Left_Palm32_Long` | `v2_3p75MHz_Left_Palm32_Long.hex` |
| 右手 32 点长线 | `Tactile500_Right_Palm32_Long` | `v2_3p75MHz_Right_Palm32_Long.hex` |

六种板型已全部用 ArmCC V5.06 update 6 重建，**0 Errors**。
Flash 算法 `APM32F402_128.FLM`，起始地址 `0x08000000`。

---

## 烧录后如何验证

### 1. Keil 调试器先看初始化是否干净（v2 重点）

Watch 窗口添加 `g_tactile_diag`：

| 字段 | 期望 | 说明 |
|---|---|---|
| **`init_fail_mask`** | **0x00000000** | 非 0 表示有通道初始化失败 |
| `init_a5_rb[ch]` | 每通道 = `0x08` | 0xA5 回读值 |
| `init_a6_rb[ch]` | 每通道 = `0x40` | 压力增益/OSR |
| `init_a7_rb[ch]` | 每通道 = `0x80` | 温度增益/OSR |
| `init_iface_rb[ch]` | `(x & 0x81) == 0x81` | 接口寄存器 |
| **`prime_conversion_us`** | 记录值 | **真实转换时间** |
| `prime_timeout` | 0 | 上电等待是否超时 |
| `full_fresh_frames` / `total_frames` | — | fresh 全满比例 |

**回读值判读**：某通道回读为 `0x00` → SPI 事务失败（通信问题）；
回读接近期望但个别位不同 → 写入生效后被芯片改写（语义差异，非通信问题）。

### 2. 上位机看 fresh

```bash
cd ~/tactile && .venv/bin/tactile500 probe --seconds 10
```

| 指标 | v1 实测 | v2 期望 |
|---|---|---|
| `full_fresh_frame_fraction` | 0.0 | 受真实转换率限制，见下 |
| `per_channel_fresh_fraction` | 0.5（可用通道） | **0.5 属正常**（转换 > 2 ms） |
| `status` | 含 `init_error` | **应无 `init_error`** |

> **注意**：即使 v2 完全正常，**`fresh` 比例预期仍是约 0.5，不是 1.0**。
> 这是 NSA2302 单次模式的真实转换能力（约 250 Hz 有效新测量 @ 500 Hz 帧率），
> 不是缺陷。0.5 正是"每两帧一次真实新转换"的如实反映。

### 3. 其他必须仍然正常

帧率约 500 Hz、`missing_slots`/`duplicates` 为 0、无 `spi_error`/`sensor_error`、数值量级不变。

---

## 待用户决策：帧率与真实转换率的取舍

既然实测到单次模式转换约 2~4 ms，就有两个方向：

| 方案 | 帧率 | 特点 |
|---|---|---|
| **A. 保持 500 Hz** | 500 Hz | 每两帧一次真实新转换；`fresh_mask` 如实标记哪帧是新的；时间戳分辨率 2 ms |
| **B. 降到 250 Hz** | 250 Hz | 每帧都是真实新转换，无重复帧；但时间分辨率降到 4 ms |
| C. 回到模拟输出模式 | 500 Hz | 数据更新快，但 `fresh_mask` 恒 0，无法区分真重复与未更新 |

**建议先按方案 A 跑通**，用 `fresh_mask` 作为"哪帧是新的"标记；
若后续分析发现重复帧无价值，再考虑 B。

---

## 回退方式

旧 OSR256 固件在同级目录 [`../烧录_OSR256_20260910`](../烧录_OSR256_20260910/先读我_OSR256烧录.md)，
未被覆盖。重烧即可恢复原行为（`fresh_mask` 将回到恒 0，但数据更新率恢复到 ~489/秒）。
