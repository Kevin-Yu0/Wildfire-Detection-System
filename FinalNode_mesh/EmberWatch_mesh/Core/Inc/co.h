/*
 * co.h
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#ifndef INC_CO_H_
#define INC_CO_H_

#include "stm32l4xx_hal.h"

extern I2C_HandleTypeDef hi2c2;

#define CO_I2C_ADDR    (0x74 << 1)  // 0xE8

uint8_t CO_Init(void);
uint8_t CO_Read(float *co_ppm);

#endif /* INC_CO_H_ */
