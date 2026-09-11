#ifndef TACTILE_CONFIG_H
#define TACTILE_CONFIG_H

#include <stdint.h>
#include "tactile_protocol.h"

/* 四块板：左12、右12、左32、右32；每块板独立接一只CH340。
 * 32点短线=新版（旧代码NEW_HARDWARE=1），长线=旧版（=0）。
 * 在Keil的Target下拉框选择板型，不再另外修改NEW_HARDWARE。
 * 原始通道顺序保持不变；网页位置映射见docs/BOARD_VARIANTS_AND_CHANNEL_MAP.md。 */
#define TACTILE_LEFT_FINGERS12       1
#define TACTILE_RIGHT_FINGERS12      2
#define TACTILE_LEFT_PALM32_LONG     3
#define TACTILE_RIGHT_PALM32_LONG    4
#define TACTILE_LEFT_PALM32_SHORT    5
#define TACTILE_RIGHT_PALM32_SHORT   6

#ifndef TACTILE_PROFILE
#define TACTILE_PROFILE TACTILE_RIGHT_PALM32_SHORT
#endif

#define TACTILE_CABLE_NONE   0U
#define TACTILE_CABLE_LONG   1U
#define TACTILE_CABLE_SHORT  2U

#if TACTILE_PROFILE == TACTILE_LEFT_FINGERS12
#define TACTILE_HAND_ID       1U
#define TACTILE_CHANNEL_COUNT 12U
#define TACTILE_CABLE_VARIANT TACTILE_CABLE_NONE
#elif TACTILE_PROFILE == TACTILE_RIGHT_FINGERS12
#define TACTILE_HAND_ID       2U
#define TACTILE_CHANNEL_COUNT 12U
#define TACTILE_CABLE_VARIANT TACTILE_CABLE_NONE
#elif TACTILE_PROFILE == TACTILE_LEFT_PALM32_LONG
#define TACTILE_HAND_ID       1U
#define TACTILE_CHANNEL_COUNT 32U
#define TACTILE_CABLE_VARIANT TACTILE_CABLE_LONG
#elif TACTILE_PROFILE == TACTILE_RIGHT_PALM32_LONG
#define TACTILE_HAND_ID       2U
#define TACTILE_CHANNEL_COUNT 32U
#define TACTILE_CABLE_VARIANT TACTILE_CABLE_LONG
#elif TACTILE_PROFILE == TACTILE_LEFT_PALM32_SHORT
#define TACTILE_HAND_ID       1U
#define TACTILE_CHANNEL_COUNT 32U
#define TACTILE_CABLE_VARIANT TACTILE_CABLE_SHORT
#elif TACTILE_PROFILE == TACTILE_RIGHT_PALM32_SHORT
#define TACTILE_HAND_ID       2U
#define TACTILE_CHANNEL_COUNT 32U
#define TACTILE_CABLE_VARIANT TACTILE_CABLE_SHORT
#else
#error "TACTILE_PROFILE must select one of the six supported boards"
#endif

/* 第一阶段验收的是整帧发送率；这不代表ADC每秒完成500次新转换。 */
#define TACTILE_FRAME_RATE_HZ        500U
#define TACTILE_SAMPLE_RATE_HZ       TACTILE_FRAME_RATE_HZ /* 旧宏名兼容 */
#define TACTILE_PERIOD_US            (1000000U / TACTILE_FRAME_RATE_HZ)
#define TACTILE_UART_BAUDRATE        921600U
#define TACTILE_MAPPING_REVISION     1U
#define TACTILE_WIRE_VERSION         0x21U /* 协议主版本 2，固件修订 1。 */

/* 2026-09-11：SPI 从 1.875MHz 提到 3.75MHz。
 * 依据 NSA2302 datasheet Rev1.2 Table 7.2：f_sclk 上限 10MHz（负载25pF）。
 * 提速原因：改为命令驱动单次转换后每帧要额外写 0x30 触发寄存器，
 * 每帧SPI字节数 320 -> 416。1.875MHz 需 1.78ms，超过 1.75ms 扫描预算；
 * 3.75MHz 只需 0.89ms，留出约一半余量。
 *
 * 实测记录：先按 7.5MHz 试过一版，初始化回读校验在 SPI1 侧通道
 * （channel < COUNT/2）成片失败，判定为 32 片并联总线在该速率下
 * 信号完整性不足。降到 3.75MHz（仍为原速 2 倍）后应消除。
 * 若仍失败，看 g_tactile_diag.init_a5_rb[] / init_fail_mask 定位。 */
#define TACTILE_SPI1_PRESCALER        SPI_BAUDRATEPRESCALER_32 /* 120/32 = 3.75MHz */
#define TACTILE_SPI2_PRESCALER        SPI_BAUDRATEPRESCALER_16 /*  60/16 = 3.75MHz */
#define TACTILE_SENSOR_PCH_CONFIG    0x40U /* 压力增益32倍，OSR=256 */
#define TACTILE_SENSOR_TCH_CONFIG    0x80U /* 内部温度，增益1倍，OSR=256 */

