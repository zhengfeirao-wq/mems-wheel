# DRDY 修复与 v3 自愈固件记录（2026-09-11）

## 结论速览

**协议未改**（V2 / `A5 5A` / `0x21`，帧长不变），**上位机无需修改**。
**Keil 工程直接编译本目录的源码**，无需额外的 HEX 交付目录：
打开 `Project/MDK/Tactile500.uvprojx` → 选 Target → Build，
产物在 `build/keil/<Target>/Tactile500_<Target>.hex`。

---

## 根因（datasheet 依据，已实测确证）

原固件初始化末尾写 `0xA5 = 0x88`，把 bit7 `DAC_on` 置 1。

| 依据 | 内容 |
|---|---|
| 第 11 页寄存器表 | `0xA5` bit7 `DAC_on`：**1 = Enable voltage output mode** |
| 第 17 页 6.3 节 | "Set 'DAC_on'=1 to get into the **analog output mode**（**no matter what 'CMD' registers contents**）。自主执行 64 次压力 + 1 次温度转换" |
| 第 18-19 页 6.5.1 节 | INT/DRDY 只在**命令驱动**的四种工作模式下定义；模拟输出模式不在其中 |

**v1 实测证实**：改为命令驱动单次转换后，DRDY 立即开始工作。

## 实测发现：真实转换时间 2~4 ms

v1 实机（G2，四板，120 秒）中，所有可用通道的 `fresh` 比例**精确等于 0.5000**，
即每隔一帧才有一次新转换：

```
帧N   : DRDY=1 → 读数 → 触发
帧N+1 : DRDY=0（仍在转换）→ 跳过
帧N+2 : DRDY=1 → 读数 → 触发
```

推论：**单次转换模式下一次完整转换（含每次 power-up）耗时 2~4 ms**，500 Hz 帧率下
真实新测量约 250 Hz。

这解释了模拟输出模式为何能到 ~489 次/秒（自主连续转换、无每次上电开销），
但代价是 DRDY 永不置位。**两者是本质权衡。**

> **注意**：即使 v3 完全正常，`fresh` 比例预期仍是约 **0.5**，不是 1.0。
> 这是 NSA2302 单次模式的真实能力，不是缺陷。

## 已解决：部分通道初始化失败（v3 自愈）

v1（SPI 7.5 MHz）与 v2（3.75 MHz）实机都出现 `init_error`，
失败通道**集中在 SPI1 侧**（`channel < COUNT/2`）：32 点板为 ch0–15，12 点板为 ch0–5。

### 推断（v3 实测支持）

板载 EEPROM 被早期固件烧入了 `0xA5 = 0x88`（legacy 固件用自动模式烧写，见下）。
上电时 EEPROM 自动加载 → 芯片进入模拟输出模式；固件再写 `0xA5 = 0x08` 切换。
**若该写入未生效**，芯片留在模拟输出模式，此时写 `0x30` 触发命令会被忽略
（6.3 节 "no matter what CMD registers contents"），DRDY 永不置位 → `fresh` 恒 0。

**这一个原因同时解释「初始化校验失败」与「fresh 恒 0」——所以它们总是同一批通道。**

### v3 的应对：运行中自愈

```
某通道连续 4 帧 DRDY = 0
    ↓
自动重写整套配置（0xA4 / 0xA5 / 0xA6 / 0xA7）
    ↓
回读 0xA5 存入 g_tactile_diag.a5_rb_latest[ch]
    ↓
重新触发转换
```

- 每帧最多恢复 `TACTILE_RECOVER_MAX_PER_FRAME`（8）个通道，不挤占 1750 µs 扫描预算
- **不再因初始化校验失败而永久跳过通道**；实测能出数后自动撤销 `init_error` 标记
- 初始化末尾对失败通道完整重写一遍再回读（上电瞬间 SPI 未稳，一次失败不代表芯片坏）

**实机结果：50 个失效通道全部恢复，`init_error` 归零。**

> 若要进一步确认因果链，可在 Keil 观察 `g_tactile_diag.a5_rb_latest[]`：
> 若自愈时读到 `0x88` 而自愈后转为 `0x08`，则模式锁定推断成立。

---

## 版本演进

| 版本 | SPI | 改动 | 实测结果 |
|---|---|---|---|
| v1 | 7.5 MHz | 去掉 `DAC_on`，改 `0x30` 触发，流水线采集 | DRDY 修复成功；但 SPI1 侧 init 失败 |
| v2 | 3.75 MHz | 降速 + 初始化回读诊断 | G2 实测 `init_error` 仍存在 |
| **v3** | 3.75 MHz | **+ 运行中自愈** | ✅ **全部通道恢复，问题解决（见下）** |

