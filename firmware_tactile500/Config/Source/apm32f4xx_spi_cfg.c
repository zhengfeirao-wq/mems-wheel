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
/* 双SPI总线：软件片选由tactile_channels.c统一管理。 */
#include "apm32f4xx_spi_cfg.h"
#include "apm32f4xx_device_cfg.h"
#include "tactile_config.h"

SPI_HandleTypeDef hspi1;
SPI_HandleTypeDef hspi2;

static void ConfigureSpi(SPI_HandleTypeDef *spi, SPI_TypeDef *instance)
{
    spi->Instance = instance;
    spi->Init.Mode = SPI_MODE_MASTER;
    spi->Init.Direction = SPI_DIRECTION_2LINES;
    spi->Init.DataSize = SPI_DATASIZE_8BIT;
    spi->Init.CLKPolarity = SPI_POLARITY_LOW;
    spi->Init.CLKPhase = SPI_PHASE_1EDGE;
    spi->Init.NSS = SPI_NSS_SOFT;
    spi->Init.BaudRatePrescaler = instance == SPI1 ? TACTILE_SPI1_PRESCALER
                                                  : TACTILE_SPI2_PRESCALER;
    spi->Init.FirstBit = SPI_FIRSTBIT_MSB;
    spi->Init.TIMode = SPI_TIMODE_DISABLE;
    spi->Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
    spi->Init.CRCPolynomial = 7U;
    if (DAL_SPI_Init(spi) != DAL_OK)
    {
        Error_Handler();
    }
    __DAL_SPI_ENABLE(spi);
}

void DAL_SPI1_Config(void)
{
    ConfigureSpi(&hspi1, SPI1);
}

void DAL_SPI2_Config(void)
{
    ConfigureSpi(&hspi2, SPI2);
}

void DAL_SPI_MspInit(SPI_HandleTypeDef *spi)
{
    GPIO_InitTypeDef gpio = {0};
    GPIO_TypeDef *port;
    uint16_t miso;
    if (spi->Instance == SPI1)
    {
        __DAL_RCM_GPIOA_CLK_ENABLE();
        __DAL_RCM_SPI1_CLK_ENABLE();
        __DAL_AFIO_REMAP_SPI1_DISABLE();
        port = GPIOA;
        gpio.Pin = GPIO_PIN_5 | GPIO_PIN_7;
        miso = GPIO_PIN_6;
    }
    else if (spi->Instance == SPI2)
    {
        __DAL_RCM_GPIOB_CLK_ENABLE();
        __DAL_RCM_SPI2_CLK_ENABLE();
        port = GPIOB;
        gpio.Pin = GPIO_PIN_13 | GPIO_PIN_15;
        miso = GPIO_PIN_14;
    }
    else
    {
        return;
    }
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    DAL_GPIO_Init(port, &gpio);
    gpio.Pin = miso;
    gpio.Mode = GPIO_MODE_INPUT;
    DAL_GPIO_Init(port, &gpio);
}

void DAL_SPI_MspDeInit(SPI_HandleTypeDef *spi)
{
    if (spi->Instance == SPI1)
    {
        __DAL_RCM_SPI1_FORCE_RESET();
        __DAL_RCM_SPI1_RELEASE_RESET();
        DAL_GPIO_DeInit(GPIOA, GPIO_PIN_5 | GPIO_PIN_6 | GPIO_PIN_7);
    }
    else if (spi->Instance == SPI2)
    {
        __DAL_RCM_SPI2_FORCE_RESET();
        __DAL_RCM_SPI2_RELEASE_RESET();
        DAL_GPIO_DeInit(GPIOB, GPIO_PIN_13 | GPIO_PIN_14 | GPIO_PIN_15);
    }
}
