#include "tactile_sensor.h"
#include "tactile_protocol.h"
#include "tactile_time.h"
#include "apm32f4xx_spi_cfg.h"
#include <string.h>

#define NSA_REG_INTERFACE    0x00U
#define NSA_REG_DATA_READY   0x02U
#define NSA_REG_TEMP_LSB     0x0AU
#define NSA_DATA_READY       0x01U
#define NSA_SENSOR_ERRORS    0xFCU

static int16_t last_temperature[TACTILE_CHANNEL_COUNT];
static int32_t last_pressure[TACTILE_CHANNEL_COUNT];
static uint32_t init_failed_mask;

/* 流水线状态。trigger_time_us 记录每通道上次触发时刻，用于测量转换耗时。 */
static uint32_t trigger_time_us[TACTILE_CHANNEL_COUNT];
static uint8_t miss_count[TACTILE_CHANNEL_COUNT];
static uint32_t frame_counter;

/* 调试器可观察的诊断量。 */
volatile TactileDiag g_tactile_diag;

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
    /* 0xE0: 连续读取（W1:W0=11）；MSB-first 模式从 0x0A 向 0x06 递减地址。
     * 取 0x0A/0x09 为温度、0x08/0x07/0x06 为压力。 */
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

/* 触发一次转换并记录时刻。不等待：转换在帧间隔里自己跑完。 */
static int TriggerConversion(uint8_t channel, uint8_t command)
{
    if (channel >= TACTILE_CHANNEL_COUNT)
    {
        return 0;
    }
    if (!WriteRegister(channel, TACTILE_SENSOR_CMD_REG, command))
    {
        return 0;
    }
    trigger_time_us[channel] = TactileTime_NowUs();
    return 1;
}

/* 上电首轮：触发全部通道并轮询到就绪。
 * 这一次轮询是唯一能测得"真实转换时间"的机会（之后 DRDY 读取都晚于转换结束）。 */
static void PrimeFirstConversion(void)
{
    uint8_t channel;
    uint8_t done[TACTILE_CHANNEL_COUNT];
    uint32_t started;
    uint32_t remaining = 0U;

    for (channel = 0U; channel < TACTILE_CHANNEL_COUNT; ++channel)
    {
        done[channel] = 1U;
        if ((init_failed_mask & (UINT32_C(1) << channel)) != 0U)
        {
            continue;
        }
        done[channel] = 0U;
        ++remaining;
        (void)TriggerConversion(channel, TACTILE_SENSOR_CMD_SENSOR);
    }

    started = TactileTime_NowUs();
    while (remaining != 0U &&
           (uint32_t)(TactileTime_NowUs() - started) <
               TACTILE_SENSOR_PRIME_TIMEOUT_US)
    {
        for (channel = 0U; channel < TACTILE_CHANNEL_COUNT; ++channel)
        {
            uint8_t ready = 0U;
            uint32_t elapsed;
            if (done[channel] != 0U)
            {
                continue;
            }
            if (!ReadRegister(channel, NSA_REG_DATA_READY, &ready))
            {
                continue;
            }
            if ((ready & NSA_DATA_READY) == 0U)
            {
                continue;
            }
            done[channel] = 1U;
            --remaining;
            elapsed = (uint32_t)(TactileTime_NowUs() - trigger_time_us[channel]);
            if (g_tactile_diag.prime_conversion_us == 0U)
            {
                g_tactile_diag.prime_conversion_us = elapsed;
            }
        }
    }
    g_tactile_diag.prime_timeout = (remaining != 0U) ? 1U : 0U;
}