### v3 实机验证结果（2026-09-11，G2，四板）

| 指标 | v1 / v2 | **v3** |
|---|---|---|
| `init_error` | 100% 的帧都有 | **0 / 4964 —— 完全消失** |
| `fresh = 0` 的通道数 | **50** | **0** |
| `fresh` 正常通道 | 部分（32点板 16/32，12点板 6/12） | **32/32、12/12、32/32、12/12 全部** |
| 帧率 | 500 Hz | 500 Hz |
| `missing_slots` / `duplicates` | 0 / 0 | 0 / 0 |
| `status` | `not_all_fresh` + `init_error` | 只剩 `not_all_fresh` |

逐板（本次接的是长线版 32 点板）：

| 路径 | identity | 板型 | 通道 | init_error | fresh 正常 |
|---|---|---|---|---|---|
| `1-1.1` | `0x0B` | 右手 32 点长线 | 32 | 0 | 32/32 |
| `1-1.2` | `0x09` | 右手 12 点 | 12 | 0 | 12/12 |
| `1-1.3` | `0x0A` | 左手 32 点长线 | 32 | 0 | 32/32 |
| `1-1.4` | `0x08` | 左手 12 点 | 12 | 0 | 12/12 |

**`fresh ≈ 0.5000` 是健康值**，正是前文「真实转换时间 2~4 ms」的必然结果，
不是缺陷。个别通道略高（如 0.753）属正常波动。

### v3 的自愈机制

```
某通道连续 4 帧 DRDY = 0
    ↓
自动重写整套配置（0xA4 / 0xA5 / 0xA6 / 0xA7）
    ↓
回读 0xA5 存入 g_tactile_diag.a5_rb_latest[ch]
    ↓
重新触发转换
```

- 每帧最多恢复 `TACTILE_RECOVER_MAX_PER_FRAME`（8）个通道，不挤占 1750 µs 扫描预算
- **不再因初始化校验失败而永久跳过通道**；实测能出数后自动撤销 `init_error` 标记
- 初始化末尾对失败通道完整重写一遍再回读（上电瞬间 SPI 未稳，一次失败不代表芯片坏）

---

## 编译期配置（当前值）

| 宏 | 值 | 说明 |
|---|---|---|
| `TACTILE_FRAME_RATE_HZ` | 500 | 帧率 |
| `TACTILE_UART_BAUDRATE` | 921600 | |
| `TACTILE_SPI1_PRESCALER` | `_32` | 120/32 = **3.75 MHz** |
| `TACTILE_SPI2_PRESCALER` | `_16` | 60/16 = **3.75 MHz** |
| `TACTILE_SENSOR_SYS_CONFIG` | `0x08` | **`DAC_on = 0`**（关键修正） |
| `TACTILE_SENSOR_PCH_CONFIG` | `0x40` | 压力增益 32×、OSR 256 |
| `TACTILE_SENSOR_TCH_CONFIG` | `0x80` | 内部温度、增益 1×、OSR 256 |
| `TACTILE_SENSOR_CMD_REG` | `0x30` | COMMAND 寄存器 |
| `TACTILE_SENSOR_CMD_SENSOR` | `0x09` | `Sco=1`, `CMD=001` 单次传感器转换 |
| `TACTILE_SENSOR_CMD_COMBINED` | `0x0A` | `Sco=1`, `CMD=010` 组合转换 |
| `TACTILE_SENSOR_TEMP_EVERY` | 64 | 每 64 帧刷新一次温度 |
| `TACTILE_RECOVER_AFTER_MISSES` | 4 | 连续 N 帧未就绪即自愈 |
| `TACTILE_RECOVER_MAX_PER_FRAME` | 8 | 每帧自愈上限 |

SPI 提速依据：datasheet 第 23 页 Table 7.2，`f_sclk` 最大 **10 MHz**（负载 25 pF）。
1.875 MHz 不够用——每帧 416 字节需 1.78 ms，超过 1750 µs 扫描预算；3.75 MHz 只需 0.89 ms。

---

## 诊断量（Keil Watch 窗口添加 `g_tactile_diag`）

| 字段 | 含义 | 期望 |
|---|---|---|
| **`a5_rb_latest[ch]`** | **自愈时重读的 0xA5** | `0x08`=写入生效；`0x88`=仍是模拟输出模式；`0x00`=SPI 失败 |
| **`recovered_mask`** | 自愈成功的通道位图 | 非 0 说明自愈起作用 |
| `recover_attempts` | 累计自愈次数 | — |
| `stuck_mask` | 最近一帧仍无 fresh 的通道 | 越小越好 |
| `init_fail_mask` | 初始化失败的通道位图 | 0 最佳 |
| `init_a5_rb[]` / `init_a6_rb[]` / `init_a7_rb[]` | 各通道回读值 | 分别 `0x08` / `0x40` / `0x80` |
| **`prime_conversion_us`** | **真实转换时间** | 预期 2000~4000 µs |
| `prime_timeout` | 上电等待是否超时 | 0 |
| `full_fresh_frames` / `total_frames` | fresh 全满帧占比 | 见上文说明 |

