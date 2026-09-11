#include "tactile_sensor.h"
#include "tactile_protocol.h"
#include "tactile_time.h"
#include "apm32f4xx_spi_cfg.h"
#include <string.h>

#define NSA_REG_INTERFACE    0x00U
#define NSA_REG_DATA_READY   0x02U
#define NSA_REG_TEMP_LSB     0x0AU
#define NSA_DATA_READY       0x01U
#define NSA_SENSOR_ERRORS   0xFCU

static int16_t last_temperature[TACTILE_CHANNEL_COUNT];
static int32_t last_pressure[TACTILE_CHANNEL_COUNT];
static uint32_t init_failed_mask;

static int SpiTransfer(uint8_t channel, const uint8_t *tx,
                       uint8_t *rx, uint8_t length)
{
    SPI_TypeDef *spi;
    TactileChipSelect cs;
    uint32_t started;
    uint32_t original_ctrl;
    uint8_t index;
    volatile uint32_t discard;

    if (channel >= TACTILE_CHANNEL_COUNT || tx == NULL || rx == NULL)
    {
        return 0;
    }
    spi = channel < TACTILE_CHANNEL_COUNT / 2U ? SPI1 : SPI2;
    cs = TactileChannels_Get(channel);
    original_ctrl = spi->CTRL1;
    started = TactileTime_NowUs();
    DAL_GPIO_WritePin(cs.port, cs.pin, GPIO_PIN_RESET);

    /* 每发一字节收一字节，既提供时钟，也避免接收溢出。 */
    for (index = 0U; index < length; ++index)
    {
        while ((spi->STS & SPI_STS_TXBEFLG) == 0U)
        {
            if ((uint32_t)(TactileTime_NowUs() - started) >=
                TACTILE_SPI_TRANSACTION_US)
            {
                goto failed;
            }
        }
        *(__IO uint8_t *)&spi->DATA = tx[index];
        while ((spi->STS & SPI_STS_RXBNEFLG) == 0U)
        {
            if ((uint32_t)(TactileTime_NowUs() - started) >=
                TACTILE_SPI_TRANSACTION_US)
            {
                goto failed;
            }
        }
        rx[index] = (uint8_t)spi->DATA;
    }
    while ((spi->STS & SPI_STS_BSYFLG) != 0U)
    {
        if ((uint32_t)(TactileTime_NowUs() - started) >=
            TACTILE_SPI_TRANSACTION_US)
        {
            goto failed;
        }
    }
    if ((spi->STS & (SPI_STS_OVRFLG | SPI_STS_MEFLG)) != 0U)
    {
        goto failed;
    }
    DAL_GPIO_WritePin(cs.port, cs.pin, GPIO_PIN_SET);
    return 1;

failed:
    DAL_GPIO_WritePin(cs.port, cs.pin, GPIO_PIN_SET);
    spi->CTRL1 &= ~SPI_CTRL1_SPIEN;
    discard = spi->DATA;
    discard = spi->STS;
    (void)discard;
    spi->CTRL1 = original_ctrl; /* 恢复主机配置与 SPIEN，下一周期可重试。 */
    return 0;
}

static int WriteRegister(uint8_t channel, uint8_t address, uint8_t value)
{
    uint8_t tx[3] = {0x00U, 0U, 0U};
    uint8_t rx[3];
    tx[1] = address;
    tx[2] = value;
    return SpiTransfer(channel, tx, rx, 3U);
}

static int ReadRegister(uint8_t channel, uint8_t address, uint8_t *value)
{
    uint8_t tx[3] = {0x80U, 0U, 0xFFU};
    uint8_t rx[3];
    tx[1] = address;
    if (!SpiTransfer(channel, tx, rx, 3U))
    {
        return 0;
    }
    *value = rx[2];
    return 1;
}

static int ReadMeasurement(uint8_t channel, int16_t *temperature,
                           int32_t *pressure)
{
    /* 0xE0: 连续读取；MSB-first 模式从 0x0A 向 0x06 递减地址。 */
    const uint8_t tx[7] = {0xE0U, NSA_REG_TEMP_LSB,
                          0xFFU, 0xFFU, 0xFFU, 0xFFU, 0xFFU};
    uint8_t rx[7];
    uint16_t temp_bits;
    int32_t raw_pressure;
    uint32_t pressure_bits;
    if (!SpiTransfer(channel, tx, rx, 7U))
    {
        return 0;
    }
    temp_bits = (uint16_t)((uint16_t)rx[2] | ((uint16_t)rx[3] << 8));
    *temperature = (int16_t)(((int32_t)(int16_t)temp_bits * 10) / 256);
    pressure_bits = (uint32_t)rx[4] | ((uint32_t)rx[5] << 8) |
                    ((uint32_t)rx[6] << 16);
    raw_pressure = (int32_t)(pressure_bits & 0x7FFFFFU) -
                   (int32_t)(pressure_bits & 0x800000U);
    /* 原固件的0.1125系数，改为精确9/80；单位仍需实物标定确认。 */
    *pressure = (raw_pressure * 9) / 80;
    return 1;
}