void TactileSensor_Init(void)
{
    uint8_t channel;

    init_failed_mask = 0U;
    frame_counter = 0U;
    g_tactile_diag.prime_conversion_us = 0U;
    g_tactile_diag.prime_timeout = 0U;
    g_tactile_diag.total_frames = 0U;
    g_tactile_diag.full_fresh_frames = 0U;
    g_tactile_diag.drdy_misses = 0U;
    g_tactile_diag.retriggers = 0U;

    for (channel = 0U; channel < TACTILE_CHANNEL_COUNT; ++channel)
    {
        last_temperature[channel] = TACTILE_INVALID_TEMP;
        last_pressure[channel] = TACTILE_INVALID_PRESSURE;
        trigger_time_us[channel] = 0U;
        miss_count[channel] = 0U;
        if (!WriteRegister(channel, NSA_REG_INTERFACE, 0x24U))
        {
            init_failed_mask |= UINT32_C(1) << channel;
        }
    }
    DAL_Delay(1000U); /* 仅启动阶段等待复位、EEPROM载入。 */

    for (channel = 0U; channel < TACTILE_CHANNEL_COUNT; ++channel)
    {
        uint8_t iface_rb = 0U;
        uint8_t a5_rb = 0U;
        uint8_t a6_rb = 0U;
        uint8_t a7_rb = 0U;
        int ok = WriteRegister(channel, NSA_REG_INTERFACE, 0x81U);
        ok &= WriteRegister(channel, 0xA4U, 0x00U);
        /* 先关闭 DAC 连续转换，设置滤波后再启动，避免改配置打断启动。 */
        ok &= WriteRegister(channel, 0xA5U, TACTILE_SENSOR_SYS_CONFIG);
        ok &= WriteRegister(channel, 0xA6U, TACTILE_SENSOR_PCH_CONFIG);
        ok &= WriteRegister(channel, 0xA7U, TACTILE_SENSOR_TCH_CONFIG);

        /* 关键修正：这里原本再写一次 0xA5 = 0x88，把 bit7 DAC_on 置 1，
         * 使芯片进入 datasheet 6.3 节的 analog output mode。该模式自主转换、
         * 忽略 CMD 寄存器，且不驱动 INT/DRDY，导致 fresh_mask 恒为 0。
         * 现在保持 TACTILE_SENSOR_SYS_CONFIG = 0x08（DAC_on = 0），
         * 改用 0x30 COMMAND 寄存器触发单次转换。 */

        /* 逐项回读并留存，失败时可在调试器直接比对期望值。 */
        ok &= ReadRegister(channel, NSA_REG_INTERFACE, &iface_rb);
        ok &= ReadRegister(channel, 0xA5U, &a5_rb);
        ok &= ReadRegister(channel, 0xA6U, &a6_rb);
        ok &= ReadRegister(channel, 0xA7U, &a7_rb);
        g_tactile_diag.init_iface_rb[channel] = iface_rb;
        g_tactile_diag.init_a5_rb[channel] = a5_rb;
        g_tactile_diag.init_a6_rb[channel] = a6_rb;
        g_tactile_diag.init_a7_rb[channel] = a7_rb;

        ok &= (iface_rb & 0x81U) == 0x81U && (iface_rb & 0x66U) == 0U;
        ok &= a5_rb == TACTILE_SENSOR_SYS_CONFIG;
        ok &= a6_rb == TACTILE_SENSOR_PCH_CONFIG;
        ok &= a7_rb == TACTILE_SENSOR_TCH_CONFIG;
        if (!ok)
        {
            init_failed_mask |= UINT32_C(1) << channel;
        }
    }
    g_tactile_diag.init_fail_mask = init_failed_mask;
    /* 不再每次上电写0xAA等标定系数，也不触发0x6A/0x6C EEPROM烧写。 */

    /* 启动流水线：先触发一轮并等到就绪，随后每帧"读上一轮、触发下一轮"。 */
    PrimeFirstConversion();
}

void TactileSensor_Collect(TactileSample *sample)
{
    uint8_t channel;
    uint8_t command;

    sample->sample_time_us = TactileTime_NowUs();
    sample->fresh_mask = 0U;
    sample->status = init_failed_mask != 0U ? TACTILE_STATUS_INIT_ERROR : 0U;

    /* 单次传感器转换不更新温度寄存器，周期性改用组合转换刷新温度。 */
    command = ((frame_counter % TACTILE_SENSOR_TEMP_EVERY) == 0U)
                  ? TACTILE_SENSOR_CMD_COMBINED
                  : TACTILE_SENSOR_CMD_SENSOR;
    ++frame_counter;

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
        /* DRDY 必须在读数据之前取：读 Data_out 会自动清 DRDY。 */
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

        if ((ready & NSA_DATA_READY) != 0U)
        {
            /* 转换已完成且数据未被读过：这是货真价实的新数据。 */
            if (!ReadMeasurement(channel, &last_temperature[channel],
                                 &last_pressure[channel]))
            {
                sample->status |= TACTILE_STATUS_SPI_ERROR;
                continue;
            }
            sample->fresh_mask |= mask;
            miss_count[channel] = 0U;
            /* 读完立刻触发下一轮，转换在帧间隔里跑，不占用扫描预算。 */
            (void)TriggerConversion(channel, command);
        }
        else
        {
            /* 转换未完成。按 datasheet 6.5.1 的要求不读正在刷新的 Data_out，
             * 保留上次数值，等下一帧。 */
            ++g_tactile_diag.drdy_misses;
            ++miss_count[channel];
            if (miss_count[channel] >= TACTILE_SENSOR_MISS_LIMIT)
            {
                (void)TriggerConversion(channel, command);
                ++g_tactile_diag.retriggers;
                miss_count[channel] = 0U;
            }
        }
    }

    ++g_tactile_diag.total_frames;
    if (sample->fresh_mask == TACTILE_CHANNEL_MASK)
    {
        ++g_tactile_diag.full_fresh_frames;
    }
    if (sample->fresh_mask != TACTILE_CHANNEL_MASK)
    {
        sample->status |= TACTILE_STATUS_NOT_ALL_FRESH;
    }
    memcpy(sample->temperature, last_temperature, sizeof(last_temperature));
    memcpy(sample->pressure, last_pressure, sizeof(last_pressure));
}
