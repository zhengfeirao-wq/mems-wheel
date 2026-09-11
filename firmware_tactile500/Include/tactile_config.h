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

/* APB2=120MHz, APB1=60MHz，两路SPI均为1.875MHz，接近原2MHz。
 * 2026-09-10 OSR256试验：压力/温度OSR均为256，保留原增益。
 * 500Hz新测量与重复率需烧录后实测；协议、片选及帧率不变。 */
#define TACTILE_SPI1_PRESCALER        SPI_BAUDRATEPRESCALER_64
#define TACTILE_SPI2_PRESCALER        SPI_BAUDRATEPRESCALER_32
#define TACTILE_SENSOR_PCH_CONFIG    0x40U /* 压力增益32倍，OSR=256 */
#define TACTILE_SENSOR_TCH_CONFIG    0x80U /* 内部温度，增益1倍，OSR=256 */
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
