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

void TactileChannels_Init(void);
TactileChipSelect TactileChannels_Get(uint8_t channel);
void TactileSensor_Init(void);
void TactileSensor_Collect(TactileSample *sample);

#endif
