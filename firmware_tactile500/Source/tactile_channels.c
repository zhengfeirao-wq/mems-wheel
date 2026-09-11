#include "tactile_sensor.h"

#if TACTILE_CHANNEL_COUNT == 32U
static const TactileChipSelect physical_cs[32] = {
    {GPIOB, GPIO_PIN_5},  {GPIOB, GPIO_PIN_4},  {GPIOB, GPIO_PIN_3},
    {GPIOD, GPIO_PIN_2},  {GPIOC, GPIO_PIN_12}, {GPIOC, GPIO_PIN_11},
    {GPIOB, GPIO_PIN_6},  {GPIOB, GPIO_PIN_7},  {GPIOB, GPIO_PIN_8},
    {GPIOB, GPIO_PIN_9},  {GPIOC, GPIO_PIN_0},  {GPIOC, GPIO_PIN_1},
    {GPIOC, GPIO_PIN_2},  {GPIOA, GPIO_PIN_15}, {GPIOC, GPIO_PIN_10},
    {GPIOC, GPIO_PIN_3},  {GPIOA, GPIO_PIN_9},  {GPIOA, GPIO_PIN_8},
    {GPIOC, GPIO_PIN_9},  {GPIOC, GPIO_PIN_8},  {GPIOC, GPIO_PIN_7},
    {GPIOC, GPIO_PIN_6},  {GPIOB, GPIO_PIN_1},  {GPIOB, GPIO_PIN_0},
    {GPIOC, GPIO_PIN_5},  {GPIOC, GPIO_PIN_4},  {GPIOA, GPIO_PIN_10},
    {GPIOA, GPIO_PIN_11}, {GPIOA, GPIO_PIN_12}, {GPIOB, GPIO_PIN_11},
    {GPIOB, GPIO_PIN_10}, {GPIOB, GPIO_PIN_2}
};

#if TACTILE_CABLE_VARIANT == TACTILE_CABLE_LONG
/* 1-based CS编号，与原长线固件完全一致，不在上位机再次重复应用。 */
static const uint8_t cs_order[32] = {
    16, 13, 12, 11, 10, 9, 8, 7, 1, 2, 3, 4, 5, 6, 14, 15,
    26, 25, 24, 23, 32, 31, 30, 29, 28, 27, 17, 18, 19, 20, 21, 22
};
#else
static const uint8_t cs_order[32] = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
    17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32
};
#endif
#endif

TactileChipSelect TactileChannels_Get(uint8_t channel)
{
    TactileChipSelect result;
    result.port = NULL;
    result.pin = 0U;
    if (channel >= TACTILE_CHANNEL_COUNT)
    {
        return result;
    }
#if TACTILE_CHANNEL_COUNT == 12U
    result.port = GPIOC;
    result.pin = (uint16_t)(1U << channel);
#else
    result = physical_cs[cs_order[channel] - 1U];
#endif
    return result;
}

void TactileChannels_Init(void)
{
    GPIO_InitTypeDef gpio = {0};
    uint8_t channel;
    __DAL_RCM_GPIOA_CLK_ENABLE();
    __DAL_RCM_GPIOB_CLK_ENABLE();
    __DAL_RCM_GPIOC_CLK_ENABLE();
    __DAL_RCM_GPIOD_CLK_ENABLE();
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;

    for (channel = 0U; channel < TACTILE_CHANNEL_COUNT; ++channel)
    {
        TactileChipSelect cs = TactileChannels_Get(channel);
        DAL_GPIO_WritePin(cs.port, cs.pin, GPIO_PIN_SET);
        gpio.Pin = cs.pin;
        DAL_GPIO_Init(cs.port, &gpio);
    }
}
