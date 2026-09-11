#include "tactile_time.h"
#include "tactile_config.h"
#include "apm32f4xx_device_cfg.h"

static volatile uint32_t reference_cycles;
static volatile uint32_t reference_us;
static uint32_t cycles_per_us;
static uint32_t next_deadline_us;

void TactileTime_Init(void)
{
    SystemCoreClockUpdate();
    if (SystemCoreClock < 1000000U || SystemCoreClock % 1000000U != 0U)
    {
        Error_Handler();
    }
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0U;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    reference_cycles = 0U;
    reference_us = 0U;
    cycles_per_us = SystemCoreClock / 1000000U;
}

void TactileTime_OnSysTick(void)
{
    uint32_t delta_us;
    uint32_t primask;
    if (cycles_per_us == 0U)
    {
        return; /* 时钟初始化前仍使用 DAL 的普通毫秒时基。 */
    }
    delta_us = (uint32_t)(DWT->CYCCNT - reference_cycles) / cycles_per_us;
    primask = TactileCritical_Enter();
    reference_cycles += delta_us * cycles_per_us;
    reference_us += delta_us;
    TactileCritical_Exit(primask);
}

uint32_t TactileTime_NowUs(void)
{
    uint32_t primask;
    uint32_t base_us;
    uint32_t cycles;
    uint32_t now_cycles;

    primask = TactileCritical_Enter();
    base_us = reference_us;
    cycles = reference_cycles;
    now_cycles = DWT->CYCCNT;
    TactileCritical_Exit(primask);
    return base_us + (uint32_t)(now_cycles - cycles) / cycles_per_us;
}

void TactileTimer_Start(void)
{
    uint32_t timer_clock = DAL_RCM_GetPCLK1Freq();
    uint32_t primask;
    if ((RCM->CFG & RCM_CFG_APB1PSC) != RCM_CFG_APB1PSC_DIV1)
    {
        timer_clock *= 2U;
    }
    if (timer_clock % 1000000U != 0U)
    {
        Error_Handler();
    }

    __DAL_RCM_TMR2_CLK_ENABLE();
    __DAL_RCM_TMR2_FORCE_RESET();
    __DAL_RCM_TMR2_RELEASE_RESET();
    TMR2->CTRL1 = TMR_CTRL1_ARPEN;
    TMR2->PSC = timer_clock / 1000000U - 1U; /* 1 MHz，即每计数1 us。 */
    TMR2->AUTORLD = TACTILE_PERIOD_US - 1U;
    TMR2->CNT = 0U;
    TMR2->CEG = TMR_CEG_UEG;
    TMR2->STS = 0U; /* 清除装载预分频值时产生的更新标志。 */
    TMR2->DIEN = TMR_DIEN_UIEN;

    /* DMA/USART 完成与定时器使用同一抢占优先级，状态操作不会相互抢占。 */
    DAL_NVIC_SetPriority(TMR2_IRQn, 1U, 0U);
    DAL_NVIC_ClearPendingIRQ(TMR2_IRQn);
    DAL_NVIC_EnableIRQ(TMR2_IRQn);
    primask = TactileCritical_Enter();
    next_deadline_us = TactileTime_NowUs() + TACTILE_PERIOD_US;
    TMR2->CTRL1 |= TMR_CTRL1_CNTEN;
    TactileCritical_Exit(primask);
}

uint32_t TactileTimer_ElapsedPeriods(uint32_t *lateness_us)
{
    uint32_t now_us = TactileTime_NowUs();
    int32_t delta = (int32_t)(now_us - next_deadline_us);
    uint32_t periods = 1U;
    uint32_t late = 0U;
    if (delta > 0)
    {
        late = (uint32_t)delta;
        periods += late / TACTILE_PERIOD_US;
        late %= TACTILE_PERIOD_US;
    }
    next_deadline_us += periods * TACTILE_PERIOD_US;
    *lateness_us = late;
    return periods;
}