/* NSA2302 系统配置寄存器 0xA5，bit7 = DAC_on（1 = Enable voltage output mode）。
 * 原固件写 0x88 置 DAC_on=1，芯片进入 datasheet 6.3 节的 analog output mode：
 * 自主执行"64次压力 + 1次温度"转换，且手册明确 "no matter what 'CMD'
 * registers contents"。该模式不属于 6.5.1 节命令驱动的四种工作模式，
 * 因此 INT/DRDY 不置位 —— 这正是 fresh_mask 恒为 0 的根因。
 * 现保持 DAC_on=0：0x08 仅保留 bit3 Regulator_sel=1（VEXT 仍为 2.4V，
 * 与原来一致，传感器激励与读数标度不变），其余位为 0。 */
#define TACTILE_SENSOR_SYS_CONFIG    0x08U

/* NSA2302 COMMAND 寄存器 0x30
 * bit3   = Sco：1 = 启动转换，转换结束自动回 0（睡眠模式除外）
 * bit2:0 = CMD：000单次温度 001单次传感器 010组合(温度+传感器) 011睡眠周期 */
#define TACTILE_SENSOR_CMD_REG       0x30U
#define TACTILE_SENSOR_CMD_SENSOR    0x09U /* Sco=1, CMD=001 单次传感器转换 */
#define TACTILE_SENSOR_CMD_COMBINED  0x0AU /* Sco=1, CMD=010 组合转换 */

/* 温度刷新周期（以帧计）。单次传感器转换不更新温度寄存器，
 * 因此每 N 帧改用一次组合转换刷新温度。500Hz 下 64 帧 = 128ms。 */
#define TACTILE_SENSOR_TEMP_EVERY    64U

/* 连续 N 帧 DRDY 未就绪则补触发一次，防止触发丢失后通道永久卡死。 */
#define TACTILE_SENSOR_MISS_LIMIT    3U

/* 上电首轮等待所有通道转换完成的上限（微秒）。
 * 该轮轮询会实测出真实的"触发->DRDY置位"耗时，存入诊断量。 */
#define TACTILE_SENSOR_PRIME_TIMEOUT_US  20000U

#define TACTILE_SPI_TRANSACTION_US   100U
#define TACTILE_SWEEP_BUDGET_US      1750U
#define TACTILE_TX_MAX_LATENESS_US   20U

/* 根据实际板型核算8N1串口预算，新增字段时编译器会阻止超出2ms的配置。
 * 按请求波特率向上取整：12点869us，32点1954us。
 * 该检查不替代晶振、UART边沿和实际中断耗时测量。 */
#define TACTILE_FRAME_BYTES          (TACTILE_FRAME_OVERHEAD + 5U * TACTILE_CHANNEL_COUNT)
#define TACTILE_UART_BITS_PER_BYTE   10U
#define TACTILE_UART_FRAME_TIME_US   ((TACTILE_FRAME_BYTES * TACTILE_UART_BITS_PER_BYTE * \
                                      1000000U + TACTILE_UART_BAUDRATE - 1U) / \
                                     TACTILE_UART_BAUDRATE)

#if TACTILE_FRAME_RATE_HZ == 0U || (1000000U % TACTILE_FRAME_RATE_HZ) != 0U
#error "Frame rate must divide the 1 MHz timer clock exactly"
#endif
#if TACTILE_FRAME_BYTES > TACTILE_FRAME_MAX_BYTES
#error "Selected board frame exceeds the transmit buffer"
#endif
#if TACTILE_UART_FRAME_TIME_US + TACTILE_TX_MAX_LATENESS_US >= TACTILE_PERIOD_US
#error "UART frame and allowed start delay do not fit in one timer period"
#endif
#if TACTILE_SWEEP_BUDGET_US >= TACTILE_PERIOD_US
#error "Sensor sweep must leave time for encoding before the next timer slot"
#endif

/* bit0: 左0/右1；bit1: 12通道0/32通道1；bit2: 长线0/短线1。
 * 12通道的 bit2 必须为0，线缆类型应解码为 NONE，而不是长线。
 * bit7:3: 映射版本。原固件中的片选排列完整保留为版本1。 */
#define TACTILE_IDENTITY ((uint8_t)( \
    (TACTILE_HAND_ID - 1U) | \
    ((TACTILE_CHANNEL_COUNT == 32U) ? 0x02U : 0U) | \
    ((TACTILE_CABLE_VARIANT == TACTILE_CABLE_SHORT) ? 0x04U : 0U) | \
    (TACTILE_MAPPING_REVISION << 3)))

#if TACTILE_CHANNEL_COUNT == 32U
#define TACTILE_CHANNEL_MASK UINT32_C(0xFFFFFFFF)
#else
#define TACTILE_CHANNEL_MASK UINT32_C(0x00000FFF)
#endif

#endif