void TactileSensor_Init(void)
{
    uint8_t channel;
    init_failed_mask = 0U;
    for (channel = 0U; channel < TACTILE_CHANNEL_COUNT; ++channel)
    {
        last_temperature[channel] = TACTILE_INVALID_TEMP;
        last_pressure[channel] = TACTILE_INVALID_PRESSURE;
        if (!WriteRegister(channel, NSA_REG_INTERFACE, 0x24U))
        {
            init_failed_mask |= UINT32_C(1) << channel;
        }
    }
    DAL_Delay(1000U); /* 仅启动阶段等待复位、EEPROM载入。 */

    for (channel = 0U; channel < TACTILE_CHANNEL_COUNT; ++channel)
    {
        uint8_t readback = 0U;
        int ok = WriteRegister(channel, NSA_REG_INTERFACE, 0x81U);
        ok &= WriteRegister(channel, 0xA4U, 0x00U);
        /* 先关闭 DAC 连续转换，设置滤波后再启动，避免改配置打断启动。 */
        ok &= WriteRegister(channel, 0xA5U, 0x08U);
        ok &= WriteRegister(channel, 0xA6U, TACTILE_SENSOR_PCH_CONFIG);
        ok &= WriteRegister(channel, 0xA7U, TACTILE_SENSOR_TCH_CONFIG);
        ok &= WriteRegister(channel, 0xA5U, 0x88U);
        ok &= ReadRegister(channel, NSA_REG_INTERFACE, &readback);
        ok &= (readback & 0x81U) == 0x81U && (readback & 0x66U) == 0U;
        ok &= ReadRegister(channel, 0xA5U, &readback);
        ok &= readback == 0x88U;
        ok &= ReadRegister(channel, 0xA6U, &readback);
        ok &= readback == TACTILE_SENSOR_PCH_CONFIG;
        ok &= ReadRegister(channel, 0xA7U, &readback);
        ok &= readback == TACTILE_SENSOR_TCH_CONFIG;
        if (!ok)
        {
            init_failed_mask |= UINT32_C(1) << channel;
        }
    }
    /* 不再每次上电写0xAA等标定系数，也不触发0x6A/0x6C EEPROM烧写。 */
}

void TactileSensor_Collect(TactileSample *sample)
{
    uint8_t channel;
    sample->sample_time_us = TactileTime_NowUs();
    sample->fresh_mask = 0U;
    sample->status = init_failed_mask != 0U ? TACTILE_STATUS_INIT_ERROR : 0U;

    for (channel = 0U; channel < TACTILE_CHANNEL_COUNT; ++channel)
    {
        uint8_t ready = 0U;
        uint32_t mask = UINT32_C(1) << channel;
        if ((uint32_t)(TactileTime_NowUs() - sample->sample_time_us) >=
            TACTILE_SWEEP_BUDGET_US)
        {
            sample->status |= TACTILE_STATUS_SWEEP_LATE;
            break;
        }
        if ((init_failed_mask & mask) != 0U)
        {
            continue;
        }
        if (!ReadRegister(channel, NSA_REG_DATA_READY, &ready))
        {
            sample->status |= TACTILE_STATUS_SPI_ERROR;
            continue;
        }
        if ((ready & NSA_SENSOR_ERRORS) != 0U)
        {
            sample->status |= TACTILE_STATUS_SENSOR_ERROR;
            continue;
        }
        /* DRDY=0 也读取寄存器值，避免连续 DAC 模式下永远输出启动哨兵。
         * 没有 DRDY 证据的读取仍标为 fresh=0，绝不把重复读当新转换。 */
        if (!ReadMeasurement(channel, &last_temperature[channel],
                             &last_pressure[channel]))
        {
            sample->status |= TACTILE_STATUS_SPI_ERROR;
            continue;
        }
        if ((ready & NSA_DATA_READY) != 0U)
        {
            sample->fresh_mask |= mask;
        }
    }
    if (sample->fresh_mask != TACTILE_CHANNEL_MASK)
    {
        sample->status |= TACTILE_STATUS_NOT_ALL_FRESH;
    }
    memcpy(sample->temperature, last_temperature, sizeof(last_temperature));
    memcpy(sample->pressure, last_pressure, sizeof(last_pressure));
}
