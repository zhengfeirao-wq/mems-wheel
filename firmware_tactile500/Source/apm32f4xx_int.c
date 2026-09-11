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
#include "apm32f4xx_int.h"
#include "apm32f4xx_usart_cfg.h"
#include "main.h"
#include "tactile_time.h"

void NMI_Handler(void) {}
void HardFault_Handler(void) { for (;;) {} }
void MemManage_Handler(void) { for (;;) {} }
void BusFault_Handler(void) { for (;;) {} }
void UsageFault_Handler(void) { for (;;) {} }
void SVC_Handler(void) {}
void DebugMon_Handler(void) {}
void PendSV_Handler(void) {}

void SysTick_Handler(void)
{
    DAL_IncTick();
    TactileTime_OnSysTick();
}

void DMA1_Channel7_IRQHandler(void)
{
    DAL_DMA_IRQHandler(&hdma_usart2_tx);
}

void USART2_IRQHandler(void)
{
    DAL_UART_IRQHandler(&huart2);
}

void TMR2_IRQHandler(void)
{
    if ((TMR2->STS & TMR_STS_UIFLG) != 0U)
    {
        TMR2->STS = ~TMR_STS_UIFLG;
        TactileApp_OnTimer();
    }
}
