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
/* Tactile500: USART2 TX on PA2, DMA1 Channel7, 921600 8N1. */
#include "apm32f4xx_usart_cfg.h"
#include "apm32f4xx_device_cfg.h"
#include "tactile_config.h"

UART_HandleTypeDef huart2;
DMA_HandleTypeDef hdma_usart2_tx;

void DAL_USART2_Config(void)
{
    huart2.Instance = USART2;
    huart2.Init.BaudRate = TACTILE_UART_BAUDRATE;
    huart2.Init.WordLength = UART_WORDLENGTH_8B;
    huart2.Init.StopBits = UART_STOPBITS_1;
    huart2.Init.Parity = UART_PARITY_NONE;
    huart2.Init.Mode = UART_MODE_TX;
    huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart2.Init.OverSampling = UART_OVERSAMPLING_16;
    if (DAL_UART_Init(&huart2) != DAL_OK)
    {
        Error_Handler();
    }
}

void DAL_UART_MspInit(UART_HandleTypeDef *uart)
{
    GPIO_InitTypeDef gpio = {0};
    if (uart->Instance != USART2)
    {
        return;
    }
    __DAL_RCM_GPIOA_CLK_ENABLE();
    __DAL_RCM_USART2_CLK_ENABLE();
    __DAL_RCM_DMA1_CLK_ENABLE();
    gpio.Pin = GPIO_PIN_2;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    DAL_GPIO_Init(GPIOA, &gpio);

    hdma_usart2_tx.Instance = DMA1_Channel7;
    hdma_usart2_tx.Init.Direction = DMA_MEMORY_TO_PERIPH;
    hdma_usart2_tx.Init.PeriphInc = DMA_PINC_DISABLE;
    hdma_usart2_tx.Init.MemInc = DMA_MINC_ENABLE;
    hdma_usart2_tx.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;
    hdma_usart2_tx.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
    hdma_usart2_tx.Init.Mode = DMA_NORMAL;
    hdma_usart2_tx.Init.Priority = DMA_PRIORITY_HIGH;
    if (DAL_DMA_Init(&hdma_usart2_tx) != DAL_OK)
    {
        Error_Handler();
    }
    __DAL_LINKDMA(uart, hdmatx, hdma_usart2_tx);

    DAL_NVIC_SetPriority(DMA1_Channel7_IRQn, 1U, 0U);
    DAL_NVIC_EnableIRQ(DMA1_Channel7_IRQn);
    DAL_NVIC_SetPriority(USART2_IRQn, 1U, 0U);
    DAL_NVIC_EnableIRQ(USART2_IRQn);
}

void DAL_UART_MspDeInit(UART_HandleTypeDef *uart)
{
    if (uart->Instance != USART2)
    {
        return;
    }
    DAL_NVIC_DisableIRQ(DMA1_Channel7_IRQn);
    DAL_NVIC_DisableIRQ(USART2_IRQn);
    (void)DAL_DMA_DeInit(uart->hdmatx);
    __DAL_RCM_USART2_FORCE_RESET();
    __DAL_RCM_USART2_RELEASE_RESET();
    DAL_GPIO_DeInit(GPIOA, GPIO_PIN_2);
}
