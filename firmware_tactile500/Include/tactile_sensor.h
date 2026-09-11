#ifndef TACTILE_SENSOR_H
#define TACTILE_SENSOR_H

#include "apm32f4xx_dal.h"
#include "tactile_config.h"

typedef struct
{
    int16_t temperature[TACTILE_CHANNEL_COUNT];
    int32_t pressure[TACTILE_CHANNEL_COUNT];
    uint32_t fresh_mask;
    uint32_t sample_time_us;
    uint8_t status;
} TactileSample;

typedef struct
{
    GPIO_TypeDef *port;
    uint16_t pin;
} TactileChipSelect;

/* 运行诊断量，供 Keil 调试器 Watch 窗口直接观察，不占用协议字段。
 * 烧录后重点看：
 *   prime_conversion_us —— NSA2302 真实转换时间（触发到 DRDY 置位的微秒数）
 *   prime_timeout       —— 1 表示上电等待超时，有通道未就绪
 *   full_fresh_frames / total_frames —— fresh_mask 全满的帧占比
 *   drdy_misses / retriggers —— DRDY 未就绪与补触发次数
 *   init_fail_mask + init_*_rb[] —— 初始化失败通道与回读值（见下） */
typedef struct
{
    uint32_t prime_conversion_us;
    uint32_t prime_timeout;
    uint32_t total_frames;
    uint32_t full_fresh_frames;
    uint32_t drdy_misses;
    uint32_t retriggers;

    /* 初始化诊断：失败通道位图 + 每通道寄存器回读值。
     * 若 init_fail_mask != 0，对照期望值即可判断哪一步失败：
     *   init_iface_rb 期望 (x & 0x81) == 0x81 且 (x & 0x66) == 0
     *   init_a5_rb    期望 0x08（TACTILE_SENSOR_SYS_CONFIG）
     *   init_a6_rb    期望 0x40（TACTILE_SENSOR_PCH_CONFIG）
     *   init_a7_rb    期望 0x80（TACTILE_SENSOR_TCH_CONFIG）
     * 回读为 0x00 通常表示 SPI 事务失败；接近期望但个别位不同，
     * 表示写入生效后被芯片改写（寄存器语义差异，不是通信问题）。 */
    uint32_t init_fail_mask;
    uint8_t init_iface_rb[TACTILE_CHANNEL_COUNT];
    uint8_t init_a5_rb[TACTILE_CHANNEL_COUNT];
    uint8_t init_a6_rb[TACTILE_CHANNEL_COUNT];
    uint8_t init_a7_rb[TACTILE_CHANNEL_COUNT];
} TactileDiag;

extern volatile TactileDiag g_tactile_diag;

void TactileChannels_Init(void);
TactileChipSelect TactileChannels_Get(uint8_t channel);
void TactileSensor_Init(void);
void TactileSensor_Collect(TactileSample *sample);

#endif
