/**
 * @file        apm32f4xx_nvic_cfg.c
 *
 * @brief       This file provides configuration support for NVIC
 *
 * @version     V1.0.0
 *
 * @date        2024-12-01
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
#include "apm32f4xx_nvic_cfg.h"

/* Private includes *******************************************************/

/* Private macro **********************************************************/

/* Private typedef ********************************************************/

/* Private variables ******************************************************/

/* Private function prototypes ********************************************/

/* External variables *****************************************************/

/* External functions *****************************************************/

/**
 * @brief   NVIC configuration
 *
 * @param   None
 *
 * @retval  None
 */
void DAL_NVIC_Config(void)
{
    __DAL_RCM_AFIO_CLK_ENABLE();
    __DAL_RCM_PMU_CLK_ENABLE();

    /* Set interrupt group priority */
    DAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4);
}
