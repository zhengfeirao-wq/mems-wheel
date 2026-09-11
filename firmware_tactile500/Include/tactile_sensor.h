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
 *   drdy_misses / retriggers —— DRDY 未就绪与补触发次数 */
typedef struct
{
    uint32_t prime_conversion_us;
    uint32_t prime_timeout;
    uint32_t total_frames;
    uint32_t full_fresh_frames;
    uint32_t drdy_misses;
    uint32_t retriggers;
} TactileDiag;

extern volatile TactileDiag g_tactile_diag;

void TactileChannels_Init(void);
TactileChipSelect TactileChannels_Get(uint8_t channel);
void TactileSensor_Init(void);
void TactileSensor_Collect(TactileSample *sample);

#endif
