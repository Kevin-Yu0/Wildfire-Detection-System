/*
 * co.c
 *
 *  Created on: May 19, 2026
 *      Author: kevin
 */

#include "co.h"

uint8_t CO_Init(void)
{
    // verify sensor is reachable
    if (HAL_I2C_IsDeviceReady(&hi2c2, CO_I2C_ADDR, 3, 100) != HAL_OK) return 0;
    return 1;
}

uint8_t CO_Read(float *co_ppm)
{
    uint8_t buf[2];
    if (HAL_I2C_Master_Receive(&hi2c2, CO_I2C_ADDR, buf, 2, 100) != HAL_OK) return 0;
    *co_ppm = (float)((buf[0] << 8) | buf[1]);
    return 1;
}
