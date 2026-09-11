/**
 * @file        apm32f4xx_device_cfg.c
 *
 * @brief       This file provides all configuration support for device
 *
 * @version     V1.0.0
 *
 * @date        2024-08-01
 *
 * @attention
 *
 *  Copyright (C) 2024-2025 Geehy Semiconductor
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

/* Includes ***************************************************************/
#include "apm32f4xx_device_cfg.h"
#include "tactile_sensor.h"

/* Private includes *******************************************************/

/* Private macro **********************************************************/

/* Private typedef ********************************************************/

/* Private variables ******************************************************/

/* Private function prototypes ********************************************/

/* External variables *****************************************************/

/* External functions *****************************************************/

/**
 * @brief   Device configuration
 *
 * @param   None
 *
 * @retval  None
 */
void DAL_DeviceConfig(void)
{
    /* Configure DAL library */
    DAL_Init();

    /* Configure NVIC */
    DAL_NVIC_Config();

    /* Configure system clock */
    DAL_SysClkConfig();

    /* Configure peripheral clock */
    DAL_RCM_PeripheralClkConfig();
    __DAL_AFIO_REMAP_SWJ_NOJTAG();
    /* Configure GPIO */
    DAL_GPIO_Config();

    /* Configure peripheral */
    DAL_USART2_Config();
    TactileChannels_Init();
    /* Configure SPI */
    DAL_SPI1_Config();
    DAL_SPI2_Config();
}

/**
 * @brief   Device reset
 *
 * @param   None
 *
 * @retval  None
 */
void DAL_DeviceReset(void)
{
    /* Reset DAL library */
    DAL_DeInit();

    /* Reset Peripheral */

    /* Reset service */
}

/**
 * @brief   System clock configuration
 *
 * @param   None
 *
 * @retval  None
 */
void DAL_SysClkConfig(void)
{
    RCM_ClkInitTypeDef RCM_ClkInitStruct = {0U};
    RCM_OscInitTypeDef RCM_OscInitStruct = {0U};

     /* Configure oscillator and PLL */
    RCM_OscInitStruct.OscillatorType    = RCM_OSCILLATORTYPE_HSE;
    RCM_OscInitStruct.HSEState          = RCM_HSE_ON;
    /* HSE 16 MHz / 2 * 15 = 120 MHz, within APM32F402 limits. */
    RCM_OscInitStruct.HSEPredivValue    = RCM_HSE_PREDIV_DIV2;
    RCM_OscInitStruct.PLL.PLLState      = RCM_PLL_ON;
    RCM_OscInitStruct.PLL.PLLSource     = RCM_PLLSOURCE_HSE;
    RCM_OscInitStruct.PLL.PLLMUL        = RCM_PLL_MUL15;
    if (DAL_RCM_OscConfig(&RCM_OscInitStruct) != DAL_OK)
    {
        Error_Handler();
    }

    /* Configure clock */
    RCM_ClkInitStruct.ClockType         = (RCM_CLOCKTYPE_SYSCLK | RCM_CLOCKTYPE_HCLK | RCM_CLOCKTYPE_PCLK1 | RCM_CLOCKTYPE_PCLK2);
    RCM_ClkInitStruct.SYSCLKSource      = RCM_SYSCLKSOURCE_PLLCLK;
    RCM_ClkInitStruct.AHBCLKDivider     = RCM_SYSCLK_DIV1;
    RCM_ClkInitStruct.APB1CLKDivider    = RCM_HCLK_DIV2; /* APB1 max 60 MHz */
    RCM_ClkInitStruct.APB2CLKDivider    = RCM_HCLK_DIV1;
    if (DAL_RCM_ClockConfig(&RCM_ClkInitStruct, FLASH_LATENCY_3) != DAL_OK)
    {
        Error_Handler();
    }
}

/**
 * @brief     Error handler
 *
 * @param     None
 *
 * @retval    None
 */
void Error_Handler(void)
{
    /* When the function is needed, this function
       could be implemented in the user file
    */
   __disable_irq();
    while (1)
    {
    }
}

#if defined(USE_FULL_ASSERT)
/**
 * @brief   Assert failed handler
 *
 * @param   file :Pointer to the source file name
 *
 * @param   line :Error line source number
 *
 * @retval  None
 */
void AssertFailedHandler(uint8_t *file, uint32_t line)
{
    /* When the function is needed, this function
       could be implemented in the user file
    */
    UNUSED(file);
    UNUSED(line);
    while(1)
    {
    }
}
#endif /* USE_FULL_ASSERT */
