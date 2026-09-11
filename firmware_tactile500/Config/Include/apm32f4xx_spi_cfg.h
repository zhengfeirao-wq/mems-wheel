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
#ifndef APM32F4XX_SPI_CFG_H
#define APM32F4XX_SPI_CFG_H
#include "apm32f4xx_dal.h"
extern SPI_HandleTypeDef hspi1;
extern SPI_HandleTypeDef hspi2;
void DAL_SPI1_Config(void);
void DAL_SPI2_Config(void);
#endif
