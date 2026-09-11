#ifndef TACTILE_TIME_H
#define TACTILE_TIME_H

#include "apm32f4xx_dal.h"

void TactileTime_Init(void);
void TactileTime_OnSysTick(void);
uint32_t TactileTime_NowUs(void);
void TactileTimer_Start(void);
uint32_t TactileTimer_ElapsedPeriods(uint32_t *lateness_us);

static inline uint32_t TactileCritical_Enter(void)
{
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    __DMB();
    return primask;
}

static inline void TactileCritical_Exit(uint32_t primask)
{
    __DMB();
    __set_PRIMASK(primask);
}

#endif
