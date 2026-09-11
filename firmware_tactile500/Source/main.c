/* *  Copyright (C) 2024-2025 Geehy Semiconductor
 *
 *  You may not use this file except in compliance with the
 *  GEEHY COPYRIGHT NOTICE (GEEHY SOFTWARE PACKAGE LICENSE).
 *
 *  The program is only for reference, which is distributed in the hope
 *  that it will be useful and instructional for customers to develop
 *  their software. Unless required by applicable law or agreed to in
 *  writing, the program is distributed on an "AS IS" BASIS, WITHOUT
 *  ANY WARRANTY OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the GEEHY SOFTWARE PACKAGE LICENSE for the governing permissions
 *  and limitations under the License.
 */
/**
 * @file main.c
 * @brief Tactile500: APM32F402, dual SPI, 500 Hz UART DMA streaming.
 *
 * Based on the supplied Geehy example; vendor license terms above apply.
 */
#include "main.h"
#include "apm32f4xx_device_cfg.h"
#include "apm32f4xx_usart_cfg.h"
#include "tactile_config.h"
#include "tactile_protocol.h"
#include "tactile_sensor.h"
#include "tactile_stream.h"
#include "tactile_time.h"

/* 可在调试器中查看累计帧数、漏发槽位、超时和DMA错误。 */
TactileStream g_tactile_stream;
static TactileSample sample;

static void RecoverUartIfNeeded(void)
{
    uint32_t primask;
    DAL_StatusTypeDef status;

    primask = TactileCritical_Enter();
    if (g_tactile_stream.recover_requested == 0U)
    {
        TactileCritical_Exit(primask);
        return;
    }
    g_tactile_stream.recovering = 1U;
    TactileCritical_Exit(primask);

    /* 恢复在主循环执行。SysTick和500Hz定时器继续运行，不在ISR里等待。 */
    status = DAL_UART_AbortTransmit(&huart2);
    primask = TactileCritical_Enter();
    if (status == DAL_OK)
    {
        TactileStream_RecoveryComplete(&g_tactile_stream);
    }
    else
    {
        TactileStream_TxError(&g_tactile_stream);
        g_tactile_stream.recovering = 0U;
    }
    TactileCritical_Exit(primask);
}

static void BuildNextFrame(void)
{
    uint32_t sequence;
    uint32_t primask;
    uint8_t status;
    size_t length;
    int slot;

    primask = TactileCritical_Enter();
    slot = TactileStream_Claim(&g_tactile_stream, &sequence);
    TactileCritical_Exit(primask);
    if (slot < 0)
    {
        return;
    }

    TactileSensor_Collect(&sample);
    primask = TactileCritical_Enter();
    if ((sample.status & TACTILE_STATUS_SWEEP_LATE) != 0U)
    {
        g_tactile_stream.latched_status |= TACTILE_STATUS_SWEEP_LATE;
        ++g_tactile_stream.sweep_overruns;
    }
    status = (uint8_t)(sample.status | g_tactile_stream.latched_status);
    TactileCritical_Exit(primask);

    length = TactileProtocol_Encode(
        g_tactile_stream.frame[slot], TACTILE_FRAME_MAX_BYTES,
        TACTILE_WIRE_VERSION, TACTILE_IDENTITY, status, sequence,
        sample.sample_time_us, sample.fresh_mask, sample.temperature,
        sample.pressure, TACTILE_CHANNEL_COUNT);

    primask = TactileCritical_Enter();
    (void)TactileStream_Publish(&g_tactile_stream, slot, length);
    TactileCritical_Exit(primask);
}

/* 仅从TMR2中断调用。这里只启动已备好的帧，不做SPI采集或CRC运算。 */
void TactileApp_OnTimer(void)
{
    uint32_t lateness_us;
    uint32_t periods;
    DAL_StatusTypeDef status;
    int slot;

    periods = TactileTimer_ElapsedPeriods(&lateness_us);
    slot = TactileStream_OnTick(&g_tactile_stream, periods,
                               lateness_us <= TACTILE_TX_MAX_LATENESS_US);
    if (slot < 0)
    {
        return;
    }
    status = DAL_UART_Transmit_DMA(&huart2,
                                   g_tactile_stream.frame[slot],
                                   (uint16_t)g_tactile_stream.length[slot]);
    if (status != DAL_OK ||
        (hdma_usart2_tx.Instance->CHCFG & DMA_CHCFG_CHEN) == 0U)
    {
        TactileStream_TxStartFailed(&g_tactile_stream);
        return;
    }
    TactileStream_TxStarted(&g_tactile_stream);
    __DAL_DMA_DISABLE_IT(&hdma_usart2_tx, DMA_IT_HT);
}

void DAL_UART_TxCpltCallback(UART_HandleTypeDef *uart)
{
    if (uart->Instance == USART2)
    {
        /* APM32F402 的普通 DMA 计数归零后 CHEN 仍置位。
         * 本版 DAL_DMA_Start_IT 未先关通道，不能在 CHEN=1 时重装计数。
         * UART TC 已确认末尾停止位发送完毕，此处关通道后才释放缓冲区。 */
        __DAL_DMA_DISABLE(&hdma_usart2_tx);
        TactileStream_TxComplete(&g_tactile_stream);
    }
}

void DAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
    if (uart->Instance == USART2)
    {
        TactileStream_TxError(&g_tactile_stream);
    }
}

int main(void)
{
    DAL_DeviceConfig();
    TactileTime_Init();
    TactileSensor_Init();
    TactileStream_Init(&g_tactile_stream);

    /* 连续上报模式：沿用原板PA0/PA1的485发送电平，不接收旧校准命令。 */
    DAL_GPIO_WritePin(GPIOA, GPIO_PIN_0 | GPIO_PIN_1, GPIO_PIN_SET);
    TactileTimer_Start();
    for (;;)
    {
        RecoverUartIfNeeded();
        BuildNextFrame();
    }
}