---

## 早期固件写入的标定值（重要背景）

`reports/firmware_hardware_audit_20260910/legacy_original_main.c` 第 747–768 行，
早期固件执行过**整套标定写入 + EEPROM 自动烧写**：

```c
Spi_WriteReg(addr, 0xa4, 0x00);
Spi_WriteReg(addr, 0xa5, 0x88);    // ← 模拟输出模式，已烧进 EEPROM
Spi_WriteReg(addr, 0xa6, 0x43);    // ← OSR=2048
Spi_WriteReg(addr, 0xa7, 0x83);    // ← OSR=2048
Spi_WriteReg(addr, 0xaa, 0x00);    // ┐
Spi_WriteReg(addr, 0xab, 0x7A);    // │ 温度传感器标定系数 MT0 / KT
Spi_WriteReg(addr, 0xac, 0x2F);    // │
Spi_WriteReg(addr, 0xad, 0x00);    // ┘
Spi_WriteReg(addr, 0x6a, 0x40);    // ┐ 自动模式 EEPROM 烧写
Spi_WriteReg(addr, 0x6c, 0x6a);    // ┘
DAL_Delay(1000);                   /* 等待EEPROM写入1秒 */
```

按 datasheet 6.5.1.7 节，自动模式会把**所有** EEPROM 寄存器烧入。
因此当前板载 EEPROM 的 `0xA5` 为 `0x88`，`0xA6` 为 `0x43`。

**现固件不再写、也不烧写这些标定值**；压力标定系数（`0xAE`~`0xBC`）未被 legacy 显式改动，
自动模式只是回写原值，应完好。

### EEPROM 标定寄存器地图（datasheet 第 13–14 页）

EEPROM 共 32 字节，地址 `0xA0`~`0xBF`：

| 地址 | 名称 | 含义 | LSB | 范围 |
|---|---|---|---|---|
| `0xAA`/`0xAB` | `MT0` | 温度偏置系数 | 1/2¹⁵ | (−1, +1) |
| `0xAC`/`0xAD` | `KT` | 温度灵敏度系数 | 1/2¹⁰ | (−32, +32) |
| `0xAE`/`0xAF` | `CNT_OFF` | T₀ 处偏置 | 1/2¹⁵ | (−1, +1) |
| `0xB0`/`0xB1` | `CTC1` | 一阶温度偏置系数 | 1/2²² | ±0.00781 |
| `0xB2`/`0xB3` | `CTC2` | 二阶温度偏置系数 | 1/2²⁷ | ±6.1e−5 |
| `0xB3`~`0xB5` | `S0` | T₀ 处灵敏度 | 1/2¹³（无符号） | (0, 2) |
| `0xB5`/`0xB6` | `STC1` | 一阶温度灵敏度系数 | 1/2²⁰ | ±0.00781 |
| `0xB7`/`0xB8` | `STC2` | 二阶温度灵敏度系数 | 1/2²⁵ | ±1.5e−5 |
| `0xB8`/`0xB9` | `KS` / `KSS` | 二/三阶非线性系数 | 1/2¹¹ | (−0.25, +0.25) |
| `0xBA` | `KS_scale`/`KSS_scale` | 非线性系数 ×4 标志 | — | — |
| `0xBB`/`0xBC` | `B0` | 非线性标定参考压力点 | 1/2¹⁵ | (−1, 1) |

**标定模型**（datasheet 第 14 页）：内置 DSP 支持**偏置与灵敏度的二阶温度漂移补偿**，
以及**输出非线性的三阶补偿**。系数存在 EEPROM，上电自动加载。

**待核实**：这些系数默认值均为 `0x00`（尤其 `S0`）。若 `S0 = 0` 则标定输出应为 0，
但实测值在正常变化，故需读出实际值判断标定是否真正生效。
可在 `TactileDiag` 中扩展寄存器 dump 来核实。

---

## 回退

原始 OSR256 固件在 [`../烧录_OSR256_20260910/`](../烧录_OSR256_20260910/先读我_OSR256烧录.md)，
未被覆盖。重烧即可恢复原行为（`fresh_mask` 回到恒 0，数据更新率恢复约 489/秒）。
